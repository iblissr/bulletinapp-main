"""Helpers de cellules de tableau (factorisation).

Ce module regroupe les petites fonctions utilitaires qui étaient
dupliquées dans ``totalisation.py``, ``moyennes.py``, ``compte_rendu.py``
et ``grades.py`` (``_hdr``, ``_val``, ``_v``, ``_fmt``, ``_item``,
``_wrap``).

Toute l'app doit utiliser les fonctions de ce module pour garantir
une présentation cohérente des cellules (couleurs de mention, gras,
centrage).
"""
from __future__ import annotations

from typing import Optional

from qtpy.QtCore import Qt
from qtpy.QtGui import QBrush, QColor, QFont
from qtpy.QtWidgets import QHeaderView, QTableWidgetItem, QWidget


# ---------------------------------------------------------------------------
# Couleurs "métier" (adaptées au thème actif via l'application palette)
# ---------------------------------------------------------------------------
from ..theme import current as _theme
from qtpy.QtGui import QColor as _QColor


def _theme_color(token: str, fallback: str) -> str:
    """Retourne une couleur depuis la palette Material 3 active,
    ou ``fallback`` si le thème n'est pas encore chargé."""
    try:
        p = _theme()
        return str(getattr(p, token, fallback))
    except Exception:  # noqa: BLE001
        return fallback


def COLOR_AVERAGE_OK() -> str:
    return _theme_color("primary", "#1F497D")


def COLOR_AVERAGE_FAIL() -> str:
    return _theme_color("danger", "#C00000")


def COLOR_AVERAGE_NA() -> str:
    return _theme_color("outline_variant", "#888888")


def COLOR_SUBJECT_MJ() -> str:
    return _theme_color("secondary", "#0D9488")


def COLOR_SUBJECT_COMPO() -> str:
    return _theme_color("tertiary", "#D97706")


def COLOR_TEXT_NA() -> str:
    return _theme_color("on_surface_variant", "#999999")


# ---------------------------------------------------------------------------
#  Étiquettes d'examens (fonction partagée)
# ---------------------------------------------------------------------------
def label_for_exam(n: int) -> tuple[str, str]:
    """Retourne ``(label_court, kind)`` pour l'examen *n* (1‑6).

    - Examens impairs → ``M.J N``, kind ``"mj"``
    - Examens pairs   → ``Compo N``, kind ``"compo"``
    """
    if n % 2 == 1:
        return f"M.J {(n + 1) // 2}", "mj"
    return f"Compo {n // 2}", "compo"


# ---------------------------------------------------------------------------
#  Helpers de formatage
# ---------------------------------------------------------------------------
def fmt_value(v, *, default: str = "NC") -> str:
    """Formate une valeur numérique pour affichage tableau.

    - ``None`` → ``default`` (par défaut ``"NC"``)
    - Nombre → ``"x.xx"`` (2 décimales)
    - Autre  → ``str(v)``
    """
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return f"{v:.2f}"
    return str(v)


def color_for_average(v: float | None) -> Optional[QColor]:
    """Renvoie la couleur sémantique d'une moyenne (``None`` → gris)."""
    if v is None:
        return QColor(COLOR_AVERAGE_NA())
    return QColor(COLOR_AVERAGE_OK() if v >= 10 else COLOR_AVERAGE_FAIL())


# ---------------------------------------------------------------------------
#  Builders d'items QTableWidgetItem
# ---------------------------------------------------------------------------
def make_item(
    text,
    *,
    bold: bool = False,
    center: bool = False,
    color: Optional[QColor | str] = None,
    underline: bool = False,
) -> QTableWidgetItem:
    """Crée un QTableWidgetItem stylé.

    Couleur peut être un :class:`QColor` ou une chaîne ``"#RRGGBB"``.
    """
    it = QTableWidgetItem("" if text is None else str(text))
    if bold or underline:
        f = it.font()
        if bold:
            f.setBold(True)
        if underline:
            f.setUnderline(True)
        it.setFont(f)
    if center:
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    if color is not None:
        if isinstance(color, str):
            color = QColor(color)
        it.setForeground(QBrush(color))
    return it


def make_header(
    text: str,
    *,
    size: int = 14,
    center: bool = True,
    bold: bool = True,
) -> QTableWidgetItem:
    """Crée une cellule d'en-tête (taille + gras)."""
    it = QTableWidgetItem(str(text) if text is not None else "")
    f = it.font()
    f.setBold(bold)
    f.setPointSize(size)
    it.setFont(f)
    if center:
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return it


def make_grade_item(
    value: float | None,
    *,
    default: str = "NC",
) -> QTableWidgetItem:
    """Item tableau spécialisé pour afficher une note/moyenne.

    - ``None`` → ``default`` en gris
    - ``< 10`` → rouge gras
    - ``>= 10`` → bleu gras
    """
    txt = fmt_value(value, default=default)
    if value is None:
        return make_item(txt, center=True, color=COLOR_TEXT_NA())
    color = color_for_average(value)
    return make_item(txt, bold=True, center=True, color=color)


# ---------------------------------------------------------------------------
#  Layout helpers
# ---------------------------------------------------------------------------
def wrap_layout(layout) -> QWidget:
    """Wrap un :class:`QLayout` dans un :class:`QWidget` transparent.

    Très utilisé par les widgets pour pouvoir insérer des layouts
    dans des Panels / TopContainers via ``addWidget``.
    """
    from qtpy.QtWidgets import QWidget as _QW
    w = _QW()
    w.setLayout(layout)
    w.setStyleSheet("background: transparent;")
    return w


def stretch_columns(table, columns: list[int], mode=QHeaderView.ResizeMode.Stretch) -> None:
    """Étire les colonnes *columns* en mode ``Stretch``, les autres en ResizeToContents."""
    header = table.horizontalHeader()
    for c in range(table.columnCount()):
        if c in columns:
            header.setSectionResizeMode(c, mode)
        else:
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
