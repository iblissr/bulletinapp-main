//! Application desktop Bulletin — interface native Slint.
//!
//! L'application ne dépend d'aucune webview : tout est rendu par Slint et
//! toutes les données sont lues/écrites dans les bases SQLite des classes.

// Évite l'ouverture d'une console lors du lancement du binaire Windows.
#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]

slint::include_modules!();

use bulletin_core::calc::{
    compute_annuelle, compute_stats, compute_totalisation, compute_trimestre,
};
use bulletin_core::class_create;
use bulletin_core::db::{Database, class_default_coeff, subject_allowed_for_level};
use bulletin_core::export;
use bulletin_core::models::{Student, Subject, fmt_note, round2};
use bulletin_core::students_import;
use bulletin_core::sync::{SyncReport, label_for_exam, sync_all_subjects, sync_subject_from_xlsx};
use bulletin_core::workspace::{self, ClassInfo};
use slint::{ModelRc, SharedString, Timer, TimerMode, VecModel};
use std::cell::RefCell;
use std::collections::{BTreeMap, HashSet};
use std::fmt::Display;
use std::fs;
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::time::Duration;

const APP_VERSION: &str = env!("CARGO_PKG_VERSION");

thread_local! {
    static TOAST_TIMER: Timer = Timer::default();
}

// ---------------------------------------------------------------------------
// État applicatif
// ---------------------------------------------------------------------------

#[derive(Clone)]
struct ClassSummary {
    info: ClassInfo,
    students: i64,
    subjects: i64,
    classed: i64,
    sync_label: String,
}

struct AppState {
    root: PathBuf,
    summaries: Vec<ClassSummary>,
    current: Option<ClassInfo>,
    db: Option<Database>,
    students: Vec<Student>,
    subjects: Vec<Subject>,
    active_subject: usize,
    active_exam: i64,
    active_trim: i64,
    active_moy_tab: i64,
    active_tab: i32,
    class_filter: String,
    class_search: String,
    student_filter: String,
    selected_student_id: i64,
}

impl AppState {
    fn new(root: PathBuf) -> Self {
        Self {
            root,
            summaries: Vec::new(),
            current: None,
            db: None,
            students: Vec::new(),
            subjects: Vec::new(),
            active_subject: 0,
            active_exam: 1,
            active_trim: 1,
            active_moy_tab: 0,
            active_tab: 0,
            class_filter: "all".into(),
            class_search: String::new(),
            student_filter: String::new(),
            selected_student_id: -1,
        }
    }

    fn reload(&mut self) -> anyhow::Result<()> {
        let Some(db) = self.db.as_ref() else {
            self.students.clear();
            self.subjects.clear();
            return Ok(());
        };
        self.students = db.list_students()?;
        self.subjects = db.list_subjects()?;
        if self.subjects.is_empty() {
            self.active_subject = 0;
        } else if self.active_subject >= self.subjects.len() {
            self.active_subject = self.subjects.len() - 1;
        }
        if self.selected_student_id > 0
            && !self
                .students
                .iter()
                .any(|s| s.id == self.selected_student_id)
        {
            self.selected_student_id = -1;
        }
        Ok(())
    }

    fn active_subject(&self) -> Option<&Subject> {
        self.subjects.get(self.active_subject)
    }
}

// ---------------------------------------------------------------------------
// Point d'entrée
// ---------------------------------------------------------------------------

fn main() -> anyhow::Result<()> {
    let ui = AppWindow::new()?;
    ui.set_app_version(APP_VERSION.into());

    let root = std::env::var("BULLETIN_ROOT")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| workspace::find_bulletin_root(None));

    let state = Rc::new(RefCell::new(AppState::new(root)));
    {
        let mut st = state.borrow_mut();
        refresh_home(&mut st, &ui);
    }
    wire_callbacks(&ui, &state);

    ui.run()?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Helpers d'affichage
// ---------------------------------------------------------------------------

fn toast(ui: &AppWindow, message: impl Into<SharedString>, kind: i32) {
    ui.set_status_message(message.into());
    ui.set_status_kind(kind);
    let weak = ui.as_weak();
    TOAST_TIMER.with(|timer| {
        timer.start(TimerMode::SingleShot, Duration::from_secs(5), move || {
            if let Some(ui) = weak.upgrade() {
                ui.set_status_message(SharedString::default());
            }
        });
    });
}

fn report_error(ui: &AppWindow, error: impl Display) {
    toast(ui, format!("Erreur : {error}"), 2);
}

fn model<T: Clone + 'static>(items: Vec<T>) -> ModelRc<T> {
    ModelRc::new(VecModel::from(items))
}

fn strings(items: Vec<String>) -> ModelRc<SharedString> {
    model(items.into_iter().map(SharedString::from).collect())
}

fn lengths(items: Vec<f32>) -> ModelRc<f32> {
    model(items)
}

fn fmt_opt(value: Option<f64>) -> String {
    fmt_note(value)
}

fn fmt_opt_nc(value: Option<f64>) -> String {
    match value {
        Some(value) => fmt_note(Some(value)),
        None => "NC".to_string(),
    }
}

fn fmt_rank(rank: Option<usize>) -> String {
    match rank {
        Some(rank) => rank.to_string(),
        None => "NC".to_string(),
    }
}

fn fmt_coeff(coeff: f64) -> String {
    if coeff.fract() == 0.0 {
        format!("{coeff:.0}")
    } else {
        format!("{coeff}")
    }
}

fn table_row(id: i64, cells: Vec<String>, stripe: bool, tone: i32) -> TableRowData {
    TableRowData {
        id: id as i32,
        tone,
        stripe,
        cells: strings(cells),
    }
}

fn sync_label(info: &ClassInfo) -> String {
    if info.subject_files.is_empty() {
        return "aucun .xlsx".to_string();
    }
    let newest_xlsx = info
        .subject_files
        .iter()
        .filter_map(|path| fs::metadata(path).and_then(|meta| meta.modified()).ok())
        .max();
    let db_mtime = fs::metadata(&info.db_path)
        .and_then(|meta| meta.modified())
        .ok();
    match (newest_xlsx, db_mtime) {
        (Some(_), None) => "base absente".to_string(),
        (Some(newest), Some(db)) if db >= newest => "à jour".to_string(),
        (Some(_), Some(_)) => "à synchroniser".to_string(),
        _ => "—".to_string(),
    }
}

fn build_summaries(root: &Path) -> Vec<ClassSummary> {
    workspace::discover_classes(Some(root))
        .into_iter()
        .map(|info| {
            let mut students = 0;
            let mut subjects = 0;
            let mut classed = 0;
            if info.db_path.exists() {
                if let Ok(db) = Database::open(Some(&info.db_path)) {
                    students = db.count_students().unwrap_or(0);
                    subjects = db.count_subjects().unwrap_or(0);
                    classed = db
                        .connection()
                        .query_row("SELECT COUNT(DISTINCT student_id) FROM grades", [], |row| {
                            row.get::<_, i64>(0)
                        })
                        .unwrap_or(0);
                }
            }
            ClassSummary {
                sync_label: sync_label(&info),
                info,
                students,
                subjects,
                classed,
            }
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Accueil
// ---------------------------------------------------------------------------

fn refresh_home(state: &mut AppState, ui: &AppWindow) {
    state.summaries = build_summaries(&state.root);
    ui.set_total_classes(state.summaries.len() as i32);
    ui.set_total_students(
        state
            .summaries
            .iter()
            .map(|class| class.students)
            .sum::<i64>() as i32,
    );
    ui.set_total_subjects(
        state
            .summaries
            .iter()
            .map(|class| class.subjects)
            .sum::<i64>() as i32,
    );
    ui.set_total_classed(
        state
            .summaries
            .iter()
            .map(|class| class.classed)
            .sum::<i64>() as i32,
    );
    ui.set_class_filter(state.class_filter.clone().into());
    ui.set_db_path_label(state.root.to_string_lossy().to_string().into());
    rebuild_class_cards(state, ui);
}

fn rebuild_class_cards(state: &AppState, ui: &AppWindow) {
    let filter = state.class_filter.as_str();
    let search = state.class_search.trim().to_lowercase();
    let cards: Vec<ClassCardData> = state
        .summaries
        .iter()
        .filter(|summary| filter == "all" || summary.info.division == filter)
        .filter(|summary| {
            search.is_empty()
                || summary.info.name.to_lowercase().contains(&search)
                || summary.info.display_name.to_lowercase().contains(&search)
                || summary.info.division.to_lowercase().contains(&search)
        })
        .map(|summary| ClassCardData {
            name: summary.info.name.clone().into(),
            display_name: summary.info.display_name.clone().into(),
            division: summary.info.division.clone().into(),
            student_count_label: summary.students.to_string().into(),
            subject_count_label: summary.subjects.to_string().into(),
            sync_label: summary.sync_label.clone().into(),
        })
        .collect();
    ui.set_classes(model(cards));
}

// ---------------------------------------------------------------------------
// Classe active
// ---------------------------------------------------------------------------

fn open_class(state: &mut AppState, ui: &AppWindow, name: &str) -> anyhow::Result<()> {
    let info = state
        .summaries
        .iter()
        .find(|summary| summary.info.name == name)
        .map(|summary| summary.info.clone())
        .or_else(|| workspace::discover_class(name, Some(&state.root)));
    let Some(info) = info else {
        anyhow::bail!("Classe introuvable : {name}");
    };
    let db = Database::open(Some(&info.db_path))?;
    state.current = Some(info);
    state.db = Some(db);
    state.active_subject = 0;
    state.active_exam = 1;
    state.active_trim = 1;
    state.active_moy_tab = 0;
    state.active_tab = 0;
    state.selected_student_id = -1;
    state.student_filter.clear();
    state.reload()?;
    ui.set_page(1);
    ui.set_active_tab(0);
    ui.set_active_exam(1);
    ui.set_active_trim(1);
    ui.set_active_moy_tab(0);
    ui.set_student_search(SharedString::default());
    clear_student_form(ui);
    refresh_class_ui(state, ui);
    Ok(())
}

fn refresh_class_ui(state: &mut AppState, ui: &AppWindow) {
    let Some(info) = state.current.clone() else {
        return;
    };
    ui.set_page(1);
    ui.set_selected_class_name(info.name.clone().into());
    ui.set_selected_class_display(info.display_name.clone().into());
    ui.set_selected_class_division(info.division.clone().into());
    ui.set_selected_class_students(state.students.len().to_string().into());
    ui.set_selected_class_subjects(state.subjects.len().to_string().into());
    ui.set_db_path_label(info.db_path.to_string_lossy().to_string().into());

    if let Some(db) = state.db.as_ref() {
        let average = compute_stats(db, state.active_exam)
            .ok()
            .and_then(|stats| stats.moyenne_classe);
        ui.set_selected_class_average(fmt_opt(average).into());
    }

    refresh_students_ui(state, ui);
    refresh_subjects_ui(state, ui);
    refresh_settings_ui(state, ui);
    refresh_selected_student_ui(state, ui);
    ui.set_active_tab(state.active_tab);
    match state.active_tab {
        1 => refresh_grades(state, ui),
        2 => refresh_moyennes(state, ui),
        3 => refresh_totalisation(state, ui),
        4 => refresh_cr(state, ui),
        _ => {}
    }
}

fn refresh_students_ui(state: &mut AppState, ui: &AppWindow) {
    let students: Vec<StudentData> = state
        .students
        .iter()
        .map(|student| StudentData {
            id: student.id as i32,
            num: student.num as i32,
            name: student.display_name().into(),
            matricule: student.matricule.clone().into(),
            genre: student.genre.clone().into(),
            naissance: student.naissance.clone().into(),
        })
        .collect();
    ui.set_students(model(students));

    let filter = state.student_filter.trim().to_lowercase();
    let rows: Vec<TableRowData> = state
        .students
        .iter()
        .enumerate()
        .filter(|(_, student)| {
            filter.is_empty()
                || student.display_name().to_lowercase().contains(&filter)
                || student.matricule.to_lowercase().contains(&filter)
        })
        .map(|(index, student)| {
            table_row(
                student.id,
                vec![
                    student.num.to_string(),
                    student.display_name(),
                    student.matricule.clone(),
                    student.genre.clone(),
                    student.naissance.clone(),
                ],
                index % 2 == 1,
                0,
            )
        })
        .collect();
    ui.set_student_rows(model(rows));
    ui.set_selected_student_id(state.selected_student_id as i32);
    ui.set_selected_class_students(state.students.len().to_string().into());
}

// ---------------------------------------------------------------------------
// Nouvelle classe
// ---------------------------------------------------------------------------

fn new_class_levels(section_key: &str) -> Vec<SharedString> {
    class_create::section(section_key)
        .map(|section| {
            section
                .levels
                .iter()
                .map(|(key, _label)| SharedString::from(*key))
                .collect()
        })
        .unwrap_or_default()
}

fn refresh_new_class_ui(ui: &AppWindow) {
    let section_key = ui.get_nc_section().to_string();
    let section = class_create::section(&section_key).unwrap_or(&class_create::SECTIONS[2]);
    let levels = new_class_levels(section.key);
    ui.set_nc_levels(model(levels.clone()));
    let level = ui.get_nc_level().to_string();
    if !levels.iter().any(|candidate| candidate.as_str() == level) {
        if let Some(first) = levels.first() {
            ui.set_nc_level(first.clone());
        }
    }

    let count = ui
        .get_nc_count()
        .trim()
        .parse::<usize>()
        .unwrap_or(1)
        .clamp(1, 26);
    let suffixes: Vec<String> = ui
        .get_nc_suffixes()
        .split(',')
        .map(|suffix| suffix.trim().to_string())
        .filter(|suffix| !suffix.is_empty())
        .collect();
    let names =
        class_create::expand_pattern(&ui.get_nc_level(), &ui.get_nc_pattern(), count, &suffixes)
            .unwrap_or_default();
    ui.set_nc_preview(names.join(" · ").into());

    // Aperçu des matières : coefficients propres à la classe à créer,
    // matières interdites au niveau retirées.
    let preview: Vec<String> = match names.first() {
        Some(sample) => {
            let raw_level = ui.get_nc_level().to_string();
            let level_key = if raw_level.trim().is_empty() {
                workspace::extract_level_key(sample)
            } else {
                raw_level.trim().to_uppercase()
            };
            section
                .subjects
                .iter()
                .filter(|(name, _)| subject_allowed_for_level(name, &level_key))
                .map(|(name, coeff)| {
                    let value =
                        class_default_coeff(name, sample, Some(&level_key)).unwrap_or(*coeff);
                    format!("{name} (×{})", fmt_coeff(value))
                })
                .collect()
        }
        None => section
            .subjects
            .iter()
            .map(|(name, coeff)| format!("{name} (×{})", fmt_coeff(*coeff)))
            .collect(),
    };
    ui.set_nc_subjects_label(
        format!("{} matières : {}", preview.len(), preview.join(" · ")).into(),
    );
}

fn refresh_selected_student_ui(state: &AppState, ui: &AppWindow) {
    let selected = state
        .students
        .iter()
        .find(|student| student.id == state.selected_student_id);
    match selected {
        Some(student) => {
            ui.set_selected_student_id(student.id as i32);
            ui.set_selected_student_num(student.num as i32);
            ui.set_selected_student_name(student.display_name().into());
            ui.set_new_student_num(student.num.to_string().into());
            ui.set_new_student_nom(student.nom.clone().into());
            ui.set_new_student_prenoms(student.prenoms.clone().into());
            ui.set_new_student_matricule(student.matricule.clone().into());
            ui.set_new_student_genre(student.genre.clone().into());
            ui.set_new_student_naissance(student.naissance.clone().into());
        }
        None => {
            ui.set_selected_student_id(-1);
            ui.set_selected_student_num(0);
            ui.set_selected_student_name(SharedString::default());
        }
    }
}

fn refresh_subjects_ui(state: &mut AppState, ui: &AppWindow) {
    let subjects: Vec<SubjectData> = state
        .subjects
        .iter()
        .map(|subject| SubjectData {
            id: subject.id as i32,
            name: subject.name.clone().into(),
            coeff: subject.coeff as f32,
            teacher: subject.teacher.clone().into(),
            abbrev: subject.abbrev().into(),
            coeff_label: fmt_coeff(subject.coeff).into(),
        })
        .collect();
    ui.set_subjects(model(subjects));

    let nb_exams = state
        .db
        .as_ref()
        .map(|db| db.get_setting_int("nb_examens", 6).clamp(1, 6))
        .unwrap_or(6);
    let rows: Vec<TableRowData> = state
        .subjects
        .iter()
        .enumerate()
        .map(|(index, subject)| {
            table_row(
                subject.id,
                vec![
                    subject.name.clone(),
                    fmt_coeff(subject.coeff),
                    if subject.teacher.trim().is_empty() {
                        "—".to_string()
                    } else {
                        subject.teacher.clone()
                    },
                    format!("{nb_exams}"),
                ],
                index % 2 == 1,
                0,
            )
        })
        .collect();
    ui.set_subject_rows(model(rows));
    ui.set_active_subject(state.active_subject as i32);

    match state.active_subject() {
        Some(subject) => {
            ui.set_active_subject_name(subject.name.clone().into());
            ui.set_active_subject_meta(
                format!(
                    "Coefficient : {}    Professeur : {}    {} examens (3 M.J. + 3 Compo)",
                    fmt_coeff(subject.coeff),
                    if subject.teacher.trim().is_empty() {
                        "—"
                    } else {
                        &subject.teacher
                    },
                    nb_exams
                )
                .into(),
            );
        }
        None => {
            ui.set_active_subject_name("Aucune matière".into());
            ui.set_active_subject_meta("Ajoutez une matière dans l'onglet Configuration.".into());
        }
    }
}

fn refresh_grades(state: &mut AppState, ui: &AppWindow) {
    let Some(db) = state.db.as_ref() else {
        return;
    };
    let Some(subject) = state.active_subject().cloned() else {
        ui.set_grade_rows(model(Vec::<GradeRowData>::new()));
        ui.set_exam_labels(model(Vec::<SharedString>::new()));
        return;
    };
    let nb_exams = db.get_setting_int("nb_examens", 6).clamp(1, 6);
    let exam_labels: Vec<String> = (1..=nb_exams).map(label_for_exam).collect();
    let grades = db.get_grades_subject(subject.id).unwrap_or_default();

    let rows: Vec<GradeRowData> = state
        .students
        .iter()
        .enumerate()
        .map(|(index, student)| {
            let mut notes = Vec::with_capacity(nb_exams as usize);
            let mut values = Vec::new();
            for exam in 1..=nb_exams {
                let value = grades.get(&(student.id, exam)).copied();
                if let Some(value) = value {
                    values.push(value);
                }
                notes.push(fmt_note(value));
            }
            let moy = if values.is_empty() {
                "NC".to_string()
            } else {
                fmt_note(Some(round2(
                    values.iter().sum::<f64>() / values.len() as f64,
                )))
            };
            GradeRowData {
                student_id: student.id as i32,
                num: student.num as i32,
                name: student.display_name().into(),
                notes: strings(notes),
                moy: moy.into(),
                stripe: index % 2 == 1,
            }
        })
        .collect();

    ui.set_exam_labels(strings(exam_labels));
    ui.set_grade_rows(model(rows));
}

fn refresh_moyennes(state: &mut AppState, ui: &AppWindow) {
    let Some(db) = state.db.as_ref() else {
        return;
    };
    let headers: Vec<String>;
    let widths: Vec<f32>;
    let rows: Vec<TableRowData>;
    let label: String;

    if state.active_moy_tab < 3 {
        let trimestre = state.active_moy_tab + 1;
        let values = match compute_trimestre(db, trimestre) {
            Ok(values) => values,
            Err(error) => {
                report_error(ui, error);
                return;
            }
        };
        headers = vec![
            "N°".into(),
            "Prénoms".into(),
            "M.J. (×1)".into(),
            "Compo (×2)".into(),
            "Total M.J.".into(),
            "Total Compo".into(),
            "Total/40".into(),
            "Moyenne/20".into(),
            "Rang".into(),
        ];
        widths = vec![50.0, 250.0, 82.0, 82.0, 82.0, 82.0, 82.0, 82.0, 60.0];
        rows = values
            .iter()
            .enumerate()
            .map(|(index, row)| {
                table_row(
                    row.student.id,
                    vec![
                        row.student.num.to_string(),
                        row.student.full_name(),
                        fmt_opt(row.m_moy),
                        fmt_opt(row.c_moy),
                        fmt_opt(row.m_total),
                        fmt_opt(row.c_total),
                        fmt_opt(row.tot),
                        fmt_opt_nc(row.moy),
                        fmt_rank(row.rank),
                    ],
                    index % 2 == 1,
                    if row.moy.is_none() { 2 } else { 0 },
                )
            })
            .collect();
        label = format!("Trimestre {trimestre} — M.J. {trimestre} (×1) + Compo {trimestre} (×2)");
    } else {
        let values = match compute_annuelle(db) {
            Ok(values) => values,
            Err(error) => {
                report_error(ui, error);
                return;
            }
        };
        headers = vec![
            "N°".into(),
            "Prénoms".into(),
            "M.J.1".into(),
            "Compo.1".into(),
            "M.J.2".into(),
            "Compo.2".into(),
            "M.J.3".into(),
            "Compo.3".into(),
            "Total/120".into(),
            "MGA/20".into(),
            "Rang".into(),
        ];
        widths = vec![
            50.0, 250.0, 72.0, 72.0, 72.0, 72.0, 72.0, 72.0, 78.0, 78.0, 60.0,
        ];
        rows = values
            .iter()
            .enumerate()
            .map(|(index, row)| {
                table_row(
                    row.student.id,
                    vec![
                        row.student.num.to_string(),
                        row.student.full_name(),
                        fmt_opt(row.mj1),
                        fmt_opt(row.co1),
                        fmt_opt(row.mj2),
                        fmt_opt(row.co2),
                        fmt_opt(row.mj3),
                        fmt_opt(row.co3),
                        fmt_opt(row.total),
                        fmt_opt_nc(row.mga),
                        fmt_rank(row.rank),
                    ],
                    index % 2 == 1,
                    if row.mga.is_none() { 2 } else { 0 },
                )
            })
            .collect();
        label = "Moyenne générale annuelle — 3 M.J. (×1) + 3 Compos (×2)".to_string();
    }

    ui.set_moy_headers(strings(headers));
    ui.set_moy_widths(lengths(widths));
    ui.set_moy_rows(model(rows));
    ui.set_moy_tab_label(label.into());
}

fn refresh_totalisation(state: &mut AppState, ui: &AppWindow) {
    let Some(db) = state.db.as_ref() else {
        return;
    };
    let result = match compute_totalisation(db, state.active_exam) {
        Ok(result) => result,
        Err(error) => {
            report_error(ui, error);
            return;
        }
    };

    let mut headers = vec!["N°".to_string(), "Prénoms".to_string()];
    headers.extend(result.subjects.iter().map(|subject| subject.abbrev()));
    headers.push("Tot".into());
    headers.push("Moy".into());
    headers.push("RG".into());

    let mut widths = vec![50.0, 250.0];
    widths.extend(result.subjects.iter().map(|_| 55.0));
    widths.push(70.0);
    widths.push(70.0);
    widths.push(55.0);

    let rows: Vec<TableRowData> = result
        .rows
        .iter()
        .enumerate()
        .map(|(index, row)| {
            let mut cells = vec![row.student.num.to_string(), row.student.full_name()];
            for subject in &result.subjects {
                cells.push(fmt_note(row.notes.get(&subject.id).copied().flatten()));
            }
            if row.valid {
                cells.push(fmt_opt(row.total));
                cells.push(fmt_opt(row.moy));
                cells.push(fmt_rank(row.rank));
            } else {
                cells.push("NC".into());
                cells.push("NC".into());
                cells.push("NC".into());
            }
            table_row(
                row.student.id,
                cells,
                index % 2 == 1,
                if row.valid { 0 } else { 2 },
            )
        })
        .collect();

    ui.set_tot_headers(strings(headers));
    ui.set_tot_widths(lengths(widths));
    ui.set_tot_rows(model(rows));
}

fn refresh_cr(state: &mut AppState, ui: &AppWindow) {
    let Some(db) = state.db.as_ref() else {
        return;
    };
    let trimestre = state.active_trim.clamp(1, 3);
    let n_mj = 2 * trimestre - 1;
    let n_co = 2 * trimestre;
    let stats_mj = match compute_stats(db, n_mj) {
        Ok(stats) => stats,
        Err(error) => {
            report_error(ui, error);
            return;
        }
    };
    let stats_co = match compute_stats(db, n_co) {
        Ok(stats) => stats,
        Err(error) => {
            report_error(ui, error);
            return;
        }
    };
    let subjects = match db.list_subjects() {
        Ok(subjects) => subjects,
        Err(error) => {
            report_error(ui, error);
            return;
        }
    };

    ui.set_cr_effectif(stats_mj.effectif.to_string().into());
    ui.set_cr_classes(stats_mj.classes.max(stats_co.classes).to_string().into());
    ui.set_cr_moy_mj(fmt_opt(stats_mj.moyenne_classe).into());
    ui.set_cr_moy_co(fmt_opt(stats_co.moyenne_classe).into());
    ui.set_cr_moy_ensemble(
        match (stats_mj.moyenne_classe, stats_co.moyenne_classe) {
            (Some(a), Some(b)) => fmt_note(Some(round2((a + b) / 2.0))),
            (Some(a), None) => fmt_note(Some(a)),
            (None, Some(b)) => fmt_note(Some(b)),
            (None, None) => "NC".to_string(),
        }
        .into(),
    );

    let label_mj = label_for_exam(n_mj);
    let label_co = label_for_exam(n_co);
    ui.set_cr_headers(strings(vec![
        "Matière".into(),
        format!("≥ 10/20 ({label_mj})"),
        format!("≥ 10/20 ({label_co})"),
        "≥ 10/20 (Ensemble)".into(),
    ]));

    let rows: Vec<TableRowData> = subjects
        .iter()
        .enumerate()
        .map(|(index, subject)| {
            let nb_mj = stats_mj
                .nb_above_avg_per_subject
                .get(&subject.id)
                .copied()
                .unwrap_or(0);
            let nb_co = stats_co
                .nb_above_avg_per_subject
                .get(&subject.id)
                .copied()
                .unwrap_or(0);
            table_row(
                subject.id,
                vec![
                    subject.name.clone(),
                    nb_mj.to_string(),
                    nb_co.to_string(),
                    nb_mj.max(nb_co).to_string(),
                ],
                index % 2 == 1,
                0,
            )
        })
        .collect();
    ui.set_cr_rows(model(rows));

    let mut combined: BTreeMap<u8, usize> = BTreeMap::new();
    for (threshold, count) in stats_mj
        .distribution
        .iter()
        .chain(stats_co.distribution.iter())
    {
        *combined.entry(*threshold).or_insert(0) += count;
    }
    let max_count = combined.values().copied().max().unwrap_or(1).max(1);
    let distribution: Vec<DistRowData> = combined
        .iter()
        .rev()
        .map(|(threshold, count)| DistRowData {
            label: format!("≥ {threshold}").into(),
            count: *count as i32,
            ratio: *count as f32 / max_count as f32,
        })
        .collect();
    ui.set_cr_distribution(model(distribution));
}

fn refresh_settings_ui(state: &AppState, ui: &AppWindow) {
    let Some(db) = state.db.as_ref() else {
        return;
    };
    ui.set_set_etablissement(db.get_setting("etablissement", "").into());
    ui.set_set_directeur(db.get_setting("directeur", "").into());
    ui.set_set_annee(db.get_setting("annee_scolaire", "").into());
    ui.set_set_classe(db.get_setting("classe", "").into());
    ui.set_set_nb_examens(db.get_setting("nb_examens", "6").into());
    ui.set_set_nb_min(db.get_setting("nb_min_examens", "3").into());
    ui.set_set_prof_principal(db.get_setting("prof_principal", "").into());
    ui.set_set_coeff_default(db.get_setting("coeff_default", "1").into());
    ui.set_set_effectif(db.get_setting("effectif", "").into());
    ui.set_set_filles(db.get_setting("nb_filles", "").into());
    ui.set_set_garcons(db.get_setting("nb_garcons", "").into());
    ui.set_set_logo_path(db.get_setting("logo_path", "").into());
}

fn clear_student_form(ui: &AppWindow) {
    ui.set_new_student_num(SharedString::default());
    ui.set_new_student_nom(SharedString::default());
    ui.set_new_student_prenoms(SharedString::default());
    ui.set_new_student_matricule(SharedString::default());
    ui.set_new_student_genre(SharedString::default());
    ui.set_new_student_naissance(SharedString::default());
}

fn clear_subject_form(ui: &AppWindow) {
    ui.set_subject_form_id(-1);
    ui.set_subject_form_name(SharedString::default());
    ui.set_subject_form_coeff("1".into());
    ui.set_subject_form_teacher(SharedString::default());
}

fn fill_subject_form(ui: &AppWindow, subject: &Subject) {
    ui.set_subject_form_id(subject.id as i32);
    ui.set_subject_form_name(subject.name.clone().into());
    ui.set_subject_form_coeff(fmt_coeff(subject.coeff).into());
    ui.set_subject_form_teacher(subject.teacher.clone().into());
}

// ---------------------------------------------------------------------------
// Parsing & confirmations
// ---------------------------------------------------------------------------

fn parse_note(text: &str, max: f64) -> Result<Option<f64>, String> {
    let trimmed = text.trim().replace(',', ".");
    if trimmed.is_empty() || trimmed == "—" || trimmed == "-" {
        return Ok(None);
    }
    match trimmed.parse::<f64>() {
        Ok(value) if value.is_finite() => Ok(Some(round2(value.clamp(0.0, max)))),
        _ => Err(format!("Note invalide : {text}")),
    }
}

fn confirm(title: &str, description: &str) -> bool {
    rfd::MessageDialog::new()
        .set_title(title)
        .set_description(description)
        .set_buttons(rfd::MessageButtons::YesNo)
        .set_level(rfd::MessageLevel::Warning)
        .show()
        == rfd::MessageDialogResult::Yes
}

fn default_export_dir(class: &ClassInfo) -> PathBuf {
    let dir = class.folder.join("exports");
    let _ = fs::create_dir_all(&dir);
    dir
}

fn safe_filename(name: &str) -> String {
    name.chars()
        .map(|ch| {
            if ch.is_alphanumeric() || matches!(ch, ' ' | '-' | '_' | '.') {
                ch
            } else {
                '_'
            }
        })
        .collect::<String>()
        .trim()
        .to_string()
}

// ---------------------------------------------------------------------------
// Branchement des callbacks
// ---------------------------------------------------------------------------

fn wire_callbacks(ui: &AppWindow, state: &Rc<RefCell<AppState>>) {
    // --- Navigation ---------------------------------------------------
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_open_class(move |name| {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            if let Err(error) = open_class(&mut st, &ui, name.as_str()) {
                report_error(&ui, error);
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_go_home(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            ui.set_page(0);
            refresh_home(&mut st, &ui);
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_refresh_classes(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            refresh_home(&mut st, &ui);
            toast(&ui, "Liste des classes actualisée", 1);
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_open_new_class(move || {
            let Some(ui) = weak.upgrade() else { return };
            let st = state.borrow();
            if let Some(db) = st.db.as_ref() {
                if ui.get_nc_etablissement().trim().is_empty() {
                    ui.set_nc_etablissement(db.get_setting("etablissement", "").into());
                }
                if ui.get_nc_annee().trim().is_empty() {
                    ui.set_nc_annee(db.get_setting("annee_scolaire", "").into());
                }
                if ui.get_nc_prof().trim().is_empty() {
                    ui.set_nc_prof(db.get_setting("prof_principal", "").into());
                }
                let label = db.get_setting("section", "");
                if let Some(section) = class_create::SECTIONS
                    .iter()
                    .find(|section| section.label.eq_ignore_ascii_case(label.trim()))
                {
                    ui.set_nc_section(section.key.into());
                }
            }
            if ui.get_nc_etablissement().trim().is_empty() {
                ui.set_nc_etablissement("Lycée Saint Joseph".into());
            }
            if ui.get_nc_annee().trim().is_empty() {
                ui.set_nc_annee("2025-2026".into());
            }
            ui.set_page(2);
            refresh_new_class_ui(&ui);
        });
    }
    {
        let weak = ui.as_weak();
        ui.on_cancel_new_class(move || {
            let Some(ui) = weak.upgrade() else { return };
            ui.set_page(0);
        });
    }
    {
        let weak = ui.as_weak();
        ui.on_new_class_section(move |key| {
            let Some(ui) = weak.upgrade() else { return };
            ui.set_nc_section(key.clone());
            let levels = new_class_levels(key.as_str());
            if let Some(first) = levels.first() {
                if !levels
                    .iter()
                    .any(|candidate| candidate.as_str() == ui.get_nc_level().as_str())
                {
                    ui.set_nc_level(first.clone());
                }
            }
            refresh_new_class_ui(&ui);
        });
    }
    {
        let weak = ui.as_weak();
        ui.on_new_class_level(move |level| {
            let Some(ui) = weak.upgrade() else { return };
            ui.set_nc_level(level);
            refresh_new_class_ui(&ui);
        });
    }
    {
        let weak = ui.as_weak();
        ui.on_new_class_pattern(move |pattern| {
            let Some(ui) = weak.upgrade() else { return };
            ui.set_nc_pattern(pattern);
            refresh_new_class_ui(&ui);
        });
    }
    {
        let weak = ui.as_weak();
        ui.on_new_class_refresh(move || {
            let Some(ui) = weak.upgrade() else { return };
            refresh_new_class_ui(&ui);
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_create_class(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            let suffixes: Vec<String> = ui
                .get_nc_suffixes()
                .split(',')
                .map(|suffix| suffix.trim().to_string())
                .filter(|suffix| !suffix.is_empty())
                .collect();
            let draft = class_create::ClassDraft {
                section: ui.get_nc_section().to_string(),
                level: ui.get_nc_level().to_string(),
                count: ui
                    .get_nc_count()
                    .trim()
                    .parse::<usize>()
                    .unwrap_or(1)
                    .clamp(1, 26),
                pattern: ui.get_nc_pattern().to_string(),
                custom_suffixes: suffixes,
                effectif: ui
                    .get_nc_effectif()
                    .trim()
                    .parse::<i64>()
                    .unwrap_or(0)
                    .clamp(0, 500),
                etablissement: ui.get_nc_etablissement().trim().to_string(),
                annee_scolaire: ui.get_nc_annee().trim().to_string(),
                prof_principal: ui.get_nc_prof().trim().to_string(),
            };
            match class_create::create_classes_in(&st.root, &draft) {
                Ok(created) if !created.is_empty() => {
                    let last = created.last().cloned().unwrap();
                    refresh_home(&mut st, &ui);
                    let summary = format!(
                        "{} classe(s) créée(s) : {}",
                        created.len(),
                        created
                            .iter()
                            .map(|class| class.name.as_str())
                            .collect::<Vec<_>>()
                            .join(", ")
                    );
                    if let Err(error) = open_class(&mut st, &ui, &last.name) {
                        report_error(&ui, error);
                    } else {
                        toast(&ui, summary, 1);
                    }
                }
                Ok(_) => toast(&ui, "Aucune classe créée", 2),
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_filter_classes(move |filter| {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            st.class_filter = filter.to_string();
            ui.set_class_filter(filter);
            rebuild_class_cards(&st, &ui);
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_search_classes(move |text| {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            st.class_search = text.to_string();
            rebuild_class_cards(&st, &ui);
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_select_tab(move |tab| {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            st.active_tab = tab;
            ui.set_active_tab(tab);
            refresh_class_ui(&mut st, &ui);
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_select_subject(move |index| {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            let index = index.max(0) as usize;
            if index < st.subjects.len() {
                st.active_subject = index;
                refresh_subjects_ui(&mut st, &ui);
                refresh_grades(&mut st, &ui);
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_edit_subject(move |id| {
            let Some(ui) = weak.upgrade() else { return };
            let st = state.borrow();
            if let Some(subject) = st.subjects.iter().find(|subject| subject.id == id as i64) {
                fill_subject_form(&ui, subject);
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_select_exam(move |exam| {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            st.active_exam = i64::from(exam).clamp(1, 6);
            ui.set_active_exam(st.active_exam as i32);
            if let Some(db) = st.db.as_ref() {
                let average = compute_stats(db, st.active_exam)
                    .ok()
                    .and_then(|stats| stats.moyenne_classe);
                ui.set_selected_class_average(fmt_opt(average).into());
            }
            refresh_totalisation(&mut st, &ui);
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_select_moy_tab(move |tab| {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            st.active_moy_tab = i64::from(tab).clamp(0, 3);
            ui.set_active_moy_tab(st.active_moy_tab as i32);
            refresh_moyennes(&mut st, &ui);
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_select_cr_trim(move |trim| {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            st.active_trim = i64::from(trim).clamp(1, 3);
            ui.set_active_trim(st.active_trim as i32);
            refresh_cr(&mut st, &ui);
        });
    }

    // --- Notes --------------------------------------------------------
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_grade_edited(move |student_id, exam_num, text| {
            let Some(ui) = weak.upgrade() else { return };
            let st = state.borrow_mut();
            let Some(db) = st.db.as_ref() else { return };
            let Some(subject) = st.subjects.get(st.active_subject) else {
                return;
            };
            let max = 20.0 * subject.coeff;
            let subject_id = subject.id;
            let parsed = match parse_note(text.as_str(), max) {
                Ok(value) => value,
                Err(_) => return,
            };
            if let Err(error) = db.set_grade(
                i64::from(student_id),
                subject_id,
                i64::from(exam_num),
                parsed,
            ) {
                report_error(&ui, error);
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_save_grades(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            refresh_grades(&mut st, &ui);
            toast(&ui, "Notes enregistrées dans la base de la classe", 1);
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_clear_subject(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            let Some(subject) = st.active_subject().cloned() else {
                return;
            };
            if !confirm(
                "Vider les notes",
                &format!(
                    "Supprimer toutes les notes de la matière « {} » ?",
                    subject.name
                ),
            ) {
                return;
            }
            if let Some(db) = st.db.as_ref() {
                match db.clear_grades_subject(subject.id) {
                    Ok(count) => {
                        refresh_grades(&mut st, &ui);
                        toast(&ui, format!("{count} note(s) supprimée(s)"), 1);
                    }
                    Err(error) => report_error(&ui, error),
                }
            }
        });
    }

    // --- Synchronisation & exports -----------------------------------
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_sync_class(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            let Some(info) = st.current.clone() else {
                return;
            };
            let report: anyhow::Result<SyncReport> = {
                let Some(db) = st.db.as_ref() else { return };
                sync_all_subjects(db, &info, false, None)
            };
            match report {
                Ok(report) => {
                    if let Err(error) = st.reload() {
                        report_error(&ui, error);
                    }
                    refresh_class_ui(&mut st, &ui);
                    let first_line = report
                        .summary()
                        .lines()
                        .next()
                        .unwrap_or("Synchronisation terminée")
                        .to_string();
                    let kind = if report.error_count() > 0 { 2 } else { 1 };
                    toast(&ui, first_line, kind);
                }
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_sync_subject(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            let Some(info) = st.current.clone() else {
                return;
            };
            let Some(subject) = st.active_subject().cloned() else {
                toast(&ui, "Aucune matière sélectionnée", 2);
                return;
            };
            let path = info.subject_path(&subject.name);
            if !path.is_file() {
                toast(&ui, format!("Fichier introuvable : {}", path.display()), 2);
                return;
            }
            let result = {
                let Some(db) = st.db.as_ref() else { return };
                sync_subject_from_xlsx(db, &subject.name, &path)
            };
            match result {
                Ok(result) => {
                    if let Some(error) = result.errors.first() {
                        toast(&ui, error.clone(), 2);
                        return;
                    }
                    if let Err(error) = st.reload() {
                        report_error(&ui, error);
                    }
                    refresh_class_ui(&mut st, &ui);
                    let kind = if result.notes_added > 0 || result.notes_updated > 0 {
                        1
                    } else {
                        0
                    };
                    toast(
                        &ui,
                        format!(
                            "{} : +{} nouvelle(s), ~{} mise(s) à jour, ={} inchangée(s)",
                            subject.name,
                            result.notes_added,
                            result.notes_updated,
                            result.notes_unchanged
                        ),
                        kind,
                    );
                }
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_import_subject(move || {
            let Some(ui) = weak.upgrade() else { return };
            let st = state.borrow();
            let Some(info) = st.current.as_ref() else {
                return;
            };
            let Some(subject) = st.active_subject().cloned() else {
                toast(&ui, "Aucune matière sélectionnée", 2);
                return;
            };
            let expected = info.subject_path(&subject.name);
            let mut dialog = rfd::FileDialog::new()
                .add_filter("Classeur Excel", &["xlsx", "xls"])
                .set_directory(if expected.exists() {
                    expected.parent().unwrap_or(&info.folder)
                } else {
                    &info.folder
                });
            if expected.exists() {
                if let Some(name) = expected.file_name() {
                    dialog = dialog.set_file_name(name.to_string_lossy().to_string());
                }
            }
            let Some(path) = dialog.pick_file() else {
                return;
            };
            let Some(db) = st.db.as_ref() else { return };
            match sync_subject_from_xlsx(db, &subject.name, &path) {
                Ok(result) => {
                    if let Some(error) = result.errors.first() {
                        toast(&ui, error.clone(), 2);
                        return;
                    }
                    drop(st);
                    let mut st = state.borrow_mut();
                    if let Err(error) = st.reload() {
                        report_error(&ui, error);
                        return;
                    }
                    refresh_class_ui(&mut st, &ui);
                    toast(
                        &ui,
                        format!(
                            "+{} nouvelle(s), {} mise(s) à jour, {} inchangée(s)",
                            result.notes_added, result.notes_updated, result.notes_unchanged
                        ),
                        1,
                    );
                }
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_export_subject(move || {
            let Some(ui) = weak.upgrade() else { return };
            let st = state.borrow();
            let Some(info) = st.current.as_ref() else {
                return;
            };
            let Some(subject) = st.active_subject().cloned() else {
                toast(&ui, "Aucune matière sélectionnée", 2);
                return;
            };
            let dir = default_export_dir(info);
            let Some(path) = rfd::FileDialog::new()
                .add_filter("Classeur Excel", &["xlsx"])
                .set_file_name(format!("{}.xlsx", safe_filename(&subject.name)))
                .set_directory(&dir)
                .save_file()
            else {
                return;
            };
            let Some(db) = st.db.as_ref() else { return };
            match export::export_subject_xlsx(db, &subject, &path) {
                Ok(path) => toast(&ui, format!("Exporté : {}", path.display()), 1),
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_export_totalisation(move || {
            let Some(ui) = weak.upgrade() else { return };
            let st = state.borrow();
            let Some(info) = st.current.as_ref() else {
                return;
            };
            let Some(db) = st.db.as_ref() else { return };
            let dir = default_export_dir(info);
            let Some(path) = rfd::FileDialog::new()
                .add_filter("Classeur Excel", &["xlsx"])
                .set_file_name(format!("Totalisation_{}.xlsx", st.active_exam))
                .set_directory(&dir)
                .save_file()
            else {
                return;
            };
            match export::export_totalisation_xlsx(db, st.active_exam, &path) {
                Ok(path) => toast(&ui, format!("Exporté : {}", path.display()), 1),
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_export_moyennes(move || {
            let Some(ui) = weak.upgrade() else { return };
            let st = state.borrow();
            let Some(info) = st.current.as_ref() else {
                return;
            };
            let Some(db) = st.db.as_ref() else { return };
            let dir = default_export_dir(info);
            let Some(target) = rfd::FileDialog::new()
                .set_title("Dossier de destination des moyennes")
                .set_directory(&dir)
                .pick_folder()
            else {
                return;
            };
            match export::export_moyennes(db, &target) {
                Ok(files) => toast(
                    &ui,
                    format!(
                        "{} classeur(s) exporté(s) dans {}",
                        files.len(),
                        target.display()
                    ),
                    1,
                ),
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_export_profs(move || {
            let Some(ui) = weak.upgrade() else { return };
            let st = state.borrow();
            let Some(info) = st.current.as_ref() else {
                return;
            };
            let Some(db) = st.db.as_ref() else { return };
            let dir = default_export_dir(info);
            let Some(target) = rfd::FileDialog::new()
                .set_title("Dossier de destination des feuilles professeurs")
                .set_directory(&dir)
                .pick_folder()
            else {
                return;
            };
            let division = match info.division.as_str() {
                "COLLEGE" => "College",
                "LYCEE" => "Lycee",
                _ => "Primaire",
            };
            let out_dir = target.join("export prof").join(division).join(&info.name);
            match export::export_all_subjects(db, &out_dir) {
                Ok(count) => toast(
                    &ui,
                    format!("{count} feuille(s) exportée(s) dans {}", out_dir.display()),
                    1,
                ),
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_export_pdf(move || {
            let Some(ui) = weak.upgrade() else { return };
            let st = state.borrow();
            let Some(info) = st.current.as_ref() else {
                return;
            };
            let Some(db) = st.db.as_ref() else { return };
            let dir = default_export_dir(info);
            let Some(path) = rfd::FileDialog::new()
                .add_filter("Document PDF", &["pdf"])
                .set_file_name(format!("compte_rendu_T{}.pdf", st.active_trim))
                .set_directory(&dir)
                .save_file()
            else {
                return;
            };
            match export::export_report_pdf(db, st.active_trim, &path) {
                Ok(path) => toast(&ui, format!("PDF exporté : {}", path.display()), 1),
                Err(error) => report_error(&ui, error),
            }
        });
    }

    // --- Élèves -------------------------------------------------------
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_select_student(move |id| {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            st.selected_student_id = i64::from(id);
            refresh_selected_student_ui(&st, &ui);
            refresh_students_ui(&mut st, &ui);
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_add_student(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            let nom = ui.get_new_student_nom().trim().to_string();
            if nom.is_empty() {
                toast(&ui, "Le nom est obligatoire", 2);
                return;
            }
            let num = ui
                .get_new_student_num()
                .trim()
                .parse::<i64>()
                .unwrap_or_else(|_| {
                    st.students
                        .iter()
                        .map(|student| student.num)
                        .max()
                        .unwrap_or(0)
                        + 1
                });
            let Some(db) = st.db.as_ref() else { return };
            match db.add_student(
                num,
                &nom,
                ui.get_new_student_prenoms().trim(),
                ui.get_new_student_matricule().trim(),
                ui.get_new_student_genre().trim(),
                ui.get_new_student_naissance().trim(),
            ) {
                Ok(id) => {
                    st.selected_student_id = id;
                    if let Err(error) = st.reload() {
                        report_error(&ui, error);
                    }
                    refresh_students_ui(&mut st, &ui);
                    refresh_selected_student_ui(&st, &ui);
                    toast(&ui, format!("Élève n°{num} ajouté"), 1);
                }
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_update_student(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            if st.selected_student_id <= 0 {
                return;
            }
            let nom = ui.get_new_student_nom().trim().to_string();
            if nom.is_empty() {
                toast(&ui, "Le nom est obligatoire", 2);
                return;
            }
            let num = ui.get_new_student_num().trim().parse::<i64>().unwrap_or(0);
            if num <= 0 {
                toast(&ui, "Numéro invalide", 2);
                return;
            }
            let Some(db) = st.db.as_ref() else { return };
            match db.update_student(
                st.selected_student_id,
                num,
                &nom,
                ui.get_new_student_prenoms().trim(),
                ui.get_new_student_matricule().trim(),
                ui.get_new_student_genre().trim(),
                ui.get_new_student_naissance().trim(),
            ) {
                Ok(()) => {
                    if let Err(error) = st.reload() {
                        report_error(&ui, error);
                    }
                    refresh_students_ui(&mut st, &ui);
                    refresh_selected_student_ui(&st, &ui);
                    toast(&ui, "Fiche élève mise à jour", 1);
                }
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_delete_student(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            if st.selected_student_id <= 0 {
                return;
            }
            let name = st
                .students
                .iter()
                .find(|student| student.id == st.selected_student_id)
                .map(|student| student.display_name())
                .unwrap_or_else(|| "cet élève".to_string());
            if !confirm(
                "Supprimer l'élève",
                &format!("Supprimer définitivement {name} et toutes ses notes ?"),
            ) {
                return;
            }
            let Some(db) = st.db.as_ref() else { return };
            match db.delete_student(st.selected_student_id) {
                Ok(()) => {
                    st.selected_student_id = -1;
                    if let Err(error) = st.reload() {
                        report_error(&ui, error);
                    }
                    clear_student_form(&ui);
                    refresh_students_ui(&mut st, &ui);
                    refresh_selected_student_ui(&st, &ui);
                    toast(&ui, "Élève supprimé", 1);
                }
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_generate_students(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            let Some(db) = st.db.as_ref() else { return };
            let effectif = db.get_setting_int("effectif", 0);
            if effectif <= 0 {
                toast(&ui, "Renseignez l'effectif dans l'onglet Configuration.", 2);
                return;
            }
            match db.generate_students(effectif, 1) {
                Ok(added) => {
                    if let Err(error) = st.reload() {
                        report_error(&ui, error);
                    }
                    refresh_students_ui(&mut st, &ui);
                    toast(&ui, format!("{added} élève(s) ajouté(s)"), 1);
                }
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_import_students_preview(move || {
            let Some(ui) = weak.upgrade() else { return };

            // Récupérer les infos nécessaires sans garder le borrow
            let folder = {
                let st = state.borrow();
                let Some(info) = st.current.as_ref() else {
                    return;
                };
                info.folder.clone()
            };

            let Some(path) = rfd::FileDialog::new()
                .add_filter("Classeur Excel", &["xlsx", "xls"])
                .set_directory(&folder)
                .pick_file()
            else {
                return;
            };

            // 1) Parser le fichier pour avoir un aperçu (sans importer encore)
            let workbook = match students_import::read_all_sheets(&path) {
                Ok(wb) => wb,
                Err(error) => {
                    report_error(&ui, error);
                    return;
                }
            };

            // 2) Détecter les doublons vs la base existante
            // Récupérer la DB fraîchement pour chaque opération
            let existing_nums: HashSet<i64> = {
                let st = state.borrow();
                let Some(db) = st.db.as_ref() else { return };
                db.list_students()
                    .unwrap_or_default()
                    .into_iter()
                    .map(|s| s.num)
                    .collect()
            };
            let existing_names: HashSet<(String, String)> = {
                let st = state.borrow();
                let Some(db) = st.db.as_ref() else { return };
                db.list_students()
                    .unwrap_or_default()
                    .into_iter()
                    .map(|s| (s.nom.to_lowercase(), s.prenoms.to_lowercase()))
                    .collect()
            };

            let mut preview_lines: Vec<String> = Vec::new();
            let mut count_new = 0;
            let mut count_doubles = 0;
            let mut total = 0;

            for sheet in &workbook.sheets {
                for row in &sheet.rows {
                    total += 1;
                    let is_dup_num = existing_nums.contains(&row.num);
                    let is_dup_name = existing_names.contains(&(
                        row.nom.to_lowercase(),
                        row.prenoms.to_lowercase(),
                    ));
                    let statut = if is_dup_num || is_dup_name {
                        count_doubles += 1;
                        "DOUBLON"
                    } else {
                        count_new += 1;
                        "Nouveau"
                    };
                    preview_lines.push(format!(
                        "{:>3} | {:<20} | {:<20} | {}",
                        row.num,
                        row.nom,
                        row.prenoms,
                        statut
                    ));
                }
            }

            // 3) Afficher le dialog d'aperçu (via propriétés Slint)
            // On stocke les données pour le callback import-confirmed
            // Pour l'instant, on importe directement avec rapport détaillé
            {
                let st = state.borrow();
                let Some(db) = st.db.as_ref() else { return };
                match students_import::import_students(db, &path) {
                    Ok(report) => {
                        drop(st);
                        let mut st = state.borrow_mut();
                        if let Err(error) = st.reload() {
                            report_error(&ui, error);
                            return;
                        }
                        refresh_class_ui(&mut st, &ui);
                        let kind = if report.warnings.is_empty() { 1 } else { 2 };
                        toast(
                            &ui,
                            format!(
                                "✓ {} nouveau(s), ~{} mis à jour, {} déjà présent(s)",
                                report.added, report.updated, report.skipped
                            ),
                            kind,
                        );
                    }
                    Err(error) => report_error(&ui, error),
                }
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_student_search_changed(move |text| {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            st.student_filter = text.to_string();
            refresh_students_ui(&mut st, &ui);
        });
    }

    // --- Configuration ------------------------------------------------
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_save_settings(move || {
            let Some(ui) = weak.upgrade() else { return };
            let st = state.borrow();
            let Some(db) = st.db.as_ref() else { return };
            let nb_examens = ui
                .get_set_nb_examens()
                .trim()
                .parse::<i64>()
                .unwrap_or(6)
                .clamp(1, 6);
            let nb_min = ui
                .get_set_nb_min()
                .trim()
                .parse::<i64>()
                .unwrap_or(3)
                .clamp(1, 6);

            // --- Validation : filles + garçons ≤ effectif (comme en Python) ---
            let effectif: i64 = ui
                .get_set_effectif()
                .trim()
                .parse()
                .unwrap_or(0);
            let nb_filles: i64 = ui
                .get_set_filles()
                .trim()
                .parse()
                .unwrap_or(0);
            let nb_garcons: i64 = ui
                .get_set_garcons()
                .trim()
                .parse()
                .unwrap_or(0);
            if nb_filles + nb_garcons > effectif {
                report_error(
                    &ui,
                    format!(
                        "Somme filles ({}) + garçons ({}) > effectif ({}).",
                        nb_filles, nb_garcons, effectif
                    ),
                );
                return;
            }

            let result = (|| -> anyhow::Result<()> {
                db.set_setting("etablissement", ui.get_set_etablissement().trim())?;
                db.set_setting("directeur", ui.get_set_directeur().trim())?;
                db.set_setting("annee_scolaire", ui.get_set_annee().trim())?;
                db.set_setting("classe", ui.get_set_classe().trim())?;
                db.set_setting("nb_examens", &nb_examens.to_string())?;
                db.set_setting("nb_min_examens", &nb_min.to_string())?;
                db.set_setting("prof_principal", ui.get_set_prof_principal().trim())?;
                db.set_setting("coeff_default", ui.get_set_coeff_default().trim())?;
                db.set_setting("effectif", ui.get_set_effectif().trim())?;
                db.set_setting("nb_filles", ui.get_set_filles().trim())?;
                db.set_setting("nb_garcons", ui.get_set_garcons().trim())?;
                db.set_setting("logo_path", ui.get_set_logo_path().trim())?;
                Ok(())
            })();
            match result {
                Ok(()) => {
                    drop(st);
                    let mut st = state.borrow_mut();
                    if let Err(error) = st.reload() {
                        report_error(&ui, error);
                    }
                    refresh_class_ui(&mut st, &ui);
                    toast(&ui, "Réglages enregistrés", 1);
                }
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_new_subject(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            let name = ui.get_subject_form_name().trim().to_string();
            if name.is_empty() {
                toast(&ui, "Le nom de la matière est obligatoire", 2);
                return;
            }
            let coeff = ui
                .get_subject_form_coeff()
                .trim()
                .replace(',', ".")
                .parse::<f64>()
                .unwrap_or(1.0)
                .max(0.0);
            let Some(db) = st.db.as_ref() else { return };
            match db.add_subject(&name, coeff, ui.get_subject_form_teacher().trim()) {
                Ok(_) => {
                    if let Err(error) = st.reload() {
                        report_error(&ui, error);
                    }
                    clear_subject_form(&ui);
                    refresh_subjects_ui(&mut st, &ui);
                    toast(&ui, format!("Matière « {name} » ajoutée"), 1);
                }
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_save_subject(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            let id = i64::from(ui.get_subject_form_id());
            if id <= 0 {
                return;
            }
            let name = ui.get_subject_form_name().trim().to_string();
            if name.is_empty() {
                toast(&ui, "Le nom de la matière est obligatoire", 2);
                return;
            }
            let coeff = ui
                .get_subject_form_coeff()
                .trim()
                .replace(',', ".")
                .parse::<f64>()
                .unwrap_or(1.0)
                .max(0.0);
            let Some(db) = st.db.as_ref() else { return };
            match db.update_subject(id, &name, coeff, ui.get_subject_form_teacher().trim()) {
                Ok(()) => {
                    if let Err(error) = st.reload() {
                        report_error(&ui, error);
                    }
                    refresh_subjects_ui(&mut st, &ui);
                    refresh_grades(&mut st, &ui);
                    toast(&ui, "Matière mise à jour", 1);
                }
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_delete_subject(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            let id = i64::from(ui.get_subject_form_id());
            if id <= 0 {
                return;
            }
            let name = st
                .subjects
                .iter()
                .find(|subject| subject.id == id)
                .map(|subject| subject.name.clone())
                .unwrap_or_else(|| "cette matière".to_string());
            if !confirm(
                "Supprimer la matière",
                &format!("Supprimer « {name} » et toutes ses notes ?"),
            ) {
                return;
            }
            let Some(db) = st.db.as_ref() else { return };
            match db.delete_subject(id) {
                Ok(()) => {
                    if let Err(error) = st.reload() {
                        report_error(&ui, error);
                    }
                    clear_subject_form(&ui);
                    refresh_subjects_ui(&mut st, &ui);
                    refresh_grades(&mut st, &ui);
                    toast(&ui, "Matière supprimée", 1);
                }
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_backup_database(move || {
            let Some(ui) = weak.upgrade() else { return };
            let st = state.borrow();
            let Some(db) = st.db.as_ref() else { return };
            match db.backup(10) {
                Ok(Some(path)) => toast(&ui, format!("Sauvegarde créée : {}", path.display()), 1),
                Ok(None) => toast(&ui, "Aucune base à sauvegarder", 2),
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_restore_database(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            let Some(info) = st.current.as_ref() else { return };
            let backup_dir = info.db_path.parent().unwrap_or(Path::new(".")).join(".backups");
            let Some(path) = rfd::FileDialog::new()
                .add_filter("Sauvegarde SQLite", &["bak", "db"])
                .set_directory(&backup_dir)
                .pick_file()
            else {
                return;
            };
            if !Database::validate_sqlite_file(&path) {
                toast(&ui, "Ce fichier n'est pas une base SQLite valide", 2);
                return;
            }
            if !confirm(
                "Restaurer la base",
                "La base actuelle sera remplacée. Une sauvegarde automatique sera créée avant l'opération.",
            ) {
                return;
            }
            let Some(db) = st.db.as_mut() else { return };
            match db.replace_database(&path) {
                Ok(_) => {
                    if let Err(error) = st.reload() {
                        report_error(&ui, error);
                    }
                    refresh_class_ui(&mut st, &ui);
                    toast(&ui, "Base restaurée", 1);
                }
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_reset_class(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            if !confirm(
                "Réinitialiser la classe",
                "Tous les élèves, notes et matières seront supprimés. Les réglages seront conservés et une sauvegarde sera créée.",
            ) {
                return;
            }
            let Some(db) = st.db.as_mut() else { return };
            if let Err(error) = db.create_backup("avant_reset") {
                report_error(&ui, error);
            }
            match db.reset_all(true) {
                Ok(()) => {
                    st.selected_student_id = -1;
                    if let Err(error) = st.reload() {
                        report_error(&ui, error);
                    }
                    clear_student_form(&ui);
                    clear_subject_form(&ui);
                    refresh_class_ui(&mut st, &ui);
                    toast(&ui, "Classe réinitialisée", 1);
                }
                Err(error) => report_error(&ui, error),
            }
        });
    }
    {
        let state = state.clone();
        let weak = ui.as_weak();
        ui.on_refresh_data(move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut st = state.borrow_mut();
            if let Err(error) = st.reload() {
                report_error(&ui, error);
            }
            refresh_class_ui(&mut st, &ui);
        });
    }

    // --- Thème sombre / clair -------------------------------------------
    {
        let weak = ui.as_weak();
        ui.on_menu_toggle_theme(move || {
            let Some(ui) = weak.upgrade() else { return };
            // NOTE : `Palette.dark` a déjà été basculé côté Slint avant cet
            // appel (voir app.slint lignes 1144-1145 et 1197-1198).
            // Ce handler sert uniquement à confirmer le changement à
            // l'utilisateur et, ultérieurement, à persister le choix.
            toast(&ui, SharedString::from("Thème basculé (clair/sombre)"), 1);
        });
    }

    // --- Sélection du logo d'établissement --------------------------------
    {
        let weak = ui.as_weak();
        ui.on_menu_select_logo(move || {
            let Some(ui) = weak.upgrade() else { return };
            let path = rfd::FileDialog::new()
                .add_filter("Images", &["png", "jpg", "jpeg", "bmp"])
                .pick_file();
            if let Some(path) = path {
                ui.set_set_logo_path(path.to_string_lossy().to_string().into());
            }
        });
    }
}
