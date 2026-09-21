"""Synchronisation bidirectionnelle entre les fichiers .xlsx du dossier
de la classe et la base SQLite.

Workflow cible (tel que voulu par le professeur principal) :

```
  Enseignant                          Logiciel
  ───────────                         ─────────
  édite <classe>/<Matière>.xlsx  ───► détecte les fichiers modifiés
  (sur sa machine, sans le logiciel)    importe les nouvelles notes
                                       dans la base de la classe
                                       recalcule totalisation, moyennes…
```

Ce module est *la* brique qui fait le pont. Il est **purement logique**
(importable sans Qt) et expose deux fonctions publiques :

- :func:`sync_subject_from_xlsx` : importe un seul sujet depuis son
  fichier ``.xlsx``
- :func:`sync_all_subjects`      : synchronise tous les fichiers
  trouvés dans le dossier de la classe

Le résultat est un :class:`SyncReport` qui décrit ce qui a été fait,
ce qui a été ignoré, et les erreurs éventuelles — utilisé par la
``SyncReportDialog`` pour informer l'utilisateur.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .db import Database
from .workspace import ClassInfo, _normalize


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Modèle
# ---------------------------------------------------------------------------
@dataclass
class SubjectSyncResult:
    """Résultat de la synchronisation d'un sujet unique."""

    subject_name: str
    xlsx_path: Optional[Path]
    matched: bool
    """``True`` si le fichier a été trouvé et reconnu pour ce sujet."""

    notes_total: int = 0
    """Nombre de notes lues dans le fichier."""

    notes_added: int = 0
    """Notes insérées en base (nouvelles)."""

    notes_updated: int = 0
    """Notes écrasées (valeur différente de l'existante)."""

    notes_unchanged: int = 0
    """Notes dont la valeur était déjà identique en base."""

    rows_skipped: int = 0
    """Lignes du fichier ignorées (num manquant, valeur invalide, etc.)."""

    students_added: int = 0
    """Élèves automatiquement ajoutés à la base (nouveaux numéros)."""

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.matched and not self.errors

    def summary_line(self) -> str:
        if not self.matched:
            return f"  ⨯ {self.subject_name} : fichier .xlsx introuvable"
        if self.errors:
            return f"  ⚠ {self.subject_name} : {self.errors[0]}"
        parts = [f"  ✓ {self.subject_name} : "]
        if self.students_added:
            parts.append(f"👤 {self.students_added} élève(s) ajouté(s), ")
        parts.append(
            f"{self.notes_added} nouvelle(s), "
            f"{self.notes_updated} mise(s) à jour, "
            f"{self.notes_unchanged} inchangée(s)"
        )
        return "".join(parts)


@dataclass
class SyncReport:
    """Bilan global d'une synchronisation."""

    class_name: str
    started_at: datetime
    finished_at: datetime
    subjects: list[SubjectSyncResult] = field(default_factory=list)

    @property
    def total_added(self) -> int:
        return sum(s.notes_added for s in self.subjects)

    @property
    def total_updated(self) -> int:
        return sum(s.notes_updated for s in self.subjects)

    @property
    def total_unchanged(self) -> int:
        return sum(s.notes_unchanged for s in self.subjects)

    @property
    def matched_count(self) -> int:
        return sum(1 for s in self.subjects if s.matched)

    @property
    def error_count(self) -> int:
        return sum(1 for s in self.subjects if s.errors)

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def total_students_added(self) -> int:
        return sum(s.students_added for s in self.subjects)

    def summary(self) -> str:
        lines = [
            f"Synchronisation {self.class_name} — "
            f"{self.matched_count}/{len(self.subjects)} matière(s) synchronisée(s) "
            f"en {self.duration_seconds:.2f}s",
        ]
        parts = []
        if self.total_students_added:
            parts.append(f"👤 +{self.total_students_added} élève(s)")
        parts.append(
            f"+{self.total_added} nouvelle(s), "
            f"~{self.total_updated} mise(s) à jour, "
            f"={self.total_unchanged} inchangée(s)"
        )
        lines.append("  " + ", ".join(parts))
        for s in self.subjects:
            lines.append(s.summary_line())
        return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Lecture d'un fichier .xlsx de notes
# ---------------------------------------------------------------------------
# Les en-têtes de notes attendues : M.J 1, M.J 2, M.J 3, Compo 1, …
# L'ordre logique est MJ1, Compo1, MJ2, Compo2, MJ3, Compo3 → exams 1..6
_EXAM_LABELS = {
    # Forme canonique (avec point)
    "m.j 1": 1, "mj 1": 1, "m.j1": 1,
    "compo 1": 2, "comp 1": 2,
    "m.j 2": 3, "mj 2": 3, "m.j2": 3,
    "compo 2": 4, "comp 2": 4,
    "m.j 3": 5, "mj 3": 5, "m.j3": 5,
    "compo 3": 6, "comp 3": 6,
    # Variantes « m j N » (le point disparaît dans _normalize)
    "m j 1": 1, "m j 2": 3, "m j 3": 5,
    # Variantes parfois observées dans les fichiers profs
    "interro 1": 1, "interro 2": 3, "interro 3": 5,
    "devoir 1": 2, "devoir 2": 4, "devoir 3": 6,
}


def _label_for_exam(n: int) -> str:
    """M.J pour impair, Compo pour pair — aligné sur ``grades.py``."""
    if n % 2 == 1:
        return f"M.J {(n + 1) // 2}"
    return f"Compo {n // 2}"


def _exam_from_label(label: object) -> Optional[int]:
    """Mappe un en-tête de colonne vers un numéro d'examen (1..6)."""
    norm = _normalize(str(label) if label is not None else "")
    if not norm:
        return None
    if norm in _EXAM_LABELS:
        return _EXAM_LABELS[norm]
    # Tolérance : si l'en-tête contient "mj" + chiffre
    import re
    m = re.match(r"^m\.?j\s*(\d+)$", norm)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 3:
            return 2 * n - 1
    m = re.match(r"^compo?\s*(\d+)$", norm)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 3:
            return 2 * n
    return None


def _find_header_row(ws, max_scan: int = 10) -> int:
    """Trouve la ligne d'en-têtes (ligne qui contient 'num' et au moins
    une colonne de note)."""
    best_row = 1
    best_score = 0
    for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan,
                                            values_only=True), start=1):
        score = 0
        for v in row:
            n = _normalize(v)
            if not n:
                continue
            if n in ("num", "numero", "n°", "nº", "n", "#", "no"):
                score += 2
            elif _exam_from_label(v) is not None:
                score += 3
            elif n in ("nom et prenoms", "nom prenoms", "nometprenoms",
                       "nom", "prenom", "prenoms", "full name", "name",
                       "eleve", "élève", "student name"):
                score += 1
        if score > best_score:
            best_score = score
            best_row = idx
    return best_row if best_score > 0 else 5


_NAME_LABELS = {
    "nom et prenoms", "nom prenoms", "nometprenoms",
    "nom et prénoms", "nom prénoms",
    "nom", "prenom", "prenoms", "prénom", "prénoms",
    "full name", "name", "eleve", "élève", "student name",
    "nom complet",
}


def _read_grades_xlsx(
    path: Path, nb_exams: int
) -> tuple[list[dict], list[str]]:
    """Lit un fichier ``.xlsx`` de notes.

    Retourne ``(rows, warnings)`` où ``rows`` est une liste de
    ``{num, exam_num, value, name}`` et ``warnings`` la liste des colonnes
    de notes non reconnues.
    """
    import openpyxl  # noqa: WPS433
    wb = openpyxl.load_workbook(str(path), data_only=True)
    ws = wb.active

    header_idx = _find_header_row(ws)
    header = [c.value for c in next(ws.iter_rows(min_row=header_idx,
                                                  max_row=header_idx))]

    # Index du num, des colonnes d'examen et de la colonne nom
    num_idx = -1
    name_idx = -1
    exam_cols: dict[int, int] = {}   # exam_num → col_idx
    for col_idx, h in enumerate(header):
        n = _normalize(h)
        if n in ("num", "numero", "n°", "nº", "n", "#", "no") and num_idx < 0:
            num_idx = col_idx
            continue
        if n in _NAME_LABELS and name_idx < 0:
            name_idx = col_idx
            continue
        ex = _exam_from_label(h)
        if ex is not None and ex not in exam_cols:
            exam_cols[ex] = col_idx

    warnings: list[str] = []
    if num_idx < 0:
        warnings.append("colonne 'Num' introuvable")
    if name_idx < 0:
        warnings.append("colonne 'Nom' introuvable — les nouveaux élèves ne pourront pas être détectés")
    for n in range(1, nb_exams + 1):
        if n not in exam_cols:
            warnings.append(f"colonne {_label_for_exam(n)} introuvable")

    rows: list[dict] = []
    for r in ws.iter_rows(min_row=header_idx + 1, values_only=True):
        if not r or all(v in (None, "") for v in r):
            continue
        if num_idx < 0 or num_idx >= len(r):
            continue
        try:
            num = int(r[num_idx])
        except (TypeError, ValueError):
            continue
        name = str(r[name_idx]).strip() if name_idx >= 0 and r[name_idx] is not None else ""
        for exam_num, col_idx in exam_cols.items():
            if col_idx >= len(r):
                continue
            v = r[col_idx]
            if v is None or v == "":
                continue
            try:
                value = float(v)
            except (TypeError, ValueError):
                continue
            rows.append({"num": num, "exam_num": exam_num, "value": value, "name": name})

    return rows, warnings


# ---------------------------------------------------------------------------
#  Synchronisation
# ---------------------------------------------------------------------------
def _get_subject_id_by_name(db: Database, name: str) -> Optional[int]:
    for s in db.list_subjects():
        if _normalize(s["name"]) == _normalize(name):
            return int(s["id"])
    return None


def _get_student_num_to_id(db: Database) -> dict[int, int]:
    """Renvoie ``{num: id}`` pour matcher les élèves par ``num``."""
    return {int(s["num"]): int(s["id"]) for s in db.list_students()}


def _get_existing_grades(
    db: Database, subject_id: int
) -> dict[tuple[int, int], float]:
    """Renvoie ``{(student_id, exam_num): value}`` pour le sujet."""
    out: dict[tuple[int, int], float] = {}
    for row in db.raw_query(
        "SELECT student_id, exam_num, value FROM grades WHERE subject_id=?",
        (subject_id,),
    ):
        if row["value"] is not None:
            out[(int(row["student_id"]), int(row["exam_num"]))] = float(row["value"])
    return out


def sync_subject_from_xlsx(
    db: Database,
    subject_name: str,
    xlsx_path: Path,
) -> SubjectSyncResult:
    """Importe le fichier ``xlsx_path`` dans le sujet ``subject_name``.

    Compare avec l'existant en base et compte ajouts / mises à jour /
    inchangés. L'écriture passe par :meth:`Database.set_grade` pour
    bénéficier de la logique ON CONFLICT.
    """
    result = SubjectSyncResult(
        subject_name=subject_name,
        xlsx_path=xlsx_path,
        matched=xlsx_path is not None and xlsx_path.is_file(),
    )
    if not result.matched:
        return result

    subject_id = _get_subject_id_by_name(db, subject_name)
    if subject_id is None:
        result.errors.append(
            f"Matière « {subject_name} » absente de la base. "
            f"Ajoutez-la dans l'onglet Configuration."
        )
        return result

    nb_exams = int(db.get_setting("nb_examens", "6") or 6)
    try:
        rows, warnings = _read_grades_xlsx(xlsx_path, nb_exams)
    except Exception as exc:  # noqa: BLE001
        log.exception("Failed to read %s", xlsx_path)
        result.errors.append(f"lecture impossible : {exc}")
        return result
    result.warnings = warnings

    num_to_id = _get_student_num_to_id(db)

    existing = _get_existing_grades(db, subject_id)

    to_write: list[tuple[int, int, int, float]] = []
    for row in rows:
        sid = num_to_id.get(row["num"])
        if sid is None:
            # Nouvel élève détecté : on l'ajoute automatiquement
            name = row.get("name", "").strip()
            if name:
                # Le nom complet dans le fichier est généralement
                # "Nom Prénom(s)" — le premier mot est le nom de famille
                parts = name.split(None, 1)
                if len(parts) == 2:
                    nom, prenom = parts[0], parts[1]
                else:
                    nom, prenom = name, ""
                try:
                    db.add_student(row["num"], nom=nom, prenoms=prenom)
                    result.students_added += 1
                    # Recharge le mapping pour la suite
                    num_to_id = _get_student_num_to_id(db)
                    sid = num_to_id.get(row["num"])
                except Exception as exc:  # noqa: BLE001
                    result.warnings.append(
                        f"Impossible d'ajouter l'élève n°{row['num']} ({name}) : {exc}"
                    )
            if sid is None:
                result.rows_skipped += 1
                continue
        key = (sid, row["exam_num"])
        old = existing.get(key)
        new = row["value"]
        if old is None:
            result.notes_added += 1
        elif abs(old - new) < 1e-6:
            result.notes_unchanged += 1
        else:
            result.notes_updated += 1
        to_write.append((sid, subject_id, row["exam_num"], new))
        result.notes_total += 1

    # Une seule transaction pour toutes les notes du sujet → ~100x plus
    # rapide que d'appeler db.set_grade() en boucle.
    if to_write:
        try:
            db.bulk_set_grades(to_write)
        except Exception as exc:  # noqa: BLE001
            log.exception("bulk_set_grades failed for %s", subject_name)
            result.errors.append(f"écriture en base impossible : {exc}")

    return result


def sync_all_subjects(
    db: Database,
    class_info: ClassInfo,
    *,
    only_dirty: bool = False,
    extra_dir: str | Path | None = None,
) -> SyncReport:
    """Synchronise **toutes** les matières trouvées dans le dossier.

    Paramètres
    ----------
    only_dirty
        Si ``True``, ne synchronise que les fichiers dont la date de
        modification est postérieure au dernier ``.db`` mtime. Pratique
        pour les syncs incrémentaux.
    extra_dir
        Dossier supplémentaire où chercher des fichiers .xlsx (ex.
        dossier d'export configuré). Les fichiers du dossier classe
        sont prioritaires en cas de doublon.
    """
    from .db import Database as _Db  # noqa: F401  (typing)
    started = datetime.now()
    report = SyncReport(
        class_name=class_info.display_name,
        started_at=started,
        finished_at=started,  # mis à jour à la fin
    )

    # Map ``nom_normalisé → fichier`` pour le dossier de la classe
    xlsx_by_norm = {_normalize(p.stem): p for p in class_info.subject_files}

    # Ajoute (et écrase) avec les fichiers du dossier d'export
    # (priorité aux fichiers modifiés par les enseignants)
    if extra_dir is not None:
        extra = Path(extra_dir)
        if extra.is_dir():
            for p in sorted(extra.glob("*.xlsx")):
                if p.name.startswith("~$"):
                    continue
                key = _normalize(p.stem)
                xlsx_by_norm[key] = p  # écrase volontairement

    db_mtime = None
    if only_dirty and class_info.db_path.exists():
        db_mtime = class_info.db_path.stat().st_mtime

    for subj in db.list_subjects():
        name = subj["name"]
        path = xlsx_by_norm.get(_normalize(name))
        if path is None:
            report.subjects.append(SubjectSyncResult(
                subject_name=name, xlsx_path=None, matched=False,
            ))
            continue
        if only_dirty and db_mtime is not None:
            if path.stat().st_mtime <= db_mtime:
                # Pas modifié depuis la dernière sync → on skip mais on
                # le marque comme "matched" pour le comptage
                report.subjects.append(SubjectSyncResult(
                    subject_name=name, xlsx_path=path, matched=True,
                    notes_unchanged=0,
                ))
                # NB : on ne lit pas le fichier, donc on ne peut pas
                # savoir combien de notes. C'est intentionnel : on
                # évite le coût d'ouverture pour rien.
                continue
        result = sync_subject_from_xlsx(db, name, path)
        report.subjects.append(result)

    report.finished_at = datetime.now()
    return report
