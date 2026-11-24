//! Cœur métier de Bulletin.
//!
//! Ce crate ne dépend d'aucune bibliothèque graphique. Il reprend
//! fidèlement le schéma SQLite, la découverte des classes et les
//! calculs de l'application Python d'origine.

pub mod calc;
pub mod class_create;
pub mod db;
pub mod export;
pub mod models;
pub mod students_import;
pub mod sync;
pub mod workspace;

pub use db::Database;
pub use models::*;
