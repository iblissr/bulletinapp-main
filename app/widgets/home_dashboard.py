"""Grand tableau de bord d'accueil (liste des classes) — refonte premium.

Affiche toutes les classes détectées dans ``BULLETIN/`` sous forme
de cards cliquables. Style eco_paiement / Material 3 avec :

- **Hero header** avec logo, titre, stats en gros chiffres
- **Barre de recherche + filter chips** (Collège / Lycée / Tous)
- **Toggle Grille ↔ Liste** (mode compact)
- **Cards redessinées** avec barre latérale d'accent, header en
  gradient, footer avec dernière sync
- **Animations** : hover sur cards (élévation + couleur)
- **Empty state** redesigné avec illustration + 2 CTA

Chaque card permet d'ouvrir la classe correspondante. Un double-clic
ou le bouton « Ouvrir » déclenche la navigation vers la
:class:`ClassView` (les onglets de la classe active).
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import qtawesome as qta
from qtpy.QtCore import (
    QEvent,
    QPropertyAnimation,
    QEasingCurve,
    QSize,
    Qt,
    Signal,
)
from qtpy.QtGui import QColor, QFont, QPainter, QPixmap
from qtpy.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .common import Panel, SectionTitle, TopContainer, set_kind
from ..theme import current as theme_current
from .table_helpers import (
    COLOR_SUBJECT_MJ,
    COLOR_SUBJECT_COMPO,
    COLOR_AVERAGE_OK,
)
from ..db import Database
from ..screen_utils import get_scale
from ..workspace import ClassInfo, discover_classes

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Card widget (1 par classe) — version refondue
# ---------------------------------------------------------------------------


class ClassCard(QFrame):
    """Card cliquable représentant une classe (refonte premium).

    - Header en gradient (couleur de division)
    - Barre latérale d'accent (4px)
    - Icône de division, nom gros, badge division
    - Stats inline (élèves, matières, fichiers)
    - Footer avec dernière sync
    - Boutons : sync (icône), ouvrir (CTA)
    - Hover : élévation + accent plus prononcé
    """

    openRequested = Signal(str)
    syncRequested = Signal(str)

    def __init__(
        self,
        info: ClassInfo,
        *,
        db: Optional[Database] = None,
        view_mode: str = "grid",  # "grid" | "list"
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.info = info
        self.db = db
        self.view_mode = view_mode
        self.setObjectName("ClassCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("view", view_mode)
        if view_mode == "grid":
            self.setMinimumWidth(240)
            self.setMaximumWidth(360)
        else:
            self.setMinimumHeight(78)
            self.setMaximumHeight(82)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Couleur d'accent par division (utilisé via QSS cardAccent property)
        if info.division == "LYCEE":
            self._accent = COLOR_SUBJECT_COMPO()
            self._card_accent = "lycee"
        else:
            self._accent = COLOR_SUBJECT_MJ()
            self._card_accent = "college"
        self.setProperty("cardAccent", self._card_accent)

        # Install event filter for hover animations
        self.setMouseTracking(True)
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        if self.view_mode == "grid":
            self._build_grid()
        else:
            self._build_list()

    def _build_grid(self) -> None:
        """Construction en mode grille (card verticale)."""
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        accent_bar = QFrame()
        accent_bar.setObjectName("ClassCardAccent")
        accent_bar.setFixedWidth(4)
        outer.addWidget(accent_bar, 0, Qt.AlignTop)

        content = QFrame()
        content.setObjectName("ClassCardContent")
        outer.addWidget(content, 1)

        lay = QVBoxLayout(content)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        header = QFrame()
        header.setObjectName("ClassCardHeader")
        header.setFixedHeight(48)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(12, 0, 12, 0)
        h_lay.setSpacing(10)

        ico = QLabel()
        ico_name = (
            "fa5s.university" if self.info.division == "LYCEE"
            else "fa5s.school"
        )
        ico.setPixmap(qta.icon(ico_name, color=self._accent).pixmap(20, 20))
        h_lay.addWidget(ico, 0, Qt.AlignVCenter)

        self._lbl_name = QLabel(self.info.display_name)
        self._lbl_name.setObjectName("ClassCardName")
        h_lay.addWidget(self._lbl_name, 1, Qt.AlignVCenter)

        div_lbl = QLabel(self.info.division)
        div_lbl.setObjectName("ClassCardDiv")
        div_lbl.setStyleSheet("background: transparent;")
        h_lay.addWidget(div_lbl, 0, Qt.AlignVCenter)
        lay.addWidget(header)

        try:
            rel_path = self.info.folder.relative_to(
                self.info.folder.parents[2]
            )
        except (IndexError, ValueError):
            rel_path = self.info.folder
        lbl_path = QLabel(str(rel_path))
        lbl_path.setObjectName("ClassCardPath")
        lbl_path.setWordWrap(True)
        lay.addWidget(lbl_path)

        stats = QHBoxLayout()
        stats.setSpacing(6)
        self._stat_students = self._make_stat("fa5s.users", "—", "Élèves")
        self._stat_subjects = self._make_stat("fa5s.book", "—", "Matières")
        self._stat_xlsx = self._make_stat(
            "fa5s.file-excel",
            str(len(self.info.subject_files)),
            "Fichiers",
        )
        for w in (self._stat_students, self._stat_subjects, self._stat_xlsx):
            stats.addWidget(w, 1)
        lay.addLayout(stats)

        footer = QHBoxLayout()
        footer.setSpacing(8)

        sync_box = QVBoxLayout()
        sync_box.setSpacing(0)
        sync_lbl = QLabel("Dernière synchronisation")
        sync_lbl.setObjectName("ClassCardSyncLabel")
        self._lbl_sync = QLabel("—")
        self._lbl_sync.setObjectName("ClassCardSyncValue")
        sync_box.addWidget(sync_lbl)
        sync_box.addWidget(self._lbl_sync)
        sync_w = QWidget()
        sync_w.setLayout(sync_box)
        footer.addWidget(sync_w, 1)

        self._btn_sync = QToolButton()
        self._btn_sync.setObjectName("ClassCardBtnSync")
        self._btn_sync.setIcon(qta.icon("fa5s.sync-alt"))
        self._btn_sync.setToolTip("Synchroniser depuis le dossier")
        self._btn_sync.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_sync.setFixedSize(36, 36)
        self._btn_sync.clicked.connect(
            lambda: self.syncRequested.emit(self.info.name)
        )
        footer.addWidget(self._btn_sync, 0, Qt.AlignBottom)

        self._btn_open = QPushButton("Ouvrir")
        self._btn_open.setObjectName("ClassCardBtnOpen")
        self._btn_open.setIcon(qta.icon("fa5s.arrow-right"))
        self._btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_open.setFixedHeight(34)
        self._btn_open.clicked.connect(
            lambda: self.openRequested.emit(self.info.name)
        )
        footer.addWidget(self._btn_open, 0, Qt.AlignBottom)
        lay.addLayout(footer)

        if self.db is not None:
            self._refresh_stats()

    def _build_list(self) -> None:
        """Construction en mode liste (card horizontale compacte)."""
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        accent_bar = QFrame()
        accent_bar.setObjectName("ClassCardAccent")
        accent_bar.setFixedWidth(4)
        outer.addWidget(accent_bar, 0, Qt.AlignVCenter)

        content = QFrame()
        content.setObjectName("ClassCardContent")
        outer.addWidget(content, 1)

        lay = QHBoxLayout(content)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(12)

        ico = QLabel()
        ico_name = (
            "fa5s.university" if self.info.division == "LYCEE"
            else "fa5s.school"
        )
        ico.setPixmap(
            qta.icon(ico_name, color=self._accent).pixmap(20, 20)
        )
        lay.addWidget(ico, 0, Qt.AlignVCenter)

        v = QVBoxLayout()
        v.setSpacing(0)
        self._lbl_name = QLabel(self.info.display_name)
        self._lbl_name.setObjectName("ClassCardName")
        v.addWidget(self._lbl_name)
        self._stat_students = QLabel("— élèves")
        self._stat_students.setObjectName("ClassCardStatValue")
        v.addWidget(self._stat_students)
        v_w = QWidget()
        v_w.setLayout(v)
        lay.addWidget(v_w, 1)

        self._lbl_sync = QLabel("—")
        self._lbl_sync.setObjectName("ClassCardSyncValue")
        lay.addWidget(self._lbl_sync, 0, Qt.AlignVCenter)

        self._btn_open = QPushButton(qta.icon("fa5s.arrow-right"), "")
        self._btn_open.setObjectName("ClassCardBtnOpen")
        self._btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_open.setFixedSize(32, 32)
        self._btn_open.clicked.connect(
            lambda: self.openRequested.emit(self.info.name)
        )
        lay.addWidget(self._btn_open, 0, Qt.AlignVCenter)

        if self.db is not None:
            self._refresh_stats_list()

    # ------------------------------------------------------------------
    def _make_stat(self, icon_name: str, value: str, label: str) -> QFrame:
        f = QFrame()
        f.setObjectName("ClassCardListStatBg")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(6)
        ico = QLabel()
        ico.setPixmap(
            qta.icon(icon_name, color=self._accent).pixmap(14, 14)
        )
        lay.addWidget(ico, 0, Qt.AlignVCenter)
        v = QLabel(value)
        v.setObjectName("ClassCardStatValue")
        lay.addWidget(v, 0, Qt.AlignVCenter)
        l = QLabel(label)
        l.setObjectName("ClassCardStatLabel")
        lay.addWidget(l, 1, Qt.AlignVCenter)
        f._value_label = v  # type: ignore[attr-defined]
        return f

    # ------------------------------------------------------------------
    def set_db(self, db: Database) -> None:
        self.db = db
        if self.view_mode == "grid":
            self._refresh_stats()
        else:
            self._refresh_stats_list()

    def _refresh_stats(self) -> None:
        if self.db is None:
            return
        try:
            students = self.db.list_students()
            subjects = self.db.list_subjects()
        except Exception:  # noqa: BLE001
            students, subjects = [], []
        self._stat_students._value_label.setText(str(len(students)))  # type: ignore[attr-defined]
        self._stat_subjects._value_label.setText(str(len(subjects)))  # type: ignore[attr-defined]
        self._refresh_sync_label()

    def _refresh_stats_list(self) -> None:
        if self.db is None:
            return
        try:
            students = self.db.list_students()
        except Exception:  # noqa: BLE001
            students = []
        self._stat_students.setText(f"{len(students)} élèves")
        self._refresh_sync_label()

    def _refresh_sync_label(self) -> None:
        if self.info.subject_files:
            try:
                mtimes = [
                    p.stat().st_mtime
                    for p in self.info.subject_files
                ]
                last = max(mtimes)
                self._lbl_sync.setText(
                    datetime.fromtimestamp(last).strftime(
                        "%d/%m/%Y %H:%M"
                    )
                )
            except OSError:
                self._lbl_sync.setText("—")
        else:
            self._lbl_sync.setText("Aucun fichier")

    # ------------------------------------------------------------------
    # Hover / focus styled via global QSS (cardAccent property)
    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.LeftButton:
            self.openRequested.emit(self.info.name)
        super().mouseDoubleClickEvent(event)


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------


class EmptyState(QFrame):
    """État vide redesigné : illustration + 2 CTA."""

    newClassRequested = Signal()
    importXlsxRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyState")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 60, 20, 60)
        lay.setSpacing(16)
        lay.setAlignment(Qt.AlignCenter)

        ico = QLabel()
        ico.setPixmap(
            qta.icon("fa5s.folder-open", color=theme_current().on_surface_variant).pixmap(96, 96)
        )
        ico.setAlignment(Qt.AlignCenter)
        lay.addWidget(ico, 0, Qt.AlignHCenter)

        title = QLabel("Aucune classe détectée")
        title.setObjectName("HeroTitle")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title, 0, Qt.AlignHCenter)

        sub = QLabel(
            "Créez votre première classe avec l'assistant, ou importez\n"
            "un classeur multi-classes pour tout créer en 1 clic."
        )
        sub.setObjectName("HeroSubtitle")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub, 0, Qt.AlignHCenter)

        # Boutons
        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addStretch(1)

        btn_import = QPushButton(
            qta.icon("fa5s.file-import"), "  Importer"
        )
        btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        set_kind(btn_import, "outlined")
        btn_import.setStyleSheet(
            "QPushButton[kind=\"outlined\"] {"
            "  padding: 10px 18px; font-size: 13px;"
            "}"
        )
        btn_import.clicked.connect(self.importXlsxRequested.emit)
        btns.addWidget(btn_import)

        btn_new = QPushButton(qta.icon("fa5s.plus"), "  Nouvelle classe")
        set_kind(btn_new, "primary")
        btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new.clicked.connect(self.newClassRequested.emit)
        btns.addWidget(btn_new)

        btns.addStretch(1)
        btns_w = QWidget()
        btns_w.setLayout(btns)
        lay.addWidget(btns_w, 0, Qt.AlignHCenter)


# ---------------------------------------------------------------------------
# Filter chips
# ---------------------------------------------------------------------------


class FilterChip(QPushButton):
    """Chip toggleable (Collège / Lycée / Tous)."""

    def __init__(self, label: str, icon: str, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setText(f"  {label}")
        self.setIcon(qta.icon(icon))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        set_kind(self, "chip")


# ---------------------------------------------------------------------------
# Home dashboard widget (refonte premium)
# ---------------------------------------------------------------------------


class HomeDashboardWidget(QWidget):
    """Grand tableau de bord d'accueil avec design moderne.

    Refonte premium :
    - **Hero header** avec logo, titre, sous-titre, stats en gros
    - **Barre de recherche** (filter live)
    - **Filter chips** : Tous / Collège / Lycée
    - **Toggle Grille ↔ Liste** (mode compact)
    - **Cards** redesignées (gradient, accent, hover)
    - **Empty state** redesigné (illustration + 2 CTA)
    """

    classSelected = Signal(str)
    newClassRequested = Signal()
    refreshRequested = Signal()
    syncRequested = Signal(str)
    importXlsxRequested = Signal()
    backupManagerRequested = Signal()
    fullResetRequested = Signal()

    def __init__(
        self,
        db: Optional[Database] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self._filter_text = ""
        self._filter_division = "ALL"  # "ALL" | "COLLEGE" | "LYCEE" | "PRIMAIRE"
        self._view_mode = "grid"       # "grid" | "list"
        self._section_grids: list[tuple[QGridLayout, list[QWidget]]] = []
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ============== TAB NAVIGATION ==============
        self._tab_widget = QTabWidget()
        self._tab_widget.setObjectName("HomeTabs")
        self._tab_widget.setTabsClosable(False)
        self._tab_widget.setMovable(False)

        # ============== ONGLET 1 : VUE DES CLASSES ==============
        classes_tab = QWidget()
        classes_tab_lay = QVBoxLayout(classes_tab)
        classes_tab_lay.setContentsMargins(0, 0, 0, 0)
        classes_tab_lay.setSpacing(0)

        # Hero header
        hero = QFrame()
        hero.setObjectName("HomeHero")
        hero_lay = QVBoxLayout(hero)
        hero_lay.setContentsMargins(20, 18, 20, 14)
        hero_lay.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        logo_box = QFrame()
        logo_box.setObjectName("HeroLogoBox")
        logo_box.setFixedSize(48, 48)
        logo_lay = QVBoxLayout(logo_box)
        logo_lay.setContentsMargins(0, 0, 0, 0)
        logo_ico = QLabel()
        logo_ico.setPixmap(
            qta.icon("fa5s.graduation-cap", color="white").pixmap(24, 24)
        )
        logo_ico.setAlignment(Qt.AlignCenter)
        logo_lay.addWidget(logo_ico)
        top_row.addWidget(logo_box)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("Bulletin Premium")
        title.setObjectName("HeroTitle")
        sub = QLabel("Classes")
        sub.setObjectName("HeroSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(sub)
        title_w = QWidget()
        title_w.setLayout(title_box)
        top_row.addWidget(title_w, 1)

        hero_lay.addLayout(top_row)

        # Stats KPI (2 gros chiffres)
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self._stat_total = self._make_kpi_hero(
            "fa5s.university", "0", "Classes", COLOR_AVERAGE_OK
        )
        self._stat_xlsx = self._make_kpi_hero(
            "fa5s.file-excel", "0", "Fichiers", "#059669"
        )
        for w in (self._stat_total, self._stat_xlsx):
            kpi_row.addWidget(w, 1)
        hero_lay.addLayout(kpi_row)

        classes_tab_lay.addWidget(hero)

        # Toolbar (search + chips + view toggle)
        toolbar = QFrame()
        toolbar.setObjectName("HomeToolbar")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(16, 10, 16, 10)
        tb_lay.setSpacing(8)

        self._search = QLineEdit()
        self._search.setObjectName("HomeSearch")
        self._search.setPlaceholderText("Filtrer par nom de classe…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_filter_changed)
        self._search.setMaximumWidth(get_scale().sw(320))
        tb_lay.addWidget(self._search)

        self._chip_all = FilterChip("Tous", "fa5s.th-large")
        self._chip_college = FilterChip("Collège", "fa5s.school")
        self._chip_lycee = FilterChip("Lycée", "fa5s.university")
        self._chip_primaire = FilterChip("Primaire", "fa5s.child")
        self._chip_all.setChecked(True)
        chip_group = QButtonGroup(self)
        chip_group.setExclusive(True)
        chip_group.addButton(self._chip_all, 0)
        chip_group.addButton(self._chip_college, 1)
        chip_group.addButton(self._chip_lycee, 2)
        chip_group.addButton(self._chip_primaire, 3)
        chip_group.idClicked.connect(self._on_chip_clicked)
        tb_lay.addWidget(self._chip_all)
        tb_lay.addWidget(self._chip_college)
        tb_lay.addWidget(self._chip_lycee)
        tb_lay.addWidget(self._chip_primaire)

        tb_lay.addStretch(1)

        view_box = QFrame()
        view_box.setObjectName("ViewToggleBox")
        view_lay = QHBoxLayout(view_box)
        view_lay.setContentsMargins(2, 2, 2, 2)
        view_lay.setSpacing(0)
        self._btn_view_grid = QToolButton()
        self._btn_view_grid.setObjectName("ViewToggleBtn")
        self._btn_view_grid.setIcon(qta.icon("fa5s.th-large"))
        self._btn_view_grid.setToolTip("Vue grille")
        self._btn_view_grid.setCheckable(True)
        self._btn_view_grid.setChecked(True)
        self._btn_view_grid.setFixedSize(30, 26)
        self._btn_view_list = QToolButton()
        self._btn_view_list.setObjectName("ViewToggleBtn")
        self._btn_view_list.setIcon(qta.icon("fa5s.bars"))
        self._btn_view_list.setToolTip("Vue liste")
        self._btn_view_list.setCheckable(True)
        self._btn_view_list.setFixedSize(30, 26)
        view_group = QButtonGroup(self)
        view_group.setExclusive(True)
        view_group.addButton(self._btn_view_grid, 0)
        view_group.addButton(self._btn_view_list, 1)
        view_group.idClicked.connect(self._on_view_clicked)
        view_lay.addWidget(self._btn_view_grid)
        view_lay.addWidget(self._btn_view_list)
        tb_lay.addWidget(view_box)

        classes_tab_lay.addWidget(toolbar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setObjectName("HomeScroll")

        self._cards_host = QWidget()
        self._cards_host.setObjectName("HomeCardsHost")
        self._cards_layout = QVBoxLayout(self._cards_host)
        self._cards_layout.setContentsMargins(16, 12, 16, 12)
        self._cards_layout.setSpacing(16)
        self._cards_layout.addStretch(1)
        self._scroll.setWidget(self._cards_host)
        classes_tab_lay.addWidget(self._scroll, 1)

        self._tab_widget.addTab(classes_tab, "Classes")

        # ============== ONGLET 2 : CONFIGURATION DES CLASSES ==============
        config_tab = QWidget()
        config_tab_lay = QVBoxLayout(config_tab)
        config_tab_lay.setContentsMargins(0, 0, 0, 0)
        config_tab_lay.setSpacing(0)

        self._build_class_config_panel(config_tab_lay)

        self._tab_widget.addTab(config_tab, "Configuration")

        root.addWidget(self._tab_widget, 1)

    # ------------------------------------------------------------------
    def _make_kpi_hero(
        self, icon_name: str, value: str, label: str, color: str
    ) -> QFrame:
        """KPI gros format pour le hero header."""
        COLOR_TO_KPI = {
            COLOR_AVERAGE_OK: "primary",
            COLOR_SUBJECT_MJ: "secondary",
            COLOR_SUBJECT_COMPO: "tertiary",
            "#059669": "success",
        }
        kpi_kind = COLOR_TO_KPI.get(color, "primary")
        f = QFrame()
        f.setObjectName("KpiHero")
        f.setMinimumHeight(64)
        lay = QHBoxLayout(f)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        ico_box = QFrame()
        ico_box.setObjectName("KpiIconBox")
        ico_box.setProperty("kpiColor", kpi_kind)
        ico_box.setFixedSize(36, 36)
        ico_lay = QVBoxLayout(ico_box)
        ico_lay.setContentsMargins(0, 0, 0, 0)
        ico = QLabel()
        ico.setPixmap(qta.icon(icon_name, color="white").pixmap(18, 18))
        ico.setAlignment(Qt.AlignCenter)
        ico_lay.addWidget(ico)
        lay.addWidget(ico_box, 0, Qt.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(0)
        v = QLabel(value)
        v.setObjectName("KpiValue")
        l = QLabel(label)
        l.setObjectName("KpiLabel")
        text.addWidget(v)
        text.addWidget(l)
        lay.addLayout(text, 1)
        f._value_label = v  # type: ignore[attr-defined]
        return f

    # ------------------------------------------------------------------
    def set_db(self, db: Database) -> None:
        """Met à jour la DB active (référence).

        Les ClassCards ouvrent leur **propre** DB (par classe), donc
        on ne propage pas la DB active aux cards ici. À la place, on
        reconstruit les cards visibles pour qu'elles rouvrent leurs
        DBs (utile quand la DB active change après un import XLSX
        ou une création de classe).
        """
        self.db = db
        if self._cards_layout.count() > 1:
            self._rebuild_visible_cards()

    def _open_class_db(self, info: ClassInfo) -> Optional[Database]:
        """Ouvre la DB de la classe info, ou None si indisponible.

        On évite de partager la DB active de la MainWindow : chaque
        classe a sa propre DB, et sur l'accueil on veut afficher
        les stats **de cette classe** (nb d'élèves, nb de matières).
        """
        try:
            db_path = getattr(info, "db_path", None)
            if db_path is None or not Path(db_path).exists():
                return None
            return Database(str(db_path))
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    def _on_filter_changed(self, text: str) -> None:
        self._filter_text = text.strip().lower()
        self._rebuild_visible_cards()

    def _on_chip_clicked(self, chip_id: int) -> None:
        self._filter_division = ["ALL", "COLLEGE", "LYCEE", "PRIMAIRE"][chip_id]
        self._rebuild_visible_cards()

    def _on_view_clicked(self, view_id: int) -> None:
        self._view_mode = ["grid", "list"][view_id]
        self._rebuild_visible_cards()

    def _on_refresh_clicked(self) -> None:
        self.refresh()
        self.refreshRequested.emit()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        classes = discover_classes()

        # Stats globales
        nb_xlsx = sum(len(c.subject_files) for c in classes)
        self._stat_total._value_label.setText(str(len(classes)))  # type: ignore[attr-defined]
        self._stat_xlsx._value_label.setText(str(nb_xlsx))  # type: ignore[attr-defined]

        # Si aucune classe du tout, affiche l'empty state
        if not classes:
            self._clear_cards()
            empty = EmptyState()
            empty.newClassRequested.connect(self.newClassRequested.emit)
            empty.importXlsxRequested.connect(self.importXlsxRequested.emit)
            self._cards_layout.insertWidget(0, empty)
            return
        self._rebuild_visible_cards()

    def _clear_cards(self) -> None:
        self._section_grids.clear()
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                w = item.widget()
                # Ferme proprement la DB ouverte par la card
                if isinstance(w, ClassCard) and w.db is not None:
                    try:
                        w.db.close()
                    except Exception:  # noqa: BLE001
                        pass
                w.deleteLater()

    def _rebuild_visible_cards(self) -> None:
        """Reconstruit la zone des cards en appliquant les filtres."""
        self._clear_cards()
        classes = discover_classes()

        # Filtre division
        if self._filter_division != "ALL":
            classes = [c for c in classes
                       if c.division == self._filter_division]
        # Filtre texte
        if self._filter_text:
            classes = [
                c for c in classes
                if self._filter_text in c.display_name.lower()
                or self._filter_text in c.name.lower()
            ]
        if not classes:
            # Message « aucun résultat »
            msg = QLabel(
                "Aucun résultat pour votre recherche.\n"
                "Essayez d'élargir les critères."
            )
            msg.setObjectName("NoResults")
            msg.setAlignment(Qt.AlignCenter)
            self._cards_layout.insertWidget(0, msg)
            return
        # Regroupe par division
        for division in ("COLLEGE", "LYCEE", "PRIMAIRE"):
            sub = [c for c in classes if c.division == division]
            if not sub:
                continue
            section = self._build_section(division, sub)
            self._cards_layout.insertWidget(
                self._cards_layout.count() - 1, section
            )

    def _compute_cols(self) -> int:
        return max(2, min(4, self.width() // 320))

    def _layout_cards(self) -> None:
        for grid, cards in self._section_grids:
            for card in cards:
                grid.removeWidget(card)
            cols = self._compute_cols()
            for c in range(cols):
                grid.setColumnStretch(c, 1)
            for i, card in enumerate(cards):
                row, col = divmod(i, cols)
                grid.addWidget(card, row, col)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_cards()

    def _build_section(
        self, division: str, classes: list[ClassInfo]
    ) -> QWidget:
        section = QWidget()
        sec_lay = QVBoxLayout(section)
        sec_lay.setContentsMargins(0, 0, 0, 0)
        sec_lay.setSpacing(10)

        label_map = {"COLLEGE": "Collège", "LYCEE": "Lycée", "PRIMAIRE": "Primaire"}
        title = QLabel(
            f"{label_map.get(division, division)}  "
            f"·  {len(classes)} classe{'s' if len(classes) > 1 else ''}"
        )
        title.setObjectName("SectionHeader")
        title.setStyleSheet("padding: 0 4px;")
        sec_lay.addWidget(title)

        if self._view_mode == "grid":
            grid_host = QWidget()
            grid = QGridLayout(grid_host)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(12)
            cols = max(2, min(4, self.width() // 320))
            for c in range(cols):
                grid.setColumnStretch(c, 1)
            cards = []
            for i, info in enumerate(classes):
                card = ClassCard(
                    info, db=self._open_class_db(info), view_mode="grid"
                )
                card.openRequested.connect(self.classSelected.emit)
                card.syncRequested.connect(self.syncRequested.emit)
                cards.append(card)
                row, col = divmod(i, cols)
                grid.addWidget(card, row, col)
            self._section_grids.append((grid, cards))
            sec_lay.addWidget(grid_host)
        else:
            list_host = QWidget()
            list_lay = QVBoxLayout(list_host)
            list_lay.setContentsMargins(0, 0, 0, 0)
            list_lay.setSpacing(6)
            for info in classes:
                card = ClassCard(
                    info, db=self._open_class_db(info), view_mode="list"
                )
                card.openRequested.connect(self.classSelected.emit)
                card.syncRequested.connect(self.syncRequested.emit)
                list_lay.addWidget(card)
            sec_lay.addWidget(list_host)
        return section

    def _build_class_config_panel(self, parent_layout: QVBoxLayout) -> None:
        """Construit le panel de configuration de classe dans l'onglet Configuration."""
        from .class_config_panel import ClassConfigPanel

        config_panel = ClassConfigPanel(db=self.db)
        config_panel.setObjectName("ClassConfigPanel")
        config_panel.setStyleSheet("""
            #ClassConfigPanel {
                margin: 16px;
                background-color: palette(window);
                border-radius: 8px;
            }
        """)
        parent_layout.addWidget(config_panel)
