//! Calculs de totalisation, moyennes trimestrielles, annuelle et
//! statistiques de compte rendu. Formules identiques au code Python.

use crate::db::Database;
use crate::models::{AnnualRow, ClassStats, Subject, TotalRow, Totalisation, TrimRow, round2};
use anyhow::{Result, bail};
use std::collections::HashMap;

/// Totalisation d'un examen (1..6).
pub fn compute_totalisation(db: &Database, exam_num: i64) -> Result<Totalisation> {
    let subjects: Vec<Subject> = db.list_subjects()?;
    let students = db.list_students()?;
    let nb_min = db.get_setting_int("nb_min_examens", 1);
    let total_coeff: f64 = subjects.iter().map(|s| s.coeff).sum();
    let grades = db.grades_for_exam(exam_num)?;

    let mut rows: Vec<TotalRow> = Vec::with_capacity(students.len());
    for student in students {
        let student_grades = grades.get(&student.id);
        let mut notes: HashMap<i64, Option<f64>> = HashMap::new();
        let mut total = 0.0;
        let mut coefs_used = 0.0;
        let mut nb_used = 0i64;

        for subject in &subjects {
            let value = student_grades.and_then(|m| m.get(&subject.id)).copied();
            notes.insert(subject.id, value);
            if let Some(value) = value {
                total += value;
                coefs_used += subject.coeff;
                nb_used += 1;
            }
        }

        let valid = nb_used >= nb_min && coefs_used > 0.0;
        rows.push(TotalRow {
            student,
            notes,
            total: if valid { Some(round2(total)) } else { None },
            moy: if valid {
                Some(round2(total / coefs_used))
            } else {
                None
            },
            rank: None,
            valid,
        });
    }

    assign_total_ranks(&mut rows);
    Ok(Totalisation {
        rows,
        subjects,
        total_coeff,
    })
}

fn assign_total_ranks(rows: &mut [TotalRow]) {
    let mut valid: Vec<usize> = rows
        .iter()
        .enumerate()
        .filter(|(_, row)| row.valid)
        .map(|(index, _)| index)
        .collect();
    valid.sort_by(|&a, &b| {
        rows[b]
            .moy
            .partial_cmp(&rows[a].moy)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    for (rank, index) in valid.into_iter().enumerate() {
        rows[index].rank = Some(rank + 1);
    }
}

/// Moyennes d'un trimestre (1, 2 ou 3).
pub fn compute_trimestre(db: &Database, trimestre: i64) -> Result<Vec<TrimRow>> {
    if !(1..=3).contains(&trimestre) {
        bail!("trimestre doit être 1, 2 ou 3");
    }
    let n_mj = 2 * trimestre - 1;
    let n_co = 2 * trimestre;
    let rows_mj = compute_totalisation(db, n_mj)?;
    let rows_co = compute_totalisation(db, n_co)?;

    let moy_mj: HashMap<i64, &TotalRow> = rows_mj.rows.iter().map(|r| (r.student.id, r)).collect();
    let moy_co: HashMap<i64, &TotalRow> = rows_co.rows.iter().map(|r| (r.student.id, r)).collect();

    let students = db.list_students()?;
    let mut out = Vec::with_capacity(students.len());
    for student in students {
        let a = moy_mj.get(&student.id).copied();
        let b = moy_co.get(&student.id).copied();
        let m_moy = a.and_then(|r| if r.valid { r.moy } else { None });
        let c_moy = b.and_then(|r| if r.valid { r.moy } else { None });
        let m_total = a.and_then(|r| if r.valid { r.total } else { None });
        let c_total = b.and_then(|r| if r.valid { r.total } else { None });

        let (tot, moy) = if m_moy.is_some() || c_moy.is_some() {
            let m = m_moy.unwrap_or(0.0);
            let c = c_moy.unwrap_or(0.0);
            let tot = round2(m + c);
            let weighted = m * 1.0 + c * 2.0;
            let mut coeff = 0.0;
            if m_moy.is_some() {
                coeff += 1.0;
            }
            if c_moy.is_some() {
                coeff += 2.0;
            }
            let moy = if coeff > 0.0 {
                Some(round2(weighted / coeff))
            } else {
                None
            };
            (Some(tot), moy)
        } else {
            (None, None)
        };

        out.push(TrimRow {
            student,
            m_moy,
            c_moy,
            m_total,
            c_total,
            tot,
            moy,
            rank: None,
        });
    }

    assign_trim_ranks(&mut out);
    Ok(out)
}

fn assign_trim_ranks(rows: &mut [TrimRow]) {
    let mut valid: Vec<usize> = rows
        .iter()
        .enumerate()
        .filter(|(_, row)| row.moy.is_some())
        .map(|(index, _)| index)
        .collect();
    valid.sort_by(|&a, &b| {
        rows[b]
            .moy
            .partial_cmp(&rows[a].moy)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    for (rank, index) in valid.into_iter().enumerate() {
        rows[index].rank = Some(rank + 1);
    }
}

/// Moyenne générale annuelle : 3 M.J. (×1) + 3 compos (×2).
pub fn compute_annuelle(db: &Database) -> Result<Vec<AnnualRow>> {
    let students = db.list_students()?;
    let mut tot_data: HashMap<i64, HashMap<i64, Option<f64>>> = HashMap::new();
    for n in 1..=6 {
        let totalisation = compute_totalisation(db, n)?;
        for row in totalisation.rows {
            tot_data
                .entry(row.student.id)
                .or_default()
                .insert(n, row.moy);
        }
    }

    let mut out = Vec::with_capacity(students.len());
    for student in students {
        let data = tot_data.get(&student.id);
        let vals: [Option<f64>; 6] = std::array::from_fn(|index| {
            data.and_then(|m| m.get(&(index as i64 + 1)).copied().flatten())
        });

        let mut weighted_sum = 0.0;
        let mut coeff_sum = 0.0;
        let mut raw_sum = 0.0;
        let mut any = false;
        for (index, value) in vals.iter().enumerate() {
            if let Some(value) = value {
                any = true;
                let coeff = if index % 2 == 0 { 1.0 } else { 2.0 };
                weighted_sum += value * coeff;
                coeff_sum += coeff;
                raw_sum += value;
            }
        }

        let (total, mga) = if any && coeff_sum > 0.0 {
            (
                Some(round2(raw_sum)),
                Some(round2(weighted_sum / coeff_sum)),
            )
        } else {
            (None, None)
        };

        out.push(AnnualRow {
            student,
            mj1: vals[0],
            co1: vals[1],
            mj2: vals[2],
            co2: vals[3],
            mj3: vals[4],
            co3: vals[5],
            total,
            mga,
            rank: None,
        });
    }

    let mut valid: Vec<usize> = out
        .iter()
        .enumerate()
        .filter(|(_, row)| row.mga.is_some())
        .map(|(index, _)| index)
        .collect();
    valid.sort_by(|&a, &b| {
        out[b]
            .mga
            .partial_cmp(&out[a].mga)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    for (rank, index) in valid.into_iter().enumerate() {
        out[index].rank = Some(rank + 1);
    }
    Ok(out)
}

/// Statistiques utilisées par le compte rendu.
pub fn compute_stats(db: &Database, exam_num: i64) -> Result<ClassStats> {
    let totalisation = compute_totalisation(db, exam_num)?;
    let students = db.list_students()?;
    let classed: Vec<&TotalRow> = totalisation.rows.iter().filter(|row| row.valid).collect();

    let moyenne_classe = if classed.is_empty() {
        None
    } else {
        let sum: f64 = classed.iter().filter_map(|row| row.moy).sum();
        Some(round2(sum / classed.len() as f64))
    };

    let mut nb_above_avg_per_subject = HashMap::new();
    for subject in &totalisation.subjects {
        let threshold = 10.0 * subject.coeff;
        let count = classed
            .iter()
            .filter(|row| {
                row.notes
                    .get(&subject.id)
                    .and_then(|value| *value)
                    .map(|value| value >= threshold)
                    .unwrap_or(false)
            })
            .count();
        nb_above_avg_per_subject.insert(subject.id, count);
    }

    let mut distribution = Vec::new();
    for seuil in (3..=18).rev() {
        let count = classed
            .iter()
            .filter(|row| {
                row.moy
                    .map(|moy| moy >= seuil as f64 && moy < (seuil + 1) as f64)
                    .unwrap_or(false)
            })
            .count();
        distribution.push((seuil, count));
    }

    Ok(ClassStats {
        effectif: students.len(),
        classes: classed.len(),
        moyenne_classe,
        nb_above_avg_per_subject,
        distribution,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::Database;

    fn seed_fixture() -> Database {
        let db = Database::open_in_memory().unwrap();
        // Matières : 3 coefficients 1, 2, 3.
        db.clear_subjects().unwrap();
        db.add_subject("A", 1.0, "").unwrap();
        db.add_subject("B", 2.0, "").unwrap();
        db.add_subject("C", 3.0, "").unwrap();
        let s1 = db.add_student(1, "Alpha", "", "", "", "").unwrap();
        let s2 = db.add_student(2, "Beta", "", "", "", "").unwrap();
        let s3 = db.add_student(3, "Gamma", "", "", "", "").unwrap();
        db.set_setting("nb_min_examens", "2").unwrap();
        let subjects = db.list_subjects().unwrap();

        // Examen 1 : notes pondérées (sur 20 × coef).
        db.set_grade(s1, subjects[0].id, 1, Some(10.0)).unwrap();
        db.set_grade(s1, subjects[1].id, 1, Some(30.0)).unwrap();
        db.set_grade(s1, subjects[2].id, 1, Some(45.0)).unwrap(); // total 85 / 6 = 14.1667

        db.set_grade(s2, subjects[0].id, 1, Some(20.0)).unwrap();
        db.set_grade(s2, subjects[1].id, 1, Some(40.0)).unwrap();
        db.set_grade(s2, subjects[2].id, 1, Some(60.0)).unwrap(); // total 120 / 6 = 20

        // s3 n'a qu'une note (< nb_min) → NC
        db.set_grade(s3, subjects[0].id, 1, Some(15.0)).unwrap();

        // Examen 2 (compo)
        db.set_grade(s1, subjects[0].id, 2, Some(8.0)).unwrap();
        db.set_grade(s1, subjects[1].id, 2, Some(24.0)).unwrap();
        db.set_grade(s1, subjects[2].id, 2, Some(36.0)).unwrap(); // 68 / 6 = 11.3333
        db.set_grade(s2, subjects[0].id, 2, Some(12.0)).unwrap();
        db.set_grade(s2, subjects[1].id, 2, Some(24.0)).unwrap();
        db.set_grade(s2, subjects[2].id, 2, Some(36.0)).unwrap(); // 72 / 6 = 12

        db
    }

    #[test]
    fn totalisation_matches_python_formulas() {
        let db = seed_fixture();
        let result = compute_totalisation(&db, 1).unwrap();
        assert_eq!(result.rows.len(), 3);

        let alpha = &result.rows[0];
        assert!(alpha.valid);
        assert_eq!(alpha.total, Some(85.0));
        assert_eq!(alpha.moy, Some(14.17));

        let beta = &result.rows[1];
        assert_eq!(beta.moy, Some(20.0));
        assert_eq!(beta.rank, Some(1));
        assert_eq!(alpha.rank, Some(2));

        let gamma = &result.rows[2];
        assert!(!gamma.valid);
        assert_eq!(gamma.moy, None);
        assert_eq!(gamma.rank, None);
    }

    #[test]
    fn trimestre_matches_python_formulas() {
        let db = seed_fixture();
        let rows = compute_trimestre(&db, 1).unwrap();
        let alpha = &rows[0];
        assert_eq!(alpha.m_moy, Some(14.17));
        assert_eq!(alpha.c_moy, Some(11.33));
        assert_eq!(alpha.tot, Some(25.5));
        // (14.17 + 2 × 11.33) / 3 = 12.2766 → 12.28
        assert_eq!(alpha.moy, Some(12.28));
        assert_eq!(alpha.m_total, Some(85.0));
        assert_eq!(alpha.c_total, Some(68.0));

        // Beta : (20 + 2 × 12) / 3 = 14.6667 → 14.67
        assert_eq!(rows[1].moy, Some(14.67));
        assert_eq!(rows[1].rank, Some(1));
        assert_eq!(alpha.rank, Some(2));
    }

    #[test]
    fn annuelle_matches_python_formulas() {
        let db = seed_fixture();
        let rows = compute_annuelle(&db).unwrap();
        let alpha = &rows[0];
        assert_eq!(alpha.mj1, Some(14.17));
        assert_eq!(alpha.co1, Some(11.33));
        assert_eq!(alpha.total, Some(25.5));
        // (14.17 × 1 + 11.33 × 2) / 3 = 12.2766 → 12.28
        assert_eq!(alpha.mga, Some(12.28));

        let beta = &rows[1];
        assert_eq!(beta.mga, Some(14.67));
        assert_eq!(beta.rank, Some(1));
    }

    #[test]
    fn stats_match_python_formulas() {
        let db = seed_fixture();
        let stats = compute_stats(&db, 1).unwrap();
        assert_eq!(stats.effectif, 3);
        assert_eq!(stats.classes, 2);
        // (14.17 + 20) / 2 = 17.085 → 17.09
        assert_eq!(stats.moyenne_classe, Some(17.09));
        assert_eq!(
            stats.distribution.iter().find(|(s, _)| *s == 14).unwrap().1,
            1
        );
    }
}
