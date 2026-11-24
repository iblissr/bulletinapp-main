//! Synchronisation bidirectionnelle entre les fichiers `.xlsx` de
//! matières et la base SQLite d'une classe.

use crate::db::Database;
use crate::workspace::{ClassInfo, normalize, subject_name_aliases};
use anyhow::{Context, Result};
use calamine::{Data, Range, Reader, open_workbook_auto};
use chrono::{DateTime, Local};
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Default, serde::Serialize)]
pub struct SubjectSyncResult {
    pub subject_name: String,
    pub xlsx_path: Option<PathBuf>,
    pub matched: bool,
    pub notes_total: usize,
    pub notes_added: usize,
    pub notes_updated: usize,
    pub notes_unchanged: usize,
    pub rows_skipped: usize,
    pub students_added: usize,
    pub warnings: Vec<String>,
    pub errors: Vec<String>,
}

impl SubjectSyncResult {
    pub fn ok(&self) -> bool {
        self.matched && self.errors.is_empty()
    }

    pub fn summary_line(&self) -> String {
        if !self.matched {
            return format!("  ✕ {} : fichier .xlsx introuvable", self.subject_name);
        }
        if let Some(error) = self.errors.first() {
            return format!("  ⚠ {} : {error}", self.subject_name);
        }
        let mut parts = Vec::new();
        if self.students_added > 0 {
            parts.push(format!("+{} élève(s)", self.students_added));
        }
        parts.push(format!(
            "{} nouvelle(s), {} mise(s) à jour, {} inchangée(s)",
            self.notes_added, self.notes_updated, self.notes_unchanged
        ));
        format!("  ✓ {} : {}", self.subject_name, parts.join(", "))
    }
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct SyncReport {
    pub class_name: String,
    pub started_at: DateTime<Local>,
    pub finished_at: DateTime<Local>,
    pub subjects: Vec<SubjectSyncResult>,
}

impl SyncReport {
    pub fn total_added(&self) -> usize {
        self.subjects.iter().map(|s| s.notes_added).sum()
    }
    pub fn total_updated(&self) -> usize {
        self.subjects.iter().map(|s| s.notes_updated).sum()
    }
    pub fn total_unchanged(&self) -> usize {
        self.subjects.iter().map(|s| s.notes_unchanged).sum()
    }
    pub fn total_students_added(&self) -> usize {
        self.subjects.iter().map(|s| s.students_added).sum()
    }
    pub fn matched_count(&self) -> usize {
        self.subjects.iter().filter(|s| s.matched).count()
    }
    pub fn error_count(&self) -> usize {
        self.subjects
            .iter()
            .filter(|s| !s.errors.is_empty())
            .count()
    }
    pub fn duration_seconds(&self) -> f64 {
        (self.finished_at - self.started_at)
            .num_milliseconds()
            .max(0) as f64
            / 1000.0
    }

    pub fn summary(&self) -> String {
        let mut lines = vec![format!(
            "Synchronisation {} — {}/{} matière(s) en {:.2}s",
            self.class_name,
            self.matched_count(),
            self.subjects.len(),
            self.duration_seconds()
        )];
        lines.push(format!(
            "  +{} nouvelle(s), ~{} mise(s) à jour, ={} inchangée(s){}",
            self.total_added(),
            self.total_updated(),
            self.total_unchanged(),
            if self.total_students_added() > 0 {
                format!(", +{} élève(s)", self.total_students_added())
            } else {
                String::new()
            }
        ));
        lines.extend(self.subjects.iter().map(|s| s.summary_line()));
        lines.join("\n")
    }
}

#[derive(Debug, Clone)]
pub struct GradeImportRow {
    pub num: i64,
    pub exam_num: i64,
    pub value: f64,
    pub name: String,
}

/// Libellé d'examen : M.J 1, Compo 1, M.J 2, …
pub fn label_for_exam(n: i64) -> String {
    if n % 2 == 1 {
        format!("M.J {}", (n + 1) / 2)
    } else {
        format!("Compo {}", n / 2)
    }
}

fn exam_from_label(value: &str) -> Option<i64> {
    let norm = normalize(value);
    if norm.is_empty() {
        return None;
    }
    let direct = match norm.as_str() {
        "m j 1" | "mj 1" | "m j1" | "mj1" | "interro 1" => Some(1),
        "compo 1" | "comp 1" | "devoir 1" => Some(2),
        "m j 2" | "mj 2" | "m j2" | "mj2" | "interro 2" => Some(3),
        "compo 2" | "comp 2" | "devoir 2" => Some(4),
        "m j 3" | "mj 3" | "m j3" | "mj3" | "interro 3" => Some(5),
        "compo 3" | "comp 3" | "devoir 3" => Some(6),
        _ => None,
    };
    if direct.is_some() {
        return direct;
    }
    let re_mj = regex::Regex::new(r"^m\.?j\s*(\d+)$").ok()?;
    if let Some(caps) = re_mj.captures(&norm) {
        if let Ok(n) = caps[1].parse::<i64>() {
            if (1..=3).contains(&n) {
                return Some(2 * n - 1);
            }
        }
    }
    let re_compo = regex::Regex::new(r"^compo?\s*(\d+)$").ok()?;
    if let Some(caps) = re_compo.captures(&norm) {
        if let Ok(n) = caps[1].parse::<i64>() {
            if (1..=3).contains(&n) {
                return Some(2 * n);
            }
        }
    }
    None
}

fn data_to_string(value: &Data) -> String {
    match value {
        Data::Empty => String::new(),
        Data::String(s) => s.clone(),
        Data::Float(f) => {
            if f.fract() == 0.0 {
                format!("{f:.0}")
            } else {
                f.to_string()
            }
        }
        Data::Int(i) => i.to_string(),
        Data::Bool(b) => b.to_string(),
        Data::DateTime(dt) => dt.to_string(),
        Data::DurationIso(_) => String::new(),
        Data::Error(_) => String::new(),
        _ => String::new(),
    }
}

fn data_to_f64(value: &Data) -> Option<f64> {
    match value {
        Data::Float(f) => Some(*f),
        Data::Int(i) => Some(*i as f64),
        Data::String(s) => s.trim().replace(',', ".").parse().ok(),
        Data::Bool(b) => Some(if *b { 1.0 } else { 0.0 }),
        Data::DateTime(dt) => Some(dt.as_f64()),
        _ => None,
    }
}

fn find_header_row(range: &Range<Data>, max_scan: usize) -> usize {
    let mut best_row = 0;
    let mut best_score = 0;
    for (index, row) in range.rows().take(max_scan).enumerate() {
        let mut score = 0;
        for value in row {
            let norm = normalize(&data_to_string(value));
            if norm.is_empty() {
                continue;
            }
            if matches!(
                norm.as_str(),
                "num" | "numero" | "n" | "#" | "no" | "n°" | "nº"
            ) {
                score += 2;
            } else if exam_from_label(&norm).is_some() {
                score += 3;
            } else if is_name_label(&norm) {
                score += 1;
            }
        }
        if score > best_score {
            best_score = score;
            best_row = index;
        }
    }
    if best_score > 0 { best_row } else { 4 }
}

fn is_name_label(norm: &str) -> bool {
    matches!(
        norm,
        "nom et prenoms"
            | "nom prenoms"
            | "nometprenoms"
            | "nom"
            | "prenom"
            | "prenoms"
            | "full name"
            | "name"
            | "eleve"
            | "student name"
            | "nom complet"
    )
}

/// Lit un fichier `.xlsx` de notes.
pub fn read_grades_xlsx(path: &Path, nb_exams: i64) -> Result<(Vec<GradeImportRow>, Vec<String>)> {
    let mut workbook =
        open_workbook_auto(path).with_context(|| format!("Ouverture de {}", path.display()))?;
    let range = workbook
        .worksheet_range_at(0)
        .ok_or_else(|| anyhow::anyhow!("Aucune feuille dans {}", path.display()))?
        .map_err(|error| anyhow::anyhow!("Lecture de {} : {error}", path.display()))?;

    let header_index = find_header_row(&range, 10);
    let Some(header) = range.rows().nth(header_index) else {
        return Ok((Vec::new(), vec!["fichier vide".into()]));
    };

    let mut num_index: Option<usize> = None;
    let mut name_index: Option<usize> = None;
    let mut exam_cols: HashMap<i64, usize> = HashMap::new();
    for (index, cell) in header.iter().enumerate() {
        let norm = normalize(&data_to_string(cell));
        if num_index.is_none()
            && matches!(
                norm.as_str(),
                "num" | "numero" | "n" | "#" | "no" | "n°" | "nº"
            )
        {
            num_index = Some(index);
            continue;
        }
        if name_index.is_none() && is_name_label(&norm) {
            name_index = Some(index);
            continue;
        }
        if let Some(exam) = exam_from_label(&norm) {
            exam_cols.entry(exam).or_insert(index);
        }
    }

    let mut warnings = Vec::new();
    if num_index.is_none() {
        warnings.push("colonne 'Num' introuvable".into());
    }
    if name_index.is_none() {
        warnings.push(
            "colonne 'Nom' introuvable — les nouveaux élèves ne pourront pas être détectés".into(),
        );
    }
    for exam in 1..=nb_exams {
        if !exam_cols.contains_key(&exam) {
            warnings.push(format!("colonne {} introuvable", label_for_exam(exam)));
        }
    }

    let mut rows = Vec::new();
    for row in range.rows().skip(header_index + 1) {
        if row
            .iter()
            .all(|cell| matches!(cell, Data::Empty) || data_to_string(cell).trim().is_empty())
        {
            continue;
        }
        let Some(num_index) = num_index else {
            continue;
        };
        let Some(num_cell) = row.get(num_index) else {
            continue;
        };
        let Some(num) = data_to_f64(num_cell).map(|value| value as i64) else {
            continue;
        };
        let name = name_index
            .and_then(|index| row.get(index))
            .map(data_to_string)
            .unwrap_or_default()
            .trim()
            .to_string();
        for (exam_num, col_index) in &exam_cols {
            let Some(cell) = row.get(*col_index) else {
                continue;
            };
            let Some(value) = data_to_f64(cell) else {
                continue;
            };
            rows.push(GradeImportRow {
                num,
                exam_num: *exam_num,
                value,
                name: name.clone(),
            });
        }
    }

    Ok((rows, warnings))
}

fn subject_id_by_name(db: &Database, name: &str) -> Result<Option<i64>> {
    let target = normalize(name);
    Ok(db
        .list_subjects()?
        .into_iter()
        .find(|subject| normalize(&subject.name) == target)
        .map(|subject| subject.id))
}

/// Importe un fichier de notes dans une matière.
pub fn sync_subject_from_xlsx(
    db: &Database,
    subject_name: &str,
    xlsx_path: &Path,
) -> Result<SubjectSyncResult> {
    let mut result = SubjectSyncResult {
        subject_name: subject_name.to_string(),
        xlsx_path: Some(xlsx_path.to_path_buf()),
        matched: xlsx_path.is_file(),
        ..Default::default()
    };
    if !result.matched {
        return Ok(result);
    }

    let Some(subject_id) = subject_id_by_name(db, subject_name)? else {
        result.errors.push(format!(
            "Matière « {subject_name} » absente de la base. Ajoutez-la dans l'onglet Configuration."
        ));
        return Ok(result);
    };

    let nb_exams = db.get_setting_int("nb_examens", 6).clamp(1, 6);
    let (rows, warnings) = match read_grades_xlsx(xlsx_path, nb_exams) {
        Ok(value) => value,
        Err(error) => {
            result.errors.push(format!("lecture impossible : {error}"));
            return Ok(result);
        }
    };
    result.warnings = warnings;

    let mut num_to_id: HashMap<i64, i64> = db
        .list_students()?
        .into_iter()
        .map(|student| (student.num, student.id))
        .collect();
    let existing = db.get_grades_subject(subject_id)?;

    let mut to_write = Vec::new();
    for row in rows {
        let mut student_id = num_to_id.get(&row.num).copied();
        if student_id.is_none() && !row.name.trim().is_empty() {
            let parts: Vec<&str> = row.name.splitn(2, char::is_whitespace).collect();
            let nom = parts.first().copied().unwrap_or(&row.name);
            let prenoms = parts.get(1).copied().unwrap_or("");
            match db.add_student(row.num, nom, prenoms, "", "", "") {
                Ok(id) => {
                    result.students_added += 1;
                    num_to_id.insert(row.num, id);
                    student_id = Some(id);
                }
                Err(error) => result.warnings.push(format!(
                    "Impossible d'ajouter l'élève n°{} ({}) : {error}",
                    row.num, row.name
                )),
            }
        }
        let Some(student_id) = student_id else {
            result.rows_skipped += 1;
            continue;
        };

        let old = existing.get(&(student_id, row.exam_num)).copied();
        if old.is_none() {
            result.notes_added += 1;
        } else if (old.unwrap() - row.value).abs() < 1e-6 {
            result.notes_unchanged += 1;
        } else {
            result.notes_updated += 1;
        }
        to_write.push((student_id, subject_id, row.exam_num, row.value));
        result.notes_total += 1;
    }

    if !to_write.is_empty() {
        if let Err(error) = db.bulk_set_grades(&to_write) {
            result
                .errors
                .push(format!("écriture en base impossible : {error}"));
        }
    }
    Ok(result)
}

/// Synchronise toutes les matières trouvées dans le dossier de la classe.
pub fn sync_all_subjects(
    db: &Database,
    class_info: &ClassInfo,
    only_dirty: bool,
    extra_dir: Option<&Path>,
) -> Result<SyncReport> {
    let started_at = Local::now();
    let mut report = SyncReport {
        class_name: class_info.display_name.clone(),
        started_at,
        finished_at: started_at,
        subjects: Vec::new(),
    };

    let mut xlsx_by_norm: HashMap<String, PathBuf> = class_info
        .subject_files
        .iter()
        .map(|path| {
            (
                normalize(&path.file_stem().unwrap_or_default().to_string_lossy()),
                path.clone(),
            )
        })
        .collect();

    if let Some(extra) = extra_dir {
        if extra.is_dir() {
            if let Ok(entries) = std::fs::read_dir(extra) {
                let mut files: Vec<PathBuf> = entries
                    .filter_map(|entry| entry.ok())
                    .map(|entry| entry.path())
                    .filter(|path| {
                        path.extension()
                            .map(|ext| ext.to_string_lossy().eq_ignore_ascii_case("xlsx"))
                            .unwrap_or(false)
                            && !path
                                .file_name()
                                .map(|name| name.to_string_lossy().starts_with("~$"))
                                .unwrap_or(false)
                    })
                    .collect();
                files.sort();
                for path in files {
                    let key = normalize(&path.file_stem().unwrap_or_default().to_string_lossy());
                    xlsx_by_norm.insert(key, path);
                }
            }
        }
    }

    let db_mtime = if only_dirty && class_info.db_path.exists() {
        std::fs::metadata(&class_info.db_path)
            .and_then(|meta| meta.modified())
            .ok()
    } else {
        None
    };

    let mut seen_subjects: HashSet<String> = HashSet::new();
    for subject in db.list_subjects()? {
        let key = normalize(&subject.name);
        seen_subjects.insert(key.clone());
        // Alias : `EVA` ↔ `Éducation à la Vie`, `Histo-geo` ↔ …
        let path = subject_name_aliases(&subject.name)
            .into_iter()
            .find_map(|alias| xlsx_by_norm.get(&alias).cloned());
        let Some(path) = path else {
            report.subjects.push(SubjectSyncResult {
                subject_name: subject.name,
                xlsx_path: None,
                matched: false,
                ..Default::default()
            });
            continue;
        };

        if let Some(db_mtime) = db_mtime {
            let modified = std::fs::metadata(&path)
                .and_then(|meta| meta.modified())
                .ok();
            if modified.map(|m| m <= db_mtime).unwrap_or(false) {
                report.subjects.push(SubjectSyncResult {
                    subject_name: subject.name,
                    xlsx_path: Some(path.clone()),
                    matched: true,
                    ..Default::default()
                });
                continue;
            }
        }

        match sync_subject_from_xlsx(db, &subject.name, &path) {
            Ok(result) => report.subjects.push(result),
            Err(error) => report.subjects.push(SubjectSyncResult {
                subject_name: subject.name,
                xlsx_path: Some(path.clone()),
                matched: true,
                errors: vec![error.to_string()],
                ..Default::default()
            }),
        }
    }

    report.finished_at = Local::now();
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn labels_are_stable() {
        assert_eq!(label_for_exam(1), "M.J 1");
        assert_eq!(label_for_exam(2), "Compo 1");
        assert_eq!(label_for_exam(6), "Compo 3");
        assert_eq!(exam_from_label("M.J 1"), Some(1));
        assert_eq!(exam_from_label("Compo 3"), Some(6));
        assert_eq!(exam_from_label("Inconnu"), None);
    }
}
