"""Couche persistance SQLite.

Schéma :
- settings (key, value)        : paramètres établissement / classe
- subjects (id, name, coeff, teacher, position)
- students (id, num, matricule, nom, prenoms, genre, naissance)
- grades   (student_id, subject_id, exam_num, value)
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Iterator

if TYPE_CHECKING:
    from .models import clear_cache as _clear_cache
else:
    # Import différé pour éviter les cycles
    def _clear_cache():
        from .models import clear_cache
        clear_cache()

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bulletin.db"
)


SCHEMA = """
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
    genre     TEXT DEFAULT '',
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
"""

DEFAULT_SETTINGS = {
    "etablissement": "Lycée Saint Joseph",
    "directeur": "Directeur",
    "annee_scolaire": "2025-2026",
    "classe": "1ERELI",
    "nb_examens": "6",
    "effectif": "45",
    "nb_filles": "",
    "nb_garcons": "",
    "nb_min_examens": "3",
    "prof_principal": "",
    "logo_path": "",
    # Apparence
    "accent_color": "",  # vide = palette par défaut ; sinon #RRGGBB
    # Export
    "export_profs_path": "",
    "export_totalisation_path": "",
    "export_moyennes_path": "",
    "export_cr_path": "",
}

# 10 matières par défaut (filière Collège du modèle Excel)
DEFAULT_SUBJECTS = [
    ("Malagasy", 3, ""),
    ("Français", 3, ""),
    ("Anglais", 2, ""),
    ("Histoire-Géographie", 3, ""),
    ("Mathématiques", 3, ""),
    ("Physique-chimie", 3, ""),
    ("SVT", 3, ""),
    ("EPS", 1, ""),
    ("Éducation à la Vie", 1, ""),
    ("Religion", 1, ""),
]


# ---------------------------------------------------------------------------
#  Coefficients par défaut, PAR CLASSE
# ---------------------------------------------------------------------------
# Source de vérité : ``memory/decisions/coefficients-par-classe.md``
# (lus en cellule **C4** des .xlsx des 17 classes le 2026-09-20).
# Chaque classe a SES coefficients : les listes ci-dessous sont les
# « groupes » du tableau, combinés par :func:`get_class_defaults`.
#
#   Groupe      Classes                         Particularité
#   ----------  ------------------------------  ----------------------------
#   COLLEGE     3EME1, 3EME2, 4EME1             Physique-chimie = 3
#   COLLEGE     4EME2, 5EME1/2, 6EME1/2/3       Physique-chimie = 2
#   LYCEE_G1    1EREL1, 1EREL2, TA1, TA2        Philosophie 2 (4 en TA)
#   LYCEE_G2    1ERES, TD                       Maths/PC/SVT = 4
#   LYCEE_G3    2NDE1, 2NDE2                    pas de Philosophie
#
# Philosophie n'existe qu'au Lycée (1ère, Terminale) : jamais au Collège,
# jamais en 2nde — voir LEVEL_SUBJECT_RESTRICTIONS.

# Collège — Physique-chimie = 3 (3EME1, 3EME2, 4EME1)
COEFFS_COLLEGE = [
    ("Religion", 1, ""),
    ("Éducation à la Vie", 1, ""),
    ("Malagasy", 3, ""),
    ("Français", 3, ""),
    ("Anglais", 2, ""),
    ("Histoire-Géographie", 3, ""),
    ("Mathématiques", 3, ""),
    ("SVT", 3, ""),
    ("Physique-chimie", 3, ""),
    ("EPS", 1, ""),
]

# Lycée — groupe 1 : 1ère L (1EREL1, 1EREL2) + TAI/TAII
# Philosophie = 2 ici ; portée à 4 pour TA1/TA2 par
# ``CLASS_COEFF_OVERRIDES`` (« TA » → philosophie : 4.0).
COEFFS_LYCEE_G1 = [
    ("Religion", 1, ""),
    ("Éducation à la Vie", 1, ""),
    ("Malagasy", 4, ""),
    ("Français", 3, ""),
    ("Anglais", 2, ""),
    ("Histoire-Géographie", 4, ""),
    ("Mathématiques", 2, ""),
    ("SVT", 2, ""),
    ("Physique-chimie", 2, ""),
    ("EPS", 1, ""),
    ("Philosophie", 2, ""),
]

# Lycée — groupe 2 : 1ère S (1ERES) et TD (groupe scientifique)
COEFFS_LYCEE_G2 = [
    ("Religion", 1, ""),
    ("Éducation à la Vie", 1, ""),
    ("Malagasy", 3, ""),
    ("Français", 2, ""),
    ("Anglais", 1, ""),
    ("Histoire-Géographie", 2, ""),
    ("Mathématiques", 4, ""),
    ("SVT", 4, ""),
    ("Physique-chimie", 4, ""),
    ("EPS", 1, ""),
    ("Philosophie", 2, ""),
]

# Lycée — groupe 3 : 2nde (2NDE1, 2NDE2) — pas de Philosophie
COEFFS_LYCEE_G3 = [
    ("Religion", 1, ""),
    ("Éducation à la Vie", 1, ""),
    ("Malagasy", 3, ""),
    ("Français", 3, ""),
    ("Anglais", 2, ""),
    ("Histoire-Géographie", 3, ""),
    ("Mathématiques", 3, ""),
    ("SVT", 3, ""),
    ("Physique-chimie", 3, ""),
    ("EPS", 1, ""),
]

# Niveaux Primaire / Maternelle : matières reprises telles quelles
# dans le catalogue de la section (pas de tableau « par classe »).
_PRIM_LEVELS = ("CP", "CE1", "CE2", "CM1", "CM2")
_MATER_LEVELS = ("PS", "MS", "GS")

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10}

# Version du tableau de coefficients appliqué aux bases existantes.
COEFF_DEFAULTS_VERSION = "2026-09-20"


def _subclass_index(suffix: str) -> int:
    """Numéro de sous-classe : ``"2"`` → 2, ``"II"`` → 2, ``""`` → 1."""
    s = (suffix or "").strip().upper()
    if not s:
        return 1
    if s.isdigit():
        return int(s)
    total = 0
    prev = 0
    for ch in reversed(s):
        v = _ROMAN_VALUES.get(ch)
        if v is None:
            return 1  # suffixe non reconnu (A, B…) → première classe
        total += -v if v < prev else v
        prev = max(prev, v)
    return total or 1


def _section_subjects(section_key: str) -> list[tuple[str, float, str]]:
    """Matières ``(nom, coeff, prof)`` d'une section du catalogue."""
    from .wizards.subjects_catalog import SECTIONS  # local : cycle Qt

    section = SECTIONS.get(section_key)
    if section is None:
        return []
    return [(name, float(coeff), "") for name, coeff in section.subjects]


def _college_subjects(class_name: str, level_key: str) -> list[tuple[str, float, str]]:
    """Collège : Physique-chimie = 3 en 3EME1/3EME2/4EME1, **2** ailleurs
    (4EME2 → 6EME3). Voir le tableau de la décision.
    """
    if level_key in ("5EME", "6EME"):
        pc = 2.0
    elif level_key == "4EME":
        suffix = class_name.strip().upper()[len(level_key):]
        pc = 3.0 if _subclass_index(suffix) == 1 else 2.0
    else:  # 3EME (et repli)
        pc = 3.0
    if pc == 3.0:
        return COEFFS_COLLEGE
    return [
        (name, pc if name == "Physique-chimie" else coeff, teacher)
        for name, coeff, teacher in COEFFS_COLLEGE
    ]


def _first_year_group(class_name: str) -> list[tuple[str, float, str]]:
    """1ère : groupe scientifique (S) ou littéraire/TA (défaut)."""
    name = class_name.strip().upper()
    suffix = name[4:] if name.startswith("1ERE") else name[1:]
    return COEFFS_LYCEE_G2 if suffix.startswith("S") else COEFFS_LYCEE_G1


def get_class_defaults(
    class_name: str, level_key: str | None = None
) -> list[tuple[str, float, str]]:
    """Matières et coefficients **par défaut** d'une classe.

    Retourne une liste de ``(nom, coefficient, professeur)`` selon le
    tableau de ``memory/decisions/coefficients-par-classe.md``.

    ``level_key`` (ex. ``"6EME"``, ``"TLE"``) peut être fourni pour
    éviter de le recalculer ; sinon il est déduit de *class_name*.

    >>> get_class_defaults("TA1")[10]         # Philosophie
    ('Philosophie', 4.0, '')
    >>> [c for n, c, _ in get_class_defaults("6EME3")
    ...  if n == "Physique-chimie"]
    [2.0]
    """
    from .workspace import extract_level_key, normalize_class_name
    from .wizards.subjects_catalog import get_class_coeff  # local : cycle Qt

    raw = str(class_name or "")
    name = normalize_class_name(raw) or raw.strip().upper()
    level = str(level_key or extract_level_key(raw)).strip().upper()

    if level == "2NDE":
        base = COEFFS_LYCEE_G3
    elif level == "1ERE":
        base = _first_year_group(name)
    elif level == "TLE":
        # TD → groupe scientifique, TAI/TAII et le reste → groupe 1
        base = COEFFS_LYCEE_G2 if name.startswith("TD") else COEFFS_LYCEE_G1
    elif level in ("3EME", "4EME", "5EME", "6EME"):
        base = _college_subjects(name, level)
    elif level in _PRIM_LEVELS:
        base = _section_subjects("PRIM")
    elif level in _MATER_LEVELS:
        base = _section_subjects("MATER")
    else:
        base = COEFFS_COLLEGE  # niveau inconnu → repli Collège

    # Surcharges du catalogue (ex: Philosophie 4 en TAI/TAII)
    return [
        (name_, get_class_coeff(name_, raw, coeff), teacher)
        for name_, coeff, teacher in base
    ]


def _subject_aliases(name: str) -> list[str]:
    """Tous les noms normalisés possibles d'une matière (avec alias)."""
    from .workspace import _get_subject_aliases, _normalize

    return _get_subject_aliases(_normalize(name))


def _defaults_by_norm(
    class_name: str, level_key: str | None = None
) -> dict[str, float]:
    """``{nom_normalisé_ou_alias: coefficient}`` pour une classe."""
    out: dict[str, float] = {}
    for name, coeff, _teacher in get_class_defaults(class_name, level_key):
        for alias in _subject_aliases(name):
            out.setdefault(alias, coeff)
    return out


def class_default_coeff(
    subject_name: str, class_name: str, level_key: str | None = None
) -> float | None:
    """Coefficient par défaut de *subject_name* pour *class_name*.

    Retourne ``None`` si la matière n'existe pas dans le tableau de
    la classe. Les alias (``Histo-geo`` ↔ ``Histoire-Géographie``,
    ``EVA`` ↔ ``Éducation à la Vie``) sont pris en compte.
    """
    defaults = _defaults_by_norm(class_name, level_key)
    for alias in _subject_aliases(subject_name):
        if alias in defaults:
            return defaults[alias]
    return None


def _apply_class_coeff_defaults(cur: sqlite3.Cursor, class_name: str) -> int:
    """Réécrit les coefficients de *class_name* depuis le tableau.

    Les matières absentes du tableau (ajoutées à la main) sont
    laissées telles quelles. Retourne le nombre de mises à jour.
    """
    defaults = _defaults_by_norm(class_name)
    if not defaults:
        return 0
    updated = 0
    for row in cur.execute("SELECT id, name, coeff FROM subjects").fetchall():
        target = None
        for alias in _subject_aliases(row["name"]):
            if alias in defaults:
                target = defaults[alias]
                break
        if target is None or float(row["coeff"] or 0.0) == target:
            continue
        cur.execute("UPDATE subjects SET coeff=? WHERE id=?", (target, row["id"]))
        updated += 1
    return updated


class Database:
    """Façade SQLite minimaliste."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or DEFAULT_PATH
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.executescript(SCHEMA)
        self._init_defaults()
        self._conn.commit()

    # ------------------------------------------------------------------
    #  Contexte
    # ------------------------------------------------------------------
    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        cur = self._conn.cursor()
        try:
            yield cur
        except Exception:
            self._conn.rollback()
            raise
        else:
            self._conn.commit()

    def _init_defaults(self) -> None:
        with self.cursor() as cur:
            # --- Micro-migrations sur bases existantes ---
            # v1.1 : renommage "Réligion" → "Religion" (faute de frappe)
            cur.execute(
                "UPDATE subjects SET name = 'Religion' "
                "WHERE name IN ('Réligion', 'réligion', 'RELIGION')"
            )
            for k, v in DEFAULT_SETTINGS.items():
                cur.execute(
                    "INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)",
                    (k, v),
                )
            # Corrige le nom de classe par défaut "1ERELI" en fonction
            # du dossier réel de la base, si la valeur est encore celle
            # par défaut.
            cur.execute("SELECT value FROM settings WHERE key='classe'")
            row = cur.fetchone()
            if row and row["value"] in ("1ERELI", "1ERE L1", ""):
                try:
                    cls = discover_class_by_db_path(self.path)
                    if cls is not None:
                        cur.execute(
                            "UPDATE settings SET value=? WHERE key='classe'",
                            (cls.name,),
                        )
                except Exception:
                    pass
            # --- v1.2 : coefficients par classe (tableau 2026-09-20) ---
            # Appliqué AVANT le seed : sur une base vide il n'y a rien à
            # réécrire, et le seed garde ainsi la priorité aux .xlsx.
            self._migrate_class_coefficients(cur)

            # --- Seed des matières quand la table est vide ---
            cur.execute("SELECT COUNT(*) AS n FROM subjects")
            if cur.fetchone()["n"] == 0:
                for name, coeff, teacher, pos in self._default_subject_rows():
                    cur.execute(
                        "INSERT INTO subjects(name,coeff,teacher,position) "
                        "VALUES(?,?,?,?)",
                        (name, coeff, teacher, pos),
                    )
            # Filet de sécurité : ne laisse jamais une base sans matière
            cur.execute("SELECT COUNT(*) AS n FROM subjects")
            if cur.fetchone()["n"] == 0:
                for i, (name, coeff, teacher) in enumerate(DEFAULT_SUBJECTS):
                    cur.execute(
                        "INSERT INTO subjects(name,coeff,teacher,position) VALUES (?,?,?,?)",
                        (name, coeff, teacher, i),
                    )

    def _migrate_class_coefficients(self, cur: sqlite3.Cursor) -> None:
        """Réécrit les coefficients d'une base existante depuis le tableau.

        Une seule fois par base (drapeau ``coeff_defaults_version`` dans
        ``settings``). Les bases dont le dossier de classe n'est pas
        détectable sont revérifiées à la prochaine ouverture.
        """
        cur.execute(
            "SELECT value FROM settings WHERE key='coeff_defaults_version'"
        )
        row = cur.fetchone()
        if row is not None and row["value"] == COEFF_DEFAULTS_VERSION:
            return
        try:
            cls = discover_class_by_db_path(self.path)
        except Exception:  # noqa: BLE001
            cls = None
        if cls is None:
            return
        _apply_class_coeff_defaults(cur, cls.name)
        cur.execute(
            "INSERT INTO settings(key,value) "
            "VALUES('coeff_defaults_version',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (COEFF_DEFAULTS_VERSION,),
        )

    def _default_subject_rows(self) -> list[tuple[str, float, str, int]]:
        """Matières à grainer pour la base courante ``(nom, coeff, prof, pos)``.

        Priorité des coefficients :
        1. cellule **C4** des ``.xlsx`` du dossier classe
        2. cache ``bulletin excel/``
        3. tableau des coefficients de la classe (:func:`get_class_defaults`)
        """
        from .workspace import (
            extract_level_key,
            get_bulletin_excel_coeff,
            read_coefficient_from_xlsx,
        )
        from .wizards.subjects_catalog import subject_allowed_for_level

        try:
            cls = discover_class_by_db_path(self.path)
        except Exception:  # noqa: BLE001
            cls = None
        if cls is None:
            return [
                (name, coeff, teacher, i)
                for i, (name, coeff, teacher) in enumerate(DEFAULT_SUBJECTS)
            ]

        level_key = extract_level_key(cls.name)
        defaults = get_class_defaults(cls.name, level_key)

        # 1) coefficients lus dans les .xlsx du dossier classe
        subject_map: dict[str, float] = {}
        for p in cls.subject_files:
            coeff = read_coefficient_from_xlsx(p)
            if coeff is None:
                continue
            for alias in _subject_aliases(p.stem):
                subject_map.setdefault(alias, coeff)

        # 2) sinon le cache « bulletin excel/ »
        if not subject_map and cls.db_path:
            for name, _coeff, _teacher in defaults:
                coeff = get_bulletin_excel_coeff(cls.name, name)
                if coeff is None:
                    continue
                for alias in _subject_aliases(name):
                    subject_map.setdefault(alias, coeff)

        # 3) tableau de la classe, matières filtrées par niveau
        rows: list[tuple[str, float, str, int]] = []
        for name, default_coeff, _teacher in defaults:
            if not subject_allowed_for_level(name, level_key):
                continue
            coeff = default_coeff
            for alias in _subject_aliases(name):
                if alias in subject_map:
                    coeff = subject_map[alias]
                    break
            rows.append((name, coeff, "", len(rows)))
        return rows

    # ------------------------------------------------------------------
    #  Settings
    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: str = "") -> str:
        with self.cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = cur.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: Any) -> None:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value) if value is not None else ""),
            )

    def all_settings(self) -> dict[str, str]:
        with self.cursor() as cur:
            cur.execute("SELECT key,value FROM settings")
            return {r["key"]: r["value"] for r in cur.fetchall()}

    # ------------------------------------------------------------------
    #  Subjects
    # ------------------------------------------------------------------
    def list_subjects(self) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute("SELECT * FROM subjects ORDER BY position, id")
            return cur.fetchall()

    # ------------------------------------------------------------------
    #  Accès bas-niveau (lecture seule, à utiliser avec parcimonie)
    # ------------------------------------------------------------------
    def raw_query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Exécute une requête SELECT brute et retourne les lignes.

        Cette méthode est la voie publique pour les modules de calcul
        qui ont besoin d'un accès direct à la base. Préférez les
        méthodes métier (:meth:`list_students`, :meth:`get_grade`, …)
        quand elles existent. Les mutations doivent passer par les
        méthodes typées (:meth:`set_grade`, :meth:`update_student`…).
        """
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def add_subject(self, name: str, coeff: float, teacher: str = "") -> int:
        with self.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(position),-1)+1 AS p FROM subjects")
            pos = cur.fetchone()["p"]
            cur.execute(
                "INSERT INTO subjects(name,coeff,teacher,position) VALUES(?,?,?,?)",
                (name, coeff, teacher, pos),
            )
            lastid = cur.lastrowid
        _clear_cache()
        return lastid

    def clear_subjects(self) -> None:
        """Vide complètement la table des matières.

        Utilisé notamment par l'assistant de création de classe
        après l'auto-seed initial, pour ne garder que les matières
        explicitement choisies par l'utilisateur.
        """
        with self.cursor() as cur:
            cur.execute("DELETE FROM subjects")
        _clear_cache()

    def set_subjects(self, subjects: list[tuple[str, float, str]]) -> None:
        """Remplace *toute* la liste des matières.

        ``subjects`` est une liste de tuples ``(name, coeff, teacher)``.
        Réinitialise ``position`` selon l'ordre fourni. Les notes
        existantes pointant vers les anciennes matières sont
        supprimées (FK ON DELETE CASCADE).
        """
        with self.cursor() as cur:
            cur.execute("DELETE FROM subjects")
            for i, (name, coeff, teacher) in enumerate(subjects):
                cur.execute(
                    "INSERT INTO subjects(name,coeff,teacher,position) "
                    "VALUES(?,?,?,?)",
                    (name, coeff, teacher, i),
                )
        _clear_cache()

    def update_subject(self, sid: int, name: str, coeff: float, teacher: str) -> None:
        with self.cursor() as cur:
            cur.execute(
                "UPDATE subjects SET name=?, coeff=?, teacher=? WHERE id=?",
                (name, coeff, teacher, sid),
            )
        _clear_cache()

    def delete_subject(self, sid: int) -> None:
        with self.cursor() as cur:
            cur.execute("DELETE FROM subjects WHERE id=?", (sid,))
            cur.execute("DELETE FROM grades WHERE subject_id=?", (sid,))
        _clear_cache()

    # ------------------------------------------------------------------
    #  Students
    # ------------------------------------------------------------------
    def list_students(self) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute("SELECT * FROM students ORDER BY num")
            return cur.fetchall()

    def find_duplicate_name(self, nom: str, prenoms: str = "",
                            exclude_id: int | None = None) -> sqlite3.Row | None:
        """Cherche un élève avec le même nom et prénoms (insensible à la casse).

        Retourne la première ligne trouvée, ou ``None`` si aucun doublon.
        ``exclude_id`` permet d'exclure un ID (utile en modification).
        """
        with self.cursor() as cur:
            if exclude_id:
                cur.execute(
                    "SELECT * FROM students "
                    "WHERE LOWER(nom)=LOWER(?) AND LOWER(prenoms)=LOWER(?) "
                    "AND id != ? LIMIT 1",
                    (nom, prenoms, exclude_id),
                )
            else:
                cur.execute(
                    "SELECT * FROM students "
                    "WHERE LOWER(nom)=LOWER(?) AND LOWER(prenoms)=LOWER(?) LIMIT 1",
                    (nom, prenoms),
                )
            return cur.fetchone()

    def add_student(self, num: int, nom: str, prenoms: str = "",
                    matricule: str = "", genre: str = "", naissance: str = "") -> int:
        dup = self.find_duplicate_name(nom, prenoms)
        if dup is not None:
            raise ValueError(
                f"Un élève avec le même nom existe déjà : "
                f"« {dup['nom']} {dup['prenoms']} » (N°{dup['num']})."
            )
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO students(num,matricule,nom,prenoms,genre,naissance) "
                "VALUES(?,?,?,?,?,?)",
                (num, matricule, nom, prenoms, genre, naissance),
            )
            lastid = cur.lastrowid
        _clear_cache()
        return lastid

    def update_student(self, sid: int, **kwargs) -> None:
        if not kwargs:
            return
        nom = kwargs.get("nom")
        prenoms = kwargs.get("prenoms")
        if nom is not None or prenoms is not None:
            # Recharger les valeurs actuelles pour les champs non fournis
            with self.cursor() as cur:
                cur.execute("SELECT nom, prenoms FROM students WHERE id=?", (sid,))
                row = cur.fetchone()
            if row:
                final_nom = nom if nom is not None else row["nom"]
                final_prenoms = prenoms if prenoms is not None else row["prenoms"]
                dup = self.find_duplicate_name(final_nom, final_prenoms, exclude_id=sid)
                if dup is not None:
                    raise ValueError(
                        f"Un autre élève porte déjà ce nom : "
                        f"« {dup['nom']} {dup['prenoms']} » (N°{dup['num']})."
                    )
        cols = ",".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [sid]
        with self.cursor() as cur:
            cur.execute(f"UPDATE students SET {cols} WHERE id=?", vals)
        _clear_cache()

    def delete_student(self, sid: int) -> None:
        with self.cursor() as cur:
            cur.execute("DELETE FROM students WHERE id=?", (sid,))
            cur.execute("DELETE FROM grades WHERE student_id=?", (sid,))
        _clear_cache()

    def generate_students(self, count: int, start: int = 1) -> int:
        """Crée `count` élèves avec Num de start à start+count-1.

        Ignore les doublons.
        """
        added = 0
        with self.cursor() as cur:
            for i in range(start, start + count):
                try:
                    cur.execute(
                        "INSERT INTO students(num,nom) VALUES(?,?)",
                        (i, f"Élève {i}"),
                    )
                    added += 1
                except sqlite3.IntegrityError:
                    pass
        if added:
            _clear_cache()
        return added

    def bulk_update_students(self, rows: Iterable[dict]) -> None:
        """rows = [{'num':1,'nom':'X','prenoms':'Y',...}, ...]

        Lève ``ValueError`` si un doublon de nom est détecté.
        """
        rows_list = list(rows)
        seen_names: set[tuple[str, str]] = set()
        # Vérification sans ouvrir de curseur imbriqué
        existing_map: dict[int, tuple[str, str]] = {}
        with self.cursor() as cur:
            cur.execute("SELECT num, nom, prenoms FROM students")
            for row in cur.fetchall():
                existing_map[int(row["num"])] = (row["nom"] or "", row["prenoms"] or "")
        for r in rows_list:
            nom = (r.get("nom") or "").strip()
            prenoms = (r.get("prenoms") or "").strip()
            if not nom:
                continue
            key = (nom.lower(), prenoms.lower())
            if key in seen_names:
                raise ValueError(
                    f"Doublon détecté dans le fichier : "
                    f"« {nom} {prenoms} » apparaît plusieurs fois."
                )
            seen_names.add(key)
            existing_num = r.get("num")
            if existing_num is not None:
                existing_num = int(existing_num)
                existing = existing_map.get(existing_num)
                if existing is not None and (existing[0].lower(), existing[1].lower()) == key:
                    continue
            dup = self.find_duplicate_name(nom, prenoms)
            if dup is not None:
                raise ValueError(
                    f"Un élève avec le même nom existe déjà dans la base : "
                    f"« {dup['nom']} {dup['prenoms']} » (N°{dup['num']}). "
                    f"Impossible d'ajouter « {nom} {prenoms} »."
                )
        with self.cursor() as cur:
            for r in rows_list:
                cur.execute(
                    "INSERT INTO students(num,matricule,nom,prenoms,genre,naissance) "
                    "VALUES(:num,:matricule,:nom,:prenoms,:genre,:naissance) "
                    "ON CONFLICT(num) DO UPDATE SET "
                    "matricule=excluded.matricule, nom=excluded.nom, "
                    "prenoms=excluded.prenoms, genre=excluded.genre, "
                    "naissance=excluded.naissance",
                    r,
                )
        _clear_cache()

    # ------------------------------------------------------------------
    #  Grades
    # ------------------------------------------------------------------
    def get_grade(self, student_id: int, subject_id: int, exam_num: int) -> float | None:
        with self.cursor() as cur:
            cur.execute(
                "SELECT value FROM grades WHERE student_id=? AND subject_id=? AND exam_num=?",
                (student_id, subject_id, exam_num),
            )
            row = cur.fetchone()
            return row["value"] if row else None

    def get_grades_subject(self, subject_id: int) -> dict[tuple[int, int], float]:
        """{ (student_id, exam_num) : value }"""
        with self.cursor() as cur:
            cur.execute(
                "SELECT student_id, exam_num, value FROM grades WHERE subject_id=?",
                (subject_id,),
            )
            return {(r["student_id"], r["exam_num"]): r["value"] for r in cur.fetchall()}

    def set_grade(self, student_id: int, subject_id: int, exam_num: int, value) -> None:
        if value is None or value == "":
            with self.cursor() as cur:
                cur.execute(
                    "DELETE FROM grades WHERE student_id=? AND subject_id=? AND exam_num=?",
                    (student_id, subject_id, exam_num),
                )
            _clear_cache()
            return
        try:
            v = float(value)
        except (TypeError, ValueError):
            return
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO grades(student_id,subject_id,exam_num,value) VALUES(?,?,?,?) "
                "ON CONFLICT(student_id,subject_id,exam_num) DO UPDATE SET value=excluded.value",
                (student_id, subject_id, exam_num, v),
            )
        _clear_cache()

    def bulk_set_grades(
        self, grades: Iterable[tuple[int, int, int, float]]
    ) -> int:
        """Écrit plusieurs notes en une seule transaction.

        ``grades`` est un iterable de ``(student_id, subject_id, exam_num, value)``.
        Le commit est fait une seule fois à la fin → ~100x plus rapide
        que d'appeler :meth:`set_grade` en boucle (SQLite fsync à chaque
        commit). Retourne le nombre de lignes effectivement écrites.
        """
        n = 0
        with self.cursor() as cur:
            cur.executemany(
                "INSERT INTO grades(student_id,subject_id,exam_num,value) "
                "VALUES(?,?,?,?) "
                "ON CONFLICT(student_id,subject_id,exam_num) "
                "DO UPDATE SET value=excluded.value",
                list(grades),
            )
            n = cur.rowcount
        _clear_cache()
        return n

    def clear_grades(self) -> None:
        with self.cursor() as cur:
            cur.execute("DELETE FROM grades")
        _clear_cache()

    # ------------------------------------------------------------------
    #  Reseed
    # ------------------------------------------------------------------
    def reset_all(self, keep_settings: bool = True) -> None:
        with self.cursor() as cur:
            cur.execute("DELETE FROM grades")
            cur.execute("DELETE FROM students")
            cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('students','grades')")
            if not keep_settings:
                cur.execute("DELETE FROM settings")
                self._init_defaults()
            cur.execute("DELETE FROM subjects")
            cur.execute("DELETE FROM sqlite_sequence WHERE name='subjects'")
        self._init_defaults()
        _clear_cache()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    #  Backup / restore / merge / wipe  (bulletin premium, pattern
    #  eco_paiement premium)
    # ------------------------------------------------------------------
    def backup(self, keep: int = 7) -> str | None:
        """Crée une copie horodatée de la base dans ``.backups/``.

        Ne garde que les ``keep`` sauvegardes les plus récentes
        (les plus anciennes sont supprimées). Retourne le chemin du
        fichier créé, ou ``None`` si la base n'a pas encore de chemin.

        Si un fichier avec le même nom existe (créations multiples
        dans la même seconde), un suffixe ``_2``, ``_3``… est ajouté.
        """
        import shutil
        from datetime import datetime
        from pathlib import Path

        if not self.path:
            return None
        src = Path(self.path)
        if not src.exists():
            return None
        backup_dir = src.parent / ".backups"
        backup_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = backup_dir / f"{src.stem}.{ts}.bak"
        # Si le fichier existe, ajoute un suffixe numérique
        counter = 2
        while dest.exists():
            dest = backup_dir / f"{src.stem}.{ts}_{counter}.bak"
            counter += 1
            if counter > 100:
                break
        try:
            shutil.copy2(str(src), str(dest))
        except OSError:
            return None
        # Rotation : garde les N plus récents
        backups = sorted(
            backup_dir.glob(f"{src.stem}.*.bak"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in backups[keep:]:
            try:
                old.unlink()
            except OSError:
                pass
        return str(dest)

    def backup_database(self, target: str | Path) -> Path:
        """Copie **atomique** de la base vers *target* via l'API SQLite
        ``Connection.backup()``.

        Cette méthode est plus sûre qu'un simple :func:`shutil.copy2`
        car SQLite garantit la cohérence transactionnelle pendant
        la copie (le fichier source peut être en cours d'écriture).
        Retourne le chemin de la sauvegarde créée.
        """
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        # SQLite backup API : src.backup(dst)
        with sqlite3.connect(str(target)) as dst:
            self._conn.backup(dst)
        return target

    def create_backup(self, prefix: str = "") -> Path | None:
        """Crée un backup horodaté avec un *préfixe* optionnel.

        Utilisé pour les sauvegardes **automatiques** déclenchées
        avant des opérations destructives (reset, replace). Le
        préfixe aide l'utilisateur à identifier la raison du backup
        dans l'explorateur de fichiers.

        Format : ``<prefix>_YYYYMMDD-HHMMSS.bak`` dans ``.backups/``.
        Si le fichier existe déjà (créations multiples dans la même
        seconde), un suffixe numérique ``_2``, ``_3``, … est ajouté.

        Retourne ``None`` si la base n'a pas de chemin.
        """
        from datetime import datetime
        from pathlib import Path

        if not self.path:
            return None
        src = Path(self.path)
        if not src.exists():
            return None
        backup_dir = src.parent / ".backups"
        backup_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        prefix_part = f"{prefix}_" if prefix else ""
        target = backup_dir / f"{prefix_part}{ts}.bak"
        # Si le fichier existe, ajoute un suffixe numérique
        counter = 2
        while target.exists():
            target = backup_dir / f"{prefix_part}{ts}_{counter}.bak"
            counter += 1
            if counter > 100:  # sécurité
                break
        return self.backup_database(target)

    def list_backups(self) -> list[Path]:
        """Liste les sauvegardes existantes dans ``.backups/``,
        triées du plus récent au plus ancien.
        """
        from pathlib import Path
        if not self.path:
            return []
        backup_dir = Path(self.path).parent / ".backups"
        if not backup_dir.is_dir():
            return []
        return sorted(
            backup_dir.glob("*.bak"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    def delete_backup(self, path: str | Path) -> bool:
        """Supprime un fichier de sauvegarde. Retourne ``True`` si OK."""
        from pathlib import Path
        p = Path(path)
        if not p.exists():
            return False
        try:
            p.unlink()
            return True
        except OSError:
            return False

    def validate_sqlite_file(self, path: str | Path) -> bool:
        """Vérifie que *path* est une base SQLite valide et non corrompue.

        Utilisé avant un restore / merge pour refuser les fichiers
        arbitraires (CSV, XLSX, exécutables…) qui auraient été
        renommés en ``.db``.

        Ouvre le fichier en mode ``ro`` (read-only) pour ne pas
        le modifier ou le verrouiller.
        """
        from pathlib import Path
        p = Path(path)
        if not p.is_file():
            return False
        try:
            uri = f"file:{p}?mode=ro"
            probe = sqlite3.connect(uri, uri=True)
            try:
                row = probe.execute("PRAGMA integrity_check").fetchone()
                return bool(row) and str(row[0]).lower() == "ok"
            finally:
                probe.close()
        except (sqlite3.Error, OSError):
            return False

    def replace_database(self, source: str | Path) -> Path:
        """Remplace la base actuelle par *source* (après un backup
        automatique de sécurité). Retourne le chemin du backup auto.
        """
        from pathlib import Path
        import shutil

        if not self.path:
            raise FileNotFoundError("Base active sans chemin : abandon")
        src = Path(source)
        if not src.is_file():
            raise FileNotFoundError(str(src))
        # Backup de sécurité automatique
        auto_bk = self.create_backup(prefix="before_replace")
        # Remplace
        shutil.copy2(str(src), str(self.path))
        # La connexion actuelle pointe sur l'ancien fichier :
        # il faut reconnecter après le replace.
        self._conn.close()
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        _clear_cache()
        return auto_bk

    def merge_database(self, source: str | Path) -> dict:
        """Fusionne *source* dans la base actuelle (additif).

        - **Élèves** : ajoutés par (num) ; existants = ignorés
        - **Notes** : ajoutées si (student, subject, exam) absent
        - **Matières** : ajoutées par nom ; existantes = conservées
        - **Paramètres** : *non fusionnés* (ceux de la base active
          priment — on ne mélange pas 2 établissements).

        Retourne un dict avec les compteurs ``added_students``,
        ``skipped_students``, ``added_grades``.
        """
        from pathlib import Path

        if not self.path:
            raise FileNotFoundError("Base active sans chemin : abandon")
        src = Path(source)
        if not src.is_file():
            raise FileNotFoundError(str(src))
        if not self.validate_sqlite_file(src):
            raise ValueError(f"Le fichier {src} n'est pas une base SQLite valide")

        added_students = 0
        skipped_students = 0
        added_grades = 0
        added_subjects = 0

        try:
            src_conn = sqlite3.connect(str(src))
            src_conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise ValueError(f"Impossible d'ouvrir {src}: {exc}") from exc

        try:
            # S'assurer que le schéma source est compatible
            src_tables = {
                str(r["name"])
                for r in src_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            required = {"students", "grades", "subjects"}
            if not required.issubset(src_tables):
                raise ValueError(
                    f"La base source n'a pas les tables attendues "
                    f"({', '.join(sorted(required - src_tables))} manquante(s))"
                )

            with self.cursor() as cur:
                # 1) Matières : on ajoute par nom si pas déjà présent
                local_subjects = {
                    str(s["name"]).strip().lower(): int(s["id"])
                    for s in cur.execute("SELECT id, name FROM subjects").fetchall()
                }
                for s in src_conn.execute(
                    "SELECT name, coeff, teacher FROM subjects"
                ).fetchall():
                    key = str(s["name"] or "").strip().lower()
                    if key and key not in local_subjects:
                        cur.execute(
                            "INSERT INTO subjects(name, coeff, teacher) "
                            "VALUES(?,?,?)",
                            (s["name"], float(s["coeff"] or 1.0), s["teacher"] or ""),
                        )
                        local_subjects[key] = int(cur.lastrowid)
                        added_subjects += 1

                # Recharge le mapping id → name pour les notes
                subject_id_by_name = {
                    str(s["name"]).strip().lower(): int(s["id"])
                    for s in cur.execute("SELECT id, name FROM subjects").fetchall()
                }

                # 2) Élèves : ajoutés par num
                local_students = {
                    int(s["num"]): int(s["id"])
                    for s in cur.execute("SELECT id, num FROM students").fetchall()
                }
                for s in src_conn.execute(
                    "SELECT num, matricule, nom, prenoms, genre, naissance "
                    "FROM students"
                ).fetchall():
                    num = int(s["num"] or 0)
                    if num <= 0:
                        skipped_students += 1
                        continue
                    if num in local_students:
                        skipped_students += 1
                        continue
                    cur.execute(
                        "INSERT INTO students(num, matricule, nom, prenoms, "
                        "genre, naissance) VALUES(?,?,?,?,?,?)",
                        (
                            num,
                            s["matricule"] or "",
                            s["nom"] or "",
                            s["prenoms"] or "",
                            s["genre"] or "",
                            s["naissance"] or "",
                        ),
                    )
                    local_students[num] = int(cur.lastrowid)
                    added_students += 1

                # 3) Notes : ajoutées par (student, subject, exam) si absent
                # Il faut remapper les (num) et (subject_name) du source
                # vers les (id) locaux. Les élèves ajoutés ci-dessus
                # ont les mêmes num dans les deux bases.
                for g in src_conn.execute(
                    "SELECT s.num AS num, sub.name AS sname, "
                    "g.exam_num, g.value "
                    "FROM grades g "
                    "JOIN students s ON g.student_id = s.id "
                    "JOIN subjects sub ON g.subject_id = sub.id"
                ).fetchall():
                    local_sid = local_students.get(int(g["num"]))
                    if local_sid is None:
                        continue
                    local_subid = subject_id_by_name.get(
                        str(g["sname"] or "").strip().lower()
                    )
                    if local_subid is None:
                        continue
                    # Vérifie si la note existe déjà
                    existing = cur.execute(
                        "SELECT 1 FROM grades WHERE student_id=? "
                        "AND subject_id=? AND exam_num=?",
                        (local_sid, local_subid, int(g["exam_num"])),
                    ).fetchone()
                    if existing is None:
                        cur.execute(
                            "INSERT INTO grades(student_id, subject_id, "
                            "exam_num, value) VALUES(?,?,?,?)",
                            (
                                local_sid,
                                local_subid,
                                int(g["exam_num"]),
                                float(g["value"] or 0.0),
                            ),
                        )
                        added_grades += 1
        finally:
            src_conn.close()

        _clear_cache()
        return {
            "added_students": added_students,
            "skipped_students": skipped_students,
            "added_grades": added_grades,
            "added_subjects": added_subjects,
        }

    def wipe_all_data(self, keep_settings: bool = True) -> None:
        """Vide la base complètement. Par défaut, conserve les
        paramètres (établissement, classe, année…) et réinitialise
        les matières. Supprime élèves + notes.
        """
        with self.cursor() as cur:
            cur.execute("DELETE FROM grades")
            cur.execute("DELETE FROM students")
            cur.execute(
                "DELETE FROM sqlite_sequence "
                "WHERE name IN ('students', 'grades')"
            )
            if not keep_settings:
                cur.execute("DELETE FROM settings")
                self._init_defaults()
            cur.execute("DELETE FROM subjects")
            cur.execute("DELETE FROM sqlite_sequence WHERE name='subjects'")
        self._init_defaults()
        _clear_cache()


# ---------------------------------------------------------------------------
#  Helpers privés pour le seeding initial
# ---------------------------------------------------------------------------
def discover_class_by_db_path(db_path: str | os.PathLike) -> object | None:
    """Retrouve un :class:`ClassInfo` dont le ``db_path`` correspond.

    Retourne ``None`` si aucun match (cas legacy : base hors workspace).
    Import local pour éviter les cycles.
    """
    from .workspace import discover_classes
    target = os.path.normpath(str(db_path)).lower()
    for c in discover_classes():
        if os.path.normpath(str(c.db_path)).lower() == target:
            return c
    # Cas de repli : la DB est dans un dossier ``data/`` d'une classe
    # de COLLEGE/, LYCEE/ ou PRIMAIRE/.
    parts = Path(str(db_path)).resolve().parts
    for i, part in enumerate(parts):
        if part in ("COLLEGE", "LYCEE", "PRIMAIRE") and i + 1 < len(parts):
            from .workspace import discover_class
            cls_name = parts[i + 1]
            found = discover_class(cls_name)
            if found is not None:
                return found
            # Dossier classe sans .xlsx ni sous-dossier bulletin/ :
            # ``discover_classes()`` l'ignore, mais on peut quand même
            # construire un ClassInfo (utile pour grainer / migrer).
            folder = Path(*parts[: i + 2])
            if folder.is_dir():
                from .workspace import ClassInfo, prettify_class_name
                xlsx_files = sorted(
                    p for p in folder.glob("*.xlsx")
                    if not p.name.startswith("~$")
                )
                return ClassInfo(
                    name=cls_name,
                    display_name=prettify_class_name(cls_name),
                    division=part,
                    folder=folder,
                    db_path=folder / "data" / "bulletin.db",
                    bulletin_path=(
                        folder / "bulletin" / f"Bulletin{cls_name.upper()}.xlsm"
                    ),
                    subject_files=xlsx_files,
                )
    return None
