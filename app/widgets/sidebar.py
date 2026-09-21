"""Sidebar de navigation latérale — refonte premium.

Remplace la barre d'outils encombrante par une sidebar verticale
avec branding, navigation principale et actions globales.
"""

from __future__ import annotations

from typing import Optional

import qtawesome as qta
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QEnterEvent
from qtpy.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..theme import current as theme_current
from .common import set_kind


class SidebarButton(QPushButton):
    """Bouton de navigation dans la sidebar."""

    def __init__(
        self,
        icon_name: str = "",
        text: str = "",
        active: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._is_active = active
        if icon_name:
            self.setIcon(qta.icon(icon_name))
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(40)
        self.setCheckable(True)
        self.setChecked(active)
        self.setProperty("sidebar", "nav")
        if active:
            self.setProperty("active", "true")


class SidebarSection(QLabel):
    """Titre de section dans la sidebar."""

    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setProperty("sidebar", "section")


class Sidebar(QFrame):
    """Sidebar de navigation principale."""

    homeRequested = Signal()
    classRequested = Signal(str)
    tabRequested = Signal(int)
    settingsRequested = Signal()
    themeToggleRequested = Signal()
    newClassRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("AppSidebar")
        self.setFixedWidth(160)  # sera ajusté par MainWindow selon l'écran

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Branding
        brand = QFrame()
        brand.setObjectName("SidebarBrand")
        brand.setFixedHeight(64)
        brand_lay = QHBoxLayout(brand)
        brand_lay.setContentsMargins(16, 0, 16, 0)
        brand_lay.setSpacing(10)

        logo = QLabel()
        logo.setPixmap(
            qta.icon("fa5s.graduation-cap", color=theme_current().primary)
            .pixmap(28, 28)
        )
        brand_lay.addWidget(logo)

        name = QLabel("Bulletin")
        name.setProperty("sidebar", "brand")
        brand_lay.addWidget(name)
        brand_lay.addStretch(1)
        layout.addWidget(brand)

        # Scrollable nav area
        scroll_container = QFrame()
        scroll_container.setObjectName("SidebarNav")
        nav_layout = QVBoxLayout(scroll_container)
        nav_layout.setContentsMargins(10, 12, 10, 12)
        nav_layout.setSpacing(2)

        # Accueil
        self._btn_home = SidebarButton("fa5s.th-large", "  Accueil", active=True)
        self._btn_home.clicked.connect(self.homeRequested.emit)
        nav_layout.addWidget(self._btn_home)

        nav_layout.addSpacing(8)

        # Nouvelle classe (position prioritaire)
        self._btn_new = QPushButton(
            qta.icon("fa5s.plus-circle"), "  Nouvelle classe"
        )
        self._btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_new.setMinimumHeight(36)
        self._btn_new.setProperty("sidebar", "nav")
        self._btn_new.clicked.connect(self.newClassRequested.emit)
        nav_layout.addWidget(self._btn_new)

        nav_layout.addSpacing(4)

        # Section classes
        section_label = SidebarSection("CLASSES")
        nav_layout.addWidget(section_label)

        self._class_buttons: list[SidebarButton] = []
        self._class_nav: QVBoxLayout = nav_layout
        self._nav_stretch = None  # repère pour insertion des classes

        self._nav_stretch = QWidget()
        self._nav_stretch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        nav_layout.addWidget(self._nav_stretch, 1)

        # Separator
        sep = QFrame()
        sep.setProperty("sidebar", "sep")
        sep.setFixedHeight(1)
        nav_layout.addWidget(sep)

        nav_layout.addSpacing(4)

        nav_layout.addSpacing(4)

        # Theme toggle + settings row
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(10, 0, 10, 0)
        bottom_row.setSpacing(4)

        self._btn_theme = QPushButton()
        self._btn_theme.setIcon(qta.icon("fa5s.moon"))
        self._btn_theme.setToolTip("Mode sombre/clair")
        self._btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_theme.setFixedSize(36, 36)
        self._btn_theme.setProperty("sidebar", "icon")
        self._btn_theme.clicked.connect(self.themeToggleRequested.emit)
        bottom_row.addWidget(self._btn_theme)

        self._btn_settings = QPushButton()
        self._btn_settings.setIcon(qta.icon("fa5s.cog"))
        self._btn_settings.setToolTip("Paramètres d'export")
        self._btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_settings.setFixedSize(36, 36)
        self._btn_settings.setProperty("sidebar", "icon")
        self._btn_settings.clicked.connect(self.settingsRequested.emit)
        bottom_row.addWidget(self._btn_settings)

        bottom_row.addStretch(1)
        layout.addLayout(bottom_row)
        layout.addSpacing(8)

        layout.addWidget(scroll_container, 1)

    # ------------------------------------------------------------------
    def set_classes(self, class_names: list[str], active_class: str = "") -> None:
        """Met à jour la liste des classes dans la sidebar."""
        for btn in self._class_buttons:
            self._class_nav.removeWidget(btn)
            btn.deleteLater()
        self._class_buttons.clear()

        insert_before = self._nav_stretch
        for name in class_names:
            btn = SidebarButton("fa5s.school", f"  {name}")
            btn.setChecked(name == active_class)
            btn.setProperty("active", "true" if name == active_class else "false")
            btn.clicked.connect(lambda _checked=False, n=name: self.classRequested.emit(n))
            self._class_nav.insertWidget(
                self._class_nav.indexOf(insert_before) if insert_before else -1,
                btn,
            )
            self._class_buttons.append(btn)

    def set_active_tab(self, index: int) -> None:
        """Marque un onglet comme actif (utilisé pour le suivi)."""
        pass  # Les tabs sont gérés par le QTabWidget

    def set_theme_icon(self, is_dark: bool) -> None:
        self._btn_theme.setIcon(
            qta.icon("fa5s.sun" if is_dark else "fa5s.moon")
        )
