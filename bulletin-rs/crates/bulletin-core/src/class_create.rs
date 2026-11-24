//! Création d'une nouvelle classe : catalogue de matières, génération des
//! noms de sous-classes, dossiers, base SQLite, élèves et feuilles `.xlsx`.
//!
//! Reprend le comportement de `app/wizards/class_wizard.py` et de
//! `app/wizards/subjects_catalog.py`, dans une version simplifiée pilotée
//! par l'interface Slint.

use crate::db::{Database, class_default_coeff, subject_allowed_for_level};
use crate::workspace::{
    extract_level_key, find_bulletin_root, normalize, prettify_class_name,
};
use anyhow::{Context, Result, anyhow, bail};
use rust_xlsxwriter::{Format, Workbook};
use std::fs;
use std::path::Path;

#[derive(Debug, Clone, Copy)]
pub struct SectionDef {
    pub key: &'static str,
    pub label: &'static str,
    pub description: &'static str,
    /// `(clé, libellé)` des niveaux.
    pub levels: &'static [(&'static str, &'static str)],
    /// `(matière, coefficient)`.
    pub subjects: &'static [(&'static str, f64)],
}

pub const SECTIONS: &[SectionDef] = &[
    SectionDef {
        key: "MATER",
        label: "Maternelle",
        description: "Petite, Moyenne et Grande Sections",
        levels: &[
            ("PS", "Petite Section"),
            ("MS", "Moyenne Section"),
            ("GS", "Grande Section"),
        ],
        subjects: &[
            ("Langage oral", 1.0),
            ("Langage écrit", 1.0),
            ("Activités numériques", 1.0),
            ("Éveil scientifique", 1.0),
            ("Activités physiques", 1.0),
            ("Activités artistiques", 1.0),
            ("Vie sociale", 1.0),
        ],
    },
    SectionDef {
        key: "PRIM",
        label: "Primaire",
        description: "Du CP au CM2",
        levels: &[
            ("CP", "CP (Cours Préparatoire)"),
            ("CE1", "CE1 (Cours Élémentaire 1)"),
            ("CE2", "CE2 (Cours Élémentaire 2)"),
            ("CM1", "CM1 (Cours Moyen 1)"),
            ("CM2", "CM2 (Cours Moyen 2)"),
        ],
        subjects: &[
            ("Malagasy", 4.0),
            ("Français", 4.0),
            ("Mathématiques", 4.0),
            ("Sciences et Techno.", 2.0),
            ("Histoire-Géographie", 2.0),
            ("Éducation civique", 1.0),
            ("EPS", 1.0),
            ("Arts plastiques", 1.0),
            ("Éducation musicale", 1.0),
        ],
    },
    SectionDef {
        key: "COLLEGE",
        label: "Collège",
        description: "De la 6ème à la 3ème",
        levels: &[
            ("6EME", "6ème"),
            ("5EME", "5ème"),
            ("4EME", "4ème"),
            ("3EME", "3ème"),
        ],
        subjects: &[
            ("Religion", 1.0),
            ("Éducation à la Vie", 1.0),
            ("Malagasy", 4.0),
            ("Français", 3.0),
            ("Anglais", 2.0),
            ("Histoire-Géographie", 4.0),
            ("Mathématiques", 2.0),
            ("SVT", 2.0),
            ("Physique-chimie", 2.0),
            ("EPS", 1.0),
        ],
    },
    SectionDef {
        key: "LYCEE",
        label: "Lycée",
        description: "De la 2nde à la Terminale",
        levels: &[("2NDE", "2nde"), ("1ERE", "1ère"), ("TLE", "Terminale")],
        subjects: &[
            ("Religion", 1.0),
            ("Éducation à la Vie", 1.0),
            ("Malagasy", 4.0),
            ("Français", 3.0),
            ("Anglais", 2.0),
            ("Histoire-Géographie", 4.0),
            ("Mathématiques", 2.0),
            ("SVT", 2.0),
            ("Physique-chimie", 2.0),
            ("EPS", 1.0),
            ("Philosophie", 2.0),
        ],
    },
];

pub fn section(key: &str) -> Option<&'static SectionDef> {
    SECTIONS
        .iter()
        .find(|section| section.key.eq_ignore_ascii_case(key.trim()))
}

/// Déduit la division de rangement d'un nom de classe normalisé.
pub fn infer_division(class_name: &str) -> &'static str {
    let name = normalize(class_name).to_uppercase().replace(' ', "");
    if name.starts_with("CP")
        || name.starts_with("CE1")
        || name.starts_with("CE2")
        || name.starts_with("CM1")
        || name.starts_with("CM2")
        || name.starts_with("PS")
        || name.starts_with("MS")
        || name.starts_with("GS")
    {
        return "PRIMAIRE";
    }
    if ["6EME", "5EME", "4EME", "3EME"]
        .iter()
        .any(|prefix| name.starts_with(prefix))
    {
        return "COLLEGE";
    }
    if ["2NDE", "1ERE", "TLE", "TALE", "TAI"]
        .iter()
        .any(|prefix| name.starts_with(prefix))
    {
        return "LYCEE";
    }
    // Abréviations lycée : 1L, 1S, 1EL1…
    let bytes = name.as_bytes();
    if bytes.first() == Some(&b'1') && name.len() <= 6 {
        return "LYCEE";
    }
    "COLLEGE"
}

/// Génère les noms de sous-classes pour un niveau et un motif donnés.
pub fn expand_pattern(
    level: &str,
    pattern: &str,
    count: usize,
    custom_suffixes: &[String],
) -> Result<Vec<String>> {
    let level = level.trim().to_uppercase();
    if count == 0 {
        return Ok(Vec::new());
    }
    match pattern {
        "numeric" => Ok((1..=count).map(|index| format!("{level}{index}")).collect()),
        "roman" => {
            const ROMAN: [&str; 11] = [
                "", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
            ];
            if count > 10 {
                bail!("Le motif romain est limité à 10 sous-classes.");
            }
            Ok((1..=count)
                .map(|index| format!("{level}{}", ROMAN[index]))
                .collect())
        }
        "alpha" => {
            if count > 26 {
                bail!("Le motif alphabétique est limité à 26 sous-classes.");
            }
            Ok((0..count)
                .map(|index| format!("{level}{}", (b'A' + index as u8) as char))
                .collect())
        }
        "custom" => {
            if custom_suffixes.len() != count {
                bail!(
                    "Motif personnalisé : il faut exactement {count} suffixe(s), {} fourni(s).",
                    custom_suffixes.len()
                );
            }
            Ok(custom_suffixes
                .iter()
                .map(|suffix| format!("{level}{}", suffix.trim().to_uppercase()))
                .collect())
        }
        other => bail!("Motif inconnu : {other}"),
    }
}

/// Paramètres saisis dans la page « Nouvelle classe ».
#[derive(Debug, Clone)]
pub struct ClassDraft {
    pub section: String,
    pub level: String,
    pub count: usize,
    pub pattern: String,
    pub custom_suffixes: Vec<String>,
    pub effectif: i64,
    pub etablissement: String,
    pub annee_scolaire: String,
    pub prof_principal: String,
}

/// Résultat de la création physique.
#[derive(Debug, Clone, serde::Serialize)]
pub struct CreatedClass {
    pub name: String,
    pub display_name: String,
    pub division: String,
    pub folder: String,
    pub students: usize,
    pub subjects: usize,
}

/// Crée les classes sous la racine de l'espace de travail courante.
pub fn create_classes(draft: &ClassDraft) -> Result<Vec<CreatedClass>> {
    let root = find_bulletin_root(None);
    create_classes_in(&root, draft)
}

/// Crée les dossiers, bases, matières, élèves et feuilles `.xlsx` vides.
pub fn create_classes_in(root: &Path, draft: &ClassDraft) -> Result<Vec<CreatedClass>> {
    let section =
        section(&draft.section).ok_or_else(|| anyhow!("Section inconnue : {}", draft.section))?;
    let names = expand_pattern(
        &draft.level,
        &draft.pattern,
        draft.count,
        &draft.custom_suffixes,
    )?;
    if names.is_empty() {
        bail!("Aucune classe à créer.");
    }

    let mut created = Vec::new();
    for name in names {
        if name.trim().is_empty() {
            continue;
        }
        let division = infer_division(&name);
        let div_dir = root.join(division);
        let class_dir = div_dir.join(&name);
        if class_dir.exists() {
            bail!(
                "Le dossier {} existe déjà. Choisissez un autre nom ou supprimez-le d'abord.",
                class_dir.display()
            );
        }
        fs::create_dir_all(class_dir.join("data"))
            .with_context(|| format!("création de {}", class_dir.join("data").display()))?;
        fs::create_dir_all(class_dir.join("bulletin"))
            .with_context(|| format!("création de {}", class_dir.join("bulletin").display()))?;

        let db_path = class_dir.join("data").join("bulletin.db");
        let db = Database::open(Some(&db_path))?;
        let display_name = prettify_class_name(&name);
        db.set_setting("etablissement", &draft.etablissement)?;
        db.set_setting("directeur", "Directeur")?;
        db.set_setting("annee_scolaire", &draft.annee_scolaire)?;
        db.set_setting("classe", &display_name)?;
        db.set_setting("nb_examens", "6")?;
        db.set_setting("effectif", &draft.effectif.max(0).to_string())?;
        db.set_setting("nb_min_examens", "3")?;
        db.set_setting("prof_principal", &draft.prof_principal)?;
        db.set_setting("section", section.label)?;
        db.set_setting("niveau", &draft.level.to_uppercase())?;

        // Matières de la section avec les coefficients propres à la
        // classe (tableau 2026-09-20), moins celles interdites au
        // niveau (ex. Philosophie en 2nde ou au collège).
        let level_key = if draft.level.trim().is_empty() {
            extract_level_key(&name)
        } else {
            draft.level.trim().to_uppercase()
        };
        let subjects: Vec<(String, f64, String)> = section
            .subjects
            .iter()
            .filter(|(subject, _)| subject_allowed_for_level(subject, &level_key))
            .map(|(subject, coeff)| {
                let class_coeff =
                    class_default_coeff(subject, &name, Some(&level_key)).unwrap_or(*coeff);
                (
                    subject.to_string(),
                    class_coeff,
                    draft.prof_principal.clone(),
                )
            })
            .collect();
        db.set_subjects(&subjects)?;
        let students = if draft.effectif > 0 {
            db.generate_students(draft.effectif, 1)?
        } else {
            0
        };

        for (name, coeff, _teacher) in &subjects {
            write_blank_subject_sheet(
                &class_dir,
                &db,
                name,
                *coeff,
                &display_name,
                &draft.etablissement,
                &draft.annee_scolaire,
                &draft.prof_principal,
            )?;
        }

        created.push(CreatedClass {
            name: name.clone(),
            display_name,
            division: division.to_string(),
            folder: class_dir.to_string_lossy().to_string(),
            students,
            subjects: subjects.len(),
        });
    }
    Ok(created)
}

/// Crée `<Matière>.xlsx` avec les métadonnées, les en-têtes et une ligne
/// par élève (numéro + nom), comme le modèle de l'application Python.
#[allow(clippy::too_many_arguments)]
fn write_blank_subject_sheet(
    class_dir: &Path,
    db: &Database,
    subject: &str,
    coeff: f64,
    display_name: &str,
    etablissement: &str,
    annee: &str,
    prof: &str,
) -> Result<()> {
    let mut workbook = Workbook::new();
    let sheet = workbook.add_worksheet();
    sheet.set_name("Sheet1")?;

    let bold = Format::new().set_bold();
    sheet.write_string(1, 1, etablissement)?;
    sheet.write_string(1, 4, subject)?;
    sheet.write_string(2, 1, display_name)?;
    sheet.write_string(2, 2, "Coeff")?;
    sheet.write_string(2, 5, "Prof")?;
    sheet.write_string(3, 1, &format!("Année scolaire : {annee}"))?;
    sheet.write_number(3, 2, coeff)?;
    sheet.write_string(3, 5, prof)?;

    let headers = [
        "Num",
        "Nom et Prénoms",
        "M.J 1",
        "Compo 1",
        "M.J 2",
        "Compo 2",
        "M.J 3",
        "Compo 3",
    ];
    for (column, header) in headers.iter().enumerate() {
        sheet.write_string_with_format(4, column as u16, *header, &bold)?;
    }
    sheet.set_column_width(1, 32)?;

    for (index, student) in db.list_students()?.iter().enumerate() {
        let row = 5 + index as u32;
        sheet.write_number(row, 0, student.num as f64)?;
        let full = format!("{} {}", student.nom, student.prenoms)
            .trim()
            .to_string();
        let fallback = format!("Élève {}", student.num);
        sheet.write_string(row, 1, if full.is_empty() { &fallback } else { &full })?;
    }

    let path = class_dir.join(format!("{subject}.xlsx"));
    workbook
        .save(&path)
        .with_context(|| format!("écriture de {}", path.display()))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn patterns_match_python_examples() {
        assert_eq!(
            expand_pattern("6EME", "numeric", 3, &[]).unwrap(),
            vec!["6EME1", "6EME2", "6EME3"]
        );
        assert_eq!(
            expand_pattern("6EME", "roman", 2, &[]).unwrap(),
            vec!["6EMEI", "6EMEII"]
        );
        assert_eq!(
            expand_pattern("6EME", "alpha", 2, &[]).unwrap(),
            vec!["6EMEA", "6EMEB"]
        );
        assert_eq!(
            expand_pattern(
                "1ERE",
                "custom",
                3,
                &["LI".to_string(), "LII".to_string(), "S".to_string()]
            )
            .unwrap(),
            vec!["1ERELI", "1ERELII", "1ERES"]
        );
    }

    #[test]
    fn divisions_are_inferred() {
        assert_eq!(infer_division("6EME1"), "COLLEGE");
        assert_eq!(infer_division("1EREL1"), "LYCEE");
        assert_eq!(infer_division("CM2A"), "PRIMAIRE");
        assert_eq!(infer_division("TAI"), "LYCEE");
    }

    fn db_coeff(db: &Database, name: &str) -> Option<f64> {
        db.list_subjects()
            .ok()?
            .iter()
            .find(|subject| subject.name == name)
            .map(|subject| subject.coeff)
    }

    fn draft(section: &str, level: &str) -> ClassDraft {
        ClassDraft {
            section: section.into(),
            level: level.into(),
            count: 1,
            pattern: "numeric".into(),
            custom_suffixes: Vec::new(),
            effectif: 1,
            etablissement: "École Test".into(),
            annee_scolaire: "2025-2026".into(),
            prof_principal: "M. Prof".into(),
        }
    }

    /// Le catalogue COLLEGE annonce Malagasy 4 / Histo-geo 4 /
    /// Physique-chimie 2 : le tableau de la classe (3EME1) prime en base
    /// **et** dans la cellule C4 du `.xlsx`.
    #[test]
    fn per_class_coefficients_replace_catalog_values() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(dir.path().join("COLLEGE")).unwrap();
        let created = create_classes_in(dir.path(), &draft("COLLEGE", "3EME")).unwrap();
        let class_dir = PathBuf::from(&created[0].folder);
        let db = Database::open(Some(&class_dir.join("data/bulletin.db"))).unwrap();

        assert_eq!(db_coeff(&db, "Malagasy"), Some(3.0));
        assert_eq!(db_coeff(&db, "Histoire-Géographie"), Some(3.0));
        assert_eq!(db_coeff(&db, "Physique-chimie"), Some(3.0));

        let sheet = class_dir.join("Physique-chimie.xlsx");
        assert_eq!(crate::workspace::read_coefficient_from_xlsx(&sheet), Some(3.0));
    }

    /// La Philosophie du catalogue LYCEE ne doit pas survivre à une
    /// création de classe de seconde.
    #[test]
    fn philosophy_is_dropped_for_seconde_classes() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(dir.path().join("LYCEE")).unwrap();
        let created = create_classes_in(dir.path(), &draft("LYCEE", "2NDE")).unwrap();
        let class_dir = PathBuf::from(&created[0].folder);
        let db = Database::open(Some(&class_dir.join("data/bulletin.db"))).unwrap();

        assert!(
            db.list_subjects()
                .unwrap()
                .iter()
                .all(|subject| subject.name != "Philosophie")
        );
        assert!(!class_dir.join("Philosophie.xlsx").exists());
        assert_eq!(created[0].subjects, 10);
    }

    /// Crée une classe dans une racine temporaire en fixant le dossier
    /// courant, car `find_bulletin_root` n'accepte pas de racine ici.
    #[test]
    fn creates_folder_database_students_and_sheets() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(dir.path().join("COLLEGE")).unwrap();
        let draft = ClassDraft {
            section: "COLLEGE".into(),
            level: "6EME".into(),
            count: 1,
            pattern: "numeric".into(),
            custom_suffixes: Vec::new(),
            effectif: 3,
            etablissement: "Collège Test".into(),
            annee_scolaire: "2025-2026".into(),
            prof_principal: "M. Prof".into(),
        };
        let created = create_classes_in(dir.path(), &draft).unwrap();
        assert_eq!(created.len(), 1);
        let class_dir = PathBuf::from(&created[0].folder);
        assert!(class_dir.join("data/bulletin.db").is_file());
        assert!(class_dir.join("Malagasy.xlsx").is_file());
        let db = Database::open(Some(&class_dir.join("data/bulletin.db"))).unwrap();
        assert_eq!(db.count_students().unwrap(), 3);
        assert_eq!(db.count_subjects().unwrap(), 10);
        assert_eq!(db.get_setting("classe", ""), "6ème 1");

        // La feuille vide générée doit être relisible par la synchronisation.
        let sync =
            crate::sync::sync_subject_from_xlsx(&db, "Malagasy", &class_dir.join("Malagasy.xlsx"))
                .unwrap();
        assert!(sync.matched);
        assert!(sync.errors.is_empty(), "{:?}", sync.errors);
        assert_eq!(sync.notes_total, 0);
    }
}
