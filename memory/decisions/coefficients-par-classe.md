# Coefficients par classe (source de vérité)

Tags: coefficients, matieres, classes, bulletin, decision

## Origine

Correction ordonnée par l'utilisateur le **2026-09-20** (session
`ses_f40bdbf6effecy4jIkq4EGo4Ro`, "Coefficients des matières par classe").
Les valeurs ont été lues dans les fichiers `.xlsx` (cellule **C4**) de
`/mnt/sda3/BULLETIN/BULLETIN/BULLETIN/{COLLEGE,LYCEE}/<classe>/`.

⚠️ Ces fichiers `.xlsx` ont **été supprimés depuis** (il ne reste que
4 `.xlsm` et 6 `.db`). Ce tableau est donc l'**unique trace complète**.
Vérifié : `COLLEGE/6EME3/bullein/Bulletin6EME3.xlsm` donne bien
Physique-chimie = 2 pour 6EME3, comme le tableau.

## Tableau des coefficients

| Matière | 1ereLI | 1ereLII | 1ereS | 2ndeI | 2ndeII | 3EME1 | 3EME2 | 4EME1 | 4EME2 | 5EME1 | 5EME2 | 6EME1 | 6EME2 | 6EME3 | TAI | TAII | TD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Malagasy | 4 | 4 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 4 | 4 | 3 |
| Français | 3 | 3 | 2 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 2 |
| Anglais | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 1 |
| Histo-geo | 4 | 4 | 2 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 4 | 4 | 2 |
| Mathématiques | 2 | 2 | 4 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 2 | 2 | 4 |
| Physique-chimie | 2 | 2 | 4 | 3 | 3 | 3 | 3 | 3 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 4 |
| SVT | 2 | 2 | 4 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 2 | 2 | 4 |
| Philosophie | 2 | 2 | 2 | — | — | — | — | — | — | — | — | — | — | — | 4 | 4 | 2 |
| EPS | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| EVA | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| Religion | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |

Règles :
- **Philosophie** : uniquement Lycée (1ère, Terminale/TA), **jamais** au
  Collège ni en 2nde. Coeff **4 en TA1/TA2** (et toute classe `TA*`),
  2 partout ailleurs (1ère, TD, TLE…).
- **Physique-chimie** = 3 en 3EME1/3EME2/4EME1 mais **2** en 4EME2→6EME3.
- Groupe « scientifique » (1ereS, TD) : Maths/Physique/SVT = **4**,
  Français/Anglais/Histo = faibles.
- Collège et 2nde : quasi uniforme (Malagasy/Français/Histo/Maths/PC/SVT
  = 3, Anglais = 2, EPS/EVA/Religion = 1).

## Noms de classes : correspondance ancien → actuel

Les dossiers ont été renommés (romain → arabe) :

| Tableau / anciens dossiers | Dossiers actuels |
|---|---|
| 1ereLI | `LYCEE/1EREL1` |
| 1ereLII | `LYCEE/1EREL2` |
| 1ereS | `LYCEE/1ERES` |
| 2ndeI | `LYCEE/2NDE1` |
| 2ndeII | `LYCEE/2NDE2` |
| TAI | `LYCEE/TA1` |
| TAII | `LYCEE/TA2` |
| TD | `LYCEE/TD` |
| 3EME1…6EME3 | `COLLEGE/3EME1`…`COLLEGE/6EME3` |

## État du code

### Avant (constaté le 2026-11-24) — depuis corrigé

- **Commit HEAD (`6e68bca`) contenait** `CLASS_DEFAULTS` +
  `_get_class_defaults()` dans `app/db.py`, mais avec des bugs :
  `TA1`/`TA2` non reconnus → fallback Collège silencieux, et
  Physique-chimie = 3 partout au Collège (alors que 4EME2→6EME3 = 2).
- Le working tree avait **perdu** cette correction (archive du
  2026-06-28 extraite par-dessus) mais contenait des ajouts absents de
  HEAD : `LEVEL_SUBJECT_RESTRICTIONS`, `CLASS_COEFF_OVERRIDES`
  (`("TA","philosophie"): 4.0`), `_SUBJECT_ALIASES`.
- → **Fusion manuelle faite**, pas de `git checkout` (ajouts du
  working tree préservés).

### Mis en place le 2026-11-24 — Python puis Rust

**Python**

- `app/db.py` : tables `COEFFS_COLLEGE`, `COEFFS_LYCEE_G1/G2/G3`
  (17 classes du tableau), `get_class_defaults()` (reconnaît les noms
  romains **et** arabes), `class_default_coeff()`, migration
  `_migrate_class_coefficients()` pilotée par la clé de settings
  `coeff_defaults_version = "2026-09-20"`.
- `app/wizards/class_wizard.py` : `ClassDraft.subjects_initial`,
  `_subjects_for_class()` (coeffs par classe + filtrage par niveau),
  coeffs par classe à la création (DB **et** cellule C4 du xlsx).
- `app/workspace.py` : `read_coefficient_from_xlsx() -> float | None`,
  `extract_level_key()`, `_SUBJECT_ALIASES`, `normalize_class_name()`.
- Migration exécutée sur les **8 bases réelles**
  `LYCEE/*/data/bulletin.db` (sauvegardes dans
  `data/.backups/bulletin.before_coeff_*.bak`).

**Rust (`bulletin-rs`)** — parité totale vérifiée par `diff`

- `workspace.rs` : `normalize_class_name`, `extract_level_key`,
  `subject_aliases` / `subject_name_aliases`, découverte de classe
  « lenient » (dossier sans xlsx ni `bulletin/`).
- `db.rs` : mêmes tables `COEFFS_*` (avec `Éducation à la Vie` plutôt
  que `EVA`, pour coller aux noms produits par le seed Python),
  `get_class_defaults`, `class_default_coeff`, `migrate_class_coefficients`
  (appelé **avant** le seed), `seed_subjects` avec coeffs par classe.
- `class_create.rs` : filtre par niveau + coeffs par classe à la création.
- `sync.rs` : recherche du xlsx alias-aware (comme `app/sync.py`).
- `main.rs` : aperçu « nouvelles matières » avec coeffs de la 1re classe.
- Tests : `db::class_defaults_match_python_rules`,
  `db::class_default_coeff_honours_aliases_and_level_rules`,
  `db::coefficient_migration_applies_once_per_database`,
  `class_create::per_class_coefficients_replace_catalog_values`,
  `class_create::philosophy_is_dropped_for_seconde_classes`,
  `workspace::normalize_class_name_matches_python_examples`,
  `workspace::extract_level_key_matches_python_examples`,
  `workspace::subject_aliases_link_base_and_file_names`.
- **Parité** : `scripts/parity_coefficients.py` (Python) vs
  `bulletin-rs/crates/bulletin-core/tests/parity_dump.rs` (Rust) →
  sorties identiques ligne à ligne.

### Décisions de port

- Les 17 classes du tableau sont indexées sous leur nom **normalisé**
  (`1EREL1`, `TA1`, `2NDE1`…) ; `normalize_class_name()` convertit les
  variantes (romaines, `1L1`, `6ème I`, `T.A`…).
- Rust nomme `Éducation à la Vie` dans `COEFFS_*` (nom réel en base) ;
  le catalogue `SECTIONS` garde `EVA`/`Histo-geo` comme Python, et la
  carte d'alias fait le pont.
- Pas de cache `bulletin excel/` dans le dépôt Rust → `seed_subjects`
  saute l'étape 2 de Python (xlsx C4, puis tableau de classe).
- Migration **une fois par base** (drapeau `coeff_defaults_version`) ;
  les saisies manuelles ultérieures sont conservées, mais une base sans
  drapeau est réécrite (choix utilisateur : « Forcer le tableau
  partout »).
- **`git checkout` interdit** : le working tree contient des ajouts
  absents de HEAD à préserver.
