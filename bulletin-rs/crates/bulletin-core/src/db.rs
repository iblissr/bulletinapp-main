//! Couche de persistance SQLite.
//!
//! Le schéma, les paramètres par défaut et les règles de pré-remplissage
//! sont identiques à l'application Python d'origine afin de pouvoir
//! ouvrir les mêmes bases sans migration.

use crate::models::{Student, Subject};
use crate::workspace::{
    discover_class_by_db_path, extract_level_key, normalize_class_name,
    read_coefficient_from_xlsx, subject_name_aliases,
};
use anyhow::{Context, Result, anyhow};
use chrono::Local;
use rusqlite::{Connection, OptionalExtension, params};
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

pub const DEFAULT_DB_RELATIVE: &str = "data/bulletin.db";

pub const SCHEMA: &str = r#"
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS subjects (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    coeff     REAL NOT NULL DEFAULT 1,
    teacher   TEXT DEFAULT '',
    position  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS students (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    num       INTEGER NOT NULL,
    matricule TEXT DEFAULT '',
    nom       TEXT NOT NULL,
    prenoms   TEXT DEFAULT '',
    genre      TEXT DEFAULT '',
    naissance  TEXT DEFAULT '',
    UNIQUE(num)
);

CREATE TABLE IF NOT EXISTS grades (
    student_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    exam_num   INTEGER NOT NULL CHECK (exam_num BETWEEN 1 AND 6),
    value      REAL,
    PRIMARY KEY (student_id, subject_id, exam_num),
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);
"#;

pub const DEFAULT_SETTINGS: &[(&str, &str)] = &[
    ("etablissement", "Lycée Saint Joseph"),
    ("directeur", "Directeur"),
    ("annee_scolaire", "2025-2026"),
    ("classe", "1ERELI"),
    ("nb_examens", "6"),
    ("effectif", "45"),
    ("nb_filles", ""),
    ("nb_garcons", ""),
    ("nb_min_examens", "3"),
    ("prof_principal", ""),
    ("coeff_default", "1"),
    ("logo_path", ""),
    ("accent_color", ""),
    ("export_profs_path", ""),
    ("export_totalisation_path", ""),
    ("export_moyennes_path", ""),
    ("export_cr_path", ""),
];

/// Collège (et repli niveau inconnu) — tableau 2026-09-20.
pub const COEFFS_COLLEGE: &[(&str, f64)] = &[
    ("Religion", 1.0),
    ("Éducation à la Vie", 1.0),
    ("Malagasy", 3.0),
    ("Français", 3.0),
    ("Anglais", 2.0),
    ("Histoire-Géographie", 3.0),
    ("Mathématiques", 3.0),
    ("SVT", 3.0),
    ("Physique-chimie", 3.0),
    ("EPS", 1.0),
];

/// Lycée — groupe 1 : 1ère L (1EREL1, 1EREL2) + TA1/TA2.
/// Philosophie vaut 2 ici, portée à **4** pour TA1/TA2 par
/// [`CLASS_COEFF_OVERRIDES`].
pub const COEFFS_LYCEE_G1: &[(&str, f64)] = &[
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
];

/// Lycée — groupe 2 : 1ère S (1ERES) et TD (groupe scientifique).
pub const COEFFS_LYCEE_G2: &[(&str, f64)] = &[
    ("Religion", 1.0),
    ("Éducation à la Vie", 1.0),
    ("Malagasy", 3.0),
    ("Français", 2.0),
    ("Anglais", 1.0),
    ("Histoire-Géographie", 2.0),
    ("Mathématiques", 4.0),
    ("SVT", 4.0),
    ("Physique-chimie", 4.0),
    ("EPS", 1.0),
    ("Philosophie", 2.0),
];

/// Lycée — groupe 3 : 2nde (2NDE1, 2NDE2) — pas de Philosophie.
pub const COEFFS_LYCEE_G3: &[(&str, f64)] = &[
    ("Religion", 1.0),
    ("Éducation à la Vie", 1.0),
    ("Malagasy", 3.0),
    ("Français", 3.0),
    ("Anglais", 2.0),
    ("Histoire-Géographie", 3.0),
    ("Mathématiques", 3.0),
    ("SVT", 3.0),
    ("Physique-chimie", 3.0),
    ("EPS", 1.0),
];

// Niveaux Primaire / Maternelle : matières reprises telles quelles
// dans le catalogue de la section (pas de tableau « par classe »).
const PRIM_LEVELS: [&str; 5] = ["CP", "CE1", "CE2", "CM1", "CM2"];
const MATER_LEVELS: [&str; 3] = ["PS", "MS", "GS"];

/// Version du tableau de coefficients appliqué aux bases existantes.
pub const COEFF_DEFAULTS_VERSION: &str = "2026-09-20";

/// Surcharges de coefficients par classe (ex. Philosophie 4 en TA1/TA2).
/// `(préfixe du nom de classe, matière normalisée, coefficient)`.
pub const CLASS_COEFF_OVERRIDES: &[(&str, &str, f64)] = &[("TA", "philosophie", 4.0)];

/// Numéro de sous-classe : `"2"` → 2, `"II"` → 2, `""` → 1.
fn subclass_index(suffix: &str) -> i64 {
    let s = suffix.trim().to_uppercase();
    if s.is_empty() {
        return 1;
    }
    if let Ok(value) = s.parse::<i64>() {
        return value;
    }
    let mut total = 0i64;
    let mut previous = 0i64;
    for ch in s.chars().rev() {
        let value = match ch {
            'I' => 1,
            'V' => 5,
            'X' => 10,
            _ => return 1, // suffixe non reconnu (A, B…) → première classe
        };
        total += if value < previous { -value } else { value };
        previous = previous.max(value);
    }
    if total == 0 {
        1
    } else {
        total
    }
}

/// Matières `(nom, coeff)` d'une section du catalogue.
fn section_subjects(section_key: &str) -> Vec<(&'static str, f64)> {
    crate::class_create::section(section_key)
        .map(|section| section.subjects.to_vec())
        .unwrap_or_default()
}

/// Collège : Physique-chimie = 3 en 3EME1/3EME2/4EME1, **2** ailleurs
/// (4EME2 → 6EME3).
fn college_subjects(class_name: &str, level_key: &str) -> Vec<(&'static str, f64)> {
    let pc = if matches!(level_key, "5EME" | "6EME") {
        2.0
    } else if level_key == "4EME" {
        let suffix = class_name.get(level_key.len()..).unwrap_or("");
        if subclass_index(suffix) == 1 {
            3.0
        } else {
            2.0
        }
    } else {
        3.0 // 3EME (et repli)
    };
    if pc == 3.0 {
        return COEFFS_COLLEGE.to_vec();
    }
    COEFFS_COLLEGE
        .iter()
        .map(|(name, coeff)| {
            (
                *name,
                if *name == "Physique-chimie" { pc } else { *coeff },
            )
        })
        .collect()
}

/// 1ère : groupe scientifique (S) ou littéraire/TA (défaut).
fn first_year_group(class_name: &str) -> Vec<(&'static str, f64)> {
    let suffix = class_name
        .strip_prefix("1ERE")
        .or_else(|| class_name.get(1..))
        .unwrap_or("");
    if suffix.starts_with("S") {
        COEFFS_LYCEE_G2.to_vec()
    } else {
        COEFFS_LYCEE_G1.to_vec()
    }
}

/// Coefficient spécifique à une classe, ou `default`.
pub fn get_class_coeff(subject_name: &str, class_name: &str, default: f64) -> f64 {
    let subject = subject_name.trim().to_lowercase();
    let class = class_name.trim().to_uppercase();
    for (prefix, candidate, coeff) in CLASS_COEFF_OVERRIDES {
        if class.starts_with(prefix) && *candidate == subject {
            return *coeff;
        }
    }
    default
}

/// Philosophie n'est enseignée qu'en 1ère et en Terminale.
pub fn subject_allowed_for_level(subject_name: &str, level_key: &str) -> bool {
    if subject_name.trim().to_lowercase() != "philosophie" {
        return true;
    }
    matches!(
        level_key.trim().to_uppercase().as_str(),
        "1ERE" | "TLE"
    )
}

/// Matières et coefficients **par défaut** d'une classe, selon le tableau
/// de `memory/decisions/coefficients-par-classe.md`.
///
/// `level_key` (`"6EME"`, `"TLE"`…) peut être fourni pour éviter de le
/// recalculer ; sinon il est déduit de `class_name`.
pub fn get_class_defaults(class_name: &str, level_key: Option<&str>) -> Vec<(&'static str, f64)> {
    let raw = class_name;
    let normalized = normalize_class_name(raw);
    let name = if normalized.is_empty() {
        raw.trim().to_uppercase()
    } else {
        normalized
    };
    let level = match level_key.map(|key| key.trim().to_uppercase()) {
        Some(key) if !key.is_empty() => key,
        _ => extract_level_key(raw).to_uppercase(),
    };

    let base: Vec<(&'static str, f64)> = match level.as_str() {
        "2NDE" => COEFFS_LYCEE_G3.to_vec(),
        "1ERE" => first_year_group(&name),
        // TD → groupe scientifique, TA1/TA2 et le reste → groupe 1
        "TLE" => {
            if name.starts_with("TD") {
                COEFFS_LYCEE_G2.to_vec()
            } else {
                COEFFS_LYCEE_G1.to_vec()
            }
        }
        "3EME" | "4EME" | "5EME" | "6EME" => college_subjects(&name, &level),
        key if PRIM_LEVELS.contains(&key) => section_subjects("PRIM"),
        key if MATER_LEVELS.contains(&key) => section_subjects("MATER"),
        _ => COEFFS_COLLEGE.to_vec(), // niveau inconnu → repli Collège
    };

    base.into_iter()
        .map(|(name, coeff)| (name, get_class_coeff(name, raw, coeff)))
        .collect()
}

/// Voir [`get_class_defaults`] avec `level_key = None`.
pub fn class_defaults(class_name: &str) -> Vec<(&'static str, f64)> {
    get_class_defaults(class_name, None)
}

/// `{nom normalisé ou alias: coefficient}` pour une classe.
fn defaults_by_norm(class_name: &str, level_key: Option<&str>) -> HashMap<String, f64> {
    let mut out: HashMap<String, f64> = HashMap::new();
    for (name, coeff) in get_class_defaults(class_name, level_key) {
        for alias in subject_name_aliases(name) {
            out.entry(alias).or_insert(coeff);
        }
    }
    out
}

/// Coefficient par défaut de `subject_name` pour `class_name`.
///
/// `None` si la matière n'existe pas dans le tableau de la classe.
/// Les alias (`Histo-geo` ↔ `Histoire-Géographie`,
/// `EVA` ↔ `Éducation à la Vie`) sont pris en compte.
pub fn class_default_coeff(
    subject_name: &str,
    class_name: &str,
    level_key: Option<&str>,
) -> Option<f64> {
    let defaults = defaults_by_norm(class_name, level_key);
    subject_name_aliases(subject_name)
        .into_iter()
        .find_map(|alias| defaults.get(&alias).copied())
}

/// Réécrit les coefficients d'une classe depuis le tableau.
///
/// Les matières absentes du tableau (ajoutées à la main) sont laissées
/// telles quelles. Retourne le nombre de mises à jour.
fn apply_class_coeff_defaults(tx: &rusqlite::Transaction<'_>, class_name: &str) -> Result<usize> {
    let defaults = defaults_by_norm(class_name, None);
    if defaults.is_empty() {
        return Ok(0);
    }
    let rows: Vec<(i64, String, f64)> = {
        let mut stmt = tx.prepare("SELECT id, name, coeff FROM subjects")?;
        let mapped = stmt
            .query_map([], |row| {
                Ok((row.get(0)?, row.get(1)?, row.get::<_, f64>(2)?))
            })?
            .collect::<rusqlite::Result<_>>()?;
        mapped
    };
    let mut updated = 0;
    for (id, name, coeff) in rows {
        let target = subject_name_aliases(&name)
            .into_iter()
            .find_map(|alias| defaults.get(&alias).copied());
        match target {
            Some(target) if coeff != target => {
                tx.execute("UPDATE subjects SET coeff=? WHERE id=?", params![target, id])?;
                updated += 1;
            }
            _ => {}
        }
    }
    Ok(updated)
}

/// Applique le tableau de coefficients à une base existante, une seule
/// fois (drapeau `coeff_defaults_version` dans `settings`).
///
/// Les bases dont le dossier de classe n'est pas détectable sont
/// revérifiées à la prochaine ouverture.
fn migrate_class_coefficients(
    tx: &rusqlite::Transaction<'_>,
    db_path: &Path,
) -> Result<bool> {
    let current: Option<String> = tx
        .query_row(
            "SELECT value FROM settings WHERE key='coeff_defaults_version'",
            [],
            |row| row.get(0),
        )
        .optional()?;
    if current.as_deref() == Some(COEFF_DEFAULTS_VERSION) {
        return Ok(false);
    }
    let Some(class) = discover_class_by_db_path(db_path) else {
        return Ok(false);
    };
    apply_class_coeff_defaults(tx, &class.name)?;
    tx.execute(
        "INSERT INTO settings(key,value) VALUES('coeff_defaults_version',?) \
         ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        params![COEFF_DEFAULTS_VERSION],
    )?;
    Ok(true)
}

/// Façade SQLite de l'application.
pub struct Database {
    conn: Connection,
    path: PathBuf,
}

impl Database {
    /// Ouvre (ou crée) une base. `None` utilise `$BULLETIN_DB` ou
    /// `data/bulletin.db` dans le dossier courant.
    pub fn open(path: Option<&Path>) -> Result<Self> {
        let path = match path {
            Some(path) => path.to_path_buf(),
            None => default_path(),
        };
        if let Some(parent) = path.parent() {
            if !parent.as_os_str().is_empty() {
                fs::create_dir_all(parent)
                    .with_context(|| format!("Création du dossier {}", parent.display()))?;
            }
        }
        let conn = Connection::open(&path)
            .with_context(|| format!("Ouverture de la base {}", path.display()))?;
        Self::from_connection(conn, path)
    }

    /// Base en mémoire (tests et aperçus).
    pub fn open_in_memory() -> Result<Self> {
        let conn = Connection::open_in_memory()?;
        Self::from_connection(conn, PathBuf::from(":memory:"))
    }

    fn from_connection(conn: Connection, path: PathBuf) -> Result<Self> {
        conn.busy_timeout(std::time::Duration::from_secs(10))?;
        conn.execute_batch("PRAGMA foreign_keys = ON;")?;
        let _ = conn.execute_batch("PRAGMA journal_mode = WAL;");
        let mut db = Self { conn, path };
        db.conn.execute_batch(SCHEMA)?;
        db.init_defaults()?;
        Ok(db)
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn path_string(&self) -> String {
        self.path.to_string_lossy().to_string()
    }

    pub fn connection(&self) -> &Connection {
        &self.conn
    }

    // ------------------------------------------------------------------
    //  Initialisation
    // ------------------------------------------------------------------
    fn init_defaults(&mut self) -> Result<()> {
        let path = self.path.clone();
        let tx = self.conn.transaction()?;

        // Micro-migration historique : Réligion → Religion.
        tx.execute(
            "UPDATE subjects SET name = 'Religion' \
             WHERE name IN ('Réligion', 'réligion', 'RELIGION')",
            [],
        )?;

        for (key, value) in DEFAULT_SETTINGS {
            tx.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)",
                params![key, value],
            )?;
        }

        // Corrige le nom de classe par défaut à partir du dossier réel.
        let current_class: Option<String> = tx
            .query_row("SELECT value FROM settings WHERE key='classe'", [], |row| {
                row.get(0)
            })
            .optional()?;
        if matches!(
            current_class.as_deref(),
            Some("1ERELI") | Some("1ERE L1") | Some("")
        ) {
            if let Some(class) = discover_class_by_db_path(&self.path) {
                tx.execute(
                    "UPDATE settings SET value=? WHERE key='classe'",
                    params![class.name],
                )?;
            }
        }

        // --- v1.2 : coefficients par classe (tableau 2026-09-20) ---
        // Appliqué AVANT le seed : sur une base vide il n'y a rien à
        // réécrire, et le seed garde ainsi la priorité aux .xlsx.
        migrate_class_coefficients(&tx, &path)?;

        let subject_count: i64 =
            tx.query_row("SELECT COUNT(*) FROM subjects", [], |row| row.get(0))?;
        if subject_count == 0 {
            seed_subjects(&tx, &path)?;
        }

        tx.commit()?;
        Ok(())
    }

    // ------------------------------------------------------------------
    //  Settings
    // ------------------------------------------------------------------
    pub fn get_setting(&self, key: &str, default: &str) -> String {
        self.conn
            .query_row(
                "SELECT value FROM settings WHERE key=?",
                params![key],
                |row| row.get::<_, Option<String>>(0),
            )
            .optional()
            .ok()
            .flatten()
            .flatten()
            .unwrap_or_else(|| default.to_string())
    }

    pub fn get_setting_int(&self, key: &str, default: i64) -> i64 {
        self.get_setting(key, &default.to_string())
            .parse::<f64>()
            .map(|v| v as i64)
            .unwrap_or(default)
    }

    pub fn set_setting(&self, key: &str, value: &str) -> Result<()> {
        self.conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) \
             ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            params![key, value],
        )?;
        Ok(())
    }

    pub fn all_settings(&self) -> Result<HashMap<String, String>> {
        let mut stmt = self.conn.prepare("SELECT key,value FROM settings")?;
        let rows = stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, Option<String>>(1)?))
        })?;
        let mut out = HashMap::new();
        for row in rows {
            let (key, value) = row?;
            out.insert(key, value.unwrap_or_default());
        }
        Ok(out)
    }

    // ------------------------------------------------------------------
    //  Subjects
    // ------------------------------------------------------------------
    pub fn list_subjects(&self) -> Result<Vec<Subject>> {
        let mut stmt = self
            .conn
            .prepare("SELECT id,name,coeff,teacher,position FROM subjects ORDER BY position,id")?;
        let rows = stmt.query_map([], |row| {
            Ok(Subject {
                id: row.get(0)?,
                name: row.get(1)?,
                coeff: row.get(2)?,
                teacher: row.get::<_, Option<String>>(3)?.unwrap_or_default(),
                position: row.get(4)?,
            })
        })?;
        rows.collect::<rusqlite::Result<Vec<_>>>()
            .map_err(Into::into)
    }

    pub fn add_subject(&self, name: &str, coeff: f64, teacher: &str) -> Result<i64> {
        let position: i64 = self.conn.query_row(
            "SELECT COALESCE(MAX(position),-1)+1 FROM subjects",
            [],
            |row| row.get(0),
        )?;
        self.conn.execute(
            "INSERT INTO subjects(name,coeff,teacher,position) VALUES(?,?,?,?)",
            params![name, coeff, teacher, position],
        )?;
        Ok(self.conn.last_insert_rowid())
    }

    pub fn clear_subjects(&self) -> Result<()> {
        self.conn.execute("DELETE FROM subjects", [])?;
        Ok(())
    }

    pub fn set_subjects(&self, subjects: &[(String, f64, String)]) -> Result<()> {
        let tx = self.conn.unchecked_transaction()?;
        tx.execute("DELETE FROM subjects", [])?;
        for (position, (name, coeff, teacher)) in subjects.iter().enumerate() {
            tx.execute(
                "INSERT INTO subjects(name,coeff,teacher,position) VALUES(?,?,?,?)",
                params![name, coeff, teacher, position as i64],
            )?;
        }
        tx.commit()?;
        Ok(())
    }

    pub fn update_subject(&self, id: i64, name: &str, coeff: f64, teacher: &str) -> Result<()> {
        self.conn.execute(
            "UPDATE subjects SET name=?, coeff=?, teacher=? WHERE id=?",
            params![name, coeff, teacher, id],
        )?;
        Ok(())
    }

    pub fn delete_subject(&self, id: i64) -> Result<()> {
        let tx = self.conn.unchecked_transaction()?;
        tx.execute("DELETE FROM subjects WHERE id=?", params![id])?;
        tx.execute("DELETE FROM grades WHERE subject_id=?", params![id])?;
        tx.commit()?;
        Ok(())
    }

    // ------------------------------------------------------------------
    //  Students
    // ------------------------------------------------------------------
    pub fn list_students(&self) -> Result<Vec<Student>> {
        let mut stmt = self.conn.prepare(
            "SELECT id,num,matricule,nom,prenoms,genre,naissance FROM students ORDER BY num",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(Student {
                id: row.get(0)?,
                num: row.get(1)?,
                matricule: row.get::<_, Option<String>>(2)?.unwrap_or_default(),
                nom: row.get(3)?,
                prenoms: row.get::<_, Option<String>>(4)?.unwrap_or_default(),
                genre: row.get::<_, Option<String>>(5)?.unwrap_or_default(),
                naissance: row.get::<_, Option<String>>(6)?.unwrap_or_default(),
            })
        })?;
        rows.collect::<rusqlite::Result<Vec<_>>>()
            .map_err(Into::into)
    }

    pub fn add_student(
        &self,
        num: i64,
        nom: &str,
        prenoms: &str,
        matricule: &str,
        genre: &str,
        naissance: &str,
    ) -> Result<i64> {
        self.conn.execute(
            "INSERT INTO students(num,matricule,nom,prenoms,genre,naissance) VALUES(?,?,?,?,?,?)",
            params![num, matricule, nom, prenoms, genre, naissance],
        )?;
        Ok(self.conn.last_insert_rowid())
    }

    pub fn update_student(
        &self,
        id: i64,
        num: i64,
        nom: &str,
        prenoms: &str,
        matricule: &str,
        genre: &str,
        naissance: &str,
    ) -> Result<()> {
        self.conn.execute(
            "UPDATE students SET num=?, nom=?, prenoms=?, matricule=?, genre=?, naissance=? WHERE id=?",
            params![num, nom, prenoms, matricule, genre, naissance, id],
        )?;
        Ok(())
    }

    pub fn delete_student(&self, id: i64) -> Result<()> {
        let tx = self.conn.unchecked_transaction()?;
        tx.execute("DELETE FROM students WHERE id=?", params![id])?;
        tx.execute("DELETE FROM grades WHERE student_id=?", params![id])?;
        tx.commit()?;
        Ok(())
    }

    /// Crée `count` élèves numérotés à partir de `start`, ignore les doublons.
    pub fn generate_students(&self, count: i64, start: i64) -> Result<usize> {
        let tx = self.conn.unchecked_transaction()?;
        let mut added = 0;
        for num in start..start + count {
            let result = tx.execute(
                "INSERT INTO students(num,nom) VALUES(?,?)",
                params![num, format!("Élève {num}")],
            );
            if result.is_ok() {
                added += 1;
            }
        }
        tx.commit()?;
        Ok(added)
    }

    /// Importe/actualise des élèves par leur numéro.
    pub fn bulk_upsert_students(&self, rows: &[Student]) -> Result<usize> {
        let tx = self.conn.unchecked_transaction()?;
        let mut count = 0;
        for student in rows {
            tx.execute(
                "INSERT INTO students(num,matricule,nom,prenoms,genre,naissance) \
                 VALUES(?,?,?,?,?,?) \
                 ON CONFLICT(num) DO UPDATE SET \
                 matricule=excluded.matricule, nom=excluded.nom, \
                 prenoms=excluded.prenoms, genre=excluded.genre, \
                 naissance=excluded.naissance",
                params![
                    student.num,
                    student.matricule,
                    student.nom,
                    student.prenoms,
                    student.genre,
                    student.naissance
                ],
            )?;
            count += 1;
        }
        tx.commit()?;
        Ok(count)
    }

    // ------------------------------------------------------------------
    //  Grades
    // ------------------------------------------------------------------
    pub fn get_grade(
        &self,
        student_id: i64,
        subject_id: i64,
        exam_num: i64,
    ) -> Result<Option<f64>> {
        self.conn
            .query_row(
                "SELECT value FROM grades WHERE student_id=? AND subject_id=? AND exam_num=?",
                params![student_id, subject_id, exam_num],
                |row| row.get::<_, Option<f64>>(0),
            )
            .optional()
            .map(|row| row.flatten())
            .map_err(Into::into)
    }

    pub fn get_grades_subject(&self, subject_id: i64) -> Result<HashMap<(i64, i64), f64>> {
        let mut stmt = self.conn.prepare(
            "SELECT student_id, exam_num, value FROM grades WHERE subject_id=? AND value IS NOT NULL",
        )?;
        let rows = stmt.query_map(params![subject_id], |row| {
            Ok((
                (row.get::<_, i64>(0)?, row.get::<_, i64>(1)?),
                row.get::<_, f64>(2)?,
            ))
        })?;
        let mut out = HashMap::new();
        for row in rows {
            let (key, value) = row?;
            out.insert(key, value);
        }
        Ok(out)
    }

    pub fn grades_for_exam(&self, exam_num: i64) -> Result<HashMap<i64, HashMap<i64, f64>>> {
        let mut stmt = self.conn.prepare(
            "SELECT student_id, subject_id, value FROM grades WHERE exam_num=? AND value IS NOT NULL",
        )?;
        let rows = stmt.query_map(params![exam_num], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, f64>(2)?,
            ))
        })?;
        let mut out: HashMap<i64, HashMap<i64, f64>> = HashMap::new();
        for row in rows {
            let (student_id, subject_id, value) = row?;
            out.entry(student_id).or_default().insert(subject_id, value);
        }
        Ok(out)
    }

    pub fn set_grade(
        &self,
        student_id: i64,
        subject_id: i64,
        exam_num: i64,
        value: Option<f64>,
    ) -> Result<()> {
        match value {
            None => {
                self.conn.execute(
                    "DELETE FROM grades WHERE student_id=? AND subject_id=? AND exam_num=?",
                    params![student_id, subject_id, exam_num],
                )?;
            }
            Some(value) => {
                self.conn.execute(
                    "INSERT INTO grades(student_id,subject_id,exam_num,value) VALUES(?,?,?,?) \
                     ON CONFLICT(student_id,subject_id,exam_num) DO UPDATE SET value=excluded.value",
                    params![student_id, subject_id, exam_num, value],
                )?;
            }
        }
        Ok(())
    }

    pub fn bulk_set_grades(&self, grades: &[(i64, i64, i64, f64)]) -> Result<usize> {
        let tx = self.conn.unchecked_transaction()?;
        {
            let mut stmt = tx.prepare(
                "INSERT INTO grades(student_id,subject_id,exam_num,value) VALUES(?,?,?,?) \
                 ON CONFLICT(student_id,subject_id,exam_num) DO UPDATE SET value=excluded.value",
            )?;
            for (student_id, subject_id, exam_num, value) in grades {
                stmt.execute(params![student_id, subject_id, exam_num, value])?;
            }
        }
        tx.commit()?;
        Ok(grades.len())
    }

    pub fn clear_grades(&self) -> Result<()> {
        self.conn.execute("DELETE FROM grades", [])?;
        Ok(())
    }

    pub fn clear_grades_subject(&self, subject_id: i64) -> Result<usize> {
        let count = self
            .conn
            .execute("DELETE FROM grades WHERE subject_id=?", params![subject_id])?;
        Ok(count)
    }

    pub fn count_students(&self) -> Result<i64> {
        Ok(self
            .conn
            .query_row("SELECT COUNT(*) FROM students", [], |row| row.get(0))?)
    }

    pub fn count_subjects(&self) -> Result<i64> {
        Ok(self
            .conn
            .query_row("SELECT COUNT(*) FROM subjects", [], |row| row.get(0))?)
    }

    pub fn count_grades(&self) -> Result<i64> {
        Ok(self
            .conn
            .query_row("SELECT COUNT(*) FROM grades", [], |row| row.get(0))?)
    }

    // ------------------------------------------------------------------
    //  Resets
    // ------------------------------------------------------------------
    pub fn reset_all(&mut self, keep_settings: bool) -> Result<()> {
        {
            let tx = self.conn.transaction()?;
            tx.execute("DELETE FROM grades", [])?;
            tx.execute("DELETE FROM students", [])?;
            tx.execute(
                "DELETE FROM sqlite_sequence WHERE name IN ('students','grades')",
                [],
            )?;
            if !keep_settings {
                tx.execute("DELETE FROM settings", [])?;
            }
            tx.execute("DELETE FROM subjects", [])?;
            tx.execute("DELETE FROM sqlite_sequence WHERE name='subjects'", [])?;
            tx.commit()?;
        }
        self.init_defaults()?;
        Ok(())
    }

    pub fn wipe_all_data(&mut self, keep_settings: bool) -> Result<()> {
        {
            let tx = self.conn.transaction()?;
            tx.execute("DELETE FROM grades", [])?;
            tx.execute("DELETE FROM students", [])?;
            tx.execute(
                "DELETE FROM sqlite_sequence WHERE name IN ('students','grades')",
                [],
            )?;
            if !keep_settings {
                tx.execute("DELETE FROM settings", [])?;
            }
            tx.execute("DELETE FROM subjects", [])?;
            tx.execute("DELETE FROM sqlite_sequence WHERE name='subjects'", [])?;
            tx.commit()?;
        }
        self.init_defaults()?;
        Ok(())
    }

    // ------------------------------------------------------------------
    //  Backups
    // ------------------------------------------------------------------
    /// Sauvegarde horodatée dans `<db_dir>/.backups/`, rotation `keep`.
    pub fn backup(&self, keep: usize) -> Result<Option<PathBuf>> {
        if self.path.as_os_str() == ":memory:" || !self.path.exists() {
            return Ok(None);
        }
        let backup_dir = self
            .path
            .parent()
            .unwrap_or(Path::new("."))
            .join(".backups");
        fs::create_dir_all(&backup_dir)?;
        let stem = self
            .path
            .file_stem()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_else(|| "bulletin".into());
        let ts = Local::now().format("%Y%m%d-%H%M%S").to_string();
        let mut target = backup_dir.join(format!("{stem}.{ts}.bak"));
        let mut counter = 2;
        while target.exists() && counter <= 100 {
            target = backup_dir.join(format!("{stem}.{ts}_{counter}.bak"));
            counter += 1;
        }
        self.backup_database(&target)?;

        let mut backups: Vec<PathBuf> = fs::read_dir(&backup_dir)?
            .filter_map(|entry| entry.ok())
            .map(|entry| entry.path())
            .filter(|path| {
                path.extension().map(|e| e == "bak").unwrap_or(false)
                    && path
                        .file_name()
                        .map(|n| n.to_string_lossy().starts_with(&format!("{stem}.")))
                        .unwrap_or(false)
            })
            .collect();
        backups.sort_by_key(|p| fs::metadata(p).and_then(|m| m.modified()).ok());
        backups.reverse();
        for old in backups.into_iter().skip(keep) {
            let _ = fs::remove_file(old);
        }
        Ok(Some(target))
    }

    /// Copie cohérente via l'API SQLite.
    pub fn backup_database(&self, target: &Path) -> Result<PathBuf> {
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent)?;
        }
        let mut destination = Connection::open(target)?;
        let backup = rusqlite::backup::Backup::new(&self.conn, &mut destination)?;
        backup.run_to_completion(5, std::time::Duration::from_millis(50), None)?;
        Ok(target.to_path_buf())
    }

    /// Sauvegarde manuelle avec préfixe (`before_replace`, `avant_reset`…).
    pub fn create_backup(&self, prefix: &str) -> Result<Option<PathBuf>> {
        if self.path.as_os_str() == ":memory:" || !self.path.exists() {
            return Ok(None);
        }
        let backup_dir = self
            .path
            .parent()
            .unwrap_or(Path::new("."))
            .join(".backups");
        fs::create_dir_all(&backup_dir)?;
        let ts = Local::now().format("%Y%m%d-%H%M%S").to_string();
        let base = if prefix.is_empty() {
            ts.clone()
        } else {
            format!("{prefix}_{ts}")
        };
        let mut target = backup_dir.join(format!("{base}.bak"));
        let mut counter = 2;
        while target.exists() && counter <= 100 {
            target = backup_dir.join(format!("{base}_{counter}.bak"));
            counter += 1;
        }
        self.backup_database(&target)?;
        Ok(Some(target))
    }

    pub fn list_backups(&self) -> Result<Vec<PathBuf>> {
        if self.path.as_os_str() == ":memory:" {
            return Ok(Vec::new());
        }
        let backup_dir = self
            .path
            .parent()
            .unwrap_or(Path::new("."))
            .join(".backups");
        if !backup_dir.is_dir() {
            return Ok(Vec::new());
        }
        let mut backups: Vec<PathBuf> = fs::read_dir(&backup_dir)?
            .filter_map(|entry| entry.ok())
            .map(|entry| entry.path())
            .filter(|path| path.extension().map(|e| e == "bak").unwrap_or(false))
            .collect();
        backups.sort_by_key(|p| fs::metadata(p).and_then(|m| m.modified()).ok());
        backups.reverse();
        Ok(backups)
    }

    pub fn delete_backup(&self, path: &Path) -> bool {
        fs::remove_file(path).is_ok()
    }

    /// Vérifie qu'un fichier est une base SQLite saine.
    pub fn validate_sqlite_file(path: &Path) -> bool {
        if !path.is_file() {
            return false;
        }
        let Ok(conn) = Connection::open_with_flags(
            path,
            rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_URI,
        ) else {
            return false;
        };
        conn.query_row("PRAGMA integrity_check", [], |row| row.get::<_, String>(0))
            .map(|value| value.eq_ignore_ascii_case("ok"))
            .unwrap_or(false)
    }

    /// Remplace la base courante après une sauvegarde automatique.
    pub fn replace_database(&mut self, source: &Path) -> Result<Option<PathBuf>> {
        if !source.is_file() {
            return Err(anyhow!("Fichier introuvable : {}", source.display()));
        }
        let auto_backup = self.create_backup("before_replace")?;
        fs::copy(source, &self.path)?;
        self.conn = Connection::open(&self.path)?;
        self.conn.busy_timeout(std::time::Duration::from_secs(10))?;
        self.conn.execute_batch("PRAGMA foreign_keys = ON;")?;
        Ok(auto_backup)
    }

    /// Fusion additive d'une autre base (élèves, matières, notes).
    pub fn merge_database(&self, source: &Path) -> Result<MergeReport> {
        if !Self::validate_sqlite_file(source) {
            return Err(anyhow!(
                "Le fichier {} n'est pas une base SQLite valide",
                source.display()
            ));
        }
        let src = Connection::open(source)?;

        let mut report = MergeReport::default();
        let tx = self.conn.unchecked_transaction()?;

        // Matières : ajout par nom si absente.
        let mut local_subjects: HashMap<String, i64> = {
            let mut stmt = tx.prepare("SELECT id,name FROM subjects")?;
            let rows = stmt.query_map([], |row| {
                Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
            })?;
            let mut map = HashMap::new();
            for row in rows {
                let (id, name) = row?;
                map.insert(name.trim().to_lowercase(), id);
            }
            map
        };
        {
            let mut stmt = src.prepare("SELECT name,coeff,teacher FROM subjects")?;
            let rows = stmt.query_map([], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, f64>(1)?,
                    row.get::<_, Option<String>>(2)?.unwrap_or_default(),
                ))
            })?;
            for row in rows {
                let (name, coeff, teacher) = row?;
                let key = name.trim().to_lowercase();
                if !key.is_empty() && !local_subjects.contains_key(&key) {
                    tx.execute(
                        "INSERT INTO subjects(name,coeff,teacher) VALUES(?,?,?)",
                        params![name, coeff, teacher],
                    )?;
                    local_subjects.insert(key, tx.last_insert_rowid());
                    report.added_subjects += 1;
                }
            }
        }

        // Élèves : ajout par num.
        let mut local_students: HashMap<i64, i64> = {
            let mut stmt = tx.prepare("SELECT id,num FROM students")?;
            let rows =
                stmt.query_map([], |row| Ok((row.get::<_, i64>(0)?, row.get::<_, i64>(1)?)))?;
            let mut map = HashMap::new();
            for row in rows {
                let (id, num) = row?;
                map.insert(num, id);
            }
            map
        };
        {
            let mut stmt =
                src.prepare("SELECT num,matricule,nom,prenoms,genre,naissance FROM students")?;
            let rows = stmt.query_map([], |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, Option<String>>(1)?.unwrap_or_default(),
                    row.get::<_, String>(2)?,
                    row.get::<_, Option<String>>(3)?.unwrap_or_default(),
                    row.get::<_, Option<String>>(4)?.unwrap_or_default(),
                    row.get::<_, Option<String>>(5)?.unwrap_or_default(),
                ))
            })?;
            for row in rows {
                let (num, matricule, nom, prenoms, genre, naissance) = row?;
                if num <= 0 || local_students.contains_key(&num) {
                    report.skipped_students += 1;
                    continue;
                }
                tx.execute(
                    "INSERT INTO students(num,matricule,nom,prenoms,genre,naissance) VALUES(?,?,?,?,?,?)",
                    params![num, matricule, nom, prenoms, genre, naissance],
                )?;
                local_students.insert(num, tx.last_insert_rowid());
                report.added_students += 1;
            }
        }

        // Notes : remappées par num d'élève et nom de matière.
        {
            let mut stmt = src.prepare(
                "SELECT s.num, sub.name, g.exam_num, g.value \
                 FROM grades g \
                 JOIN students s ON g.student_id=s.id \
                 JOIN subjects sub ON g.subject_id=sub.id \
                 WHERE g.value IS NOT NULL",
            )?;
            let rows = stmt.query_map([], |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, f64>(3)?,
                ))
            })?;
            for row in rows {
                let (num, subject_name, exam_num, value) = row?;
                let Some(student_id) = local_students.get(&num) else {
                    continue;
                };
                let Some(subject_id) = local_subjects.get(&subject_name.trim().to_lowercase())
                else {
                    continue;
                };
                let exists: Option<i64> = tx
                    .query_row(
                        "SELECT 1 FROM grades WHERE student_id=? AND subject_id=? AND exam_num=?",
                        params![student_id, subject_id, exam_num],
                        |row| row.get(0),
                    )
                    .optional()?;
                if exists.is_none() {
                    tx.execute(
                        "INSERT INTO grades(student_id,subject_id,exam_num,value) VALUES(?,?,?,?)",
                        params![student_id, subject_id, exam_num, value],
                    )?;
                    report.added_grades += 1;
                }
            }
        }

        tx.commit()?;
        Ok(report)
    }
}

/// Pré-remplit la table `subjects` lors de la première ouverture d'une
/// classe. Priorité des coefficients :
/// 1. cellule **C4** des `.xlsx` du dossier classe
/// 2. tableau des coefficients de la classe ([`get_class_defaults`])
fn seed_subjects(tx: &rusqlite::Transaction<'_>, db_path: &Path) -> Result<()> {
    let Some(class) = discover_class_by_db_path(db_path) else {
        for (position, (name, coeff)) in COEFFS_COLLEGE.iter().enumerate() {
            tx.execute(
                "INSERT INTO subjects(name,coeff,teacher,position) VALUES(?,?,?,?)",
                params![*name, *coeff, "", position as i64],
            )?;
        }
        return Ok(());
    };

    let level = extract_level_key(&class.name);
    let defaults = get_class_defaults(&class.name, Some(&level));

    // 1) coefficients lus dans les `.xlsx` du dossier classe
    let mut subject_map: HashMap<String, f64> = HashMap::new();
    for path in &class.subject_files {
        let Some(stem) = path.file_stem() else {
            continue;
        };
        let Some(coeff) = read_coefficient_from_xlsx(path) else {
            continue;
        };
        for alias in subject_name_aliases(&stem.to_string_lossy()) {
            subject_map.entry(alias).or_insert(coeff);
        }
    }

    // 2) tableau de la classe, matières filtrées par niveau
    let mut rows: Vec<(String, f64)> = Vec::new();
    for (name, default_coeff) in defaults {
        if !subject_allowed_for_level(name, &level) {
            continue;
        }
        let mut coeff = default_coeff;
        for alias in subject_name_aliases(name) {
            if let Some(value) = subject_map.get(&alias) {
                coeff = *value;
                break;
            }
        }
        rows.push((name.to_string(), coeff));
    }

    for (position, (name, coeff)) in rows.into_iter().enumerate() {
        tx.execute(
            "INSERT INTO subjects(name,coeff,teacher,position) VALUES(?,?,?,?)",
            params![name, coeff, "", position as i64],
        )?;
    }
    Ok(())
}

#[derive(Debug, Default, Clone, serde::Serialize)]
pub struct MergeReport {
    pub added_students: usize,
    pub skipped_students: usize,
    pub added_grades: usize,
    pub added_subjects: usize,
}

/// Chemin par défaut de la base neutre.
pub fn default_path() -> PathBuf {
    if let Ok(path) = std::env::var("BULLETIN_DB") {
        if !path.trim().is_empty() {
            return PathBuf::from(path);
        }
    }
    PathBuf::from(DEFAULT_DB_RELATIVE)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn schema_and_defaults_are_created() {
        let db = Database::open_in_memory().unwrap();
        assert_eq!(db.count_subjects().unwrap(), 10);
        assert_eq!(db.count_students().unwrap(), 0);
        assert_eq!(db.get_setting("nb_examens", ""), "6");
        assert_eq!(db.get_setting("nb_min_examens", ""), "3");
    }

    /// Coefficient d'une matière dans le tableau retourné par
    /// [`get_class_defaults`].
    fn table_coeff(rows: &[(&str, f64)], subject: &str) -> Option<f64> {
        rows.iter()
            .find(|(name, _)| *name == subject)
            .map(|(_, coeff)| *coeff)
    }

    fn subject_coeff(db: &Database, name: &str) -> Option<f64> {
        db.list_subjects().ok()?.iter().find(|s| s.name == name).map(|s| s.coeff)
    }

    fn subject_id(db: &Database, name: &str) -> i64 {
        db.list_subjects()
            .unwrap()
            .iter()
            .find(|s| s.name == name)
            .map(|s| s.id)
            .unwrap_or_else(|| panic!("matière absente de la base : {name}"))
    }

    #[test]
    fn class_defaults_match_python_rules() {
        // 1ère L : Malagasy / Histoire-Géo à 4, Maths / PC / SVT à 2.
        // Nouvel ordre : Religion, Éducation à la Vie, Malagasy, Français, Anglais, Histoire-Géographie, Mathématiques, SVT, Physique-chimie, EPS, Philosophie
        assert_eq!(table_coeff(&class_defaults("1ERELI"), "Malagasy"), Some(4.0));
        assert_eq!(table_coeff(&class_defaults("1EREL1"), "Malagasy"), Some(4.0));
        assert_eq!(
            table_coeff(&class_defaults("1EREL1"), "Physique-chimie"),
            Some(2.0)
        );
        // 1ère S : groupe scientifique.
        assert_eq!(table_coeff(&class_defaults("1ERES"), "Histoire-Géographie"), Some(2.0));

        // Philosophie n'existe ni en 2nde ni au collège.
        for class in ["2NDE1", "2NDE2", "3EME1", "4EME1", "4EME2", "6EME3"] {
            assert!(
                class_defaults(class).iter().all(|(name, _)| *name != "Philosophie"),
                "{class} ne doit pas avoir de Philosophie"
            );
        }

        // Philosophie : 4 en TA1/TA2 (et T* commençant par TA), 2 ailleurs.
        for class in ["TA1", "TA2", "TAI", "TAII", "TALL", "TAD"] {
            assert_eq!(
                table_coeff(&class_defaults(class), "Philosophie"),
                Some(4.0),
                "Philosophie en {class}"
            );
        }
        for class in ["TD", "TLE", "1EREL1", "1EREL2"] {
            assert_eq!(
                table_coeff(&class_defaults(class), "Philosophie"),
                Some(2.0),
                "Philosophie en {class}"
            );
        }

        // Physique-chimie : 3 en 3EME1/3EME2/4EME1, 2 ailleurs (4EME2 → 6EME3).
        for class in ["3EME1", "3EME2", "4EME1"] {
            assert_eq!(
                table_coeff(&class_defaults(class), "Physique-chimie"),
                Some(3.0),
                "Physique-chimie en {class}"
            );
        }
        for class in ["4EME2", "5EME1", "6EME1", "6EME3"] {
            assert_eq!(
                table_coeff(&class_defaults(class), "Physique-chimie"),
                Some(2.0),
                "Physique-chimie en {class}"
            );
        }
    }

    #[test]
    fn class_default_coeff_honours_aliases_and_level_rules() {
        assert_eq!(class_default_coeff("EVA", "6EME3", None), Some(1.0));
        assert_eq!(
            class_default_coeff("Éducation à la Vie", "6EME3", None),
            Some(1.0)
        );
        assert_eq!(class_default_coeff("Histo-geo", "4EME1", None), Some(3.0));
        assert_eq!(
            class_default_coeff("Histoire-Géographie", "1EREL1", None),
            Some(4.0)
        );
        assert_eq!(class_default_coeff("Malagasy", "1ERES", None), Some(3.0));
        // Matière absente du tableau de la classe.
        assert_eq!(class_default_coeff("Philosophie", "2NDE1", None), None);

        assert!(subject_allowed_for_level("Philosophie", "1ERE"));
        assert!(subject_allowed_for_level("Philosophie", "TLE"));
        assert!(!subject_allowed_for_level("Philosophie", "2NDE"));
        assert!(!subject_allowed_for_level("Philosophie", "6EME"));
        assert!(subject_allowed_for_level("Mathématiques", "6EME"));
    }

    /// Ouvre une base dans un vrai dossier de classe et vérifie que le
    /// tableau 2026-09-20 s'applique : seed compris, réécriture des
    /// saisies manuelles, et drapeau `coeff_defaults_version` posé.
    #[test]
    fn coefficient_migration_applies_once_per_database() -> Result<()> {
        let dir = tempfile::tempdir().unwrap();
        // « TA9 » : nom volontairement absent de l'arborescence réelle
        // pour que la découverte pointe sur ce dossier temporaire.
        let class_dir = dir.path().join("LYCEE").join("TA9");
        fs::create_dir_all(class_dir.join("data")).unwrap();
        fs::create_dir_all(class_dir.join("bulletin")).unwrap();
        let db_path = class_dir.join("data").join("bulletin.db");

        let db = Database::open(Some(&db_path)).unwrap();
        assert_eq!(subject_coeff(&db, "Philosophie"), Some(4.0));
        assert_eq!(subject_coeff(&db, "Mathématiques"), Some(2.0));
        assert_eq!(
            db.get_setting("coeff_defaults_version", ""),
            COEFF_DEFAULTS_VERSION
        );

        // Saisie manuelle + drapeau retiré = base « à migrer ».
        db.update_subject(subject_id(&db, "Mathématiques"), "Mathématiques", 9.0, "")?;
        db.set_setting("coeff_defaults_version", "")?;
        drop(db);

        // La migration réécrit la saisie hors tableau…
        let db = Database::open(Some(&db_path))?;
        assert_eq!(subject_coeff(&db, "Mathématiques"), Some(2.0));
        assert_eq!(
            db.get_setting("coeff_defaults_version", ""),
            COEFF_DEFAULTS_VERSION
        );

        // …une seule fois : la nouvelle saisie survit à la réouverture.
        db.update_subject(subject_id(&db, "Mathématiques"), "Mathématiques", 9.0, "")?;
        drop(db);
        let db = Database::open(Some(&db_path))?;
        assert_eq!(subject_coeff(&db, "Mathématiques"), Some(9.0));
        Ok(())
    }

    #[test]
    fn grades_roundtrip_and_delete() {
        let db = Database::open_in_memory().unwrap();
        let student = db.add_student(1, "Rakoto", "Jean", "", "", "").unwrap();
        let subject = db.list_subjects().unwrap()[0].id;
        db.set_grade(student, subject, 1, Some(12.5)).unwrap();
        assert_eq!(db.get_grade(student, subject, 1).unwrap(), Some(12.5));
        db.set_grade(student, subject, 1, None).unwrap();
        assert_eq!(db.get_grade(student, subject, 1).unwrap(), None);
    }
}
