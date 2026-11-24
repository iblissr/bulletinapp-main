//! Parité Python ↔ Rust sur les règles de coefficients par classe.
//!
//! Ce test n'asserte rien : il **imprime** les mêmes lignes que
//! `scripts/parity_coefficients.py`. Comparer les deux sorties :
//!
//! ```text
//! cargo test -p bulletin-core --test parity_dump -- --nocapture \
//!     | grep -P '^###|\t' > /tmp/rs.txt
//! python3 ../scripts/parity_coefficients.py > /tmp/py.txt
//! diff /tmp/py.txt /tmp/rs.txt
//! ```

use bulletin_core::db::{class_default_coeff, get_class_defaults};
use bulletin_core::workspace::{extract_level_key, normalize_class_name};

const NAMES: &[&str] = &[
    "6e I",
    "6ème 2",
    "3e I",
    "1ère L1",
    "2nde II",
    "TAI",
    "TAII",
    "TD",
    "TA1",
    "TA2",
    "1ERELI",
    "1ERELII",
    "1ereS",
    "1ERE L1",
    "1L1",
    "1ES",
    "3EME1",
    "4EME1",
    "4EME2",
    "5EME1",
    "6EME3",
    "2NDE1",
    "2NDE2",
    "2NDEA",
    "CM2",
    "PS",
    "TLE",
    "TALL",
    "TAD",
    "1ERES",
    "6 I",
    "6EMEI",
    "3EME",
    "CE1",
    "CP",
    "TIA",
    "IA",
    "1L",
    "1S",
    "1A",
    "6ème I",
    "5EMEII",
    "2NDEB",
    "1ère S",
    "TLE2",
    "TLEA",
    "CE2",
    "CM1",
    "6EME",
    "1E",
    "1",
    "T",
    "1EREL",
    "1°L1",
    "6eme 1",
    "4ème 2",
    "6EMEII",
    "T.A",
    "2nde 1",
    "1ère LII",
];

const PROBES: &[(&str, &str)] = &[
    ("Philosophie", "TA1"),
    ("Philosophie", "TAI"),
    ("Philosophie", "TD"),
    ("Philosophie", "1EREL1"),
    ("Philosophie", "2NDE1"),
    ("Physique-chimie", "4EME1"),
    ("Physique-chimie", "4EME2"),
    ("Physique-chimie", "6EME3"),
    ("Physique-chimie", "3EME1"),
    ("EVA", "6EME3"),
    ("Histo-geo", "4EME1"),
    ("Éducation à la Vie", "6EME3"),
    ("Histoire-Géographie", "1EREL1"),
    ("Malagasy", "1ERES"),
    ("Philosophie", "TALL"),
    ("Philosophie", "TAD"),
    ("Philosophie", "TLE"),
];

#[test]
fn parity_dump() {
    println!("### normalize_class_name / extract_level_key");
    for name in NAMES {
        println!(
            "{name}\t{}\t{}",
            normalize_class_name(name),
            extract_level_key(name)
        );
    }

    println!("### get_class_defaults");
    for name in NAMES {
        let rows: Vec<String> = get_class_defaults(name, None)
            .into_iter()
            .map(|(subject, coeff)| format!("{subject}={coeff}"))
            .collect();
        println!("{name}\t{}", rows.join(" "));
    }

    println!("### class_default_coeff");
    for (subject, class) in PROBES {
        let value = class_default_coeff(subject, class, None)
            .map(|coeff| coeff.to_string())
            .unwrap_or_else(|| "None".to_string());
        println!("{subject}\t{class}\t{value}");
    }
}
