//! Modèles métier partagés entre l'UI, les calculs et les imports.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Matière enseignée dans une classe.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Subject {
    pub id: i64,
    pub name: String,
    pub coeff: f64,
    pub teacher: String,
    pub position: i64,
}

impl Subject {
    /// Abréviation utilisée dans les en-têtes compacts (3 lettres).
    pub fn abbrev(&self) -> String {
        let n = self.name.trim();
        n.chars().take(3).collect()
    }
}

/// Élève inscrit dans une classe.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Student {
    pub id: i64,
    pub num: i64,
    pub matricule: String,
    pub nom: String,
    pub prenoms: String,
    pub genre: String,
    pub naissance: String,
}

impl Student {
    pub fn full_name(&self) -> String {
        if self.prenoms.trim().is_empty() {
            self.nom.clone()
        } else {
            format!("{} {}", self.nom, self.prenoms).trim().to_string()
        }
    }

    /// Nom affiché quand le nom de famille est vide (élèves générés).
    pub fn display_name(&self) -> String {
        let n = self.full_name();
        if n.trim().is_empty() {
            format!("Élève {}", self.num)
        } else {
            n
        }
    }
}

/// Ligne de totalisation d'un examen (1..6).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TotalRow {
    pub student: Student,
    /// Notes par identifiant de matière. `None` = note absente.
    pub notes: HashMap<i64, Option<f64>>,
    /// Somme brute des notes pondérées (None si l'élève est non classé).
    pub total: Option<f64>,
    /// Moyenne pondérée sur 20 (None si non classé).
    pub moy: Option<f64>,
    pub rank: Option<usize>,
    pub valid: bool,
}

/// Résultat complet d'une totalisation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Totalisation {
    pub rows: Vec<TotalRow>,
    pub subjects: Vec<Subject>,
    /// Somme des coefficients de toutes les matières.
    pub total_coeff: f64,
}

/// Ligne de moyenne trimestrielle.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrimRow {
    pub student: Student,
    /// Moyenne du M.J. (coefficient 1).
    pub m_moy: Option<f64>,
    /// Moyenne de la composition (coefficient 2).
    pub c_moy: Option<f64>,
    /// Total brut du M.J.
    pub m_total: Option<f64>,
    /// Total brut de la composition.
    pub c_total: Option<f64>,
    /// Somme brute des deux moyennes (sur 40).
    pub tot: Option<f64>,
    /// Moyenne pondérée du trimestre : (M.J. ×1 + Compo ×2) / 3.
    pub moy: Option<f64>,
    pub rank: Option<usize>,
}

/// Ligne de moyenne annuelle (6 notes : 3 M.J. + 3 compos).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnnualRow {
    pub student: Student,
    pub mj1: Option<f64>,
    pub co1: Option<f64>,
    pub mj2: Option<f64>,
    pub co2: Option<f64>,
    pub mj3: Option<f64>,
    pub co3: Option<f64>,
    /// Somme brute des 6 notes (sur 120).
    pub total: Option<f64>,
    /// Moyenne générale annuelle pondérée (M.J. ×1, Compo ×2).
    pub mga: Option<f64>,
    pub rank: Option<usize>,
}

/// Statistiques de classe pour le compte rendu.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClassStats {
    pub effectif: usize,
    pub classes: usize,
    pub moyenne_classe: Option<f64>,
    /// Nombre d'élèves au-dessus de 10/20 par matière.
    pub nb_above_avg_per_subject: HashMap<i64, usize>,
    /// Répartition par tranche : 18..3 → nombre d'élèves.
    pub distribution: Vec<(u8, usize)>,
}

/// Arrondi à 2 décimales, avec le même comportement que `round(x, 2)`
/// en Python (arrondi au plus proche, demi vers le pair).
pub fn round2(value: f64) -> f64 {
    if !value.is_finite() {
        return value;
    }
    format!("{value:.2}").parse().unwrap_or(value)
}

/// Formate une note pour l'affichage : `12.5` → `"12.5"`, `None` → `"—"`.
pub fn fmt_note(value: Option<f64>) -> String {
    match value {
        Some(v) if v.fract() == 0.0 => format!("{v:.0}"),
        Some(v) => {
            let s = format!("{v:.2}");
            s.trim_end_matches('0').trim_end_matches('.').to_string()
        }
        None => "—".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round2_matches_python_half_even() {
        assert_eq!(round2(12.345), 12.35);
        assert_eq!(round2(2.675), 2.67); // 2.675 est en réalité 2.67499…
        assert_eq!(round2(10.0), 10.0);
    }

    #[test]
    fn student_full_name_keeps_order() {
        let s = Student {
            id: 1,
            num: 1,
            matricule: String::new(),
            nom: "Rakoto".into(),
            prenoms: "Jean".into(),
            genre: String::new(),
            naissance: String::new(),
        };
        assert_eq!(s.full_name(), "Rakoto Jean");
    }
}
