"""Découverte et gestion des « workspaces » (un workspace = une classe).

Le projet BULLETIN/ contient deux grandes divisions (LYCEE/ et COLLEGE/)
chacune avec plusieurs sous-dossiers de classe. Chaque classe possède :

- un fichier .xlsx par matière (saisie par l'enseignant)
- un sous-dossier ``bulletin/`` contenant le ``Bulletin<CLASSE>.xlsm``
  généré

Ce module scanne l'arborescence, expose une liste de :class:`ClassInfo`
et fournit des helpers de résolution de chemins (``<classe>/<Matière>.xlsx``,
``<classe>/bulletin/Bulletin<CLASSE>.xlsm``).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Modèle
# ---------------------------------------------------------------------------
# Les dossiers réels : ``BULLETIN/COLLEGE/3EME1`` → niveau = "COLLEGE"
#                      ``BULLETIN/LYCEE/1ereLI``  → niveau = "LYCEE"
DIVISIONS: tuple[str, ...] = ("COLLEGE", "LYCEE", "PRIMAIRE")

# Sujets exclus par niveau de classe. La clé est le nom normalisé
# de la matière, la valeur est un pattern regex sur le nom de la classe
# (insensible à la casse). Les matières listées ici ne sont incluses
# que si la classe correspond au pattern.
_SUBJECT_LEVEL_RULES: dict[str, str] = {
    # Philosophie : seulement Première et Terminale (pas Seconde, pas Collège)
    "philosophie": r"^(1ere|1ère|1e?re?l|1e?re?s|t[ae]?|td)",
}


@dataclass(frozen=True)
class ClassInfo:
    """Métadonnées d'une classe découverte.

    Attributes
    ----------
    name
        Nom du dossier (``3EME1``, ``1ereLI``, …) — c'est l'identifiant
        humain (utilisé aussi pour le nom de fichier .xlsm).
    display_name
        Libellé plus lisible (capitalise + remet les romains en
        majuscules : ``3EME1`` → ``3ème 1``, ``1ereLI`` → ``1ère LI``).
    division
        ``"COLLEGE"`` ou ``"LYCEE"``.
    folder
        Chemin absolu du dossier de la classe.
    db_path
        Chemin proposé pour la base SQLite (par défaut
        ``<folder>/data/bulletin.db``).
    bulletin_path
        Chemin du ``Bulletin<CLASSE>.xlsm`` dans ``<folder>/bulletin/``.
    subject_files
        Liste des fichiers ``.xlsx`` de matières détectés à la racine
        du dossier (ex. ``Anglais.xlsx``, ``Mathématiques.xlsx``).
    """

    name: str
    display_name: str
    division: str
    folder: Path
    db_path: Path
    bulletin_path: Path
    subject_files: list[Path] = field(default_factory=list)

    def bulletin_name(self) -> str:
        """Nom de fichier officiel du bulletin : ``Bulletin1ERELI.xlsm``."""
        return f"Bulletin{self.name.upper()}.xlsm"

    def subject_path(self, subject_name: str) -> Path:
        """Renvoie ``<folder>/<Matière>.xlsx``.

        ``subject_name`` peut être passé en casse libre (la recherche
        est insensible à la casse et aux accents).
        """
        target = _normalize(subject_name)
        for p in self.subject_files:
            if _normalize(p.stem) == target:
                return p
        # Fallback : nom tel quel, l'import lèvera une erreur claire.
        return self.folder / f"{subject_name}.xlsx"

    def has_subject(self, subject_name: str) -> bool:
        target = _normalize(subject_name)
        return any(_normalize(p.stem) == target for p in self.subject_files)


# ---------------------------------------------------------------------------
# Normalisation (équivalent de l'import_helpers, mais sans dépendance Qt)
# ---------------------------------------------------------------------------
def _normalize(text: str) -> str:
    if not text:
        return ""
    s = str(text).strip().lower()
    import unicodedata
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# Décoration des noms de classes
# ---------------------------------------------------------------------------
# 3EME1 → "3ème 1", 1ereLI → "1ère LI", 2ndeII → "2nde II", TAI → "TAI"
_CLASS_DISPLAY_RE = re.compile(r"^(\d+)?(eme|ère|ere|nde)?(.*)$", re.IGNORECASE)


def prettify_class_name(raw: str) -> str:
    """Transforme ``3EME1`` en ``3ème 1``, ``1ereLI`` en ``1ère LI``."""
    m = _CLASS_DISPLAY_RE.match(raw.strip())
    if not m:
        return raw
    num, kind, rest = m.groups()
    # Construit le préfixe (avec ou sans espace selon qu'il y a un
    # suffixe romain/chiffre derrière). On colle au suffixe s'il
    # existe pour avoir ``3ème 1`` et non ``3 ème 1``.
    prefix = ""
    if num:
        prefix += num
    if kind:
        kl = kind.lower()
        if kl == "eme":
            prefix += "ème"
        elif kl in ("ère", "ere"):
            prefix += "ère"
        elif kl == "nde":
            prefix += "nde"
    # Sépare le suffixe du préfixe par un espace s'il y a un préfixe
    # et un suffixe non vide
    if prefix and rest:
        return f"{prefix} {rest}"
    return prefix + (rest or "")


# ---------------------------------------------------------------------------
# Découverte
# ---------------------------------------------------------------------------
def find_bulletin_root(start: Optional[Path] = None) -> Path:
    """Remonte l'arborescence pour trouver le dossier ``BULLETIN/``.

    On cherche un dossier contenant les sous-dossiers ``COLLEGE`` et
    ``LYCEE`` (ou un seul des deux). Si rien n'est trouvé :

    - Si ``start`` a été fourni explicitement, on retourne ``start``
      tel quel (le caller a fourni un workspace vide, on respecte ça).
    - Sinon, on retourne le ``BULLETIN/`` calculé depuis la racine
      du projet (grand-parent de ``app/``).
    """
    if start is not None:
        p = Path(start).resolve()
        # Si start est déjà un workspace avec COLLEGE/LYCEE/PRIMAIRE, on garde
        if any((p / d).is_dir() for d in DIVISIONS):
            return p
        # Sinon on remonte dans les parents
        for ancestor in [p, *p.parents]:
            if any((ancestor / d).is_dir() for d in DIVISIONS):
                return ancestor
        # Aucun parent n'a COLLEGE/LYCEE/PRIMAIRE : on respecte le root fourni
        return p
    p = Path(__file__).resolve()
    for ancestor in [p, *p.parents]:
        if any((ancestor / d).is_dir() for d in DIVISIONS):
            return ancestor
    # Fallback : on suppose que c'est le grand-parent de ``bulletinAPP``
    return Path(__file__).resolve().parents[3]


def discover_classes(root: Optional[Path] = None) -> list[ClassInfo]:
    """Scanne ``BULLETIN/`` et retourne la liste triée des classes.

    Le tri est ``division ASC, display_name ASC``.

    Le scanner accepte à la fois les noms canoniques
    (``COLLEGE``/``LYCEE``, en majuscules) et les versions
    accentuées utilisées par l'assistant de création
    (``Collège``/``Lycée``).
    """
    bulletin_root = find_bulletin_root(root)
    classes: list[ClassInfo] = []
    # On accepte plusieurs variantes de noms de dossier pour
    # rester rétrocompatible avec les classes existantes (en
    # majuscules) tout en supportant les versions accentuées
    # que l'assistant peut produire.
    seen: set[Path] = set()
    accent_map = {
        "COLLEGE": "Collège",
        "LYCEE": "Lycée",
        "PRIMAIRE": "Primaire",
    }
    for division in DIVISIONS:
        candidates = [division, division.capitalize()]
        if division in accent_map:
            candidates.append(accent_map[division])
        for div_name in candidates:
            div_dir = bulletin_root / div_name
            if not div_dir.is_dir():
                continue
            for class_dir in sorted(div_dir.iterdir(), key=lambda d: d.name.lower()):
                if not class_dir.is_dir():
                    continue
                if class_dir in seen:
                    continue
                seen.add(class_dir)
                if class_dir.name.lower() in ("data", "bulletin"):
                    continue
                info = _build_class_info(class_dir, division)
                if info is not None:
                    classes.append(info)
    classes.sort(key=lambda c: (c.division, c.display_name.lower()))
    return classes


def discover_class(name: str, root: Optional[Path] = None) -> Optional[ClassInfo]:
    """Retrouve un :class:`ClassInfo` par son nom de dossier."""
    target = name.strip()
    for c in discover_classes(root):
        if c.name.lower() == target.lower():
            return c
    return None


def _build_class_info(class_dir: Path, division: str) -> Optional[ClassInfo]:
    """Construit un :class:`ClassInfo` à partir d'un dossier.

    La classe est considérée valide si :
    - le dossier contient au moins un ``.xlsx`` de matière, OU
    - il contient un sous-dossier ``bulletin/`` (classe « orpheline »).
    """
    xlsx_files = sorted(
        p for p in class_dir.glob("*.xlsx") if not p.name.startswith("~$")
    )
    # Filtre les matières selon le niveau de la classe
    class_name_lower = class_dir.name.lower()
    xlsx_files = [
        p for p in xlsx_files
        if not _is_subject_excluded(p.stem, class_name_lower)
    ]
    bulletin_dir = class_dir / "bulletin"
    bulletin_path = bulletin_dir / f"Bulletin{class_dir.name.upper()}.xlsm"
    db_dir = class_dir / "data"
    db_path = db_dir / "bulletin.db"

    if not xlsx_files and not bulletin_dir.is_dir():
        return None  # pas une classe

    return ClassInfo(
        name=class_dir.name,
        display_name=prettify_class_name(class_dir.name),
        division=division,
        folder=class_dir,
        db_path=db_path,
        bulletin_path=bulletin_path,
        subject_files=xlsx_files,
    )


def _is_subject_excluded(subject_name: str, class_name_lower: str) -> bool:
    """Retourne True si la matière ne doit pas figurer dans cette classe."""
    normalized = _normalize(subject_name)
    if normalized not in _SUBJECT_LEVEL_RULES:
        return False
    pattern = _SUBJECT_LEVEL_RULES[normalized]
    return not bool(re.search(pattern, class_name_lower))


# ---------------------------------------------------------------------------
# Mapping matière ↔ fichier
# ---------------------------------------------------------------------------
def read_coefficient_from_xlsx(path: Path) -> float | None:
    """Lit le coefficient dans un fichier ``.xlsx`` de matière.
    
    Le coefficient est stocké en cellule **C4** (ligne 4, colonne 3)
    du premier onglet du fichier.
    
    Retourne le coefficient, ou ``None`` si la lecture échoue.
    """
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path), data_only=True)
        ws = wb.active
        val = ws["C4"].value
        if val is not None:
            return float(val)
    except Exception:
        pass
    return None


# Cache session pour les chemins de dossiers bulletin excel
_bulletin_excel_class_dirs: dict[str, Path] = {}


def _get_bulletin_excel_matieres_dir(class_name: str) -> Path | None:
    """Trouve le dossier ``Donnees_Matieres`` correspondant à une classe
    dans ``bulletin excel/``.

    Parcourt les dossiers de la division, lit la cellule B3 du premier
    xlsx pour identifier la classe, et retourne le chemin vers
    ``Donnees_Matieres/`` si trouvé.
    
    Le résultat est mis en cache par classe pour la session en cours.
    """
    global _bulletin_excel_class_dirs
    norm_cls = normalize_class_name(class_name)
    if norm_cls in _bulletin_excel_class_dirs:
        d = _bulletin_excel_class_dirs[norm_cls]
        return d if d.exists() else None

    try:
        src = Path(__file__).resolve().parent.parent / "bulletin excel"
        div = infer_division(class_name)
        div_dir = src / div
        if not div_dir.is_dir():
            return None

        for cls_folder in sorted(div_dir.iterdir()):
            if not cls_folder.is_dir():
                continue
            mat_dir = cls_folder / "Donnees_Matieres"
            if not mat_dir.is_dir():
                continue
            # Identifie la classe via B3 du premier xlsx
            cls_key: str | None = None
            for probe in sorted(mat_dir.glob("*.xlsx")):
                if probe.name.startswith("~$"):
                    continue
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(str(probe), data_only=True)
                    ws = wb.active
                    raw = ws["B3"].value
                    if raw:
                        cls_key = normalize_class_name(str(raw).strip())
                except Exception:
                    pass
                break
            if cls_key is None:
                cls_key = normalize_class_name(cls_folder.name)
            if cls_key == norm_cls:
                _bulletin_excel_class_dirs[norm_cls] = mat_dir
                return mat_dir
    except Exception:
        pass
    return None


def get_bulletin_excel_coeff(
    class_name: str, subject_name: str
) -> float | None:
    """Retourne le coefficient d'une matière pour une classe donnée,
    tel que lu dans les fichiers ``bulletin excel/``.
    
    Cherche le dossier de la classe dans ``bulletin excel/``,
    puis le fichier de la matière, et lit la cellule C4.
    Retourne ``None`` si la matière/classe est introuvable.
    """
    mat_dir = _get_bulletin_excel_matieres_dir(class_name)
    if mat_dir is None:
        return None
    norm_subj = _normalize(subject_name)
    for p in sorted(mat_dir.glob("*.xlsx")):
        if p.name.startswith("~$"):
            continue
        if _normalize(p.stem) == norm_subj:
            return read_coefficient_from_xlsx(p)
    return None


def detect_subjects_from_xlsx(class_info: ClassInfo) -> dict[str, Path]:
    """Renvoie ``{nom_de_matiere_normalisé: chemin_xlsx}``.

    Utilisé lors de la première ouverture d'une classe pour pré-remplir
    la table ``subjects`` à partir des fichiers trouvés sur le disque.
    Les coefficients et enseignants resteront à zéro / vide et seront
    renseignés dans l'onglet Configuration.
    """
    out: dict[str, Path] = {}
    for p in class_info.subject_files:
        out[_normalize(p.stem)] = p
    return out


# ---------------------------------------------------------------------------
# Bulletin premium : reset total du workspace (pattern eco_paiement)
# ---------------------------------------------------------------------------
def _list_class_dirs(root: Optional[Path] = None) -> list[Path]:
    """Retourne la liste des dossiers de classe réels
    (COLLEGE/*/ et LYCEE/*/), en excluant les dossiers techniques
    (data, bulletin, .backups, …).
    """
    bulletin_root = find_bulletin_root(root)
    out: list[Path] = []
    seen: set[Path] = set()
    accent_map = {
        "COLLEGE": "Collège",
        "LYCEE": "Lycée",
        "PRIMAIRE": "Primaire",
    }
    for division in DIVISIONS:
        for cand in (division, division.capitalize(),
                     *([accent_map[division]] if division in accent_map else [])):
            div_dir = bulletin_root / cand
            if not div_dir.is_dir():
                continue
            for class_dir in div_dir.iterdir():
                if not class_dir.is_dir():
                    continue
                if class_dir in seen:
                    continue
                seen.add(class_dir)
                # Exclure les dossiers techniques
                if class_dir.name.lower() in (
                    "data", "bulletin", ".backups", "exports"
                ):
                    continue
                out.append(class_dir)
    return sorted(out, key=lambda d: str(d).lower())


def delete_all_classes(
    root: Optional[Path] = None,
    keep_xlsx: bool = False,
    keep_bulletins: bool = False,
) -> dict:
    """Supprime TOUTES les classes du workspace.

    Par défaut (le plus destructif) : supprime ``data/`` (DB),
    ``bulletin/`` (xlsm générés) ET les ``.xlsx`` de matières. Les
    dossiers de classe vides restent en place.

    Paramètres
    ----------
    root
        Racine BULLETIN/. Auto-détectée par défaut.
    keep_xlsx
        Si ``True``, garde les fichiers ``.xlsx`` (matières) saisis
        par les enseignants. Utile pour repartir des saisies.
    keep_bulletins
        Si ``True``, garde les ``Bulletin*.xlsm`` déjà générés.

    Retourne
    --------
    dict avec les compteurs ``{"classes": N, "data": N, "bulletin": N,
    "xlsx": N, "backups": N}``.
    """
    import shutil
    counters = {"classes": 0, "data": 0, "bulletin": 0, "xlsx": 0,
               "backups": 0, "errors": []}

    for class_dir in _list_class_dirs(root):
        counters["classes"] += 1
        # 1) data/ (DB + .backups)
        data_dir = class_dir / "data"
        if data_dir.is_dir():
            for p in data_dir.rglob("*"):
                if p.is_file():
                    try:
                        p.unlink()
                        if ".backups" in p.parts:
                            counters["backups"] += 1
                        else:
                            counters["data"] += 1
                    except OSError as exc:
                        counters["errors"].append(f"{p}: {exc}")
            # Supprime le dossier vide
            try:
                shutil.rmtree(str(data_dir), ignore_errors=True)
            except OSError as exc:
                counters["errors"].append(f"{data_dir}: {exc}")
        # 2) bulletin/
        if not keep_bulletins:
            bulletin_dir = class_dir / "bulletin"
            if bulletin_dir.is_dir():
                try:
                    shutil.rmtree(str(bulletin_dir))
                    counters["bulletin"] += 1
                except OSError as exc:
                    counters["errors"].append(f"{bulletin_dir}: {exc}")
        # 3) .xlsx de matières (sauf si keep_xlsx)
        if not keep_xlsx:
            for xlsx in class_dir.glob("*.xlsx"):
                if xlsx.name.startswith("~$"):
                    continue
                try:
                    xlsx.unlink()
                    counters["xlsx"] += 1
                except OSError as exc:
                    counters["errors"].append(f"{xlsx}: {exc}")
    return counters


def delete_single_class(
    class_name: str,
    root: Optional[Path] = None,
) -> bool:
    """Supprime une classe précise (par nom de dossier).

    Utilisé pour le bouton « Supprimer cette classe » depuis l'accueil.
    Retourne ``True`` si au moins un dossier a été supprimé.
    """
    import shutil
    info = discover_class(class_name, root)
    if info is None:
        return False
    deleted = False
    folder = info.folder
    # data/ + .backups + bulletin/ + xlsx
    for sub in ("data", "bulletin"):
        d = folder / sub
        if d.is_dir():
            try:
                shutil.rmtree(str(d))
                deleted = True
            except OSError:
                pass
    for xlsx in folder.glob("*.xlsx"):
        if xlsx.name.startswith("~$"):
            continue
        try:
            xlsx.unlink()
            deleted = True
        except OSError:
            pass
    return deleted


# ---------------------------------------------------------------------------
# Configuration globale (export, sync, etc.) stockée en JSON à la racine
# ---------------------------------------------------------------------------
import json as _json

_GLOBAL_CONFIG_PATH: Path | None = None


def _get_global_config_path() -> Path:
    global _GLOBAL_CONFIG_PATH
    if _GLOBAL_CONFIG_PATH is None:
        _GLOBAL_CONFIG_PATH = find_bulletin_root() / ".bulletin_config.json"
    return _GLOBAL_CONFIG_PATH


def get_global_config(key: str, default: str = "") -> str:
    """Lit une clé dans la configuration globale (JSON à la racine)."""
    cfg_path = _get_global_config_path()
    if not cfg_path.exists():
        return default
    try:
        data = _json.loads(cfg_path.read_text(encoding="utf-8"))
        return str(data.get(key, default))
    except (OSError, _json.JSONDecodeError, ValueError):
        return default


def set_global_config(key: str, value: str) -> None:
    """Écrit une clé dans la configuration globale (JSON à la racine)."""
    cfg_path = _get_global_config_path()
    try:
        if cfg_path.exists():
            data = _json.loads(cfg_path.read_text(encoding="utf-8"))
        else:
            data = {}
        data[key] = value
        cfg_path.write_text(_json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except (OSError, _json.JSONDecodeError, ValueError):
        pass


# ---------------------------------------------------------------------------
# Bulletin premium : normalisation / inférence de classe depuis un sheet
# ---------------------------------------------------------------------------
import unicodedata as _unicodedata


def _strip_accents(s: str) -> str:
    nfkd = _unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in nfkd if not _unicodedata.combining(c))


def normalize_class_name(raw: str) -> str:
    """Normalise un nom de classe (« 6e I », « 6ème 1 », « 3 EME 2 »…)
    en nom de dossier canonique (« 6EME1 », « 3EME2 »).

    - Uppercase
    - Accents retirés
    - Ponctuation et espaces remplacés
    - « 6e I » / « 6ème 1 » / « 6EME 1 » / « 6E I » → « 6EME1 »
    - « 1ère L1 » → « 1EREL1 »
    - « 2nde II » → « 2NDEII »
    - « T.A » / « T.A D » / « TAD » → « TAD »
    - Le suffixe romain (I, II, III, IV, …) ou arabe (1, 2, 3) est
      accolé au préfixe (EME, ERE, NDE) sans espace.

    >>> normalize_class_name("6e I")
    '6EME1'
    >>> normalize_class_name("6ème 2")
    '6EME2'
    >>> normalize_class_name("3e I")
    '3EME1'
    >>> normalize_class_name("1ère L1")
    '1EREL1'
    >>> normalize_class_name("2nde II")
    '2NDEII'
    """
    s = _strip_accents(str(raw or "")).upper().strip()
    if not s:
        return ""
    # Symbole degré « ° » utilisé à Madagascar pour « ère » : « 1°L1 » → « 1L1 »
    s = s.replace("°", "")
    # Remplace les variantes d'écriture du préfixe niveau
    # (e, eme, ème, ere, ère, nde, nde)
    s = re.sub(r"^(\d+)\s*E(ME)?(?=\b|\s|[^A-Z0-9])", r"\1EME", s)
    s = re.sub(r"^(\d+)\s*ER(E)?(?=\b|\s|[^A-Z0-9])", r"\1ERE", s)
    s = re.sub(r"^(\d+)\s*ND(E)?(?=\b|\s|[^A-Z0-9])", r"\1NDE", s)
    # Variantes lycée (1ère, 2nde, T, Tle, Tale)
    s = re.sub(r"^1\s*ER(E)?(?=\b|\s|[^A-Z0-9])", "1ERE", s)
    s = re.sub(r"^2\s*ND(E)?(?=\b|\s|[^A-Z0-9])", "2NDE", s)
    s = re.sub(r"^T\s*LE\b", "TLE", s)
    s = re.sub(r"^T\s*ALE\b", "TALE", s)
    s = re.sub(r"^TLE\b", "TLE", s)
    # Variante « 1EL1 », « 1EL2 » (1ère L 1, 1ère L 2) → « 1EREL1 », « 1EREL2 »
    s = re.sub(r"^1EL(\d*)$", r"1EREL\1", s)
    # Variante « 1ES » (1ère S) → « 1ERES »
    s = re.sub(r"^1ES(\d*)$", r"1ERES\1", s)
    # Abbréviations « 1L », « 1L1 », « 1L2 », « 1S », « 1A », « 1C »,
    # « 1D » utilisées à Madagascar pour désigner « 1ère L », « 1ère S »,
    # etc. On les transforme en « 1EREL », « 1EREL1 », « 1ERES »…
    s = re.sub(r"^1([LSABCD])(\d*)$", r"1ERE\1\2", s)
    # Points, virgules, tirets → espaces
    s = re.sub(r"[\.\,;\:\-\_/\\]", " ", s)
    # Espaces multiples → 1
    s = re.sub(r"\s+", " ", s).strip()
    # Supprime tous les espaces (collage EME+chiffre/romain)
    s = s.replace(" ", "")
    # Cas spécial : "6 I", "6 II", "3 III" sans préfixe EME.
    # On les interprète comme "6EME1", "6EME2", "3EME3" si le
    # préfixe correspond à un niveau de collège (3-6).
    m = re.match(r"^([3-6])([IVX]+)$", s)
    if m and not s.startswith(("3EME", "4EME", "5EME", "6EME")):
        prefix, roman = m.groups()
        roman_map = {
            "VIII": 8, "VII": 7, "VI": 6, "IV": 4, "III": 3, "II": 2,
            "IX": 9, "V": 5, "I": 1,
        }
        if roman in roman_map:
            s = f"{prefix}EME{roman_map[roman]}"
            return s
    # Convertit les chiffres romains en fin de chaîne en chiffres
    # arabes (I→1, II→2, III→3, IV→4, V→5) pour rester cohérent
    # avec les dossiers existants (3EME1, 4EME2, …)
    roman_map = {
        "VIII": 8, "VII": 7, "VI": 6, "IV": 4, "III": 3, "II": 2,
        "IX": 9, "V": 5, "I": 1,
    }
    m = re.search(r"([IVX]+)$", s)
    if m:
        roman = m.group(1)
        if roman in roman_map:
            s = s[: -len(roman)] + str(roman_map[roman])
    return s


def infer_division(class_name: str) -> str:
    """Déduit la division (COLLEGE ou LYCEE) depuis un nom de classe
    normalisé (6EME1 → COLLEGE, 1EREL1 → LYCEE).

    Heuristique :
    - « 6EME* », « 5EME* », « 4EME* », « 3EME* » → COLLEGE
    - « 2NDE* », « 1ERE* », « TLE* », « TALE* » → LYCEE
    - Fallback : COLLEGE (le plus fréquent)
    """
    n = normalize_class_name(class_name)
    if not n:
        return "COLLEGE"
    # Primaire
    if re.match(r"^CP|CE[12]|CM[12]", n):
        return "PRIMAIRE"
    # Collège
    if re.match(r"^(6|5|4|3)EME", n):
        return "COLLEGE"
    # Lycée
    if re.match(r"^(2NDE|1ERE|TLE|TALE|TAI|T[A-Z]+)", n):
        return "LYCEE"
    # Abbréviations lycée : « 1L », « 1S », « 1EL1 » (1ère L/S/etc.)
    # même non normalisées en 1ERE*, ce sont des classes de 1ère.
    if re.match(r"^1[A-Z]{1,4}\d*$", n):
        return "LYCEE"
    # Fallback
    return "COLLEGE"


def create_class_folder(
    class_name: str,
    root: Optional[Path] = None,
    create_db: bool = True,
) -> Optional["ClassInfo"]:
    """Crée un dossier de classe complet (data/, bulletin/, etc.).

    - ``class_name`` est un nom lisible (« 6e I »). Il est normalisé
      en nom de dossier (« 6EME1 »).
    - La division (COLLEGE / LYCEE) est inférée automatiquement.
    - Le dossier racine (BULLETIN/) est auto-détecté si ``root``
      n'est pas fourni.
    - Si ``create_db=True``, crée un fichier SQLite vide dans
      ``<folder>/data/bulletin.db`` (et l'initialise avec la
      classe :class:`Database`).
    - Si la classe existe déjà, retourne son :class:`ClassInfo`
      sans rien recréer.

    Retourne le :class:`ClassInfo` correspondant, ou ``None`` si
    le nom normalisé est vide.
    """
    folder_name = normalize_class_name(class_name)
    if not folder_name:
        return None
    division = infer_division(folder_name)
    bulletin_root = find_bulletin_root(root)
    div_dir = bulletin_root / division
    div_dir.mkdir(parents=True, exist_ok=True)
    class_dir = div_dir / folder_name
    class_dir.mkdir(parents=True, exist_ok=True)
    (class_dir / "data").mkdir(exist_ok=True)
    (class_dir / "bulletin").mkdir(exist_ok=True)
    db_path = class_dir / "data" / "bulletin.db"
    if create_db and not db_path.exists():
        # Initialise la DB avec les tables par défaut
        from .db import Database
        Database(str(db_path))
    # Construit / retourne le ClassInfo
    info = discover_class(folder_name, bulletin_root)
    if info is None:
        # Re-scan pour la prendre en compte
        info = _build_class_info(class_dir, division)
    return info


def import_xlsx_sheet_to_class(
    sheet: "ParsedSheet",
    class_info: "ClassInfo",
    target_division: Optional[str] = None,
) -> dict:
    """Importe un :class:`ParsedSheet` dans la classe ``class_info``.

    Crée la DB si elle n'existe pas, ouvre la :class:`Database`
    correspondante, applique ``bulk_update_students``, et retourne
    un dict de stats (``{"added": N, "skipped": M, "total": T}``).
    """
    from .db import Database
    n_before = 0
    db = Database(str(class_info.db_path))
    try:
        existing = db.list_students()
        n_before = len(existing)
        db.bulk_update_students(sheet.rows)
        n_after = len(db.list_students())
    finally:
        db.close()
    return {
        "added": max(0, n_after - n_before),
        "total": n_after,
        "class": class_info.name,
        "division": class_info.division,
    }
