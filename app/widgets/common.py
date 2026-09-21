"""Widgets communs réutilisables dans toute l'application.

Adaptés du projet eco_paiement pour qtpy. Tous les widgets
visent un look Material 3 : coins arrondis, surfaces plates,
typographie soignée.

Widgets fournis :
- :class:`TopContainer`  : header de page (icône + titre + actions)
- :class:`Panel`         : carte avec titre optionnel
- :class:`StatCard`      : carte statistique (titre + valeur + indice)
- :class:`MiniCard`      : petite carte avec libellé
- :class:`Toast`         : notification éphémère
- :class:`ClassChipBar`  : barre horizontale de chips pour choisir
- :class:`SectionTitle`  : titre de section discret
- :class:`SearchBar`     : champ de recherche avec icône loupe + clear
- :class:`Breadcrumb`    : fil d'Ariane cliquable
- :class:`ProgressOverlay` : overlay avec spinner pour opérations longues

Helpers :
- :func:`set_kind`         : applique la propriété ``kind`` (QSS)
- :func:`show_toast`       : affiche un toast sur la fenêtre parente
- :func:`make_debounce`    : timer de debounce pour la recherche
- :func:`unify_button_sizes` : harmonise la taille de boutons
- :func:`install_table_sort` : active le tri par clic d'en-tête de colonne
"""
from __future__ import annotations

from typing import Callable, Optional

import qtawesome as qta
from ..theme import current as theme_current
from qtpy.QtCore import (
    QPoint,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from qtpy.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from qtpy.QtWidgets import (
    QAbstractButton,
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def set_kind(widget: QPushButton, kind: str) -> None:
    """Apply a ``kind`` dynamic property to *widget* (used by QSS selectors)."""
    widget.setProperty("kind", str(kind))
    widget.style().unpolish(widget)
    widget.style().polish(widget)


# ---------------------------------------------------------------------------
# Switch (interrupteur on/off style Material 3)
# ---------------------------------------------------------------------------


class Switch(QAbstractButton):
    """Interrupteur on/off style Material 3 avec icônes sun/moon.

    Émet :pyattr:`toggled` quand l'état change. Possède aussi
    :pyattr:`isChecked` pour lire l'état courant.
    """

    toggled = Signal(bool)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        on_icon: str = "fa5s.sun",
        off_icon: str = "fa5s.moon",
        width: int = 56,
        height: int = 30,
    ) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("Switch")
        self._w = width
        self._h = height
        # Pré-rendu des pixmaps (évite bug qtawesome au paintEvent)
        ico_size = int((height - 6) * 0.6)
        self._on_pix = qta.icon(on_icon, color="#FFFFFF").pixmap(ico_size, ico_size)
        self._off_pix = qta.icon(off_icon, color="#94A3B8").pixmap(ico_size, ico_size)
        self.setFixedSize(width, height)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, _checked: bool) -> None:
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        rect = self.rect()
        # Fond (track)
        if self.isChecked():
            track_color = QColor(theme_current().primary)
        else:
            track_color = QColor(theme_current().outline)
        radius = self._h / 2
        p.setBrush(QBrush(track_color))
        p.drawRoundedRect(rect, radius, radius)
        # Handle (cercle)
        margin = 3
        diameter = self._h - 2 * margin
        if self.isChecked():
            hx = self._w - diameter - margin
        else:
            hx = margin
        handle_rect = QRect(rect.x() + hx, rect.y() + margin, diameter, diameter)
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.drawEllipse(handle_rect)
        # Icône dans le handle (pixmap pré-rendu)
        pix = self._on_pix if self.isChecked() else self._off_pix
        ico_x = handle_rect.x() + (diameter - pix.width()) // 2
        ico_y = handle_rect.y() + (diameter - pix.height()) // 2
        p.drawPixmap(ico_x, ico_y, pix)
        p.end()

    def hitButton(self, pos) -> bool:  # noqa: N802 (Qt API)
        return self.rect().contains(pos)


def unify_button_sizes(buttons: list[QPushButton], height: int = 34, min_width: int = 0) -> None:
    """Resize *buttons* to share a common width/height."""
    if not buttons:
        return
    width = max(b.sizeHint().width() for b in buttons)
    if min_width:
        width = max(width, int(min_width))
    for b in buttons:
        b.setFixedHeight(int(height))
        if width:
            b.setMinimumWidth(int(width))


# ---------------------------------------------------------------------------
# Top container (page header)
# ---------------------------------------------------------------------------


class TopContainer(QFrame):
    """Header strip with a colored icon, page title and right-aligned actions.

    Le titre est mis en gras (20px) avec un fond ``surface``
    légèrement détaché du contenu. Les actions sont alignées à
    droite via :meth:`add_action` (à appeler après construction).
    """

    def __init__(
        self,
        icon_letter: str,
        title: str,
        subtitle: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TopContainer")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 12)
        self._layout.setSpacing(14)

        # Icône gradient (lettre ou emoji court)
        self._icon = QLabel(icon_letter[:2] if icon_letter else "•")
        self._icon.setObjectName("PageIcon")
        self._icon.setFixedSize(44, 44)
        self._icon.setAlignment(Qt.AlignCenter)
        f = QFont()
        f.setBold(True)
        f.setPointSize(16)
        self._icon.setFont(f)
        self._layout.addWidget(self._icon)

        # Bloc titre + sous-titre (prend toute la place dispo)
        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(0)
        self._title = QLabel(title)
        self._title.setObjectName("PageTitle")
        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("PageSubtitle")
        self._subtitle.setVisible(bool(subtitle))
        text_box.addWidget(self._title)
        text_box.addWidget(self._subtitle)
        self._layout.addLayout(text_box, 1)

        # Ajoute les actions directement au layout principal
        # (pas de stretch interne : le text_box stretch=1 les pousse à droite)

    def add_action(self, widget: QWidget) -> None:
        """Ajoute un widget d'action à droite du TopContainer."""
        self._layout.addWidget(widget)

    def set_title(self, title: str, subtitle: str = "") -> None:
        self._title.setText(title)
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))

    def set_icon(self, letter: str) -> None:
        self._icon.setText(letter[:2] if letter else "•")


# ---------------------------------------------------------------------------
# Panel (card-style container)
# ---------------------------------------------------------------------------


class Panel(QFrame):
    """Carte avec un titre optionnel (icône + texte) et un body auto-layout.

    Le body est accessible via :meth:`body_layout`. Le titre est
    positionné en haut, le contenu remplit le reste.
    """

    def __init__(
        self,
        title: str = "",
        icon: Optional[QIcon] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 12, 14, 12)
        self._layout.setSpacing(10)

        self._title_label: Optional[QLabel] = None
        self._header_row: Optional[QHBoxLayout] = None
        if title or icon:
            row = QHBoxLayout()
            row.setSpacing(6)
            row.setContentsMargins(0, 0, 0, 0)
            if icon is not None and not icon.isNull():
                ico_lbl = QLabel()
                from qtpy.QtCore import QSize
                ico_lbl.setPixmap(icon.pixmap(QSize(18, 18)))
                ico_lbl.setStyleSheet("background: transparent;")
                row.addWidget(ico_lbl, 0, Qt.AlignVCenter)
            self._title_label = QLabel(title)
            self._title_label.setObjectName("PanelTitle")
            row.addWidget(self._title_label, 1, Qt.AlignVCenter)
            self._header_row = row
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            container.setLayout(row)
            self._layout.addWidget(container)

    def body_layout(self) -> QVBoxLayout:
        return self._layout

    def add_header_action(self, widget: QWidget) -> None:
        """Ajoute un widget (ex : bouton) à droite du titre du panel."""
        if self._header_row is None:
            # Crée une ligne d'en-tête minimale
            self._title_label = QLabel("")
            self._title_label.setObjectName("PanelTitle")
            row = QHBoxLayout()
            row.setSpacing(6)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(self._title_label, 1, Qt.AlignVCenter)
            self._header_row = row
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            container.setLayout(row)
            self._layout.insertWidget(0, container)
        self._header_row.addWidget(widget, 0, Qt.AlignVCenter)

    def set_title(self, title: str) -> None:
        if self._title_label is None:
            self._title_label = QLabel(title)
            self._title_label.setObjectName("PanelTitle")
            self._layout.insertWidget(0, self._title_label)
        else:
            self._title_label.setText(title)


# ---------------------------------------------------------------------------
# Stat card
# ---------------------------------------------------------------------------


class StatCard(QFrame):
    """Carte statistique : titre en majuscules, grande valeur, indice optionnel.

    La valeur peut être colorée via l'argument ``accent`` (sinon
    couleur par défaut ``on_surface``).
    """

    def __init__(
        self,
        title: str,
        value: str,
        hint: str = "",
        accent: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        # Map accent hex to statKind property for QSS-based coloring
        ACCENT_MAP = {
            "#4F46E5": "primary",
            "#0D9488": "secondary",
            "#D97706": "tertiary",
            "#059669": "success",
        }
        if accent:
            self.setProperty("statKind", ACCENT_MAP.get(accent, "primary"))
        self.setMinimumHeight(64)
        self.setMaximumHeight(80)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(3)

        self._title = QLabel(title)
        self._title.setObjectName("CardTitle")
        self._value = QLabel(value)
        self._value.setObjectName("CardValue")
        self._value.setWordWrap(False)
        self._value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._hint = QLabel(hint)
        self._hint.setObjectName("CardHint")
        self._hint.setVisible(bool(hint))
        lay.addWidget(self._title)
        lay.addWidget(self._value)
        lay.addWidget(self._hint)

    def set_value(self, value: str, hint: str = "") -> None:
        self._value.setText(value)
        if hint:
            self._hint.setText(hint)
            self._hint.setVisible(True)
        else:
            self._hint.setVisible(False)


# ---------------------------------------------------------------------------
# Section title (sous-titre discret)
# ---------------------------------------------------------------------------


class SectionTitle(QLabel):
    """Titre de section discret (UPPERCASE + espacement)."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("SectionTitle")


# ---------------------------------------------------------------------------
# Class chip bar (filter pills)
# ---------------------------------------------------------------------------


class ClassChipBar(QWidget):
    """Barre horizontale de chips pour sélectionner un identifiant.

    Émet le signal :pyattr:`changed` avec l'identifiant du chip
    cliqué. Le chip actif est mis en évidence via la propriété
    QSS ``active="1"``.
    """

    changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._inner = QWidget()
        self._lay = QHBoxLayout(self._inner)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(6)
        self._lay.addStretch(1)

        self._scroll.setWidget(self._inner)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._active_id: str = "ALL"

    def set_items(self, items: list[tuple[str, str]]) -> None:
        """``items`` is a list of ``(id, label)`` pairs (id='ALL' supported)."""
        for btn in self._group.buttons():
            self._group.removeButton(btn)
            btn.setParent(None)
            btn.deleteLater()
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for cid, label in items:
            btn = QPushButton(label)
            btn.setCheckable(True)
            set_kind(btn, "chip")
            btn.setProperty("id_str", cid)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(btn)
            self._lay.insertWidget(self._lay.count() - 1, btn)
        self._group.buttonClicked.connect(self._on_click)
        self.set_active(self._active_id)

    def _on_click(self, btn: QPushButton) -> None:
        cid = btn.property("id_str") or "ALL"
        if cid != self._active_id:
            self._active_id = cid
            self.changed.emit(cid)

    def active(self) -> str:
        return self._active_id

    def set_active(self, id_str: str) -> None:
        self._active_id = id_str or "ALL"
        for btn in self._group.buttons():
            is_active = btn.property("id_str") == self._active_id
            btn.setChecked(is_active)
            btn.setProperty("active", "1" if is_active else "0")
            btn.style().unpolish(btn)
            btn.style().polish(btn)


# ---------------------------------------------------------------------------
# Toast notification
# ---------------------------------------------------------------------------


class Toast(QLabel):
    """Notification éphémère en bas à droite de la fenêtre parente."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignCenter)
        self.setProperty("kind", "info")
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, kind: str = "info", duration_ms: int = 2400) -> None:
        self.setText(text)
        self.setProperty("kind", kind)
        self.style().unpolish(self)
        self.style().polish(self)
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def _place(self) -> None:
        if self.parent() is None:
            return
        margin = 18
        x = self.parent().width() - self.width() - margin
        y = self.parent().height() - self.height() - margin
        self.move(max(margin, x), max(margin, y))


def show_toast(parent: QWidget, text: str, kind: str = "info") -> None:
    """Show a toast in the top-level window containing *parent*."""
    top = parent.window()
    if top is None:
        return
    if not hasattr(top, "_toast"):
        top._toast = Toast(top)  # type: ignore[attr-defined]
    top._toast.show_message(text, kind=kind)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Debounce helper
# ---------------------------------------------------------------------------

def make_debounce(widget: QWidget, callback, delay_ms: int = 180) -> QTimer:
    """Create and parent a debounce QTimer wired to *callback*."""
    t = QTimer(widget)
    t.setSingleShot(True)
    t.setInterval(delay_ms)
    t.timeout.connect(callback)
    return t


# ---------------------------------------------------------------------------
#  Search bar
# ---------------------------------------------------------------------------

class SearchBar(QLineEdit):
    """Champ de recherche avec icône loupe et bouton clear.

    Émet :pyattr:`textChanged` (hérité) et :pyattr:`cleared` quand
    l'utilisateur vide le champ. La classe parente ``QLineEdit``
    propose déjà un placeholder et un texte — on ajoute juste
    l'icône à gauche et le bouton clear à droite.
    """

    cleared = Signal()

    def __init__(
        self,
        placeholder: str = "Rechercher…",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        # Hauteur confortable
        self.setMinimumHeight(34)
        # Icône loupe (padding-left)
        search_icon = qta.icon("fa5s.search", color=theme_current().on_surface_variant)
        self.addAction(search_icon, QLineEdit.ActionPosition.LeadingPosition)
        # Le clearButtonEnabled met automatiquement une croix
        # à droite quand il y a du texte.
        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str) -> None:
        if not text:
            self.cleared.emit()


# ---------------------------------------------------------------------------
#  Breadcrumb (fil d'Ariane)
# ---------------------------------------------------------------------------

class Breadcrumb(QFrame):
    """Fil d'Ariane cliquable de type « Accueil › Collège › 3EME1 ».

    Chaque segment est un :class:`QPushButton` plat. Le dernier
    segment est non-cliquable (page courante).

    Émet :pyattr:`segmentClicked` avec l'index du segment cliqué
    (0 = racine).
    """

    segmentClicked = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Breadcrumb")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(4)
        self._segments: list[str] = []
        self._current: int = -1  # index du segment « courant » (non cliquable)

    def set_segments(self, segments: list[str], current: int = -1) -> None:
        """Remplace le fil d'Ariane.

        ``segments`` = liste de libellés.
        ``current`` = index du segment actif (-1 = dernier).
        """
        # Nettoie les widgets existants
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._segments = list(segments)
        if current < 0:
            current = len(segments) - 1
        self._current = current

        p = theme_current()
        # Icône pour chaque segment : 0=home, 1=classe, 2+=onglet
        SEG_ICONS = ["fa5s.home", "fa5s.school", "fa5s.folder"]
        for i, label in enumerate(segments):
            if i > 0:
                sep = QLabel("›")
                sep.setObjectName("BreadcrumbSep")
                self._layout.addWidget(sep)
            idx_ico = min(i, len(SEG_ICONS) - 1)
            if i == current:
                # Page courante : pill non-cliquable
                btn = QPushButton(
                    qta.icon(SEG_ICONS[idx_ico], color=p.on_surface_variant),
                    f"  {label}")
                btn.setEnabled(False)
                btn.setCursor(Qt.CursorShape.ArrowCursor)
                btn.setMinimumHeight(28)
                set_kind(btn, "flat")
                self._layout.addWidget(btn)
            else:
                # Segment cliquable
                btn = QPushButton(
                    qta.icon(SEG_ICONS[idx_ico], color=p.primary),
                    f"  {label}")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setMinimumHeight(28)
                set_kind(btn, "outlined")
                btn.clicked.connect(
                    lambda _checked=False, idx=i: self.segmentClicked.emit(idx)
                )
                self._layout.addWidget(btn)
        self._layout.addStretch(1)


# ---------------------------------------------------------------------------
#  Progress overlay (overlay transparent avec spinner)
# ---------------------------------------------------------------------------

class ProgressOverlay(QFrame):
    """Overlay semi-transparent avec spinner centré.

    À placer au-dessus d'un widget parent (par exemple via
    ``QStackedWidget``). L'overlay capture les clics et affiche
    un message + un :class:`QProgressBar` indéterminé.

    Usage::

        overlay = ProgressOverlay(self, "Synchronisation…")
        overlay.start()
        # ... do work ...
        overlay.stop()
    """

    def __init__(
        self,
        parent: QWidget,
        message: str = "Chargement…",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ProgressOverlay")
        # Le style (fond semi-transparent) est dans le QSS global
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Spinner
        self.spinner = QLabel()
        self.spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sp = qta.icon("fa5s.spinner", color="white")
        self.spinner.setPixmap(sp.pixmap(36, 36))
        lay.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        # Message
        self.label = QLabel(message)
        self.label.setObjectName("ProgressOverlayMsg")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.label, 0, Qt.AlignmentFlag.AlignHCenter)
        # Animation du spinner
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._rotate)
        self._angle = 0
        self.hide()

    def start(self, message: str | None = None) -> None:
        if message:
            self.label.setText(message)
        if self.parent() is not None:
            self.setGeometry(self.parent().rect())
        self.raise_()
        self.show()
        self._timer.start()
        QApplication.processEvents()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def set_message(self, message: str) -> None:
        self.label.setText(message)

    def resizeEvent(self, event):  # noqa: N802 (Qt API)
        # Suit la taille du parent à chaque resize de la fenêtre
        if self.parent() is not None:
            self.setGeometry(self.parent().rect())
        super().resizeEvent(event)

    def _rotate(self) -> None:
        self._angle = (self._angle + 30) % 360
        from qtpy.QtGui import QTransform
        base = qta.icon("fa5s.spinner", color="white").pixmap(36, 36)
        rotated = base.transformed(QTransform().rotate(self._angle), Qt.SmoothTransformation)
        self.spinner.setPixmap(rotated)


# ---------------------------------------------------------------------------
#  Sortable table helper
# ---------------------------------------------------------------------------

def install_table_sort(
    table: QTableWidget,
    *,
    numeric_columns: Optional[set[int]] = None,
    callback: Optional[Callable[[int, bool], None]] = None,
) -> None:
    """Active le tri par clic d'en-tête sur une QTableWidget.

    - ``numeric_columns`` : set d'indices de colonnes dont les valeurs
      sont numériques (tri numérique au lieu d'alphabétique).
    - ``callback`` : fonction appelée après chaque tri avec
      ``(column_index, descending)``.

    Le tri fonctionne en cachant/montrant les lignes (rapide pour
    des tables de taille modérée comme celle d'un onglet Notes).
    """
    numeric_columns = numeric_columns or set()
    header = table.horizontalHeader()
    header.setSectionsClickable(True)
    header.setSortIndicatorShown(True)
    header.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
    # L'astuce : on stocke les positions d'origine pour pouvoir
    # dé-trier en remettant dans l'ordre initial. Sinon Qt réordonne
    # les items en place ce qui casse les références dans nos widgets
    # custom (GradeSpinBox, etc.).
    _state = {"col": -1, "order": Qt.SortOrder.AscendingOrder}

    def _do_sort(col: int, order: Qt.SortOrder) -> None:
        # Construit une liste (row_idx, sort_key) puis trie
        items = []
        for row in range(table.rowCount()):
            it = table.item(row, col) if table.columnCount() else None
            if it is not None and col in numeric_columns:
                try:
                    key = (0, float(it.text().replace(",", ".")))
                except (TypeError, ValueError):
                    key = (1, it.text() or "")
            else:
                key = (1, (it.text() if it is not None else "").lower())
            items.append((row, key))
        items.sort(key=lambda x: x[1],
                   reverse=(order == Qt.SortOrder.DescendingOrder))
        # Sauvegarde toutes les données de lignes, puis réécrit dans
        # l'ordre trié (plus fiable que le décalage ligne par ligne).
        saved_rows = []
        for row in range(table.rowCount()):
            cells = []
            for c in range(table.columnCount()):
                cells.append((
                    table.takeItem(row, c),
                    table.cellWidget(row, c),
                ))
                if table.cellWidget(row, c) is not None:
                    table.removeCellWidget(row, c)
            saved_rows.append(cells)
        # Réécrit dans l'ordre trié
        sorted_indices = [r for r, _ in items]
        for new_row, old_row in enumerate(sorted_indices):
            for c, (it, w) in enumerate(saved_rows[old_row]):
                if it is not None:
                    table.setItem(new_row, c, it)
                if w is not None:
                    table.setCellWidget(new_row, c, w)
        _state["col"] = col
        _state["order"] = order
        if callback is not None:
            callback(col, order == Qt.SortOrder.DescendingOrder)

    def _on_sort_clicked(col: int) -> None:
        if col == _state["col"]:
            order = (
                Qt.SortOrder.DescendingOrder
                if _state["order"] == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            order = Qt.SortOrder.AscendingOrder
        _do_sort(col, order)

    header.sectionClicked.connect(_on_sort_clicked)
