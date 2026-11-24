use bulletin_core::{Database, calc};
use std::path::Path;

fn main() -> anyhow::Result<()> {
    let path = std::env::args().nth(1).expect("chemin de la base");
    let db = Database::open(Some(Path::new(&path)))?;

    let mut totals = serde_json::Map::new();
    for exam in 1..=6 {
        let result = calc::compute_totalisation(&db, exam)?;
        totals.insert(exam.to_string(), serde_json::to_value(result)?);
    }

    let mut trims = serde_json::Map::new();
    for trimestre in 1..=3 {
        trims.insert(
            trimestre.to_string(),
            serde_json::to_value(calc::compute_trimestre(&db, trimestre)?)?,
        );
    }

    let annual = calc::compute_annuelle(&db)?;
    let mut stats = serde_json::Map::new();
    for exam in 1..=6 {
        stats.insert(
            exam.to_string(),
            serde_json::to_value(calc::compute_stats(&db, exam)?)?,
        );
    }

    let dump = serde_json::json!({
        "path": db.path_string(),
        "totalisations": totals,
        "trimestres": trims,
        "annuelle": annual,
        "stats": stats,
    });
    println!("{}", serde_json::to_string(&dump)?);
    Ok(())
}
