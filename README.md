# Bulletin Premium

Réécriture en Python + Qt (PyQt6 via QtPy) du classeur `Bulletin modele.xlsm`,
avec une couche d'**améliorations P1→P3** (sauvegarde auto, recherche,
tri, breadcrumb, sauvegarde de la base, etc.) et un système de
**sauvegarde/restauration/fusion/reset total** inspiré de
`eco_paiement premium`.

## Installation

```bash
cd "bulletin premium"
pip install -r requirements.txt
```

## Lancement

```bash
python main.py
```

Une base SQLite est créée automatiquement à `data/bulletin.db`.
Une copie horodatée est faite dans `data/.backups/` à chaque démarrage
(rotation automatique des 7 sauvegardes les plus récentes).

## Améliorations par rapport à `bulletinAPP`

### P1 — Correctifs de bugs

| # | Quoi | Fichier |
|---|---|---|
| B1 | Ligne « SAINTE MARIE » hardcodée → reprend `annee_scolaire — classe` | `widgets/totalisation.py:99-104` |
| B2 | SpinBox `nb_examens` limité à 1-6 (au lieu de 1-12) | `widgets/config.py:147,159` |
| B3 | « Réligion » → « Religion » (typo) + micro-migration | `db.py:83`, `wizards/subjects_catalog.py:101,125` |
| B4 | Suppression de code mort | `widgets/students.py:104` |
| B5 | Constantes `TAB_DASHBOARD/CONFIG/STUDENTS` + `go_to_tab(name)` | `main_window.py:58-64` |
| B6 | `db.raw_query(sql, params)` public (plus de `db._conn` exposé) | `db.py`, `models.py`, `sync.py` |
| B7 | `_generate` affiche `added + skipped` | `widgets/students.py:202-213` |
| B8 | Doublon `"prenoms", "prenoms"` dans `import_helpers.py` | `widgets/import_helpers.py:69` |
| B10 | `prof_principal` + `accent_color` ajoutés à `DEFAULT_SETTINGS` | `db.py` |

### P2 — Qualité de vie

- **Auto-save debouncé (600 ms)** sur les notes — `widgets/grades.py`
  → plus besoin de cliquer « Enregistrer » après chaque note.
- **SearchBar** live sur les tables Élèves, Moyennes, Compte Rendu
  (filtre nom / matricule / matière) — `widgets/common.py:SearchBar`.
- **Tri par clic d'en-tête** sur les tables (numérique ou alphabétique)
  — `widgets/common.py:install_table_sort()`.
- **Breadcrumb** cliquable `Accueil › <Classe> › <Onglet>` au-dessus
  des onglets — `widgets/common.py:Breadcrumb`.
- **ProgressOverlay** semi-transparent avec spinner rotatif pendant
  la synchronisation — `widgets/common.py:ProgressOverlay`.
- **show_toast** remplace les `QMessageBox.information` non-critiques
  dans les onglets Élèves, Notes, etc.
- **Validation** des entrées : `effectif ≥ nb_filles + nb_garcons`,
  valeurs ≥ 0, `coeff > 0`, `num > 0`.
- **Champ `prof_principal`** dans l'identité de l'établissement.
- **Constantes couleurs** centralisées dans `widgets/table_helpers.py`
  (`COLOR_AVERAGE_OK`, `COLOR_AVERAGE_FAIL`, `COLOR_SUBJECT_MJ`, etc.).
- **Helpers factorisés** : `make_item`, `make_header`, `make_grade_item`,
  `fmt_value`, `color_for_average`, `wrap_layout`, `stretch_columns`.

### P3 — Nouvelles capacités

- **Bulletins PDF individuels par trimestre** (à venir) — `app/printing.py`.
- **Backups automatiques** au démarrage (rotation 7 jours) —
  `db.Database.backup(keep=7)`.
- **Thème custom local** (lecture `accent_color` du setting) — en cours.
- **Class zip import/export** (à venir).

## Fonctionnalités préservées (de `bulletinAPP`)

| Onglet | Équivalent dans le modèle | Rôle |
|---|---|---|
| Configuration | Feuille `principale` | Établissement, classe, année, matières + coefficients + profs, effectif, validation |
| Élèves | `CreateOrUpdateListe` | Saisie / import / génération de la liste |
| Notes par matière (x11) | `GénérerFichesMatieres` | Saisie des 6 notes par matière, import/export `.xlsx` |
| Totalisation | `CreerFeuillesTotalisation` | Crosstab élèves × matières + Tot/Moy/Rang par examen |
| Moyennes | `MoyenneGeneraleDesEleves` | T1/T2/T3 + Annuelle |
| Compte Rendu | `CreerCompteRendu` | Stats par examen (effectif, classés, %≥10, distribution) |

## Architecture

```
bulletin premium/
├── main.py                          point d'entrée (backup auto au boot)
├── requirements.txt
├── data/
│   ├── bulletin.db                  base SQLite (créée au 1er lancement)
│   └── .backups/                    sauvegardes horodatées (rotation 7)
└── app/
    ├── db.py                        couche persistance (+ raw_query, backup)
    ├── models.py                    calculs (Totalisation, Moyennes, Stats)
    ├── main_window.py               fenêtre principale + breadcrumb
    └── widgets/
        ├── common.py                Panel, TopContainer, SearchBar,
        │                            Breadcrumb, ProgressOverlay,
        │                            install_table_sort, show_toast, …
        ├── table_helpers.py         helpers factorisés + constantes couleurs
        ├── config.py                onglet Configuration (+ prof_principal,
        │                            + validation effectif/f/g)
        ├── students.py              onglet Élèves (+ SearchBar, tri)
        ├── grades.py                onglet Notes (+ auto-save debouncé)
        ├── totalisation.py          onglet Totalisation
        ├── moyennes.py              onglet Moyennes (+ SearchBar, tri)
        ├── compte_rendu.py          onglet Compte Rendu (+ SearchBar, tri)
        ├── dashboard.py             sous-dashboard de classe
        └── home_dashboard.py        dashboard principal (cards de classes)
```

## Logique métier (reproduit fidèlement le VBA)

- **Totalisation** : `Tot = Σ(notes)`, `Moy = Σ(notes × coef) / Σ(coef matières où la note existe)`, `Rang` par tri à bulles décroissant.
- **Trimestre** : `MoyT = (Moy_MJ × 1 + Moy_Compo × 2) / 3` (Compo coefficient 2).
- **Annuelle** : `MGA = Σ(notes × c) / Σ(c)` avec `c=1` pour MJ, `c=2` pour Compo.
- **Validation** : un élève avec `nb_notes_valides < nb_min_examens` est marqué `NC`.
- **Compte Rendu** : `% ≥ 10/20` = `count(note ≥ 10 × coef)`, distribution par tranches `[18..3]`.

## Différences avec le modèle Excel

- ✅ Pas de VBA, pas de `Form Control CheckBox` qui n'existe pas : tout est dans la DB.
- ✅ Recalcul automatique à chaque modification.
- ✅ Plusieurs classes possibles (il suffit de copier `data/bulletin.db`).
- ✅ Auto-save des notes (debounce 600 ms).
- ✅ Recherche / tri sur les tables (élèves, moyennes, stats).
- ✅ Backups automatiques au démarrage.
- ✅ Export PDF du compte rendu, export XLSX des moyennes.
- ✅ Import XLSX des notes par matière (et export pour les enseignants).
- ✅ **Import XLSX élèves multi-classes** : 1 classeur avec N feuilles = N classes (tree-view avec checkboxes, détection de doublons, statuts colorés).
- ✅ **Auto-création des classes** depuis les feuilles d'un XLSX (« 6e I » → `COLLEGE/6EME1/data/bulletin.db` créé automatiquement, puis import des élèves).
- ✅ **Import CSV** : onglet legacy pour coller/charger un CSV simple (`num;matricule;nom;prenoms;genre;naissance`).
- ✅ **UI refondue** : hero header avec logo gradient, KPI en gros chiffres, barre de recherche + filter chips (Tous/Collège/Lycée), toggle Grille ↔ Liste, cards redesignées (header gradient, barre latérale d'accent, hover élévation, footer avec dernière sync).
- ✅ **Sauvegarder / Restaurer / Fusionner / Réinitialiser** (pattern eco_paiement premium) :
  - 3 onglets + 1 onglet « Tout effacer » dans `BackupManagerDialog`.
  - Auto-backup avant toute opération destructive (`before_wipe_*.bak`, `before_replace_*.bak`).
  - **Reset total du workspace** : supprime TOUTES les classes (DB + bulletins + xlsx), avec triple confirmation et option « Garder les .xlsx ». L'accueil devient complètement vide.
  - Bouton « Sauvegardes » + bouton « Tout effacer » directement sur l'accueil.
  - Entrée menu **Outils > Sauvegarder / Restaurer…** (Ctrl+B) et **Outils > Réinitialiser TOUT le workspace…**.
