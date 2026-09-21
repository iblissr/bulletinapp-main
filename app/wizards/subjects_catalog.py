"""Catalogue de matières par section (Maternelle / Primaire / Collège / Lycée).

Utilisé par l'assistant de création de classe pour pré-remplir la
table ``subjects`` de la nouvelle base SQLite.

Les coefficients sont indicatifs (issus des pratiques courantes à
Madagascar) et restent modifiables par l'utilisateur dans l'onglet
Configuration après création de la classe.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SectionDef:
    """Définition d'une section (Maternelle, Primaire, Collège, Lycée)."""

    key: str
    label: str
    description: str
    levels: tuple[tuple[str, str], ...]
    """Liste des niveaux : ``(key, label)`` — ex. ``("6EME", "6ème")``."""
    subjects: tuple[tuple[str, float], ...]
    """Liste des matières par défaut : ``(nom, coefficient)``."""


# ---------------------------------------------------------------------------
#  Définition des sections
# ---------------------------------------------------------------------------
SECTIONS: dict[str, SectionDef] = {

    "MATER": SectionDef(
        key="MATER",
        label="Maternelle",
        description="Petite, Moyenne et Grande Sections (PS, MS, GS)",
        levels=(
            ("PS", "Petite Section"),
            ("MS", "Moyenne Section"),
            ("GS", "Grande Section"),
        ),
        subjects=(
            # Pas de notation chiffrée en maternelle, mais on crée des
            # « domaines » pour que l'app reste structurée et que les
            # profs puissent cocher des compétences.
            ("Langage oral", 1.0),
            ("Langage écrit", 1.0),
            ("Activités numériques", 1.0),
            ("Éveil scientifique", 1.0),
            ("Activités physiques", 1.0),
            ("Activités artistiques", 1.0),
            ("Vie sociale", 1.0),
        ),
    ),

    "PRIM": SectionDef(
        key="PRIM",
        label="Primaire",
        description="Du CP au CM2",
        levels=(
            ("CP",   "CP (Cours Préparatoire)"),
            ("CE1",  "CE1 (Cours Élémentaire 1)"),
            ("CE2",  "CE2 (Cours Élémentaire 2)"),
            ("CM1",  "CM1 (Cours Moyen 1)"),
            ("CM2",  "CM2 (Cours Moyen 2)"),
        ),
        subjects=(
            ("Malagasy",             4.0),
            ("Français",             4.0),
            ("Mathématiques",        4.0),
            ("Sciences et Techno.",  2.0),
            ("Histoire-Géographie",  2.0),
            ("Éducation civique",    1.0),
            ("EPS",                  1.0),
            ("Arts plastiques",      1.0),
            ("Éducation musicale",   1.0),
        ),
    ),

    "COLLEGE": SectionDef(
        key="COLLEGE",
        label="Collège",
        description="De la 6ème à la 3ème",
        levels=(
            ("6EME", "6ème"),
            ("5EME", "5ème"),
            ("4EME", "4ème"),
            ("3EME", "3ème"),
        ),
        subjects=(
            ("Malagasy",        4.0),
            ("Français",        3.0),
            ("Anglais",         2.0),
            ("Histo-geo",       4.0),
            ("Mathématiques",   2.0),
            ("Physique-chimie", 2.0),
            ("SVT",             2.0),
            ("EPS",             1.0),
            ("EVA",             1.0),
            ("Religion",        1.0),
        ),
    ),

    "LYCEE": SectionDef(
        key="LYCEE",
        label="Lycée",
        description="De la 2nde à la Terminale",
        levels=(
            ("2NDE", "2nde"),
            ("1ERE", "1ère"),
            ("TLE",  "Terminale"),
        ),
        subjects=(
            ("Malagasy",        4.0),
            ("Français",        3.0),
            ("Anglais",         2.0),
            ("Philosophie",     2.0),
            ("Histo-geo",       4.0),
            ("Mathématiques",   2.0),
            ("Physique-chimie", 2.0),
            ("SVT",             2.0),
            ("EPS",             1.0),
            ("EVA",             1.0),
            ("Religion",        1.0),
        ),
    ),
}


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------
def get_section(key: str) -> Optional[SectionDef]:
    return SECTIONS.get(key.upper())


def list_sections() -> list[SectionDef]:
    """Retourne les sections dans l'ordre d'affichage."""
    return [SECTIONS["MATER"], SECTIONS["PRIM"],
            SECTIONS["COLLEGE"], SECTIONS["LYCEE"]]


# ---------------------------------------------------------------------------
#  Sous-classes : génération des noms
# ---------------------------------------------------------------------------
# Trois patterns sont proposés :
# - "numeric" : 1, 2, 3 → 6EME1, 6EME2
# - "roman"   : I, II, III → 6EMEI, 6EMEII
# - "alpha"   : A, B, C → 6EMEA, 6EMEB
# - "custom"  : l'utilisateur saisit chaque suffixe

PATTERNS: tuple[tuple[str, str], ...] = (
    ("numeric", "Numérique (1, 2, 3…)"),
    ("roman",   "Romain (I, II, III…)"),
    ("alpha",   "Lettres (A, B, C…)"),
    ("custom",  "Personnalisé (saisie libre)"),
)


def expand_pattern(level: str, pattern: str, count: int,
                   custom_suffixes: list[str] | None = None) -> list[str]:
    """Génère la liste des noms de sous-classes pour un niveau donné.

    Exemples
    --------
    >>> expand_pattern("6EME", "numeric", 3)
    ['6EME1', '6EME2', '6EME3']
    >>> expand_pattern("6EME", "roman", 2)
    ['6EMEI', '6EMEII']
    >>> expand_pattern("6EME", "alpha", 2)
    ['6EMEA', '6EMEB']
    >>> expand_pattern("1ERE", "custom", 3, ["LI", "LII", "S"])
    ['1ERELI', '1ERELII', '1ERES']
    """
    level = level.strip().upper()
    if count < 1:
        return []
    if pattern == "numeric":
        return [f"{level}{i}" for i in range(1, count + 1)]
    if pattern == "roman":
        roman = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
        if count > len(roman) - 1:
            raise ValueError(
                f"Pattern romain limité à {len(roman) - 1} sous-classes."
            )
        return [f"{level}{roman[i]}" for i in range(1, count + 1)]
    if pattern == "alpha":
        if count > 26:
            raise ValueError("Pattern lettres limité à 26 sous-classes.")
        return [f"{level}{chr(ord('A') + i)}" for i in range(count)]
    if pattern == "custom":
        if not custom_suffixes or len(custom_suffixes) != count:
            raise ValueError(
                f"Pattern personnalisé : il faut exactement {count} suffixes."
            )
        return [f"{level}{s.strip().upper()}" for s in custom_suffixes]
    raise ValueError(f"Pattern inconnu : {pattern!r}")
