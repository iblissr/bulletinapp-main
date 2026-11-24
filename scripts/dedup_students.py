"""Supprime les élèves en doublon (même nom + prénoms) dans chaque classe.

Stratégie : pour chaque groupe de doublons, on conserve l'élève
avec le plus petit N°, on lui attribue les notes des doublons,
puis on supprime les doublons.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC))

from app.workspace import discover_classes


def dedup_one(db_path: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    dupes = conn.execute("""
        SELECT nom, prenoms, COUNT(*) as cnt,
               GROUP_CONCAT(id, ',') as ids,
               GROUP_CONCAT(num, ',') as nums
        FROM students
        GROUP BY LOWER(nom), LOWER(prenoms)
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
    """).fetchall()

    results = []
    for d in dupes:
        ids = [int(x) for x in d["ids"].split(",")]
        nums = [int(x) for x in d["nums"].split(",")]
        # Garder celui avec le plus petit num
        pairs = sorted(zip(nums, ids))
        keep_id = pairs[0][1]
        dup_ids = [pid for _, pid in pairs[1:]]

        # Migrer les notes des doublons vers le conservé
        for did in dup_ids:
            conn.execute(
                "INSERT OR IGNORE INTO grades(student_id, subject_id, exam_num, value) "
                "SELECT ?, subject_id, exam_num, value FROM grades WHERE student_id=?",
                (keep_id, did),
            )
            conn.execute("DELETE FROM grades WHERE student_id=?", (did,))
            conn.execute("DELETE FROM students WHERE id=?", (did,))

        conn.commit()
        results.append({
            "nom": d["nom"],
            "prenoms": d["prenoms"],
            "keep_id": keep_id,
            "deleted_ids": dup_ids,
        })
    conn.close()
    return results


def main() -> None:
    classes = discover_classes()
    total = 0
    for c in classes:
        db_path = str(c.db_path)
        if not Path(db_path).exists():
            continue
        results = dedup_one(db_path)
        if results:
            print(f"\n=== {c.name} ({c.division}) ===")
            for r in results:
                print(f"  {r['nom']} {r['prenoms']}: "
                      f"gardé id={r['keep_id']}, supprimé ids={r['deleted_ids']}")
                total += len(r["deleted_ids"])
    print(f"\nTotal : {total} doublon(s) supprimé(s).")


if __name__ == "__main__":
    main()
