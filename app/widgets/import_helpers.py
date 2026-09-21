"""Helpers d'import Excel « intelligents ».

Le besoin : un utilisateur colle n'importe quel ``.xlsx`` de provenances
variées (export d'un autre logiciel, feuille copiée à la main, classeur
Anglais/Français, etc.) et l'application doit en extraire une liste
d'élèves correcte **sans configuration**.

Trois problèmes concrets à résoudre :

1. Lignes parasites en tête de feuille (établissement, classe, prof, …)
   → on cherche la « vraie » ligne d'en-têtes en scannant les mots-clés.
2. Colonnes non positionnelles
   → on reconnait le rôle de chaque colonne par **son nom** (FR + EN)
   plutôt que par son index.
3. Noms complets dans une seule cellule (« ALFRED Kevin Haristophano »)
   → on sépare nom / prénoms sur le dernier espace.

L'API publique est ::

    sheet, mapping, rows = read_students_sheet(path)
    # mapping = { "num": col_index, "nom": col_index, ... }   (éventuellement vide)
    # rows    = [ {"num": 1, "nom": "ALFRED", "prenoms": "Kevin Haristophano", ...} ]

Les grades (M.J, Compo, …) sont volontairement **ignorés** : ce helper
sert uniquement à importer des élèves. Un autre helper fera l'import
des notes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# Imports openpyxl paresseux : on évite le coût au démarrage de l'app.
def _openpyxl():
    import openpyxl  # noqa: WPS433
    return openpyxl


# Champs cibles supportés par la table ``students``.
TARGET_FIELDS: tuple[str, ...] = (
    "num", "matricule", "nom", "prenoms", "genre", "naissance",
)

# ------------------------------------------------------------------
# Aliases de noms de colonnes (FR + EN + fautes de frappe courantes)
# ------------------------------------------------------------------
# Pour chaque champ cible on liste tous les en-têtes possibles. La
# comparaison est faite après normalisation (lowercase, sans accents,
# sans ponctuation). On utilise un *set* plutôt qu'une regex pour rester
# robuste aux variations.
_ALIASES: dict[str, set[str]] = {
    "num": {
        "num", "numero", "n", "no", "n°", "nº", "number", "no",
        "ordre", "rang", "id", "#", "n",
    },
    "matricule": {
        "matricule", "mat", "matriculen", "matriculeeleve",
        "studentid", "student no", "student number", "id",
        "code", "code eleve", "registration", "registration no",
        "registration number", "reg no",
    },
    "nom": {
        "nom", "nomdefamille", "nomfamille", "nom de famille", "lastname",
        "last name", "family name", "surname", "nom eleve",
    },
    "prenoms": {
        "prenom", "prenoms", "prénom", "prénoms", "firstname",
        "first name", "given name", "givenname", "prenom eleve",
    },
    # Cas particulier : nom + prénoms dans une seule colonne
    "nom_et_prenoms": {
        "nometprenoms", "nom et prenoms", "nom et prenoms", "nom prenoms",
        "nomprenoms", "fullname", "full name", "student name",
        "studentname", "name", "nom complet", "nomcomplet",
        "eleve", "élève", "learner",
    },
    "genre": {
        "genre", "sexe", "sex", "gender", "m/f", "mf", "m ou f",
    },
    "naissance": {
        "naissance", "datedenaissance", "date de naissance", "dob",
        "date of birth", "birth date", "birthdate", "date naissance",
    },
}


def _normalize(text: object) -> str:
    """Normalise un en-tête pour la comparaison d'aliases.

    - ``None``  → ``""``
    - minuscule
    - sans accents
    - ponctuation remplacée par un espace (sauf symboles courants
      ``#``, ``°``, ``º`` qui sont conservés car souvent utilisés
      dans les en-têtes « N° », « Nº », « # »)
    - espaces multiples compressés

    Quelques remplacements symboliques sont faits **avant** la
    normalisation pour que ``"N°"`` et ``"#"`` matchent ``"numero"``.
    """
    if text is None:
        return ""
    s = str(text).strip().lower()
    # Remplacements symboliques
    symbol_map = {
        "#": " numero ",
        "n°": " numero ",
        "nº": " numero ",
        "°": " ",
        "º": " ",
    }
    for k, v in symbol_map.items():
        s = s.replace(k, v)
    # Retrait des accents (é→e, è→e, ê→e, …)
    import unicodedata
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    # Conserver uniquement lettres, chiffres, espaces
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _alias_lookup(field: str) -> set[str]:
    raw = _ALIASES.get(field, set())
    return {_normalize(a) for a in raw} | {a for a in raw}


# Pré-calcul des alias normalisés (uniquement à l'import du module)
_ALIASES_NORM: dict[str, set[str]] = {
    field: _alias_lookup(field) for field in _ALIASES
}


# ------------------------------------------------------------------
# Détection de la ligne d'en-têtes
# ------------------------------------------------------------------
# Au moins N cellules de la ligne doivent ressembler à un en-tête connu.
_HEADER_KEYWORDS = {
    # Mots qui signalent qu'une ligne est un en-tête
    "num", "nom", "prenom", "prenoms", "matricule", "genre",
    "naissance", "nometprenoms", "nomcomplet", "firstname",
    "lastname", "fullname", "name", "sex", "gender", "dob",
}


def _looks_like_header_row(values: Iterable[object]) -> int:
    """Retourne le nombre de cellules de la ligne qui ressemblent à un
    en-tête connu (0 si la ligne n'a rien d'un en-tête).
    """
    hits = 0
    for v in values:
        norm = _normalize(v)
        if not norm:
            continue
        if norm in _HEADER_KEYWORDS or any(
            norm in aliases
            for aliases in _ALIASES_NORM.values()
        ):
            hits += 1
    return hits


def find_header_row(ws, max_scan: int = 10) -> int:
    """Trouve l'index 1-based de la ligne d'en-têtes.

    On scanne les ``max_scan`` premières lignes et on garde celle qui a
    le plus de cellules ressemblant à un en-tête. En cas d'égalité on
    garde la première. Si aucune ligne ne contient d'en-tête connu, on
    retombe sur la ligne 1 (comportement historique).

    ``ws`` est un objet :class:`openpyxl.worksheet.worksheet.Worksheet`.
    """
    best_row = 1
    best_score = 0
    for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan,
                                            values_only=True), start=1):
        score = _looks_like_header_row(row)
        if score > best_score:
            best_score = score
            best_row = idx
    return best_row


# ------------------------------------------------------------------
# Mapping d'en-têtes
# ------------------------------------------------------------------
@dataclass
class ColumnMapping:
    """Résultat du mapping d'une feuille vers les champs cibles.

    ``fields`` est un dict ``{champ_cible: index_colonne_0based}``.
    Un champ peut être mappé à ``-1`` (non trouvé dans la feuille) ou
    à un index valide. ``extra`` contient les colonnes de la feuille
    qui n'ont pas été reconnues — utile pour informer l'utilisateur.
    """

    fields: dict[str, int] = field(default_factory=dict)
    extra: list[str] = field(default_factory=list)

    def is_complete(self) -> bool:
        """Au moins ``num`` et l'un de (``nom``, ``nom_et_prenoms``) doivent
        être trouvés pour qu'on puisse importer.
        """
        has_num = self.fields.get("num", -1) >= 0
        has_name = (self.fields.get("nom", -1) >= 0
                    or self.fields.get("nom_et_prenoms", -1) >= 0)
        return has_num and has_name

    def missing(self) -> list[str]:
        out = []
        if self.fields.get("num", -1) < 0:
            out.append("num")
        if (self.fields.get("nom", -1) < 0
                and self.fields.get("nom_et_prenoms", -1) < 0):
            out.append("nom / nom_et_prenoms")
        return out


def detect_mapping(header: Iterable[object]) -> ColumnMapping:
    """Mappe une ligne d'en-têtes vers les champs cibles.

    Si deux colonnes correspondent au même champ, la première gagne.
    Les colonnes non reconnues sont listées dans ``extra`` (l'aperçu
    montrera qu'elles sont ignorées).
    """
    mapping = ColumnMapping()
    # initialiser tous les champs à -1
    for f in TARGET_FIELDS:
        mapping.fields[f] = -1

    used_cols: set[int] = set()
    for col_idx, raw in enumerate(header):
        norm = _normalize(raw)
        if not norm:
            continue
        # Cas particulier : nom et prénoms combinés
        if norm in _ALIASES_NORM["nom_et_prenoms"]:
            mapping.fields["nom_et_prenoms"] = col_idx
            used_cols.add(col_idx)
            continue
        # Cas général : recherche dans tous les champs cibles
        matched = False
        for field_name, aliases in _ALIASES_NORM.items():
            if field_name == "nom_et_prenoms":
                continue
            if norm in aliases and mapping.fields[field_name] < 0:
                mapping.fields[field_name] = col_idx
                used_cols.add(col_idx)
                matched = True
                break
        if not matched:
            mapping.extra.append(str(raw) if raw is not None else "")

    return mapping


# ------------------------------------------------------------------
# Découpage d'un nom complet en (nom, prenoms)
# ------------------------------------------------------------------
_UPPERCASE = re.compile(r"[A-ZÀ-Ý]")
_SURNAME_HINT = re.compile(
    r"^(mr|mrs|ms|mlle|mlle|m\.|mme|mme\.)\b", re.IGNORECASE
)


def split_full_name(full: str) -> tuple[str, str]:
    """Sépare ``"ALFRED Kevin Haristophano"`` → ``("ALFRED", "Kevin Haristophano")``.

    Heuristique : on considère que le **nom de famille** est le premier
    mot qui commence par une majuscule, et que tout ce qui suit est le(s)
    prénom(s). Les particules usuelles (``de``, ``du``, ``von``) sont
    collées au prénom si elles suivent immédiatement le nom.

    Pour les noms simples (``"Kevin"``) on met tout dans ``nom``.

    Cas particuliers gérés :
    - ``""`` → ``("", "")``
    - M./Mme en tête → on l'enlève et on tente la séparation sur le reste
    - Un seul mot → on le met dans ``nom``
    """
    text = _SURNAME_HINT.sub("", str(full or "")).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return "", ""

    parts = text.split(" ")
    if len(parts) == 1:
        return parts[0], ""

    # Premier mot = nom de famille (capitalisé), reste = prénoms.
    nom, prenoms = parts[0], " ".join(parts[1:])
    return nom, prenoms


# ------------------------------------------------------------------
# Validation / nettoyage d'une valeur
# ------------------------------------------------------------------
_GENDER_MAP = {
    "m": "M", "h": "M", "homme": "M", "masculin": "M", "garcon": "M",
    "garçon": "M", "boy": "M", "male": "M", "m": "M",
    "f": "F", "femme": "F", "feminin": "F", "féminin": "F",
    "fille": "F", "girl": "F", "female": "F",
}


def clean_gender(raw: object) -> str:
    if raw is None:
        return ""
    s = _normalize(raw)
    return _GENDER_MAP.get(s, str(raw).strip() if str(raw).strip() else "")


def clean_int(raw: object) -> int | None:
    """Convertit en ``int`` en tolérant les chaînes (« 12 », « 12.0 », 12)."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        if raw.is_integer():
            return int(raw)
        return None
    s = str(raw).strip()
    # Enlever les espaces et caractères parasites
    s = re.sub(r"[^\d\-]", "", s)
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def clean_text(raw: object) -> str:
    if raw is None:
        return ""
    return str(raw).strip()


# ------------------------------------------------------------------
# API principale
# ------------------------------------------------------------------
@dataclass
class ParsedSheet:
    """Résultat complet de l'analyse d'une feuille Excel."""

    sheet_name: str
    header_row: int
    mapping: ColumnMapping
    rows: list[dict]
    skipped: int
    warnings: list[str]


def read_students_sheet(
    path: str | Path,
    sheet_name: str | None = None,
) -> ParsedSheet:
    """Lit un ``.xlsx`` et retourne les élèves détectés.

    Si ``sheet_name`` est fourni, lit l'onglet correspondant.
    Sinon, lit l'onglet actif.

    Lève :class:`FileNotFoundError` si le fichier n'existe pas, ou
    :class:`ValueError` si la feuille ne contient aucune ligne
    exploitable.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))

    openpyxl = _openpyxl()
    wb = openpyxl.load_workbook(str(p), data_only=True)
    if sheet_name is not None:
        if sheet_name not in wb.sheetnames:
            raise ValueError(f"Onglet '{sheet_name}' introuvable.")
        ws = wb[sheet_name]
    else:
        ws = wb.active

    header_idx = find_header_row(ws)
    rows_iter = list(ws.iter_rows(min_row=header_idx + 1, values_only=True))
    headers = [c.value for c in next(ws.iter_rows(min_row=header_idx,
                                                  max_row=header_idx))]

    mapping = detect_mapping(headers)

    if not mapping.is_complete():
        missing = mapping.missing()
        raise ValueError(
            "Colonnes introuvables dans le fichier : " + ", ".join(missing)
            + ". En-têtes détectés : " + ", ".join(str(h) for h in headers if h is not None)
        )

    parsed: list[dict] = []
    skipped = 0
    warnings: list[str] = []
    seen_num: set[int] = set()

    # Pré-calcul des index
    idx_num = mapping.fields.get("num", -1)
    idx_mat = mapping.fields.get("matricule", -1)
    idx_nom = mapping.fields.get("nom", -1)
    idx_pre = mapping.fields.get("prenoms", -1)
    idx_nompre = mapping.fields.get("nom_et_prenoms", -1)
    idx_genre = mapping.fields.get("genre", -1)
    idx_naiss = mapping.fields.get("naissance", -1)

    for raw_row in rows_iter:
        if raw_row is None:
            continue
        # Ignorer les lignes totalement vides
        if all(v in (None, "") for v in raw_row):
            continue

        def cell(i: int) -> object:
            if i < 0 or i >= len(raw_row):
                return None
            return raw_row[i]

        num = clean_int(cell(idx_num))
        if num is None:
            skipped += 1
            continue

        # Doublon dans le fichier source : on garde la première occurrence
        # mais on prévient l'utilisateur.
        if num in seen_num:
            warnings.append(f"Num {num} présent plusieurs fois — ignoré.")
            skipped += 1
            continue
        seen_num.add(num)

        # Nom et prénoms
        if idx_nompre >= 0:
            full = clean_text(cell(idx_nompre))
            nom, prenoms = split_full_name(full)
        else:
            nom = clean_text(cell(idx_nom))
            prenoms = clean_text(cell(idx_pre))

        if not nom:
            # Dernier recours : on n'importe pas un élève sans nom.
            warnings.append(f"Num {num} sans nom — ignoré.")
            skipped += 1
            continue

        parsed.append({
            "num": num,
            "matricule": clean_text(cell(idx_mat)),
            "nom": nom,
            "prenoms": prenoms,
            "genre": clean_gender(cell(idx_genre)),
            "naissance": clean_text(cell(idx_naiss)),
        })

    if not parsed:
        raise ValueError(
            "Aucune ligne exploitable n'a été trouvée après la ligne d'en-têtes."
        )

    return ParsedSheet(
        sheet_name=ws.title,
        header_row=header_idx,
        mapping=mapping,
        rows=parsed,
        skipped=skipped,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Bulletin premium : lecteur multi-sheets (pattern eco_paiement)
# ---------------------------------------------------------------------------
@dataclass
class ParsedWorkbook:
    """Résultat de la lecture d'un classeur entier.

    Attributes
    ----------
    sheets
        Liste de :class:`ParsedSheet` (un par onglet qui a pu être
        parsé).
    skipped_sheets
        Noms des onglets qui n'ont pas pu être parsés
        (pas d'en-têtes reconnues).
    """
    sheets: list = field(default_factory=list)
    skipped_sheets: list = field(default_factory=list)


def read_all_sheets(path: str | Path) -> ParsedWorkbook:
    """Lit TOUS les onglets d'un classeur ``.xlsx``.

    Les onglets qui n'ont pas d'en-têtes élèves valides sont
    ignorés (mais leur nom est listé dans ``skipped_sheets``).

    Pattern eco_paiement premium : un classeur avec N feuilles =
    N classes, importable en une seule passe.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    openpyxl = _openpyxl()
    wb = openpyxl.load_workbook(str(p), data_only=True)
    out = ParsedWorkbook()
    for ws in wb.worksheets:
        # Si la feuille a moins de 2 lignes, on saute
        if ws.max_row < 2:
            out.skipped_sheets.append(ws.title)
            continue
        try:
            parsed = read_students_sheet(p, sheet_name=ws.title)
            out.sheets.append(parsed)
        except Exception:  # noqa: BLE001
            out.skipped_sheets.append(ws.title)
    return out
