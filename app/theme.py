"""Application theme (Material 3 inspired).

Le thème est exposé sous forme de :class:`Palette`. Deux palettes
sont prédéfinies : *light* et *dark*. La fonction :func:`qss_for`
génère la feuille de style QSS complète pour une palette donnée.

Les couleurs suivent le système de tokens Material 3 (primary /
on-primary / primary-container / …) ce qui garde un look cohérent
si la couleur de marque change.

La QSS est régénérée à chaque bascule light/dark ; :func:`apply`
met à jour le stylesheet global de l'application.

Adapté de eco_paiement/eco_paiement_mvc/theme.py pour qtpy
(PyQt5 / PyQt6 / PySide2 / PySide6).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from qtpy.QtGui import QColor
from qtpy.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    """A complete Material 3-style palette."""

    name: str

    # Surfaces / backgrounds
    background: str
    surface: str
    surface_dim: str
    surface_bright: str
    surface_container_lowest: str
    surface_container_low: str
    surface_container: str
    surface_container_high: str
    surface_container_highest: str

    # Text / on-colors
    on_surface: str
    on_surface_variant: str

    # Outlines
    outline: str
    outline_variant: str

    # Primary
    primary: str
    on_primary: str
    primary_container: str
    on_primary_container: str
    primary_hover: str

    # Secondary
    secondary: str
    on_secondary: str
    secondary_container: str
    on_secondary_container: str

    # Tertiary
    tertiary: str
    on_tertiary: str
    tertiary_container: str
    on_tertiary_container: str

    # Status
    success: str
    on_success: str
    success_container: str
    on_success_container: str
    warning: str
    on_warning: str
    warning_container: str
    on_warning_container: str
    danger: str
    on_danger: str
    danger_container: str
    on_danger_container: str
    info: str
    on_info: str
    info_container: str
    on_info_container: str

    # Toolbar / sidebar
    toolbar_bg: str
    toolbar_border: str
    sidebar_bg: str
    sidebar_text: str
    sidebar_text_muted: str
    sidebar_hover_bg: str
    sidebar_active_bg: str
    sidebar_active_text: str
    sidebar_border: str


# ---------------------------------------------------------------------------
# Predefined palettes
# ---------------------------------------------------------------------------


LIGHT = Palette(
    name="light",
    # Surfaces
    background="#F4F6FA",
    surface="#FFFFFF",
    surface_dim="#E8ECF2",
    surface_bright="#FFFFFF",
    surface_container_lowest="#FFFFFF",
    surface_container_low="#F8FAFC",
    surface_container="#F1F5F9",
    surface_container_high="#E2E8F0",
    surface_container_highest="#CBD5E1",
    # Text
    on_surface="#0F172A",
    on_surface_variant="#475569",
    # Outlines
    outline="#CBD5E1",
    outline_variant="#E2E8F0",
    # Primary (Indigo)
    primary="#6366F1",
    on_primary="#FFFFFF",
    primary_container="#E0E7FF",
    on_primary_container="#312E81",
    primary_hover="#4F46E5",
    # Secondary (Teal)
    secondary="#14B8A6",
    on_secondary="#FFFFFF",
    secondary_container="#CCFBF1",
    on_secondary_container="#134E4A",
    # Tertiary (Amber)
    tertiary="#F59E0B",
    on_tertiary="#FFFFFF",
    tertiary_container="#FEF3C7",
    on_tertiary_container="#78350F",
    # Status
    success="#059669",
    on_success="#FFFFFF",
    success_container="#D1FAE5",
    on_success_container="#064E3B",
    warning="#D97706",
    on_warning="#FFFFFF",
    warning_container="#FEF3C7",
    on_warning_container="#78350F",
    danger="#DC2626",
    on_danger="#FFFFFF",
    danger_container="#FEE2E2",
    on_danger_container="#7F1D1D",
    info="#2563EB",
    on_info="#FFFFFF",
    info_container="#DBEAFE",
    on_info_container="#1E3A8A",
    # Toolbar / sidebar
    toolbar_bg="#FFFFFF",
    toolbar_border="#E2E8F0",
    sidebar_bg="#FFFFFF",
    sidebar_text="#0F172A",
    sidebar_text_muted="#64748B",
    sidebar_hover_bg="#F1F5F9",
    sidebar_active_bg="#EEF2FF",
    sidebar_active_text="#4338CA",
    sidebar_border="#E2E8F0",
)


DARK = Palette(
    name="dark",
    # Surfaces
    background="#0B1120",
    surface="#111827",
    surface_dim="#0B1120",
    surface_bright="#1F2937",
    surface_container_lowest="#0B1120",
    surface_container_low="#0F172A",
    surface_container="#1F2937",
    surface_container_high="#374151",
    surface_container_highest="#4B5563",
    # Text
    on_surface="#F1F5F9",
    on_surface_variant="#94A3B8",
    # Outlines
    outline="#334155",
    outline_variant="#1F2937",
    # Primary
    primary="#818CF8",
    on_primary="#1E1B4B",
    primary_container="#312E81",
    on_primary_container="#E0E7FF",
    primary_hover="#A5B4FC",
    # Secondary
    secondary="#34D399",
    on_secondary="#022C22",
    secondary_container="#064E3B",
    on_secondary_container="#D1FAE5",
    # Tertiary
    tertiary="#FBBF24",
    on_tertiary="#451A03",
    tertiary_container="#78350F",
    on_tertiary_container="#FEF3C7",
    # Status
    success="#34D399",
    on_success="#022C22",
    success_container="#064E3B",
    on_success_container="#D1FAE5",
    warning="#FBBF24",
    warning_container="#78350F",
    on_warning_container="#FEF3C7",
    danger="#F87171",
    on_danger="#450A0A",
    danger_container="#7F1D1D",
    on_danger_container="#FEE2E2",
    info="#60A5FA",
    info_container="#1E3A8A",
    on_info_container="#DBEAFE",
    on_warning="#451A03",
    on_info="#172554",
    # Toolbar / sidebar
    toolbar_bg="#0F172A",
    toolbar_border="#1F2937",
    sidebar_bg="#0B1120",
    sidebar_text="#F1F5F9",
    sidebar_text_muted="#64748B",
    sidebar_hover_bg="#1F2937",
    sidebar_active_bg="#1E1B4B",
    sidebar_active_text="#A5B4FC",
    sidebar_border="#1F2937",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def with_alpha(hex_color: str, alpha: float) -> str:
    """Return ``rgba(r, g, b, a)`` from a ``#rrggbb`` color."""
    c = QColor(hex_color)
    if not c.isValid():
        return f"rgba(0, 0, 0, {alpha})"
    a = max(0.0, min(1.0, alpha))
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a:.3f})"


def is_dark(p: Palette) -> bool:
    """Return True if *p* is a dark palette (heuristic on background luminance)."""
    bg = QColor(p.background)
    return bg.lightness() < 128


# ---------------------------------------------------------------------------
# QSS generation
# ---------------------------------------------------------------------------


def qss_for(p: Palette) -> str:
    """Generate the full QSS stylesheet for *p*."""

    font_family = (
        '"Inter", "SF Pro Text", "Segoe UI Variable", '
        '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    )

    sidebar_selected_bg = with_alpha(p.primary, 0.14)
    sidebar_selected_border = with_alpha(p.primary, 0.45)
    sidebar_hover_bg = with_alpha(p.primary, 0.08)
    card_hover_bg = p.surface_container_low
    focus_ring = with_alpha(p.primary, 0.35)

    return f"""
/* ============================================================ */
/*  Base                                                         */
/* ============================================================ */
* {{
    font-family: {font_family};
    font-size: 13px;
    color: {p.on_surface};
    outline: 0;
}}
QWidget {{
    background: transparent;
}}
QMainWindow, QDialog#MainDialog {{
    background: {p.background};
}}
QToolTip {{
    background: {p.on_surface};
    color: {p.surface};
    border: none; padding: 6px 10px; border-radius: 6px; font-size: 12px;
}}

/* ============================================================ */
/*  Status label                                                 */
/* ============================================================ */
QLabel#StatusLabel {{
    color: {p.on_surface_variant};
    font-size: 12px; padding: 0 8px; background: transparent;
}}

/* ============================================================ */
/*  Inputs                                                       */
/* ============================================================ */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit,
QTextEdit, QPlainTextEdit {{
    background: {p.surface};
    border: 1px solid {p.outline_variant};
    border-radius: 10px; padding: 7px 12px;
    selection-background-color: {p.primary_container};
    selection-color: {p.on_primary_container};
    color: {p.on_surface};
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover,
QDoubleSpinBox:hover, QDateEdit:hover,
QTextEdit:hover, QPlainTextEdit:hover {{
    border-color: {p.outline};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus,
QTextEdit:focus, QPlainTextEdit:focus {{
    border: 2px solid {p.primary}; padding: 6px 11px;
}}
QDoubleSpinBox#GradeSpin {{
    background: transparent;
    border: 1px solid {p.outline_variant};
    border-radius: 8px; padding: 4px 8px;
    color: {p.on_surface_variant};
    font-weight: 600; min-height: 24px;
    selection-background-color: {p.primary_container};
    selection-color: {p.on_primary_container};
}}
QDoubleSpinBox#GradeSpin[filled="1"] {{
    border: 1.5px solid {p.primary};
    background: {p.primary_container};
    color: {p.on_primary_container}; font-weight: 700;
}}
QDoubleSpinBox#GradeSpin:hover {{ border-color: {p.outline}; }}
QDoubleSpinBox#GradeSpin:focus {{
    border: 2px solid {p.primary};
    background: {p.surface}; color: {p.on_surface}; padding: 3px 7px;
}}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {p.surface};
    border: 1px solid {p.outline_variant}; border-radius: 8px; padding: 4px;
    selection-background-color: {p.primary_container};
    selection-color: {p.on_primary_container}; outline: 0;
}}

/* ============================================================ */
/*  Buttons                                                      */
/* ============================================================ */
QPushButton {{
    background: {p.surface}; color: {p.on_surface};
    border: 1px solid {p.outline_variant}; border-radius: 10px;
    padding: 7px 16px; font-weight: 600; min-height: 18px;
}}
QPushButton:hover {{
    background: {p.surface_container_low}; border-color: {p.outline};
}}
QPushButton:pressed {{ background: {p.surface_container}; }}
QPushButton:disabled {{
    color: {with_alpha(p.on_surface, 0.38)};
    background: {with_alpha(p.surface_container, 0.5)};
    border-color: {with_alpha(p.outline_variant, 0.5)};
}}
QPushButton[kind="primary"] {{
    background: {p.primary}; color: {p.on_primary};
    border: none; border-radius: 10px; padding: 8px 16px; font-weight: 700;
}}
QPushButton[kind="primary"]:hover {{ background: {p.primary_hover}; }}
QPushButton[kind="primary"]:pressed {{
    background: {p.primary_hover}; padding-top: 8px; padding-bottom: 6px;
}}
QPushButton[kind="primary"]:disabled {{
    background: {p.surface_container}; color: {p.on_surface_variant};
}}
QPushButton[kind="tonal"] {{
    background: {p.primary_container}; color: {p.on_primary_container};
    border: none; font-weight: 700;
}}
QPushButton[kind="tonal"]:hover {{
    background: {with_alpha(p.primary, 0.18)};
}}
QPushButton[kind="outlined"] {{
    background: transparent; color: {p.primary};
    border: 1px solid {p.outline}; font-weight: 600;
}}
QPushButton[kind="outlined"]:hover {{
    background: {with_alpha(p.primary, 0.08)}; border-color: {p.primary};
}}
QPushButton[kind="text"] {{
    background: transparent; color: {p.primary};
    border: 1px solid transparent; padding: 6px 10px; font-weight: 600;
}}
QPushButton[kind="text"]:hover {{
    background: {with_alpha(p.primary, 0.08)};
    border-color: {with_alpha(p.primary, 0.2)};
}}
QPushButton[kind="danger"] {{
    background: {p.danger}; color: {p.on_danger};
    border: none; font-weight: 700;
}}
QPushButton[kind="danger"]:hover {{ background: {with_alpha(p.danger, 0.88)}; }}
QPushButton[kind="ghost"] {{
    background: transparent; border: 1px solid {p.outline}; color: {p.on_surface};
}}
QPushButton[kind="ghost"]:hover {{
    background: {with_alpha(p.on_surface, 0.06)};
}}
QPushButton[kind="flat"] {{
    background: transparent; border: 1px solid {p.outline_variant};
    color: {p.on_surface_variant}; padding: 6px 10px; font-weight: 600;
}}
QPushButton[kind="flat"]:hover {{
    background: {p.surface_container_low}; color: {p.on_surface};
    border-color: {p.outline};
}}
QPushButton[kind="seg"] {{
    background: {p.surface}; border: 1px solid {p.outline_variant};
    border-radius: 9px; color: {p.on_surface_variant};
    padding: 6px 14px; font-weight: 600;
}}
QPushButton[kind="seg"]:hover {{
    background: {p.surface_container_low}; color: {p.on_surface};
}}
QPushButton[kind="seg"][active="1"] {{
    background: {p.primary_container}; color: {p.on_primary_container};
    border-color: {p.primary_container};
}}
QPushButton[kind="chip"] {{
    background: {p.surface_container_lowest}; border: 1px solid {p.outline_variant};
    border-radius: 14px; padding: 5px 14px;
    font-size: 12px; font-weight: 600; color: {p.on_surface_variant};
}}
QPushButton[kind="chip"]:hover {{
    background: {p.surface_container_low}; color: {p.on_surface};
    border-color: {p.outline};
}}
QPushButton[kind="chip"][active="1"] {{
    background: {p.primary_container}; color: {p.on_primary_container};
    border-color: {p.primary_container};
}}

/* ============================================================ */
/*  Toolbar                                                      */
/* ============================================================ */
QToolBar {{
    background: {p.toolbar_bg}; border: none;
    border-bottom: 1px solid {p.toolbar_border};
    padding: 6px 10px; spacing: 8px;
}}
QToolBar::separator {{
    background: {p.outline_variant}; width: 1px; margin: 6px 4px;
}}
QToolBar QLabel {{
    color: {p.on_surface_variant}; font-weight: 700; font-size: 12px;
}}
QToolBar QToolButton {{
    padding: 6px; border-radius: 8px;
    background: transparent; border: 1px solid transparent;
}}
QToolBar QToolButton:hover {{
    background: {p.surface_container_low}; border: 1px solid {p.outline};
}}
QToolBar QToolButton:pressed {{ background: {p.outline_variant}; }}

/* ============================================================ */
/*  TopContainer                                                 */
/* ============================================================ */
QFrame#TopContainer {{
    background: {p.surface}; border: 1px solid {p.outline_variant};
    border-radius: 14px;
}}
QLabel#PageTitle {{
    font-size: 22px; font-weight: 800; color: {p.on_surface};
    letter-spacing: -0.3px;
}}
QLabel#PageSubtitle {{
    color: {p.on_surface_variant}; font-size: 13px; font-weight: 500;
}}
QLabel#PageIcon {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 {p.primary}, stop:1 {p.secondary});
    color: white; border-radius: 10px; min-width: 36px; min-height: 36px;
    qproperty-alignment: AlignCenter; font-weight: 800;
}}

/* ============================================================ */
/*  Panels & cards                                               */
/* ============================================================ */
QFrame#Panel {{
    background: {p.surface}; border: 1px solid {p.outline_variant};
    border-radius: 14px;
}}
QFrame#Panel:hover {{
    border: 1px solid {p.outline};
}}
QLabel#PanelTitle {{
    font-size: 16px; font-weight: 800; color: {p.on_surface};
    padding-bottom: 4px; letter-spacing: -0.1px;
}}
QLabel#PanelSubtitle {{
    color: {p.on_surface_variant}; font-size: 12px; font-weight: 500;
}}
QFrame#Card {{
    background: {p.surface}; border: 1px solid {p.outline_variant};
    border-radius: 14px;
}}
QFrame#Card:hover {{ background: {card_hover_bg}; }}
QLabel#CardTitle {{
    color: {p.on_surface_variant}; font-weight: 700; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.8px;
}}
QLabel#CardValue {{
    font-size: 22px; font-weight: 800; color: {p.on_surface};
    letter-spacing: -0.4px;
}}
QLabel#CardHint {{
    color: {p.on_surface_variant}; font-size: 11px; font-weight: 500;
}}

/* ============================================================ */
/*  Home dashboard                                               */
/* ============================================================ */
QFrame#ClassCard {{
    background: {p.surface}; border: 1px solid {p.outline_variant};
    border-radius: 14px;
}}
QFrame#ClassCard:hover {{
    border: 1px solid {p.primary}; background: {card_hover_bg};
}}
QFrame#EmptyState {{
    background: {p.surface}; border: 2px dashed {p.outline_variant};
    border-radius: 14px;
}}
QScrollArea#HomeScroll {{ background: transparent; border: none; }}
QWidget#HomeCardsHost {{ background: transparent; }}

/* ============================================================ */
/*  Tabs                                                         */
/* ============================================================ */
QTabBar#CycleTabs::tab {{
    background: transparent; color: {p.on_surface_variant};
    padding: 8px 14px; margin-right: 4px;
    border: 1px solid transparent; border-bottom: none;
    border-top-left-radius: 10px; border-top-right-radius: 10px;
    font-weight: 700; min-width: 80px; max-width: 160px;
}}
QTabBar#CycleTabs::tab:selected {{
    background: {p.primary}; color: {p.on_primary};
}}
QTabBar#CycleTabs::tab:hover:!selected {{
    background: {p.surface_container_low}; color: {p.on_surface};
}}
QTabWidget::pane {{
    border: 1px solid {p.outline_variant}; border-radius: 12px;
    background: {p.surface}; top: -1px;
}}
QTabBar::tab {{
    background: transparent; color: {p.on_surface_variant};
    padding: 8px 16px; border: 1px solid transparent; font-weight: 600;
}}
QTabBar::tab:selected {{
    color: {p.primary}; border-bottom: 2px solid {p.primary};
}}
QTabBar::tab:hover:!selected {{ color: {p.on_surface}; }}

/* ============================================================ */
/*  Chips                                                        */
/* ============================================================ */
QLabel[chip="green"] {{
    background: {p.success_container}; color: {p.on_success_container};
    border-radius: 10px; padding: 4px 12px; font-weight: 700; font-size: 12px;
}}
QLabel[chip="red"] {{
    background: {p.danger_container}; color: {p.on_danger_container};
    border-radius: 10px; padding: 4px 12px; font-weight: 700; font-size: 12px;
}}
QLabel[chip="orange"] {{
    background: {p.warning_container}; color: {p.on_warning_container};
    border-radius: 10px; padding: 4px 12px; font-weight: 700; font-size: 12px;
}}
QLabel[chip="blue"] {{
    background: {p.info_container}; color: {p.on_info_container};
    border-radius: 10px; padding: 4px 12px; font-weight: 700; font-size: 12px;
}}
QLabel[chip="grey"] {{
    background: {p.surface_container_high}; color: {p.on_surface_variant};
    border-radius: 10px; padding: 4px 12px; font-weight: 700; font-size: 12px;
}}

/* ============================================================ */
/*  Tables                                                       */
/* ============================================================ */
QTableWidget, QTableView, QTreeView, QListView {{
    background: {p.surface};
    alternate-background-color: {p.surface_container_lowest};
    border: 1px solid {p.outline_variant}; border-radius: 12px;
    gridline-color: {p.outline_variant};
    selection-background-color: {p.primary_container};
    selection-color: {p.on_primary_container}; outline: 0;
}}
QTableWidget::item, QTableView::item, QTreeView::item {{
    padding: 6px 8px; border: none;
}}
QTableWidget::item:hover, QTableView::item:hover {{
    background: {with_alpha(p.primary, 0.06)};
}}
QHeaderView::section {{
    background: {p.surface_container_low}; color: {p.on_surface_variant};
    padding: 9px 10px; border: none;
    border-right: 1px solid {p.outline_variant};
    border-bottom: 1px solid {p.outline_variant};
    font-weight: 700; text-transform: uppercase; font-size: 13px;
    letter-spacing: 0.4px;
}}
QHeaderView::section:first {{ border-top-left-radius: 11px; }}
QHeaderView::section:last {{ border-right: none; border-top-right-radius: 11px; }}
QTableCornerButton::section {{
    background: {p.surface_container_low}; border: none;
    border-bottom: 1px solid {p.outline_variant};
    border-top-left-radius: 11px;
}}

/* ============================================================ */
/*  Dialogs                                                      */
/* ============================================================ */
QDialog, QMessageBox {{ background: {p.surface}; }}
QDialog#ModalDialog, QDialog[modal="true"] {{
    background: {p.surface_container_low};
}}
QGroupBox {{
    background: {p.surface}; border: 1px solid {p.outline_variant};
    border-radius: 12px; margin-top: 16px; padding: 12px;
    font-weight: 700; color: {p.on_surface};
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 12px; padding: 0 8px;
    background: {p.surface}; color: {p.on_surface};
}}
QRadioButton, QCheckBox {{
    spacing: 8px; color: {p.on_surface}; background: transparent;
}}
QRadioButton::indicator, QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 4px;
}}

/* ============================================================ */
/*  Scrollbars                                                   */
/* ============================================================ */
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 6px 4px 6px 2px;
}}
QScrollBar::handle:vertical {{
    background: {p.outline}; border-radius: 5px; min-height: 30px; border: none;
}}
QScrollBar::handle:vertical:hover {{ background: {p.on_surface_variant}; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px 6px;
}}
QScrollBar::handle:horizontal {{
    background: {p.outline}; border-radius: 5px; min-width: 30px; border: none;
}}
QScrollBar::handle:horizontal:hover {{ background: {p.on_surface_variant}; }}

/* ============================================================ */
/*  Toast                                                        */
/* ============================================================ */
QLabel#Toast {{
    background: {p.on_surface}; color: {p.surface};
    border-radius: 10px; padding: 12px 18px; font-weight: 600;
}}
QLabel#Toast[kind="success"] {{
    background: {p.success}; color: {p.on_success};
}}
QLabel#Toast[kind="error"] {{
    background: {p.danger}; color: {p.on_danger};
}}
QLabel#Toast[kind="warning"] {{
    background: {p.warning}; color: {p.on_warning};
}}
QLabel#Toast[kind="info"] {{
    background: {p.info}; color: {p.on_info};
}}

/* ============================================================ */
/*  Menu                                                         */
/* ============================================================ */
QMenuBar {{
    background: {p.toolbar_bg}; color: {p.on_surface};
    border-bottom: 1px solid {p.toolbar_border};
}}
QMenuBar::item {{
    background: transparent; padding: 6px 10px; border-radius: 6px;
}}
QMenuBar::item:selected {{ background: {p.surface_container_low}; }}
QMenu {{
    background: {p.surface}; color: {p.on_surface};
    border: 1px solid {p.outline_variant}; border-radius: 10px; padding: 6px;
}}
QMenu::item {{ padding: 8px 16px; border-radius: 6px; }}
QMenu::item:selected {{
    background: {p.primary_container}; color: {p.on_primary_container};
}}
QMenu::separator {{
    height: 1px; background: {p.outline_variant}; margin: 4px 8px;
}}

/* ============================================================ */
/*  Progress & Status bar                                        */
/* ============================================================ */
QProgressBar {{
    background: {p.surface_container_high}; border: none; border-radius: 6px;
    text-align: center; color: {p.on_surface_variant}; height: 10px;
}}
QProgressBar::chunk {{ background: {p.primary}; border-radius: 6px; }}
QStatusBar {{
    background: {p.surface}; color: {p.on_surface_variant};
    border-top: 1px solid {p.outline_variant};
}}
QFrame#ProgressOverlay {{
    background: {with_alpha(p.on_surface, 0.55)};
}}

/* ============================================================ */
/*  Sidebar                                                      */
/* ============================================================ */
QFrame#AppSidebar {{
    background: {p.sidebar_bg};
    border-right: 1px solid {p.outline_variant};
}}
QFrame#SidebarBrand {{
    background: transparent;
    border-bottom: 1px solid {p.outline_variant};
}}
QLabel[sidebar="brand"] {{
    color: {p.on_surface};
    font-size: 16px; font-weight: 800; letter-spacing: -0.3px;
    background: transparent;
}}
QFrame#SidebarNav {{
    background: transparent;
}}
QLabel[sidebar="section"] {{
    color: {p.on_surface_variant};
    font-size: 10px; font-weight: 800; letter-spacing: 1px;
    padding: 8px 10px 4px; text-transform: uppercase;
    background: transparent;
}}
QPushButton[sidebar="nav"] {{
    background: transparent; color: {p.on_surface_variant};
    border: none; border-radius: 8px; padding: 8px 12px;
    font-size: 13px; font-weight: 600; text-align: left;
}}
QPushButton[sidebar="nav"]:hover {{
    background: {p.sidebar_hover_bg}; color: {p.on_surface};
}}
QPushButton[sidebar="nav"][active="true"] {{
    background: {p.sidebar_active_bg}; color: {p.sidebar_active_text};
    font-weight: 700;
}}
QPushButton[sidebar="action"] {{
    background: transparent; color: {p.primary};
    border: 1px solid {p.outline_variant}; border-radius: 8px;
    padding: 8px 12px; font-size: 12px; font-weight: 700;
}}
QPushButton[sidebar="action"]:hover {{
    background: {p.primary_container}; border-color: {p.primary};
}}
QPushButton[sidebar="icon"] {{
    background: transparent; border: none; border-radius: 8px;
    color: {p.on_surface_variant};
}}
QPushButton[sidebar="icon"]:hover {{
    background: {p.sidebar_hover_bg}; color: {p.on_surface};
}}
QFrame[sidebar="sep"] {{
    background: {p.outline_variant}; border: none; margin: 4px 10px;
}}

/* ============================================================ */
/*  Export settings description                                  */
/* ============================================================ */
QLabel#ExportSettingsDesc {{
    color: {p.on_surface_variant}; font-size: 12px; margin-bottom: 8px;
}}
QLabel#ExportSettingsTitle {{
    font-size: 16px; font-weight: 700; padding: 8px 0;
}}

/* ============================================================ */
/*  SectionTitle (common.py)                                     */
/* ============================================================ */
QLabel#SectionTitle {{
    color: {p.on_surface_variant}; font-size: 12px;
    font-weight: 800; letter-spacing: 1.2px;
    text-transform: uppercase; padding: 6px 2px;
}}

/* ============================================================ */
/*  ClassCard accent variants (home_dashboard)                   */
/* ============================================================ */
QFrame#ClassCardAccent {{
    border: none;
}}
QFrame#ClassCard[cardAccent="college"] #ClassCardAccent {{
    background: {p.secondary};
}}
QFrame#ClassCard[cardAccent="lycee"] #ClassCardAccent {{
    background: {p.tertiary};
}}
QFrame#ClassCardHeader {{
    border: none; border-radius: 8px;
}}
QFrame#ClassCard[cardAccent="college"] #ClassCardHeader {{
    background: {p.secondary_container};
}}
QFrame#ClassCard[cardAccent="lycee"] #ClassCardHeader {{
    background: {p.tertiary_container};
}}
QLabel#ClassCardName {{
    background: transparent; font-weight: 700; letter-spacing: -0.2px;
}}
QFrame#ClassCard[cardAccent="college"] #ClassCardName {{
    color: {p.on_surface};
}}
QFrame#ClassCard[cardAccent="lycee"] #ClassCardName {{
    color: {p.on_surface};
}}
QLabel#ClassCardDiv {{
    background: {p.surface_container_low}; border-radius: 4px;
    padding: 4px 10px; font-size: 10px; font-weight: 700;
    letter-spacing: 0.8px; color: {p.on_surface_variant};
}}
QLabel#ClassCardPath {{
    color: {p.on_surface_variant}; font-size: 10px; background: transparent;
}}
QLabel#ClassCardSyncLabel {{
    color: {p.on_surface_variant}; font-size: 10px; font-weight: 600;
    letter-spacing: 0.3px; text-transform: uppercase; background: transparent;
}}
QLabel#ClassCardSyncValue {{
    color: {p.on_surface_variant}; font-size: 11px; background: transparent;
}}
QLabel#ClassCardStatValue {{
    background: transparent; font-weight: 700;
}}
QFrame#ClassCard[cardAccent="college"] #ClassCardStatValue {{
    color: {p.on_surface};
}}
QFrame#ClassCard[cardAccent="lycee"] #ClassCardStatValue {{
    color: {p.on_surface};
}}
QLabel#ClassCardStatLabel {{
    color: {p.on_surface_variant}; background: transparent; font-size: 10px;
}}
QFrame#ClassCardListStatBg {{
    background: {p.surface_container_lowest}; border: none; border-radius: 5px;
}}

/* ============================================================ */
/*  HomeTabs (tab navigation in dashboard)                       */
/* ============================================================ */
QTabWidget#HomeTabs::pane {{
    border: none; background: {p.background};
}}
QTabBar#HomeTabs::tab {{
    background: {p.surface}; color: {p.on_surface_variant};
    padding: 12px 28px; margin-right: 2px;
    border: none; font-weight: 700; font-size: 13px;
    border-top-left-radius: 8px; border-top-right-radius: 8px;
    border-bottom: 2px solid transparent;
}}
QTabBar#HomeTabs::tab:selected {{
    color: {p.primary}; border-bottom: 2px solid {p.primary};
    background: {p.background};
}}
QTabBar#HomeTabs::tab:hover:!selected {{
    color: {p.on_surface}; background: {p.surface_container_low};
}}
QWidget#ConfigInput {{
    background: {p.surface}; border: 1px solid {p.outline_variant};
    border-radius: 6px; padding: 6px 10px; font-size: 12px;
    color: {p.on_surface};
}}
QWidget#ConfigInput:focus {{
    border: 2px solid {p.primary}; padding: 5px 9px;
}}
QFrame#SubjectCard {{
    background: {p.surface_container}; border: 1px solid {p.outline_variant};
    border-radius: 10px; padding: 0;
}}
QFrame#SubjectCard:hover {{
    border-color: {p.primary}; background: {p.surface_container_high};
}}
QWidget#ConfigRow {{
    border-bottom: 1px solid {p.surface_container_high};
}}
QLabel#ConfigLabel {{
    color: {p.on_surface_variant}; font-size: 12px; font-weight: 600;
}}
QLabel#ConfigValue {{
    color: {p.on_surface}; font-weight: 500; font-size: 13px;
}}

/* ============================================================ */
/*  HomeHero / HomeToolbar / KpiHero                             */
/* ============================================================ */
QFrame#HomeHero {{
    background: {p.surface}; border: none;
    border-bottom: 1px solid {p.outline_variant};
}}
QFrame#HeroLogoBox {{
    border: none; border-radius: 12px;
    background: {p.primary};
}}
QLabel#HeroTitle {{
    color: {p.on_surface}; background: transparent;
    font-size: 20px; font-weight: 700; letter-spacing: -0.3px;
}}
QLabel#HeroSubtitle {{
    color: {p.on_surface_variant}; background: transparent;
    font-size: 13px; font-weight: 500;
}}
QFrame#HomeToolbar {{
    background: {p.surface}; border: none;
    border-bottom: 1px solid {p.outline_variant};
}}
QLineEdit#HomeSearch {{
    background: {p.surface_container_lowest}; color: {p.on_surface};
    border: 1px solid {p.outline_variant}; border-radius: 8px;
    padding: 8px 12px; font-size: 13px;
    selection-background-color: {p.primary_container};
}}
QLineEdit#HomeSearch:focus {{
    background: {p.surface_container_low}; border-color: {p.primary};
}}
QFrame#ViewToggleBox {{
    background: {p.surface_container_lowest}; border: none; border-radius: 6px;
}}
QToolButton#ViewToggleBtn {{
    background: transparent; border: 1px solid {p.outline_variant};
    border-radius: 5px; color: {p.on_surface_variant};
}}
QToolButton#ViewToggleBtn:checked {{
    background: {p.surface_container_low}; border: 1px solid {p.outline_variant};
    color: {p.primary};
}}
QToolButton#ViewToggleBtn:hover {{
    background: {p.surface_container_low}; color: {p.on_surface};
}}
QFrame#KpiHero {{
    background: {p.surface_container_lowest}; border: none; border-radius: 10px;
}}
QFrame#KpiIconBox {{
    border: none; border-radius: 8px;
}}
QFrame#KpiIconBox[kpiColor="primary"] {{ background: {p.primary_container}; }}
QFrame#KpiIconBox[kpiColor="secondary"] {{ background: {p.secondary_container}; }}
QFrame#KpiIconBox[kpiColor="tertiary"] {{ background: {p.tertiary_container}; }}
QFrame#KpiIconBox[kpiColor="success"] {{ background: {p.success_container}; }}
QLabel#KpiValue {{
    background: transparent; font-size: 20px; font-weight: 700;
    letter-spacing: -0.3px;
}}
QLabel#KpiLabel {{
    color: {p.on_surface_variant}; background: transparent;
    font-size: 11px; font-weight: 600; letter-spacing: 0.3px;
    text-transform: uppercase;
}}
QLabel#SectionHeader {{
    color: {p.on_surface}; background: transparent;
    font-size: 14px; font-weight: 700; letter-spacing: 0.2px;
    padding: 0 4px;
}}
QLabel#NoResults {{
    color: {p.on_surface_variant}; font-size: 13px; padding: 36px;
}}

/* ============================================================ */
/*  ClassCard buttons (accent-matched)                           */
/* ============================================================ */
QToolButton#ClassCardBtnSync {{
    border-radius: 6px; font-weight: 600; font-size: 12px;
    padding: 5px 12px; border: 1px solid {p.outline_variant};
}}
QFrame#ClassCard[cardAccent="college"] #ClassCardBtnSync {{
    background: {p.surface_container_low}; color: {p.on_surface_variant};
    border-color: {p.outline_variant};
}}
QFrame#ClassCard[cardAccent="college"] #ClassCardBtnSync:hover {{
    background: {p.surface_container}; color: {p.on_surface};
    border-color: {p.outline};
}}
QFrame#ClassCard[cardAccent="lycee"] #ClassCardBtnSync {{
    background: {p.surface_container_low}; color: {p.on_surface_variant};
    border-color: {p.outline_variant};
}}
QFrame#ClassCard[cardAccent="lycee"] #ClassCardBtnSync:hover {{
    background: {p.surface_container}; color: {p.on_surface};
    border-color: {p.outline};
}}
QPushButton#ClassCardBtnOpen {{
    border: none; border-radius: 6px; font-weight: 600; font-size: 13px;
    padding: 0 14px;
}}
QFrame#ClassCard[cardAccent="college"] #ClassCardBtnOpen {{
    background: {p.surface_container_low}; color: {p.on_surface_variant};
}}
QFrame#ClassCard[cardAccent="college"] #ClassCardBtnOpen:hover {{
    background: {p.surface_container}; color: {p.on_surface};
}}
QFrame#ClassCard[cardAccent="lycee"] #ClassCardBtnOpen {{
    background: {p.surface_container_low}; color: {p.on_surface_variant};
}}
QFrame#ClassCard[cardAccent="lycee"] #ClassCardBtnOpen:hover {{
    background: {p.surface_container}; color: {p.on_surface};
}}
QFrame#ClassCard[cardAccent="college"]:hover,
QFrame#ClassCard[cardAccent="college"]:focus {{
    border-color: {p.outline};
}}
QFrame#ClassCard[cardAccent="lycee"]:hover,
QFrame#ClassCard[cardAccent="lycee"]:focus {{
    border-color: {p.outline};
}}

/* ============================================================ */
/*  Backup & wipe dialogs                                        */
/* ============================================================ */
QLabel#BackupWarn {{
    color: {p.on_surface}; background: {p.surface_container_high};
    padding: 8px 12px; border-radius: 6px; font-size: 12px;
}}
QLabel#BackupNotes {{
    background: {p.surface_container_low}; padding: 10px;
    border-radius: 6px; font-size: 11px;
}}

/* ============================================================ */
/*  Import XLSX wizard                                           */
/* ============================================================ */
QLabel#WizardIntro,
QLabel#WizardSummary {{
    color: {p.on_surface_variant}; font-size: 12px;
}}
QLabel#WizardFileName {{
    color: {p.on_surface_variant};
}}

/* ============================================================ */
/*  Import preview                                               */
/* ============================================================ */
QLabel#PreviewWarn {{
    background: {p.warning_container}; border: 1px solid {p.warning};
    padding: 6px; border-radius: 4px; color: {p.on_warning_container};
}}
QLabel#PreviewSub {{
    color: {p.on_surface_variant}; font-size: 12px;
}}

/* ============================================================ */
/*  Sync report                                                  */
/* ============================================================ */
QLabel#SyncStatusTitle {{
    font-size: 16px; font-weight: 700;
}}
QLabel#SyncSubtitle {{
    color: {p.on_surface_variant};
}}

/* ============================================================ */
/*  Class wizard                                                 */
/* ============================================================ */
QLabel#WizardPageTitle {{
    font-size: 16px; font-weight: 700; color: {p.primary};
}}
QLabel#WizardPageSubtitle {{
    color: {p.on_surface_variant}; font-size: 12px;
}}
QFrame#WizardPreview {{
    background: {p.surface_container_low}; padding: 8px;
    border-radius: 4px;
}}

/* ============================================================ */
/*  ProgressOverlay inner label                                  */
/* ============================================================ */
QLabel#ProgressOverlayMsg {{
    color: {p.on_surface}; font-size: 14px; font-weight: 600;
    padding: 8px 16px;
}}

/* ============================================================ */
/*  Btn backup / wipe all (home toolbar actions)                 */
/* ============================================================ */
QPushButton#BtnBackup {{
    background: {p.surface_container_low}; color: {p.on_surface_variant};
    border: 1px solid {p.outline_variant}; border-radius: 8px;
}}
QPushButton#BtnBackup:hover {{
    background: {p.tertiary_container}; color: {p.on_tertiary_container};
    border: 1px solid {p.tertiary};
}}
QPushButton#BtnWipeAll {{
    background: {p.surface_container_low}; color: {p.on_surface_variant};
    border: 1px solid {p.outline_variant}; border-radius: 8px;
}}
QPushButton#BtnWipeAll:hover {{
    background: {p.danger_container}; color: {p.on_danger_container};
    border: 1px solid {p.danger};
}}

/* ============================================================ */
/*  Dashboard quick action buttons                               */
/* ============================================================ */
QPushButton#DashAction {{
    background: transparent; color: {p.primary};
    border: 1px solid {p.outline}; border-radius: 8px;
    font-size: 13px; font-weight: 600; padding: 6px 14px;
    text-align: left;
}}
QPushButton#DashAction:hover {{
    background: {p.primary_container}; border-color: {p.primary_hover};
}}
QPushButton#DashAction:pressed {{
    background: {p.primary_container};
}}

/* ============================================================ */
/*  Breadcrumb separator                                        */
/* ============================================================ */
QLabel#BreadcrumbSep {{
    color: {p.on_surface_variant}; font-size: 14px; font-weight: 700; padding: 0 6px;
}}

/* ============================================================ */
/*  StatCard accent colors (by statKind property)               */
/* ============================================================ */
QFrame#Card[statKind="primary"] QLabel#CardValue {{ color: {p.primary}; }}
QFrame#Card[statKind="secondary"] QLabel#CardValue {{ color: {p.secondary}; }}
QFrame#Card[statKind="tertiary"] QLabel#CardValue {{ color: {p.tertiary}; }}
QFrame#Card[statKind="success"] QLabel#CardValue {{ color: {p.success}; }}
"""


# ---------------------------------------------------------------------------
# Active theme
# ---------------------------------------------------------------------------


_active: Palette = LIGHT


def current() -> Palette:
    """Return the currently active palette."""
    return _active


def set_active(palette: Palette) -> None:
    """Update the active palette (call before :func:`apply`)."""
    global _active
    _active = palette


def apply(palette: Optional[Palette] = None) -> None:
    """Apply the active palette as a global QSS stylesheet and QPalette."""
    global _active
    p = palette or _active
    _active = p
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(qss_for(p))
        app.setPalette(_to_qpalette(p))
        # Force tous les widgets à ré-évaluer leur palette (nécessaire
        # pour les stylesheets de widgets individuels qui utilisent
        # ``palette(...)`` — sinon Qt ne les met pas à jour).
        for w in app.allWidgets():
            w.style().unpolish(w)
            w.style().polish(w)


def _to_qpalette(p: Palette) -> QPalette:
    """Construit un QPalette standard à partir d'une Palette Material 3.

    Cela permet aux sélecteurs QSS ``palette(...)`` (rôles Qt classiques)
    de renvoyer des couleurs correctes dans les deux thèmes.
    """
    from qtpy.QtGui import QPalette, QColor
    qp = QPalette()
    qp.setColor(QPalette.ColorRole.Window, QColor(p.surface))
    qp.setColor(QPalette.ColorRole.WindowText, QColor(p.on_surface))
    qp.setColor(QPalette.ColorRole.Base, QColor(p.surface_container))
    qp.setColor(QPalette.ColorRole.AlternateBase, QColor(p.surface_container_high))
    qp.setColor(QPalette.ColorRole.Text, QColor(p.on_surface))
    qp.setColor(QPalette.ColorRole.Button, QColor(p.surface_container))
    qp.setColor(QPalette.ColorRole.ButtonText, QColor(p.on_surface))
    qp.setColor(QPalette.ColorRole.PlaceholderText, QColor(p.on_surface_variant))
    qp.setColor(QPalette.ColorRole.Highlight, QColor(p.primary))
    qp.setColor(QPalette.ColorRole.HighlightedText, QColor(p.on_primary))
    qp.setColor(QPalette.ColorRole.ToolTipBase, QColor(p.surface_container_high))
    qp.setColor(QPalette.ColorRole.ToolTipText, QColor(p.on_surface))
    qp.setColor(QPalette.ColorRole.Shadow, QColor(p.on_surface))
    qp.setColor(QPalette.ColorRole.Dark, QColor(p.surface_container_high))
    qp.setColor(QPalette.ColorRole.Mid, QColor(p.outline_variant))
    qp.setColor(QPalette.ColorRole.Midlight, QColor(p.surface_container_low))
    qp.setColor(QPalette.ColorRole.Light, QColor(p.surface_bright))
    return qp


def cycle_palette() -> Palette:
    """Switch between LIGHT and DARK. Returns the new active palette."""
    p = DARK if _active.name == "light" else LIGHT
    apply(p)
    return p
