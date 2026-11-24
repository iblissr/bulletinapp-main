# Bulletin — portage Rust natif

Application de gestion de bulletins scolaires, portée de l'application
Python/PyQt6 vers **Rust + [Slint](https://slint.dev/)**.

- **Aucune webview**, aucun runtime Python : le rendu est fait par Slint.
- **Mêmes données** : bases SQLite et classeurs `.xlsx` existants, sans
  migration.
- **Mêmes calculs** : totalisation par examen, moyennes trimestrielles,
  moyenne annuelle, rangs et statistiques. La parité avec le Python est
  vérifiée par des tests (voir plus bas).
- **Même espace de travail** : `COLLEGE/`, `LYCEE/`, `PRIMAIRE/`.

## Structure

```
bulletin-rs/
├── crates/
│   ├── bulletin-core/     # métier : SQLite, calculs, lecture/écriture xlsx,
│   │                      #   imports, création de classe, export PDF
│   └── bulletin-app/      # interface Slint + callbacks
│       ├── src/main.rs
│       └── ui/app.slint
├── build_windows.sh       # compilation croisée Linux → Windows
└── Cargo.toml
```

## Prérequis

- Rust stable récent (testé avec 1.95).
- Linux : les bibliothèques graphiques habituelles (Wayland ou X11),
  `pkg-config`, un compilateur C (pour SQLite embarqué).
- Windows (compilation croisée) : cible `x86_64-pc-windows-gnu` et
  mingw-w64.

## Compilation

### Linux

```bash
cd bulletin-rs
cargo build --release -p bulletin-app
# binaire : target/release/bulletin-app
```

### Windows (depuis Linux)

```bash
cd bulletin-rs
./build_windows.sh
# binaire : target/x86_64-pc-windows-gnu/release/bulletin-app.exe
```

Le `.exe` est produit en sous-système `windows` (pas de console).
Il a été testé sous Wine avec les bases existantes.

Des copies prêtes à l'emploi sont également fournies dans `dist/` :

- `dist/bulletin-linux-x86_64`
- `dist/bulletin-windows-x86_64.exe`

### Exécution

```bash
./target/release/bulletin-app
```

La racine de l'espace de travail est cherchée dans le dossier courant et
ses parents (présence de `COLLEGE/`, `LYCEE/` ou `PRIMAIRE/`). Elle peut
aussi être imposée :

```bash
BULLETIN_ROOT=/chemin/vers/BULLETIN ./target/release/bulletin-app
```

Au premier lancement, l'application ne crée pas de base vide : elle
affiche les classes déjà présentes. La création se fait depuis
« Nouvelle classe ».

## Écrans

| Écran | Fonctions |
|---|---|
| Accueil | cartes des classes, filtres division, recherche, statistiques, nouvelle classe |
| Élèves | liste, ajout/modification/suppression, génération de liste, import Excel |
| Notes | saisie par matière et par examen, import/synchronisation/export `.xlsx` |
| Moyennes | 3 trimestres + moyenne annuelle, classement, export |
| Totalisation | classement par examen, export |
| Compte rendu | statistiques par matière, répartition des moyennes, export PDF |
| Configuration | établissement, année, examens, effectif, matières et coefficients, sauvegarde/restauration |
| Nouvelle classe | section, niveau, motif de sous-classes, effectif, création des dossiers, base, matières, élèves et `.xlsx` |

## Imports

- **Élèves** : reprise des heuristiques de `import_helpers.py` — détection
  de la ligne d'en-têtes, alias français/anglais, découpage « NOM Prénoms »,
  fusion de tous les onglets, mise à jour par numéro.
- **Notes** : lecture des classeurs de matières, tolérante aux lignes de
  métadonnées et aux en-têtes `M.J` / `Compo`.

## Exports

- Feuille de matière `.xlsx`.
- Totalisation et moyennes `.xlsx`.
- Feuilles profs.
- Compte rendu **PDF autonome** : writer maison (Helvetica base-14,
  encodage WinAnsi), aucune dépendance externe ni accès réseau.
- Sauvegarde / restauration de la base SQLite.

## Tests

```bash
cd bulletin-rs
cargo test --workspace
```

La suite couvre notamment :

- les formules de calcul (totalisation, trimestres, annuelle, stats) ;
- la parité avec des résultats Python de référence ;
- l'import d'élèves (en-têtes décalés, colonnes FR/EN, doublons) ;
- la création de classe (dossiers, base, matières, élèves, `.xlsx`) ;
- la relecture des feuilles vides par la synchronisation ;
- l'export PDF (en-tête `%PDF` et structure valide).

Un exemple permet de vider les calculs d'une base pour comparaison :

```bash
cargo run -p bulletin-core --example dump -- /chemin/vers/bulletin.db
```

## Notes de comportement

- Comme dans l'application Python, **Philosophie** n'apparaît dans les
  matières d'une classe que pour les niveaux Première et Terminale.
- Les notes sont stockées en points pondérés par le coefficient, comme
  dans le schéma d'origine.
- Les exports sont écrits dans `<classe>/exports/` par défaut, avec un
  sous-dossier `export prof/<division>/<classe>/` pour les feuilles
  professeurs.
- Aucun accès réseau n'est effectué par l'application.

## Différences assumées avec la version PyQt6

Le cœur métier, les écrans et les données sont identiques. Certains
conforts de l'interface Python ne sont pas repris à l'identique :

| Point | Version Python | Version Rust |
|---|---|---|
| Création de classe | assistant en 7 étapes | page unique (mêmes fichiers produits) |
| Thème | clair + sombre | clair uniquement |
| Imports | assistant avec aperçu | import direct avec résumé |
| Sauvegardes | par classe + fusion/écrasement global | par classe : créer, restaurer, vider |
| Dossiers d'export | configurables | `<classe>/exports/` |
| Logo d'établissement | choisi et utilisé dans le PDF | non repris |
| Tri des tableaux | clic sur les en-têtes | ordre naturel / classement |

La page « Nouvelle classe » crée les mêmes dossiers, bases, matières,
élèves et classeurs `.xlsx` que l'assistant Python. Les effectifs, les
matières et leurs coefficients restent modifiables ensuite dans
l'onglet Configuration.
