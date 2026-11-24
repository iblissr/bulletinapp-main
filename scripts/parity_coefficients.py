"""Parité Python ↔ Rust : noms de classe, niveau et coefficients.

Sortie formatée exactement comme `bulletin-rs/crates/bulletin-core/tests/parity_dump.rs`
: les deux fichiers sont à comparer ligne à ligne.

    python3 scripts/parity_coefficients.py > /tmp/py.txt
    cd bulletin-rs && cargo test -p bulletin-core --test parity_dump -- --nocapture \
        | grep -P '^###|\\t' > /tmp/rs.txt
    diff /tmp/py.txt /tmp/rs.txt
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.workspace import extract_level_key, normalize_class_name  # noqa: E402
from app.db import get_class_defaults, class_default_coeff  # noqa: E402

NAMES = [
    "6e I", "6ème 2", "3e I", "1ère L1", "2nde II", "TAI", "TAII", "TD",
    "TA1", "TA2", "1ERELI", "1ERELII", "1ereS", "1ERE L1", "1L1", "1ES",
    "3EME1", "4EME1", "4EME2", "5EME1", "6EME3", "2NDE1", "2NDE2", "2NDEA",
    "CM2", "PS", "TLE", "TALL", "TAD", "1ERES", "6 I", "6EMEI",
    "3EME", "CE1", "CP", "TIA", "IA",
    "1L", "1S", "1A", "6ème I", "5EMEII", "2NDEB", "1ère S", "TLE2",
    "TLEA", "CE2", "CM1", "6EME", "1E", "1", "T", "1EREL", "1°L1",
    "6eme 1", "4ème 2", "6EMEII", "T.A", "2nde 1", "1ère LII",
]

PROBES = [
    ("Philosophie", "TA1"), ("Philosophie", "TAI"), ("Philosophie", "TD"),
    ("Philosophie", "1EREL1"), ("Philosophie", "2NDE1"),
    ("Physique-chimie", "4EME1"), ("Physique-chimie", "4EME2"),
    ("Physique-chimie", "6EME3"), ("Physique-chimie", "3EME1"),
    ("EVA", "6EME3"), ("Histo-geo", "4EME1"), ("Éducation à la Vie", "6EME3"),
    ("Histoire-Géographie", "1EREL1"), ("Malagasy", "1ERES"),
    ("Philosophie", "TALL"), ("Philosophie", "TAD"), ("Philosophie", "TLE"),
]

print("### normalize_class_name / extract_level_key")
for n in NAMES:
    print(f"{n}\t{normalize_class_name(n)}\t{extract_level_key(n)}")

print("### get_class_defaults")
for n in NAMES:
    rows = get_class_defaults(n)
    print(f"{n}\t" + " ".join(f"{m}={c:g}" for m, c, _ in rows))

print("### class_default_coeff")
for subject, cls in PROBES:
    value = class_default_coeff(subject, cls)
    print(f"{subject}\t{cls}\t{'None' if value is None else format(value, 'g')}")
