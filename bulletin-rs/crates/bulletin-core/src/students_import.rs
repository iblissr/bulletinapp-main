//! Import « intelligent » d'une liste d'élèves depuis un classeur Excel.
//!
//! Reprend les heuristiques de `app/widgets/import_helpers.py` :
//! - détection de la ligne d'en-têtes (les classeurs contiennent souvent
//!   des lignes d'établissement/classe/prof avant le tableau) ;
//! - reconnaissance des colonnes par leurs noms (français et anglais) ;
//! - découpage des noms complets « NOM Prénoms ».
//!
//! L'import fusionne tous les onglets exploitables et met à jour les
//! élèves existants par leur numéro (`ON CONFLICT(num)`).

use crate::db::Database;
use crate::models::Student;
use crate::workspace::normalize;
use anyhow::{Context, Result, anyhow};
use calamine::{Data, Reader, open_workbook_auto};
use std::collections::{HashMap, HashSet};
use std::path::Path;

/// Un élève extrait d'un classeur.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct StudentImportRow {
    pub num: i64,
    pub matricule: String,
    pub nom: String,
    pub prenoms: String,
    pub genre: String,
    pub naissance: String,
}

impl StudentImportRow {
    fn to_student(&self, id: i64) -> Student {
        Student {
            id,
            num: self.num,
            matricule: self.matricule.clone(),
            nom: self.nom.clone(),
            prenoms: self.prenoms.clone(),
            genre: self.genre.clone(),
            naissance: self.naissance.clone(),
        }
    }
}

/// Colonnes reconnues (index 0-based), `-1`/absent si introuvable.
#[derive(Debug, Clone, Default, serde::Serialize)]
pub struct ColumnMapping {
    pub num: Option<usize>,
    pub matricule: Option<usize>,
    pub nom: Option<usize>,
    pub prenoms: Option<usize>,
    pub nom_et_prenoms: Option<usize>,
    pub genre: Option<usize>,
    pub naissance: Option<usize>,
}

impl ColumnMapping {
    pub fn is_complete(&self) -> bool {
        self.num.is_some() && (self.nom.is_some() || self.nom_et_prenoms.is_some())
    }

    pub fn missing(&self) -> Vec<&'static str> {
        let mut out = Vec::new();
        if self.num.is_none() {
            out.push("num");
        }
        if self.nom.is_none() && self.nom_et_prenoms.is_none() {
            out.push("nom / nom et prénoms");
        }
        out
    }
}

/// Résultat d'analyse d'un onglet.
#[derive(Debug, Clone, serde::Serialize)]
pub struct ParsedSheet {
    pub sheet_name: String,
    /// Numéro de ligne (1-based) de la ligne d'en-têtes.
    pub header_row: usize,
    pub mapping: ColumnMapping,
    pub rows: Vec<StudentImportRow>,
    pub skipped: usize,
    pub warnings: Vec<String>,
}

/// Résultat d'analyse d'un classeur complet.
#[derive(Debug, Clone, serde::Serialize)]
pub struct ParsedWorkbook {
    pub sheets: Vec<ParsedSheet>,
    pub skipped_sheets: Vec<String>,
}

impl ParsedWorkbook {
    pub fn total_rows(&self) -> usize {
        self.sheets.iter().map(|sheet| sheet.rows.len()).sum()
    }
}

/// Résultat d'un import en base.
#[derive(Debug, Clone, serde::Serialize)]
pub struct StudentImportReport {
    pub added: usize,
    pub updated: usize,
    pub skipped: usize,
    pub sheets: usize,
    pub warnings: Vec<String>,
}

// ---------------------------------------------------------------------------
//  Alias de colonnes
// ---------------------------------------------------------------------------

const ALIAS_NUM: &[&str] = &[
    "num", "numero", "n", "no", "n°", "nº", "number", "ordre", "rang", "id", "#",
];
const ALIAS_MATRICULE: &[&str] = &[
    "matricule",
    "mat",
    "matriculen",
    "matriculeeleve",
    "studentid",
    "student no",
    "student number",
    "id",
    "code",
    "code eleve",
    "registration",
    "registration no",
    "registration number",
    "reg no",
];
const ALIAS_NOM: &[&str] = &[
    "nom",
    "nomdefamille",
    "nomfamille",
    "nom de famille",
    "lastname",
    "last name",
    "family name",
    "surname",
    "nom eleve",
];
const ALIAS_PRENOMS: &[&str] = &[
    "prenom",
    "prenoms",
    "prénom",
    "prénoms",
    "firstname",
    "first name",
    "given name",
    "givenname",
    "prenom eleve",
];
const ALIAS_FULL_NAME: &[&str] = &[
    "nometprenoms",
    "nom et prenoms",
    "nom prenoms",
    "nomprenoms",
    "fullname",
    "full name",
    "student name",
    "studentname",
    "name",
    "nom complet",
    "nomcomplet",
    "eleve",
    "élève",
    "learner",
];
const ALIAS_GENRE: &[&str] = &["genre", "sexe", "sex", "gender", "m/f", "mf", "m ou f"];
const ALIAS_NAISSANCE: &[&str] = &[
    "naissance",
    "datedenaissance",
    "date de naissance",
    "dob",
    "date of birth",
    "birth date",
    "birthdate",
    "date naissance",
];

const HEADER_KEYWORDS: &[&str] = &[
    "num",
    "nom",
    "prenom",
    "prenoms",
    "matricule",
    "genre",
    "naissance",
    "nometprenoms",
    "nomcomplet",
    "firstname",
    "lastname",
    "fullname",
    "name",
    "sex",
    "gender",
    "dob",
];

fn normalized_aliases(raw: &[&str]) -> HashSet<String> {
    raw.iter().map(|alias| normalize_header(alias)).collect()
}

/// Normalise un en-tête : minuscules, symboles `#`/`N°` convertis,
/// accents retirés, ponctuation remplacée par des espaces.
fn normalize_header(text: &str) -> String {
    let lowered = text.trim().to_lowercase();
    let replaced = lowered
        .replace('#', " numero ")
        .replace("n°", " numero ")
        .replace("nº", " numero ")
        .replace('°', " ")
        .replace('º', " ");
    normalize(&replaced)
}

// ---------------------------------------------------------------------------
//  Détection des en-têtes
// ---------------------------------------------------------------------------

fn looks_like_header_row(row: &[Data]) -> usize {
    let all_aliases = [
        ALIAS_NUM,
        ALIAS_MATRICULE,
        ALIAS_NOM,
        ALIAS_PRENOMS,
        ALIAS_FULL_NAME,
        ALIAS_GENRE,
        ALIAS_NAISSANCE,
    ]
    .iter()
    .flat_map(|aliases| normalized_aliases(aliases))
    .collect::<HashSet<_>>();

    row.iter()
        .filter(|cell| {
            let norm = normalize_header(&cell_text(cell));
            if norm.is_empty() {
                return false;
            }
            HEADER_KEYWORDS.contains(&norm.as_str()) || all_aliases.contains(&norm)
        })
        .count()
}

/// Retourne l'index 0-based de la ligne d'en-têtes (0 par défaut).
fn find_header_row(rows: &[Vec<Data>], max_scan: usize) -> usize {
    let mut best_row = 0;
    let mut best_score = 0;
    for (index, row) in rows.iter().take(max_scan).enumerate() {
        let score = looks_like_header_row(row);
        if score > best_score {
            best_score = score;
            best_row = index;
        }
    }
    best_row
}

fn detect_mapping(header: &[Data]) -> (ColumnMapping, Vec<String>) {
    let mut mapping = ColumnMapping::default();
    let mut extra = Vec::new();

    let num = normalized_aliases(ALIAS_NUM);
    let matricule = normalized_aliases(ALIAS_MATRICULE);
    let nom = normalized_aliases(ALIAS_NOM);
    let prenoms = normalized_aliases(ALIAS_PRENOMS);
    let full_name = normalized_aliases(ALIAS_FULL_NAME);
    let genre = normalized_aliases(ALIAS_GENRE);
    let naissance = normalized_aliases(ALIAS_NAISSANCE);

    for (index, cell) in header.iter().enumerate() {
        let raw = cell_text(cell);
        let norm = normalize_header(&raw);
        if norm.is_empty() {
            continue;
        }
        if full_name.contains(&norm) {
            mapping.nom_et_prenoms.get_or_insert(index);
            continue;
        }
        let mut matched = true;
        if mapping.num.is_none() && num.contains(&norm) {
            mapping.num = Some(index);
        } else if mapping.matricule.is_none() && matricule.contains(&norm) {
            mapping.matricule = Some(index);
        } else if mapping.nom.is_none() && nom.contains(&norm) {
            mapping.nom = Some(index);
        } else if mapping.prenoms.is_none() && prenoms.contains(&norm) {
            mapping.prenoms = Some(index);
        } else if mapping.genre.is_none() && genre.contains(&norm) {
            mapping.genre = Some(index);
        } else if mapping.naissance.is_none() && naissance.contains(&norm) {
            mapping.naissance = Some(index);
        } else {
            matched = false;
        }
        if !matched {
            extra.push(raw);
        }
    }

    (mapping, extra)
}

// ---------------------------------------------------------------------------
//  Valeurs de cellules
// ---------------------------------------------------------------------------

fn cell_text(cell: &Data) -> String {
    match cell {
        Data::Empty => String::new(),
        Data::String(value) => value.trim().to_string(),
        Data::Int(value) => value.to_string(),
        Data::Float(value) => {
            if value.fract() == 0.0 {
                format!("{value:.0}")
            } else {
                value.to_string()
            }
        }
        Data::Bool(value) => value.to_string(),
        Data::DateTime(value) => value.to_string(),
        Data::DateTimeIso(value) | Data::DurationIso(value) => value.clone(),
        Data::Error(error) => format!("{error:?}"),
    }
}

fn cell_int(cell: Option<&Data>) -> Option<i64> {
    let cell = cell?;
    match cell {
        Data::Empty => None,
        Data::Int(value) => Some(*value),
        Data::Float(value) => {
            if value.fract() == 0.0 {
                Some(*value as i64)
            } else {
                None
            }
        }
        Data::String(value) => {
            let digits: String = value
                .chars()
                .filter(|c| c.is_ascii_digit() || *c == '-')
                .collect();
            digits.parse().ok()
        }
        _ => None,
    }
}

// ---------------------------------------------------------------------------
//  Nettoyage
// ---------------------------------------------------------------------------

/// Sépare « ALFRED Kevin Haristophano » en (« ALFRED », « Kevin … »).
pub fn split_full_name(full: &str) -> (String, String) {
    let mut text = full.trim().to_string();
    let lowered = text.to_lowercase();
    for prefix in ["mlle", "mme.", "mrs", "ms", "mr", "m.", "mme"] {
        if lowered.starts_with(prefix)
            && lowered[prefix.len()..]
                .chars()
                .next()
                .is_none_or(|c| c.is_whitespace())
        {
            text = text[prefix.len()..].trim().to_string();
            break;
        }
    }
    let text = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if text.is_empty() {
        return (String::new(), String::new());
    }
    let mut parts = text.splitn(2, ' ');
    let nom = parts.next().unwrap_or_default().to_string();
    let prenoms = parts.next().unwrap_or_default().to_string();
    (nom, prenoms)
}

fn clean_gender(raw: &str) -> String {
    let norm = normalize(raw);
    match norm.as_str() {
        "m" | "h" | "homme" | "masculin" | "garcon" | "boy" | "male" => "M".to_string(),
        "f" | "femme" | "feminin" | "fille" | "girl" | "female" => "F".to_string(),
        _ => raw.trim().to_string(),
    }
}

fn cell_at<'a>(row: &'a [Data], index: Option<usize>) -> Option<&'a Data> {
    index.and_then(|index| row.get(index))
}

fn is_empty_row(row: &[Data]) -> bool {
    row.iter().all(|cell| match cell {
        Data::Empty => true,
        other => cell_text(other).is_empty(),
    })
}

// ---------------------------------------------------------------------------
//  Lecture
// ---------------------------------------------------------------------------

/// Lit un onglet et renvoie les élèves détectés.
pub fn parse_sheet(name: &str, rows: &[Vec<Data>]) -> Option<ParsedSheet> {
    if rows.is_empty() {
        return None;
    }
    let header_index = find_header_row(rows, 10);
    let header = rows.get(header_index)?;
    let (mapping, _extra) = detect_mapping(header);
    if !mapping.is_complete() {
        return None;
    }

    let mut parsed = Vec::new();
    let mut skipped = 0;
    let mut warnings = Vec::new();
    let mut seen_num = HashSet::new();

    for row in rows.iter().skip(header_index + 1) {
        if is_empty_row(row) {
            continue;
        }
        let Some(num) = cell_int(cell_at(row, mapping.num)) else {
            skipped += 1;
            continue;
        };
        if !seen_num.insert(num) {
            warnings.push(format!("Num {num} présent plusieurs fois — ignoré."));
            skipped += 1;
            continue;
        }
        let (nom, prenoms) = if let Some(index) = mapping.nom_et_prenoms {
            split_full_name(&cell_at(row, Some(index)).map(cell_text).unwrap_or_default())
        } else {
            (
                cell_at(row, mapping.nom).map(cell_text).unwrap_or_default(),
                cell_at(row, mapping.prenoms)
                    .map(cell_text)
                    .unwrap_or_default(),
            )
        };
        if nom.is_empty() {
            warnings.push(format!("Num {num} sans nom — ignoré."));
            skipped += 1;
            continue;
        }
        parsed.push(StudentImportRow {
            num,
            matricule: cell_at(row, mapping.matricule)
                .map(cell_text)
                .unwrap_or_default(),
            nom,
            prenoms,
            genre: cell_at(row, mapping.genre)
                .map(cell_text)
                .map(|value| clean_gender(&value))
                .unwrap_or_default(),
            naissance: cell_at(row, mapping.naissance)
                .map(cell_text)
                .unwrap_or_default(),
        });
    }

    if parsed.is_empty() {
        return None;
    }

    Some(ParsedSheet {
        sheet_name: name.to_string(),
        header_row: header_index + 1,
        mapping,
        rows: parsed,
        skipped,
        warnings,
    })
}

/// Lit tous les onglets exploitables d'un classeur.
pub fn read_all_sheets(path: &Path) -> Result<ParsedWorkbook> {
    if !path.is_file() {
        return Err(anyhow!("fichier introuvable : {}", path.display()));
    }
    let mut workbook =
        open_workbook_auto(path).with_context(|| format!("ouverture de {}", path.display()))?;
    let names = workbook.sheet_names().to_vec();
    let mut parsed = Vec::new();
    let mut skipped_sheets = Vec::new();
    for name in names {
        let range = match workbook.worksheet_range(&name) {
            Ok(range) => range,
            Err(_) => {
                skipped_sheets.push(name);
                continue;
            }
        };
        let rows: Vec<Vec<Data>> = range.rows().map(|row| row.to_vec()).collect();
        match parse_sheet(&name, &rows) {
            Some(sheet) => parsed.push(sheet),
            None => skipped_sheets.push(name),
        }
    }
    if parsed.is_empty() {
        return Err(anyhow!(
            "Aucune ligne exploitable n'a été trouvée. En-têtes attendus : Num, Nom (ou Nom et prénoms)."
        ));
    }
    Ok(ParsedWorkbook {
        sheets: parsed,
        skipped_sheets,
    })
}

/// Analyse un classeur puis met à jour la base de la classe.
///
/// Les numéros déjà présents sont mis à jour, les autres sont ajoutés.
/// En cas de doublon entre onglets, la dernière occurrence gagne (comme
/// la fusion `bulk_update_students` de l'application Python).
pub fn import_students(db: &Database, path: &Path) -> Result<StudentImportReport> {
    let workbook = read_all_sheets(path)?;
    let existing: HashSet<i64> = db
        .list_students()?
        .into_iter()
        .map(|student| student.num)
        .collect();

    let mut order: Vec<i64> = Vec::new();
    let mut by_num: HashMap<i64, Student> = HashMap::new();
    let mut skipped = 0;
    let mut warnings = Vec::new();

    for sheet in &workbook.sheets {
        skipped += sheet.skipped;
        warnings.extend(sheet.warnings.iter().cloned());
        for row in &sheet.rows {
            if by_num.contains_key(&row.num) {
                warnings.push(format!(
                    "Num {} présent dans plusieurs onglets — la dernière occurrence est retenue.",
                    row.num
                ));
            } else {
                order.push(row.num);
            }
            let id = by_num.get(&row.num).map(|student| student.id).unwrap_or(0);
            by_num.insert(row.num, row.to_student(id));
        }
    }

    let students: Vec<Student> = order
        .into_iter()
        .filter_map(|num| by_num.get(&num).cloned())
        .collect();
    let added = students
        .iter()
        .filter(|student| !existing.contains(&student.num))
        .count();
    let updated = students.len() - added;
    db.bulk_upsert_students(&students)?;

    Ok(StudentImportReport {
        added,
        updated,
        skipped,
        sheets: workbook.sheets.len(),
        warnings,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(values: &[&str]) -> Vec<Data> {
        values
            .iter()
            .map(|value| {
                if value.is_empty() {
                    Data::Empty
                } else {
                    Data::String((*value).to_string())
                }
            })
            .collect()
    }

    #[test]
    fn header_detection_skips_title_rows() {
        let rows = vec![
            row(&["Lycée Saint Joseph"]),
            row(&["Classe : 3ème 1"]),
            row(&["N°", "Nom et prénoms", "Sexe", "Date de naissance"]),
            row(&["1", "ALFRED Kevin", "M", "01/01/2010"]),
        ];
        let sheet = parse_sheet("Feuille", &rows).expect("sheet");
        assert_eq!(sheet.header_row, 3);
        assert_eq!(sheet.rows.len(), 1);
        assert_eq!(sheet.rows[0].nom, "ALFRED");
        assert_eq!(sheet.rows[0].prenoms, "Kevin");
        assert_eq!(sheet.rows[0].genre, "M");
    }

    #[test]
    fn english_headers_and_separate_names() {
        let rows = vec![
            row(&["Number", "Last name", "First name", "Gender"]),
            row(&["7", "RAKOTO", "Jean Claude", "M"]),
        ];
        let sheet = parse_sheet("Sheet1", &rows).expect("sheet");
        assert_eq!(sheet.rows[0].num, 7);
        assert_eq!(sheet.rows[0].nom, "RAKOTO");
        assert_eq!(sheet.rows[0].prenoms, "Jean Claude");
    }

    #[test]
    fn duplicate_nums_are_skipped() {
        let rows = vec![row(&["Num", "Nom"]), row(&["1", "A"]), row(&["1", "B"])];
        let sheet = parse_sheet("Sheet1", &rows).expect("sheet");
        assert_eq!(sheet.rows.len(), 1);
        assert_eq!(sheet.rows[0].nom, "A");
        assert_eq!(sheet.skipped, 1);
    }

    #[test]
    fn split_full_name_handles_simple_and_prefixed_names() {
        assert_eq!(
            split_full_name("ALFRED Kevin Haristophano"),
            ("ALFRED".to_string(), "Kevin Haristophano".to_string())
        );
        assert_eq!(
            split_full_name("Kevin"),
            ("Kevin".to_string(), String::new())
        );
        assert_eq!(
            split_full_name("M. RAKOTO Jean"),
            ("RAKOTO".to_string(), "Jean".to_string())
        );
    }

    #[test]
    fn import_updates_existing_students() {
        let db = Database::open_in_memory().unwrap();
        db.add_student(1, "ANCIEN", "Nom", "", "", "").unwrap();
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("eleves.xlsx");
        let mut workbook = rust_xlsxwriter::Workbook::new();
        let sheet = workbook.add_worksheet();
        sheet.write_string(0, 0, "Num").unwrap();
        sheet.write_string(0, 1, "Nom et prénoms").unwrap();
        sheet.write_string(1, 0, "1").unwrap();
        sheet.write_string(1, 1, "NOUVEAU Paul").unwrap();
        sheet.write_string(2, 0, "2").unwrap();
        sheet.write_string(2, 1, "AJOUTE Marie").unwrap();
        workbook.save(&path).unwrap();

        let report = import_students(&db, &path).unwrap();
        assert_eq!(report.added, 1);
        assert_eq!(report.updated, 1);
        let students = db.list_students().unwrap();
        assert_eq!(students.len(), 2);
        let first = students.iter().find(|student| student.num == 1).unwrap();
        assert_eq!(first.nom, "NOUVEAU");
        assert_eq!(first.prenoms, "Paul");
    }
}
