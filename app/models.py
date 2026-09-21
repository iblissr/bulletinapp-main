"""Logique métier (calculs reproduisant la logique VBA)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .db import Database

# Cache des totalisations (vidé lors des écritures DB)
_totalisation_cache: dict[str, Any] = {}
_cache_version: int = 0


def clear_cache() -> None:
    """Vide le cache de calcul. Appelé après toute écriture dans la DB."""
    global _cache_version
    _cache_version += 1


def _cached_totalisation(db: Database, exam_num: int):
    """Retourne le résultat de compute_totalisation en utilisant un cache
    par (db.path, exam_num, cache_version)."""
    global _totalisation_cache, _cache_version
    key = f"{db.path}:{exam_num}:{_cache_version}"
    if key not in _totalisation_cache:
        _totalisation_cache[key] = compute_totalisation(db, exam_num)
        # Nettoie les vieilles entrées (max 100)
        if len(_totalisation_cache) > 100:
            _totalisation_cache.clear()
    return _totalisation_cache[key]


@dataclass
class Subject:
    id: int
    name: str
    coeff: float
    teacher: str = ""

    @property
    def abbrev(self) -> str:
        n = self.name.strip()
        return n[:3] if len(n) >= 3 else n


@dataclass
class Student:
    id: int
    num: int
    nom: str
    prenoms: str = ""

    @property
    def full_name(self) -> str:
        if self.prenoms:
            return f"{self.nom} {self.prenoms}".strip()
        return self.nom


def load_subjects(db: Database) -> list[Subject]:
    return [Subject(s["id"], s["name"], s["coeff"], s["teacher"])
            for s in db.list_subjects()]


def load_students(db: Database) -> list[Student]:
    return [Student(s["id"], s["num"], s["nom"], s["prenoms"])
            for s in db.list_students()]


def get_setting_int(db: Database, key: str, default: int = 0) -> int:
    try:
        return int(float(db.get_setting(key, str(default))))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
#  Totalisation par note (1..6)
# ---------------------------------------------------------------------------
def compute_totalisation(
    db: Database, exam_num: int
) -> tuple[list[dict], list[Subject], float]:
    """Retourne (lignes, matières, total_coefficients).

    Chaque ligne = {student, notes: {subj_id: value}, total, moy, rank}.
    Les élèves n'atteignant pas nb_min sont marqués "NC".
    """
    subjects = load_subjects(db)
    students = load_students(db)
    nb_min = get_setting_int(db, "nb_min_examens", 1)
    total_coeff = sum(s.coeff for s in subjects)

    # 1 seule requête pour toutes les notes de l'examen (au lieu de N)
    grades_rows = db.raw_query(
        "SELECT student_id, subject_id, value FROM grades "
        "WHERE exam_num=?",
        (exam_num,),
    )

    # Structure : {student_id: {subject_id: value}}
    grades: dict[int, dict[int, float]] = {}
    for row in grades_rows:
        sid = int(row["student_id"])
        subj = int(row["subject_id"])
        val = float(row["value"])
        grades.setdefault(sid, {})[subj] = val

    rows = []
    for st in students:
        st_grades = grades.get(st.id, {})
        per_subject: dict[int, float | None] = {}
        total = 0.0
        coefs_used = 0.0
        nb_used = 0
        for s in subjects:
            v = st_grades.get(s.id)
            per_subject[s.id] = v
            if v is not None:
                total += v
                coefs_used += s.coeff
                nb_used += 1
        if nb_used >= nb_min and coefs_used > 0:
            moy = total / coefs_used
            rows.append(
                {
                    "student": st,
                    "notes": per_subject,
                    "total": round(total, 2),
                    "moy": round(moy, 2),
                    "rank": None,
                    "valid": True,
                }
            )
        else:
            rows.append(
                {
                    "student": st,
                    "notes": per_subject,
                    "total": None,
                    "moy": None,
                    "rank": None,
                    "valid": False,
                }
            )

    _assign_ranks(rows)
    return rows, subjects, total_coeff


def _assign_ranks(rows: Sequence[dict]) -> None:
    """Tri décroissant par moyenne. O(n log n) au lieu du tri à bulles O(n²)."""
    valid = sorted(
        [r for r in rows if r["valid"]],
        key=lambda r: r["moy"],
        reverse=True,
    )
    for idx, r in enumerate(valid, 1):
        r["rank"] = idx


# ---------------------------------------------------------------------------
#  Moyennes trimestrielles + annuelle
# ---------------------------------------------------------------------------
@dataclass
class TrimRow:
    """Une ligne de moyenne trimestrielle.

    Chaque trimestre = 1 MJ (note journalière) + 1 Compo.
    - ``m_moy``  : moyenne pondérée du MJ (toutes matières, coefficient 1)
    - ``c_moy``  : moyenne pondérée de la Compo (toutes matières, coefficient 2)
    - ``m_total`` : total brut des notes du MJ (somme des valeurs)
    - ``c_total`` : total brut des notes de la Compo (somme des valeurs)
    - ``tot``    : somme brute des 2 notes (moyennes, /40 max)
    - ``moy``    : moyenne pondérée du trimestre = (m_moy × 1 + c_moy × 2) / 3
    - ``rank``   : rang dans la classe
    """
    student: Student
    m_moy: float | None
    c_moy: float | None
    m_total: float | None
    c_total: float | None
    tot: float | None
    moy: float | None
    rank: int | None


def compute_trimestre(db: Database, trimestre: int) -> list[TrimRow]:
    """trimestre ∈ {1,2,3} → utilise totalisation(2t-1) pour M.J et totalisation(2t) pour Compo."""
    if trimestre not in (1, 2, 3):
        raise ValueError("trimestre doit être 1, 2 ou 3")
    n_mj = 2 * trimestre - 1
    n_co = 2 * trimestre
    rows_mj, _, _ = _cached_totalisation(db, n_mj)
    rows_co, _, _ = _cached_totalisation(db, n_co)
    moy_mj = {r["student"].id: r for r in rows_mj}
    moy_co = {r["student"].id: r for r in rows_co}

    students = load_students(db)
    out: list[TrimRow] = []
    for st in students:
        a = moy_mj.get(st.id)
        b = moy_co.get(st.id)
        m_moy = a["moy"] if a and a["valid"] else None
        c_moy = b["moy"] if b and b["valid"] else None
        m_total = a["total"] if a and a["valid"] else None
        c_total = b["total"] if b and b["valid"] else None
        if m_moy is not None or c_moy is not None:
            tot = round((m_moy or 0) + (c_moy or 0), 2)
            tot_p = (m_moy or 0) * 1 + (c_moy or 0) * 2
            coe_p = (1 if m_moy is not None else 0) + (2 if c_moy is not None else 0)
            moy = round(tot_p / coe_p, 2) if coe_p > 0 else None
        else:
            tot = None
            moy = None
        out.append(TrimRow(st, m_moy, c_moy, m_total, c_total, tot, moy, None))

    _rank_trim(out)
    return out


def _rank_trim(rows: Iterable[TrimRow]) -> None:
    valid = sorted(
        [r for r in rows if r.moy is not None],
        key=lambda r: r.moy,
        reverse=True,
    )
    for idx, r in enumerate(valid, 1):
        r.rank = idx


# ---------------------------------------------------------------------------
#  Moyenne annuelle
# ---------------------------------------------------------------------------
@dataclass
class AnnualRow:
    """Une ligne de moyenne annuelle.

    6 notes au total : 3 MJ (mj1..mj3) et 3 Compo (co1..co3).
    Coefficients : MJ = 1, Compo = 2 (par trimestre).
    - ``total`` : somme brute des 6 notes (sur 120)
    - ``mga``   : moyenne pondérée annuelle = Σ(note × c) / Σ(c)
    - ``rank``  : rang dans la classe
    """
    student: Student
    mj1: float | None
    co1: float | None
    mj2: float | None
    co2: float | None
    mj3: float | None
    co3: float | None
    total: float | None
    mga: float | None
    rank: int | None


def compute_annuelle(db: Database) -> list[AnnualRow]:
    """MGA = moyenne pondérée : MJ × 1 + Compo × 2.

    Renvoie aussi ``total`` (somme brute des 6 notes, sur 120).
    """
    students = load_students(db)
    tot_data: dict[int, dict[int, float | None]] = {}  # {student_id: {1..6: moy}}
    for n in range(1, 7):
        rows, _, _ = _cached_totalisation(db, n)
        for r in rows:
            tot_data.setdefault(r["student"].id, {})[n] = r["moy"]

    out: list[AnnualRow] = []
    for st in students:
        d = tot_data.get(st.id, {})
        vals = [d.get(k) for k in range(1, 7)]
        valid = [v for v in vals if v is not None]
        if valid:
            tot = sum((v or 0) * (2 if (i % 2 == 0) else 1)
                      for i, v in enumerate(vals, 1) if v is not None)
            coe = sum(2 if (i % 2 == 0) else 1
                      for i, v in enumerate(vals, 1) if v is not None)
            mga = round(tot / coe, 2)
            # Total brut = somme des 6 notes (chaque note est /20)
            total_brut = round(sum(v for v in vals if v is not None), 2)
        else:
            mga = None
            total_brut = None
        out.append(
            AnnualRow(
                st,
                d.get(1), d.get(2), d.get(3), d.get(4), d.get(5), d.get(6),
                total_brut, mga, None,
            )
        )
    valid_sorted = sorted([r for r in out if r.mga is not None],
                           key=lambda r: r.mga, reverse=True)
    for idx, r in enumerate(valid_sorted, 1):
        r.rank = idx
    return out


# ---------------------------------------------------------------------------
#  Statistiques pour Compte Rendu
# ---------------------------------------------------------------------------
@dataclass
class ClassStats:
    effectif: int
    classes: int
    moyenne_classe: float | None
    nb_above_avg_per_subject: dict[int, int]   # subject_id → count
    distribution: dict[float, int]            # seuil (18..3) → count


def compute_stats(db: Database, exam_num: int) -> ClassStats:
    rows, subjects, _ = _cached_totalisation(db, exam_num)
    nb_min = get_setting_int(db, "nb_min_examens", 1)
    students = load_students(db)
    effectif = len(students)
    classed = [r for r in rows if r["valid"]]
    n_classed = len(classed)
    if n_classed:
        moy_classe = round(sum(r["moy"] for r in classed) / n_classed, 2)
    else:
        moy_classe = None

    nb_above: dict[int, int] = {}
    for s in subjects:
        cnt = 0
        for r in classed:
            v = r["notes"].get(s.id)
            if v is not None and v >= 10 * s.coeff:
                cnt += 1
        nb_above[s.id] = cnt

    distribution: dict[float, int] = {}
    for seuil in range(18, 2, -1):
        cnt = sum(1 for r in classed
                  if r["moy"] is not None and seuil <= r["moy"] < seuil + 1)
        distribution[float(seuil)] = cnt

    return ClassStats(effectif, n_classed, moy_classe, nb_above, distribution)
