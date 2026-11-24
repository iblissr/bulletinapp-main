//! Découverte et gestion des « workspaces » (un workspace = une classe).
//!
//! Reprend l'arborescence historique :
//! `BULLETIN/COLLEGE/3EME1/`, `BULLETIN/LYCEE/1ereLI/`, etc.
//! Chaque classe possède ses fichiers `.xlsx` de matières et une base
//! SQLite dans `<classe>/data/bulletin.db`.

use anyhow::{Context, Result};
use calamine::{Data, Reader, open_workbook_auto};
use regex::Regex;
use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use unicode_normalization::UnicodeNormalization;

pub const DIVISIONS: [&str; 3] = ["COLLEGE", "LYCEE", "PRIMAIRE"];

/// Métadonnées d'une classe découverte.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClassInfo {
    /// Nom du dossier (`3EME1`, `1ereLI`, …).
    pub name: String,
    /// Libellé lisible (`3ème 1`, `1ère LI`, …).
    pub display_name: String,
    /// `COLLEGE`, `LYCEE` ou `PRIMAIRE`.
    pub division: String,
    pub folder: PathBuf,
    pub db_path: PathBuf,
    pub bulletin_path: PathBuf,
    pub subject_files: Vec<PathBuf>,
}

impl ClassInfo {
    /// Nom officiel du bulletin : `Bulletin1ERELI.xlsm`.
    pub fn bulletin_name(&self) -> String {
        format!("Bulletin{}.xlsm", self.name.to_uppercase())
    }

    /// Chemin `<classe>/<Matière>.xlsx`, insensible à la casse, aux
    /// accents et aux alias (`EVA` ↔ `Éducation à la Vie`…).
    pub fn subject_path(&self, subject_name: &str) -> PathBuf {
        let aliases = subject_name_aliases(subject_name);
        for p in &self.subject_files {
            if let Some(stem) = p.file_stem() {
                let norm = normalize(&stem.to_string_lossy());
                if aliases.contains(&norm) {
                    return p.clone();
                }
            }
        }
        self.folder.join(format!("{subject_name}.xlsx"))
    }

    pub fn has_subject(&self, subject_name: &str) -> bool {
        let aliases = subject_name_aliases(subject_name);
        self.subject_files.iter().any(|p| {
            p.file_stem()
                .map(|s| aliases.contains(&normalize(&s.to_string_lossy())))
                .unwrap_or(false)
        })
    }
}

/// Normalisation des noms (casse, accents, ponctuation).
pub fn normalize(text: &str) -> String {
    if text.trim().is_empty() {
        return String::new();
    }
    let lowered = text.trim().to_lowercase();
    let without_accents: String = lowered.nfd().filter(|c| !is_combining_mark(*c)).collect();
    let mut out = String::with_capacity(without_accents.len());
    let mut previous_space = false;
    for c in without_accents.chars() {
        if c.is_ascii_alphanumeric() || c == ' ' {
            if c == ' ' {
                if previous_space {
                    continue;
                }
                previous_space = true;
            } else {
                previous_space = false;
            }
            out.push(c);
        } else {
            if !previous_space && !out.is_empty() {
                out.push(' ');
                previous_space = true;
            }
        }
    }
    out.trim().to_string()
}

fn is_combining_mark(c: char) -> bool {
    matches!(c as u32, 0x0300..=0x036F | 0x1AB0..=0x1AFF | 0x1DC0..=0x1DFF | 0x20D0..=0x20FF | 0xFE20..=0xFE2F)
}

/// `3EME1` → `3ème 1`, `1ereLI` → `1ère LI`, `TAI` → `TAI`.
pub fn prettify_class_name(raw: &str) -> String {
    let raw = raw.trim();
    if raw.is_empty() {
        return String::new();
    }
    let re = Regex::new(r"(?i)^(\d+)?(eme|ère|ere|nde)?(.*)$").unwrap();
    let Some(caps) = re.captures(raw) else {
        return raw.to_string();
    };
    let num = caps.get(1).map(|m| m.as_str()).unwrap_or("");
    let kind = caps.get(2).map(|m| m.as_str()).unwrap_or("");
    let rest = caps.get(3).map(|m| m.as_str()).unwrap_or("");

    let mut prefix = String::new();
    prefix.push_str(num);
    match kind.to_lowercase().as_str() {
        "eme" => prefix.push_str("ème"),
        "ère" | "ere" => prefix.push_str("ère"),
        "nde" => prefix.push_str("nde"),
        _ => {}
    }
    if !prefix.is_empty() && !rest.is_empty() {
        format!("{prefix} {rest}")
    } else {
        format!("{prefix}{rest}")
    }
}

// ---------------------------------------------------------------------------
// Aliases de matières : base ↔ noms de fichiers `.xlsx`
// ---------------------------------------------------------------------------
/// Tous les noms normalisés possibles pour un sujet (nom + alias).
///
/// `education a la vie` ↔ `eva`, `histoire geographie` ↔ `histo geo`.
pub fn subject_aliases(normalized_name: &str) -> Vec<String> {
    let mut names = vec![normalized_name.to_string()];
    match normalized_name {
        "education a la vie" => names.push("eva".to_string()),
        "histoire geographie" => names.push("histo geo".to_string()),
        "eva" => names.push("education a la vie".to_string()),
        "histo geo" => names.push("histoire geographie".to_string()),
        _ => {}
    }
    names
}

/// Alias d'un nom de sujet brut (casse / accents / ponctuation ignorés).
pub fn subject_name_aliases(name: &str) -> Vec<String> {
    subject_aliases(&normalize(name))
}

// ---------------------------------------------------------------------------
// Noms de classes : normalisation et niveau
// ---------------------------------------------------------------------------
fn strip_accents_upper(text: &str) -> String {
    text.nfd()
        .filter(|c| !is_combining_mark(*c))
        .collect::<String>()
        .to_uppercase()
        .trim()
        .to_string()
}

/// Frontière attendue par les lookaheads `(?=\b|\s|[^A-Z0-9])` du modèle
/// Python, une fois la chaîne passée en majuscules.
fn level_boundary(chars: &[char], pos: usize) -> bool {
    match chars.get(pos) {
        None => true,
        Some(&c) => !(c.is_ascii_uppercase() || c.is_ascii_digit()),
    }
}

/// Frontière `\b` (fin de chaîne, ou caractère non « mot »).
fn word_boundary(chars: &[char], pos: usize) -> bool {
    match chars.get(pos) {
        None => true,
        Some(&c) => !(c.is_ascii_alphanumeric() || c == '_'),
    }
}

fn replace_prefix(chars: &[char], end: usize, out: &str) -> Vec<char> {
    let mut result: Vec<char> = out.chars().collect();
    result.extend_from_slice(&chars[end..]);
    result
}

/// `^(\d+)\s*E(ME)?` → `\1EME` (et variantes `ER`→`ERE`, `ND`→`NDE`).
fn rewrite_num_prefix(chars: &[char], head: &str, tail: &str, out: &str) -> Vec<char> {
    let mut idx = 0;
    while idx < chars.len() && chars[idx].is_ascii_digit() {
        idx += 1;
    }
    if idx == 0 {
        return chars.to_vec();
    }
    let digits: String = chars[..idx].iter().collect();
    while idx < chars.len() && chars[idx].is_whitespace() {
        idx += 1;
    }
    let head_chars: Vec<char> = head.chars().collect();
    if !chars[idx..].starts_with(&head_chars) {
        return chars.to_vec();
    }
    let after_head = idx + head_chars.len();
    let mut end = after_head;
    let tail_chars: Vec<char> = tail.chars().collect();
    if chars[after_head..].starts_with(&tail_chars) {
        let after_tail = after_head + tail_chars.len();
        if level_boundary(chars, after_tail) {
            end = after_tail;
        }
    }
    if !level_boundary(chars, end) {
        return chars.to_vec();
    }
    replace_prefix(chars, end, &format!("{digits}{out}"))
}

/// `^T\s*LE\b` → `TLE` (et `^T\s*ALE\b` → `TALE`).
fn rewrite_t_prefix(chars: &[char], tail: &str, out: &str) -> Vec<char> {
    if chars.first() != Some(&'T') {
        return chars.to_vec();
    }
    let mut idx = 1;
    while idx < chars.len() && chars[idx].is_whitespace() {
        idx += 1;
    }
    let tail_chars: Vec<char> = tail.chars().collect();
    if !chars[idx..].starts_with(&tail_chars) {
        return chars.to_vec();
    }
    let end = idx + tail_chars.len();
    if !word_boundary(chars, end) {
        return chars.to_vec();
    }
    replace_prefix(chars, end, out)
}

/// `^1EL(\d*)$` → `1EREL`, `^1ES(\d*)$` → `1ERES`,
/// `^1([LSABCD])(\d*)$` → `1ERE…`.
fn rewrite_first_prefix(chars: &[char]) -> Vec<char> {
    if chars.len() < 2 || chars[0] != '1' {
        return chars.to_vec();
    }
    let tail_is_digits = |from: usize| chars[from..].iter().all(|c| c.is_ascii_digit());
    if chars.len() >= 3 && chars[1] == 'E' && chars[2] == 'L' && tail_is_digits(3) {
        return replace_prefix(chars, 3, "1EREL");
    }
    if chars.len() >= 3 && chars[1] == 'E' && chars[2] == 'S' && tail_is_digits(3) {
        return replace_prefix(chars, 3, "1ERES");
    }
    if matches!(chars[1], 'L' | 'S' | 'A' | 'B' | 'C' | 'D') && tail_is_digits(2) {
        return replace_prefix(chars, 1, "1ERE");
    }
    chars.to_vec()
}

fn roman_to_number(roman: &str) -> Option<i64> {
    Some(match roman {
        "I" => 1,
        "II" => 2,
        "III" => 3,
        "IV" => 4,
        "V" => 5,
        "VI" => 6,
        "VII" => 7,
        "VIII" => 8,
        "IX" => 9,
        _ => return None,
    })
}

fn is_roman(c: char) -> bool {
    matches!(c, 'I' | 'V' | 'X')
}

/// Normalise un nom de classe en nom de dossier canonique.
///
/// `6e I` → `6EME1`, `6ème 2` → `6EME2`, `1ère L1` → `1EREL1`,
/// `2nde II` → `2NDE2`, `TAI` → `TA1`.
pub fn normalize_class_name(raw: &str) -> String {
    let mut chars: Vec<char> = strip_accents_upper(raw).chars().collect();
    if chars.is_empty() {
        return String::new();
    }
    // Symbole degré « ° » (« 1°L1 » → « 1L1 »).
    chars.retain(|c| *c != '°');

    chars = rewrite_num_prefix(&chars, "E", "ME", "EME");
    chars = rewrite_num_prefix(&chars, "ER", "E", "ERE");
    chars = rewrite_num_prefix(&chars, "ND", "E", "NDE");
    chars = rewrite_t_prefix(&chars, "LE", "TLE");
    chars = rewrite_t_prefix(&chars, "ALE", "TALE");
    chars = rewrite_first_prefix(&chars);

    // Ponctuation → espaces, puis tous les espaces supprimés.
    let mut compacted = String::with_capacity(chars.len());
    for c in chars {
        if c.is_whitespace() || matches!(c, '.' | ',' | ';' | ':' | '-' | '_' | '/' | '\\') {
            continue;
        }
        compacted.push(c);
    }

    // « 6 I », « 3 III » sans préfixe EME → « 6EME1 », « 3EME3 ».
    let bytes = compacted.as_bytes();
    if bytes.len() >= 2
        && matches!(bytes[0], b'3'..=b'6')
        && compacted[1..].chars().all(is_roman)
        && !["3EME", "4EME", "5EME", "6EME"]
            .iter()
            .any(|prefix| compacted.starts_with(prefix))
    {
        if let Some(value) = roman_to_number(&compacted[1..]) {
            return format!("{}EME{value}", bytes[0] as char);
        }
    }

    // Chiffres romains en fin de chaîne → chiffres arabes.
    let letters: Vec<char> = compacted.chars().collect();
    let mut start = letters.len();
    while start > 0 && is_roman(letters[start - 1]) {
        start -= 1;
    }
    if start < letters.len() {
        let roman: String = letters[start..].iter().collect();
        if let Some(value) = roman_to_number(&roman) {
            let mut out: String = letters[..start].iter().collect();
            out.push_str(&value.to_string());
            return out;
        }
    }
    compacted
}

/// Extrait la clé de niveau d'un nom de classe.
///
/// `6EME1` → `6EME`, `1EREL1` → `1ERE`, `TA1` → `TLE`, `2NDEA` → `2NDE`.
/// Chaîne vide si le niveau est indéterminé.
pub fn extract_level_key(class_name: &str) -> String {
    let n = normalize_class_name(class_name);
    if n.is_empty() {
        return String::new();
    }
    // Primaire
    for prefix in ["CP", "CE1", "CE2", "CM1", "CM2"] {
        if n.starts_with(prefix) {
            return prefix.to_string();
        }
    }
    // Collège
    for prefix in ["3EME", "4EME", "5EME", "6EME"] {
        if n.starts_with(prefix) {
            return prefix.to_string();
        }
    }
    // Lycée
    if n.starts_with("2NDE") {
        return "2NDE".to_string();
    }
    if n.starts_with("1ERE") {
        return "1ERE".to_string();
    }
    if n.starts_with("TLE") || n.starts_with("TALE") || n.starts_with("TAI") {
        return "TLE".to_string();
    }
    // Terminale abrégée : T suivi d'au moins une lettre (TAD, TD, TALL…).
    let letters: Vec<char> = n.chars().collect();
    if letters.first() == Some(&'T') && letters.get(1).is_some_and(|c| c.is_ascii_uppercase()) {
        return "TLE".to_string();
    }
    // Première abrégée : 1 suivi de 1 à 4 lettres (1LI, 1EREL1…).
    if letters.first() == Some(&'1') {
        let rest = &letters[1..];
        let leading: usize = rest.iter().take_while(|c| c.is_ascii_uppercase()).count();
        if (1..=4).contains(&leading) && rest[leading..].iter().all(|c| c.is_ascii_digit()) {
            return "1ERE".to_string();
        }
    }
    String::new()
}

/// Cherche la racine `BULLETIN/` en remontant les parents.
pub fn find_bulletin_root(start: Option<&Path>) -> PathBuf {
    let start_path = match start {
        Some(p) => p.to_path_buf(),
        None => std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")),
    };
    let start_path = start_path.canonicalize().unwrap_or(start_path);

    if is_bulletin_root(&start_path) {
        return start_path;
    }
    for ancestor in start_path.ancestors().skip(1) {
        if is_bulletin_root(ancestor) {
            return ancestor.to_path_buf();
        }
    }
    if let Some(explicit) = start {
        return explicit.to_path_buf();
    }
    // Repli : le dossier qui contient cet exécutable, ou le dossier courant.
    start_path
}

fn is_bulletin_root(path: &Path) -> bool {
    DIVISIONS.iter().any(|division| {
        division_candidates(division)
            .iter()
            .any(|candidate| path.join(candidate).is_dir())
    })
}

fn division_candidates(division: &str) -> Vec<&'static str> {
    match division {
        "COLLEGE" => vec!["COLLEGE", "College", "Collège"],
        "LYCEE" => vec!["LYCEE", "Lycee", "Lycée"],
        "PRIMAIRE" => vec!["PRIMAIRE", "Primaire"],
        _ => vec![],
    }
}

/// Scanne la racine et retourne les classes triées par division puis nom.
pub fn discover_classes(root: Option<&Path>) -> Vec<ClassInfo> {
    let bulletin_root = find_bulletin_root(root);
    let mut classes = Vec::new();
    let mut seen: HashSet<PathBuf> = HashSet::new();

    for division in DIVISIONS {
        for div_name in division_candidates(division) {
            let div_dir = bulletin_root.join(div_name);
            if !div_dir.is_dir() {
                continue;
            }
            let Ok(entries) = fs::read_dir(&div_dir) else {
                continue;
            };
            let mut class_dirs: Vec<PathBuf> = entries
                .filter_map(|entry| entry.ok())
                .map(|entry| entry.path())
                .filter(|path| path.is_dir())
                .collect();
            class_dirs.sort_by_key(|p| p.file_name().map(|n| n.to_string_lossy().to_lowercase()));
            for class_dir in class_dirs {
                let canonical = class_dir
                    .canonicalize()
                    .unwrap_or_else(|_| class_dir.clone());
                if !seen.insert(canonical) {
                    continue;
                }
                let name = class_dir
                    .file_name()
                    .map(|n| n.to_string_lossy().to_string())
                    .unwrap_or_default();
                if matches!(name.to_lowercase().as_str(), "data" | "bulletin") {
                    continue;
                }
                if let Some(info) = build_class_info(&class_dir, division) {
                    classes.push(info);
                }
            }
        }
    }
    classes.sort_by(|a, b| {
        a.division.cmp(&b.division).then_with(|| {
            a.display_name
                .to_lowercase()
                .cmp(&b.display_name.to_lowercase())
        })
    });
    classes
}

pub fn discover_class(name: &str, root: Option<&Path>) -> Option<ClassInfo> {
    let target = name.trim().to_lowercase();
    discover_classes(root)
        .into_iter()
        .find(|class| class.name.to_lowercase() == target)
}

fn build_class_info(class_dir: &Path, division: &str) -> Option<ClassInfo> {
    build_class_info_impl(class_dir, division, false)
}

/// Variante tolérante : accepte un dossier classe vide (ni `.xlsx`, ni sous-dossier
/// `bulletin/`) pour pouvoir grainer / migrer sa base.
pub fn build_class_info_lenient(class_dir: &Path, division: &str) -> Option<ClassInfo> {
    build_class_info_impl(class_dir, division, true)
}

fn build_class_info_impl(class_dir: &Path, division: &str, lenient: bool) -> Option<ClassInfo> {
    let mut subject_files: Vec<PathBuf> = fs::read_dir(class_dir)
        .ok()?
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.path())
        .filter(|path| {
            path.is_file()
                && path
                    .extension()
                    .map(|ext| ext.to_string_lossy().eq_ignore_ascii_case("xlsx"))
                    .unwrap_or(false)
                && !path
                    .file_name()
                    .map(|name| name.to_string_lossy().starts_with("~$"))
                    .unwrap_or(false)
        })
        .filter(|path| {
            let subject = path
                .file_stem()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_default();
            !is_subject_excluded(&subject, &class_dir_name(class_dir).to_lowercase())
        })
        .collect();
    subject_files.sort_by_key(|p| p.file_name().map(|n| n.to_string_lossy().to_lowercase()));

    let bulletin_dir = class_dir.join("bulletin");
    let bulletin_path = bulletin_dir.join(format!(
        "Bulletin{}.xlsm",
        class_dir_name(class_dir).to_uppercase()
    ));
    let db_path = class_dir.join("data").join("bulletin.db");

    if !lenient && subject_files.is_empty() && !bulletin_dir.is_dir() {
        return None;
    }

    let name = class_dir_name(class_dir);
    Some(ClassInfo {
        display_name: prettify_class_name(&name),
        name,
        division: division.to_string(),
        folder: class_dir.to_path_buf(),
        db_path,
        bulletin_path,
        subject_files,
    })
}

fn class_dir_name(class_dir: &Path) -> String {
    class_dir
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_default()
}

/// Philosophie n'apparaît qu'en Première/Terminale, pas en Seconde ni au collège.
pub fn is_subject_excluded(subject_name: &str, class_name_lower: &str) -> bool {
    if normalize(subject_name) != "philosophie" {
        return false;
    }
    let re = Regex::new(r"^(1ere|1ère|1e?re?l|1e?re?s|t[ae]?|td)").unwrap();
    !re.is_match(class_name_lower)
}

/// Retrouve une classe à partir du chemin de sa base SQLite.
pub fn discover_class_by_db_path(db_path: &Path) -> Option<ClassInfo> {
    let target = normalized_path(db_path);
    let classes = discover_classes(None);
    if let Some(found) = classes
        .iter()
        .find(|class| normalized_path(&class.db_path) == target)
    {
        return Some(found.clone());
    }

    // Repli : un composant COLLEGE/LYCEE suivi du nom de la classe.
    let components: Vec<String> = db_path
        .components()
        .map(|c| c.as_os_str().to_string_lossy().to_string())
        .collect();
    for (index, component) in components.iter().enumerate() {
        if matches!(
            component.as_str(),
            "COLLEGE" | "LYCEE" | "Collège" | "Lycée" | "PRIMAIRE" | "Primaire"
        ) && index + 1 < components.len()
        {
            if let Some(found) = discover_class(&components[index + 1], None) {
                return Some(found);
            }
            // Dossier classe sans .xlsx ni sous-dossier `bulletin/` :
            // `discover_classes()` l'ignore, mais on peut quand même
            // construire un ClassInfo (utile pour grainer / migrer).
            let folder = db_path
                .parent()
                .and_then(|p| p.parent())
                .map(Path::to_path_buf);
            if let Some(folder) = folder {
                if folder.is_dir()
                    && class_dir_name(&folder).eq_ignore_ascii_case(&components[index + 1])
                {
                    let division = match component.as_str() {
                        "LYCEE" | "Lycée" => "LYCEE",
                        "PRIMAIRE" | "Primaire" => "PRIMAIRE",
                        _ => "COLLEGE",
                    };
                    if let Some(info) = build_class_info_lenient(&folder, division) {
                        return Some(info);
                    }
                }
            }
        }
    }
    None
}

fn normalized_path(path: &Path) -> String {
    path.canonicalize()
        .unwrap_or_else(|_| path.to_path_buf())
        .to_string_lossy()
        .to_lowercase()
}

/// Lit le coefficient en cellule C4 du premier onglet d'un `.xlsx`.
pub fn read_coefficient_from_xlsx(path: &Path) -> Option<f64> {
    let mut workbook = open_workbook_auto(path).ok()?;
    let range = workbook.worksheet_range_at(0)?.ok()?;
    let cell = range.get_value((3, 2))?; // ligne 4, colonne C
    match cell {
        Data::Float(value) => Some(*value),
        Data::Int(value) => Some(*value as f64),
        Data::String(value) => value.trim().replace(',', ".").parse().ok(),
        Data::DateTime(value) => Some(value.as_f64()),
        _ => None,
    }
}

/// Liste les dossiers de classe réels (hors `data`, `bulletin`, etc.).
pub fn list_class_dirs(root: Option<&Path>) -> Vec<PathBuf> {
    let bulletin_root = find_bulletin_root(root);
    let mut out = Vec::new();
    let mut seen = HashSet::new();
    for division in DIVISIONS {
        for div_name in division_candidates(division) {
            let div_dir = bulletin_root.join(div_name);
            if !div_dir.is_dir() {
                continue;
            }
            let Ok(entries) = fs::read_dir(&div_dir) else {
                continue;
            };
            for entry in entries.filter_map(|e| e.ok()) {
                let path = entry.path();
                if !path.is_dir() {
                    continue;
                }
                if matches!(
                    class_dir_name(&path).to_lowercase().as_str(),
                    "data" | "bulletin" | ".backups" | "exports"
                ) {
                    continue;
                }
                let canonical = path.canonicalize().unwrap_or_else(|_| path.clone());
                if seen.insert(canonical) {
                    out.push(path);
                }
            }
        }
    }
    out.sort_by_key(|p| p.to_string_lossy().to_lowercase());
    out
}

/// Supprime une classe et son contenu (même comportement que Python).
pub fn delete_single_class(name: &str, root: Option<&Path>) -> Result<bool> {
    let Some(info) = discover_class(name, root) else {
        return Ok(false);
    };
    if info.folder.exists() {
        fs::remove_dir_all(&info.folder)
            .with_context(|| format!("Suppression de {}", info.folder.display()))?;
    }
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalize_removes_accents_and_punctuation() {
        assert_eq!(normalize("  Mathématiques  "), "mathematiques");
        assert_eq!(normalize("M.J 1"), "m j 1");
        assert_eq!(normalize("Nom et Prénoms"), "nom et prenoms");
    }

    #[test]
    fn prettify_matches_python_examples() {
        assert_eq!(prettify_class_name("3EME1"), "3ème 1");
        assert_eq!(prettify_class_name("1ereLI"), "1ère LI");
        assert_eq!(prettify_class_name("2ndeII"), "2nde II");
        assert_eq!(prettify_class_name("TAI"), "TAI");
    }

    #[test]
    fn philosophy_is_excluded_outside_premiere_and_terminale() {
        assert!(is_subject_excluded("Philosophie", "2ndei"));
        assert!(is_subject_excluded("Philosophie", "3eme1"));
        assert!(!is_subject_excluded("Philosophie", "1ereli"));
        assert!(!is_subject_excluded("Philosophie", "tai"));
    }

    #[test]
    fn normalize_class_name_matches_python_examples() {
        assert_eq!(normalize_class_name("6e I"), "6EME1");
        assert_eq!(normalize_class_name("6ème 2"), "6EME2");
        assert_eq!(normalize_class_name("3e I"), "3EME1");
        assert_eq!(normalize_class_name("1ère L1"), "1EREL1");
        assert_eq!(normalize_class_name("2nde II"), "2NDE2");
        // Abréviations lycée malgaches.
        assert_eq!(normalize_class_name("1L1"), "1EREL1");
        assert_eq!(normalize_class_name("1ES"), "1ERES");
        assert_eq!(normalize_class_name("1°L1"), "1EREL1");
        // Romain → arabe, et variante « 6eme 1 ».
        assert_eq!(normalize_class_name("TAI"), "TA1");
        assert_eq!(normalize_class_name("TAII"), "TA2");
        assert_eq!(normalize_class_name("1ERELII"), "1EREL2");
        assert_eq!(normalize_class_name("6EMEI"), "6EME1");
        assert_eq!(normalize_class_name("6eme 1"), "6EME1");
        assert_eq!(normalize_class_name("6 I"), "6EME1");
        assert_eq!(normalize_class_name("  T.A  "), "TA");
        assert_eq!(normalize_class_name(""), "");
    }

    #[test]
    fn extract_level_key_matches_python_examples() {
        assert_eq!(extract_level_key("6EME1"), "6EME");
        assert_eq!(extract_level_key("3EME1"), "3EME");
        assert_eq!(extract_level_key("1ERELI"), "1ERE");
        assert_eq!(extract_level_key("2NDEA"), "2NDE");
        assert_eq!(extract_level_key("TA1"), "TLE");
        assert_eq!(extract_level_key("TD"), "TLE");
        assert_eq!(extract_level_key("TLE2"), "TLE");
        assert_eq!(extract_level_key("CM2"), "CM2");
        // Pas de clé pour la maternelle (comme en Python) ni pour un
        // nom non reconnu.
        assert_eq!(extract_level_key("PS"), "");
        assert_eq!(extract_level_key("IA"), "");
        assert_eq!(extract_level_key(""), "");
    }

    #[test]
    fn subject_aliases_link_base_and_file_names() {
        assert_eq!(
            subject_name_aliases("Éducation à la Vie"),
            vec!["education a la vie", "eva"]
        );
        assert_eq!(
            subject_name_aliases("EVA"),
            vec!["eva", "education a la vie"]
        );
        assert_eq!(
            subject_name_aliases("Histo-geo"),
            vec!["histo geo", "histoire geographie"]
        );
        assert_eq!(subject_name_aliases("Mathématiques"), vec!["mathematiques"]);
    }
}
