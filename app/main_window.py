"""Fenetre principale — refonte premium avec sidebar latérale.

Architecture : QStackedWidget central 
- page 0 : HomeDashboardWidget (tableau de bord)
- page 1 : ClassView (breadcrumb + QTabWidget)
Sidebar à gauche pour la navigation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import qtawesome as qta
from qtpy.QtCore import QSize, Qt
from qtpy.QtGui import QAction
from qtpy.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .workspace import discover_class, discover_classes
from . import theme
from .db import Database, discover_class_by_db_path
from .screen_utils import get_scale
from .widgets.backup_dialog import BackupManagerDialog
from .widgets.class_switcher import ClassSwitcher
from .widgets.common import (
    Breadcrumb,
    ProgressOverlay,
    set_kind,
    show_toast,
)
from .widgets.compte_rendu import CompteRenduWidget
from .widgets.config import ConfigWidget
from .widgets.dashboard import DashboardWidget
from .widgets.export_settings import show_export_settings_dialog
from .widgets.grades import SubjectGradesWidget
from .widgets.home_dashboard import HomeDashboardWidget
from .widgets.moyennes import MoyennesWidget
from .widgets.sidebar import Sidebar
from .widgets.students import StudentsWidget
from .widgets.sync_report import SyncReportDialog
from .widgets.totalisation import TotalisationWidget

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Fenetre principale.

    Layout:
    ┌──────────────────────────────────────────────────┐
    │ MenuBar                                          │
    ├──────────┬───────────────────────────────────────┤
    │          │ CompactToolBar (switcher + actions)    │
    │ SIDEBAR  ├───────────────────────────────────────┤
    │          │ QStackedWidget:                       │
    │  220px   │  [0] HomeDashboard                    │
    │          │  [1] ClassView:                       │
    │          │    ├ Breadcrumb                       │
    │          │    └ QTabWidget (tabs)                │
    ├──────────┴───────────────────────────────────────┤
    │ StatusBar                                        │
    └──────────────────────────────────────────────────┘
    """

    def __init__(self, db: Optional[Database] = None) -> None:
        super().__init__()
        self.db = db
        self._scale = get_scale()
        self.setWindowTitle("Bulletin")
        self.setMinimumSize(*self._scale.min_window_size)

        # Conteneur racine : sidebar + stacked central
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar(self)
        self.sidebar.homeRequested.connect(self._show_home)
        self.sidebar.classRequested.connect(self._on_sidebar_class_clicked)
        self.sidebar.themeToggleRequested.connect(self._action_toggle_theme)
        self.sidebar.settingsRequested.connect(
            lambda: show_export_settings_dialog(self, self.db)
        )
        self.sidebar.newClassRequested.connect(self._action_new_class)
        self.sidebar.setVisible(False)  # cachée au démarrage
        self.sidebar.setFixedWidth(self._scale.sidebar_width)
        root_layout.addWidget(self.sidebar)

        # Colonne de droite : toolbar + stacked
        right_col = QWidget()
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Toolbar compacte
        self._build_compact_toolbar(right_layout)

        # Stacked widget central
        self._stack = QStackedWidget()
        right_layout.addWidget(self._stack, 1)

        # Page 0 : HomeDashboard
        self.home_dashboard = HomeDashboardWidget(self.db, self)
        self.home_dashboard.classSelected.connect(self._on_class_card_clicked)
        self.home_dashboard.newClassRequested.connect(self._action_new_class)
        self.home_dashboard.refreshRequested.connect(self._on_home_refresh_requested)
        self.home_dashboard.syncRequested.connect(self._on_home_sync_requested)
        self.home_dashboard.importXlsxRequested.connect(
            self._action_import_xlsx_from_home
        )
        self.home_dashboard.backupManagerRequested.connect(
            self._action_open_backup_manager
        )
        self.home_dashboard.fullResetRequested.connect(
            self._action_full_reset_from_home
        )
        self._stack.addWidget(self.home_dashboard)  # index 0

        # Page 1 : ClassView (breadcrumb + tabs)
        self._build_class_view()
        self._stack.addWidget(self._class_view)  # index 1

        root_layout.addWidget(right_col, 1)
        self.setCentralWidget(root)

        # Menu bar
        self._build_menubar()

        # Status bar
        self.setStatusBar(QStatusBar())
        self.lbl_status = QLabel("Prêt")
        self.lbl_status.setObjectName("StatusLabel")
        self.statusBar().addPermanentWidget(self.lbl_status)

        # Remplit la sidebar avec les classes découvertes
        self._refresh_sidebar_classes()

    # ------------------------------------------------------------------
    # Méthodes builders
    # ------------------------------------------------------------------
    def _build_compact_toolbar(self, parent_layout: QVBoxLayout) -> None:
        """Barre d'outils compacte au-dessus du stacked widget."""
        tb = QWidget()
        tb.setObjectName("CompactToolbar")
        tb.setFixedHeight(48)
        lay = QHBoxLayout(tb)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(8)

        self._btn_menu = QPushButton(qta.icon("fa5s.bars"), "")
        self._btn_menu.setToolTip("Afficher/masquer la sidebar")
        self._btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_menu.setFixedSize(34, 34)
        self._btn_menu.clicked.connect(self._toggle_sidebar)
        lay.addWidget(self._btn_menu)

        self.class_switcher = ClassSwitcher(self)
        self.class_switcher.classChanged.connect(self._on_class_changed)
        self.class_switcher.setMaximumWidth(self._scale.switcher_width)

        lay.addStretch(1)

        self._btn_import = QPushButton(
            qta.icon("fa5s.file-import"), " Importer"
        )
        set_kind(self._btn_import, "tonal")
        self._btn_import.setToolTip(
            "Importer une liste d'élèves (multi-classes)"
        )
        self._btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_import.setMinimumHeight(32)
        self._btn_import.clicked.connect(self._action_import_xlsx_from_home)
        lay.addWidget(self._btn_import)

        self._btn_sync = QPushButton(
            qta.icon("fa5s.cloud-download-alt"), " Synchroniser"
        )
        set_kind(self._btn_sync, "tonal")
        self._btn_sync.setToolTip(
            "Synchroniser les notes depuis les fichiers"
        )
        self._btn_sync.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_sync.setMinimumHeight(32)
        self._btn_sync.clicked.connect(lambda: self._action_sync(silent=False))
        lay.addWidget(self._btn_sync)

        self._btn_export = QPushButton(
            qta.icon("fa5s.file-export"), " Export matiere"
        )
        set_kind(self._btn_export, "tonal")
        self._btn_export.setToolTip("Exporter les feuilles des professeurs")
        self._btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_export.setMinimumHeight(32)
        self._btn_export.clicked.connect(self._action_export_profs)
        lay.addWidget(self._btn_export)

        self._btn_export_all = QPushButton(
            qta.icon("fa5s.file-download"), " Exporter tout"
        )
        set_kind(self._btn_export_all, "filled")
        self._btn_export_all.setToolTip(
            "Exporter matières, totaux, moyennes et compte rendu"
        )
        self._btn_export_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_export_all.setMinimumHeight(32)
        self._btn_export_all.clicked.connect(self._action_export_all_results)
        lay.addWidget(self._btn_export_all)



        parent_layout.addWidget(tb)

    def _build_class_view(self) -> None:
        """Construit la ClassView : breadcrumb + QTabWidget."""
        self._class_view = QWidget()

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setMovable(False)
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(False)
        self.tabs.setIconSize(QSize(18, 18))
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabBar().setObjectName("CycleTabs")
        self.tabs.tabBar().setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.tabBar().setExpanding(False)

        self.subject_tabs: dict[int, SubjectGradesWidget] = {}

        self.breadcrumb = Breadcrumb()
        self.breadcrumb.segmentClicked.connect(self._on_breadcrumb_clicked)

        self._build_class_tabs()

        cv_layout = QVBoxLayout(self._class_view)
        cv_layout.setContentsMargins(0, 0, 0, 0)
        cv_layout.setSpacing(0)
        cv_layout.addWidget(self.breadcrumb)
        cv_layout.addWidget(self.tabs, 1)

        self.tabs.currentChanged.connect(self._on_tab_changed_breadcrumb)

    def _build_menubar(self) -> None:
        mb = self.menuBar()

        m_file = mb.addMenu("&Fichier")
        act_new = QAction(qta.icon("fa5s.plus"), "Nouvelle classe…", self)
        act_new.setShortcut("Ctrl+N")
        act_new.triggered.connect(self._action_new_class)
        m_file.addAction(act_new)

        act_sync = QAction(
            qta.icon("fa5s.cloud-download-alt"), "Synchroniser", self
        )
        act_sync.setShortcut("Ctrl+R")
        act_sync.triggered.connect(lambda: self._action_sync(silent=False))
        m_file.addAction(act_sync)

        m_file.addSeparator()

        act_import = QAction(
            qta.icon("fa5s.file-import"), "Importer des élèves…", self
        )
        act_import.setShortcut("Ctrl+I")
        act_import.triggered.connect(self._action_import_xlsx_from_home)
        m_file.addAction(act_import)

        m_file.addSeparator()

        act_export = QAction(
            qta.icon("fa5s.file-export"), "Export matiere", self
        )
        act_export.setShortcut("Ctrl+E")
        act_export.triggered.connect(self._action_export_profs)
        m_file.addAction(act_export)

        act_export_all = QAction(
            qta.icon("fa5s.file-download"), "Exporter tout (matières + résultats)…", self
        )
        act_export_all.setShortcut("Ctrl+Shift+E")
        act_export_all.triggered.connect(self._action_export_all_results)
        m_file.addAction(act_export_all)

        m_file.addSeparator()

        act_quit = QAction("Quitter", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_tools = mb.addMenu("&Outils")
        act_params = QAction(
            qta.icon("fa5s.cog"), "Paramètres d'exportation…", self
        )
        act_params.triggered.connect(
            lambda: show_export_settings_dialog(self, self.db)
        )
        m_tools.addAction(act_params)

        act_backup = QAction(
            qta.icon("fa5s.database"), "Gestion des sauvegardes…", self
        )
        act_backup.triggered.connect(self._action_open_backup_manager)
        m_tools.addAction(act_backup)

        act_sync_params = QAction(
            qta.icon("fa5s.cog"), "Paramètres de synchronisation…", self
        )
        act_sync_params.triggered.connect(self._action_sync_settings)
        m_tools.addAction(act_sync_params)

        m_tools.addSeparator()

        act_reset = QAction(
            qta.icon("fa5s.broom"), "Réinitialiser la classe…", self
        )
        act_reset.triggered.connect(self._action_reset)
        m_tools.addAction(act_reset)

        m_view = mb.addMenu("&Affichage")
        act_theme = QAction(
            qta.icon("fa5s.moon"), "Mode sombre/clair", self
        )
        act_theme.setShortcut("Ctrl+T")
        act_theme.triggered.connect(self._action_toggle_theme)
        m_view.addAction(act_theme)

        m_help = mb.addMenu("&Aide")
        act_about = QAction("À propos…", self)
        act_about.triggered.connect(self._about)
        m_help.addAction(act_about)

        act_save = QAction(qta.icon("fa5s.save"), "Enregistrer", self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self._action_save)
        m_file.addAction(act_save)

        act_search = QAction(qta.icon("fa5s.search"), "Rechercher", self)
        act_search.setShortcut("Ctrl+F")
        act_search.triggered.connect(self._action_search)
        m_file.addAction(act_search)

    # ------------------------------------------------------------------
    # Sidebar / Navigation
    # ------------------------------------------------------------------
    def _toggle_sidebar(self) -> None:
        visible = not self.sidebar.isVisible()
        self.sidebar.setVisible(visible)

    def _refresh_sidebar_classes(self) -> None:
        classes = discover_classes()
        names = [c.name for c in classes]
        active = ""
        if self.db and self.db.path:
            cls = discover_class_by_db_path(self.db.path)
            if cls:
                active = cls.name
        self.sidebar.set_classes(names, active_class=active)

    def _on_sidebar_class_clicked(self, class_name: str) -> None:
        current = self.class_switcher.current_class_name() if hasattr(self, 'class_switcher') else None
        if current == class_name:
            self._show_class_view()
            return
        self._on_class_changed(class_name)

    def _show_home(self) -> None:
        self._stack.setCurrentIndex(0)
        # Reset DB to neutral when going home
        if self.db is not None and self.db.path:
            try:
                self.db.close()
            except Exception:
                pass
        self.db = Database(None)
        self.home_dashboard.set_db(self.db)
        self.home_dashboard.refresh()
        # Reset class selection
        if hasattr(self, 'class_switcher'):
            self.class_switcher.clear_selection()
        self._refresh_sidebar_classes()
        self.setWindowTitle("Bulletin — Accueil")
        self.lbl_status.setText("Accueil — toutes les classes")

    def _show_class_view(self) -> None:
        if self._stack.currentIndex() != 1:
            self._stack.setCurrentIndex(1)

    # ------------------------------------------------------------------
    # Breadcrumb
    # ------------------------------------------------------------------
    def _on_tab_changed_breadcrumb(self, idx: int) -> None:
        tab_name = self.tabs.tabText(idx) or ""
        classe = self.db.get_setting("classe", "")
        self.breadcrumb.set_segments(
            ["Accueil", classe or "Classe", tab_name or "—"],
            current=2,
        )

    def _on_breadcrumb_clicked(self, idx: int) -> None:
        if idx == 0:
            self._show_home()

    # ------------------------------------------------------------------
    # Class tabs building
    # ------------------------------------------------------------------
    def _build_class_tabs(self) -> None:
        """Construit/reconstruit les onglets de la classe active."""
        from .models import load_subjects

        # Vider les onglets existants
        while self.tabs.count():
            w = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if w:
                w.deleteLater()
        self.subject_tabs.clear()

        if self.db is None or not self.db.path:
            return

        # Onglet 0 : Dashboard
        self.dashboard = DashboardWidget(self.db, self)
        self.tabs.addTab(
            self.dashboard,
            qta.icon("fa5s.th-large"),
            "Tableau de bord",
        )

        # Onglet 1 : Configuration
        self.config = ConfigWidget(self.db)
        self.config.changed.connect(self._on_config_changed)
        self.tabs.addTab(
            self.config,
            qta.icon("fa5s.cog"),
            "Configuration",
        )

        # Onglet 2 : Élèves
        self.students = StudentsWidget(self.db)
        self.tabs.addTab(
            self.students,
            qta.icon("fa5s.users"),
            "Élèves",
        )

        # Onglets dynamiques : une matière = un onglet Notes
        subjects = load_subjects(self.db)
        for s in subjects:
            w = SubjectGradesWidget(self.db, s, self)
            self.subject_tabs[s.id] = w
            ico = "fa5s.pencil-alt"
            self.tabs.addTab(
                w, qta.icon(ico), s.name,
            )

        # Avant-dernier : Totalisation
        self.totalisation = TotalisationWidget(self.db)
        self.tabs.addTab(
            self.totalisation,
            qta.icon("fa5s.table"),
            "Totaux",
        )

        # Avant-avant-dernier : Moyennes
        self.moyennes = MoyennesWidget(self.db)
        self.tabs.addTab(
            self.moyennes,
            qta.icon("fa5s.chart-bar"),
            "Moyennes",
        )

        # Dernier : Compte Rendu
        self.cr = CompteRenduWidget(self.db)
        self.tabs.addTab(
            self.cr,
            qta.icon("fa5s.file-alt"),
            "Compte Rendu",
        )

        # Met à jour le breadcrumb
        self._on_tab_changed_breadcrumb(self.tabs.currentIndex())

    # ------------------------------------------------------------------
    # Navigation logique
    # ------------------------------------------------------------------
    def go_to_tab(self, name: str) -> None:
        n = self.tabs.count()
        mapping = {
            "dashboard": 0,
            "config": 1,
            "students": 2,
            "totalisation": n - 3,
            "moyennes": n - 2,
            "compte_rendu": n - 1,
        }
        if name in mapping:
            idx = max(0, min(mapping[name], n - 1))
            self.tabs.setCurrentIndex(idx)
            return
        if name.startswith("subject:"):
            try:
                sid = int(name.split(":", 1)[1])
            except ValueError:
                return
            w = self.subject_tabs.get(sid)
            if w is not None:
                idx = self.tabs.indexOf(w)
                if idx >= 0:
                    self.tabs.setCurrentIndex(idx)

    def _refresh_calc_tabs(self) -> None:
        for attr in ("totalisation", "moyennes", "cr"):
            w = getattr(self, attr, None)
            if w is not None and hasattr(w, "refresh"):
                try:
                    w.refresh()
                except Exception:
                    log.exception("refresh %s failed", attr)

    # ------------------------------------------------------------------
    # Changement de classe
    # ------------------------------------------------------------------
    def _on_class_changed(self, class_name: str) -> None:
        info = discover_class(class_name)
        if info is None:
            QMessageBox.warning(
                self, "Classe introuvable",
                f"La classe « {class_name} » n'a pas été trouvée.",
            )
            return
        new_db = Database(str(info.db_path))
        self._swap_database(new_db)
        self.lbl_status.setText(
            f"Classe active : {info.display_name}  ({info.division})"
        )
        log.info("Switched to class %s (%s)", class_name, info.db_path)
        show_toast(self, f"Classe : {info.display_name}", kind="info")
        if self._stack.currentIndex() != 1:
            self._show_class_view()
        else:
            self.setWindowTitle(
                f"Bulletin — {info.display_name}"
            )
        self._refresh_sidebar_classes()

        if info.subject_files:
            try:
                self._action_sync(silent=True)
            except Exception:
                log.exception("Auto-sync failed on class switch")

    def _on_class_card_clicked(self, class_name: str) -> None:
        current = self.class_switcher.current_class_name() if hasattr(self, 'class_switcher') else None
        if current == class_name:
            self._show_class_view()
            return
        self._on_class_changed(class_name)

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------
    def _action_sync(self, silent: bool = False) -> None:
        from .sync import sync_all_subjects, SyncReport

        cls = discover_class_by_db_path(self.db.path)
        if cls is None:
            # Accueil → synchroniser toutes les classes
            from .workspace import discover_classes, get_global_config

            global_export_dir = get_global_config("export_profs_global_path", "")

            all_classes = discover_classes()
            if not all_classes:
                show_toast(self, "Aucune classe trouvée.", "info")
                return

            global_reports: list[SyncReport] = []
            for info in all_classes:
                db = Database(str(info.db_path))
                # Cherche les fichiers dans export prof/<division>/<classe>/
                extra = None
                if global_export_dir:
                    div_name = "College" if info.division == "COLLEGE" else "Lycée" if info.division == "LYCEE" else "Primaire"
                    class_dir = Path(global_export_dir) / "export prof" / div_name / info.name
                    if class_dir.is_dir():
                        extra = class_dir
                try:
                    report = sync_all_subjects(db, info, extra_dir=extra)
                    global_reports.append(report)
                except Exception as exc:
                    log.exception("Sync failed for %s", info.name)
                finally:
                    db.close()

            total_added = sum(r.total_added for r in global_reports)
            total_updated = sum(r.total_updated for r in global_reports)
            total_unchanged = sum(r.total_unchanged for r in global_reports)
            self.lbl_status.setText(
                f"Synchro globale : +{total_added} ~{total_updated} "
                f"={total_unchanged} — {len(global_reports)} classe(s)"
            )
            self.home_dashboard.refresh()
            if not silent and global_reports:
                for r in global_reports:
                    total_added2 = r.total_added
                    total_updated2 = r.total_updated
                    total_unchanged2 = r.total_unchanged
                    show_toast(
                        self,
                        f"Sync {r.class_name} : +{total_added2} ~{total_updated2} ={total_unchanged2}",
                        "success",
                    )
            return

        extra = None
        saved = self.db.get_setting("export_profs_path", "").strip()
        if saved:
            extra = Path(saved) / "Bulletin" / "Feuilles Profs"
            if not extra.is_dir():
                extra = Path(saved)
        else:
            # Cherche dans le dossier d'export global
            from .workspace import get_global_config
            global_export_dir = get_global_config("export_profs_global_path", "")
            if global_export_dir:
                div_name = "College" if cls.division == "COLLEGE" else "Lycée" if cls.division == "LYCEE" else "Primaire"
                class_dir = Path(global_export_dir) / "export prof" / div_name / cls.name
                if class_dir.is_dir():
                    extra = class_dir

        if not cls.subject_files and (extra is None or not extra.is_dir()):
            show_toast(self, "Aucun fichier trouvé pour la synchronisation.", "info")
            return

        overlay = ProgressOverlay(
            self.centralWidget(),
            f"Synchronisation de {cls.display_name}…",
        )
        overlay.resize(self.centralWidget().size())
        overlay.start()

        try:
            report = sync_all_subjects(self.db, cls, extra_dir=extra)
        except Exception as exc:
            log.exception("Sync failed")
            overlay.stop()
            show_toast(self, f"Sync échouée : {exc}", "error")
            return
        finally:
            overlay.stop()

        self._refresh_calc_tabs()
        for w in self.subject_tabs.values():
            w.refresh()
        if hasattr(self, "dashboard"):
            self.dashboard.refresh()
        if hasattr(self, "home_dashboard"):
            self.home_dashboard.refresh()

        if silent:
            self.lbl_status.setText(
                f"Synchro {cls.display_name} : "
                f"+{report.total_added} ~{report.total_updated} "
                f"={report.total_unchanged} — {report.duration_seconds:.1f}s"
            )
            return

        dlg = SyncReportDialog(report, str(cls.folder), self)
        dlg.exec()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _action_new_class(self) -> None:
        from .wizards.class_wizard import run_wizard
        draft = run_wizard(self)
        if draft is None:
            return
        classes = discover_classes()
        if classes:
            if hasattr(self, 'class_switcher'):
                self.class_switcher.refresh()
            self._on_class_changed(classes[-1].name)
        self.home_dashboard.refresh()
        self._refresh_sidebar_classes()
        show_toast(self, "Nouvelle classe créée", kind="success")

    def _action_reset(self) -> None:
        if QMessageBox.question(
            self, "Tout effacer",
            "SUPPRESSION TOTALE DE L'ESPACE DE TRAVAIL\n\n"
            "Cela va SUPPRIMER DÉFINITIVEMENT :\n"
            "- Toutes les classes (élèves, notes, matières, paramètres)\n"
            "- Tous les fichiers de saisie\n"
            "- Tous les bulletins générés\n\n"
            "Les dossiers vides seront conservés.\n"
            "Une sauvegarde de sécurité sera créée automatiquement.\n\n"
            "Continuer ?",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db.create_backup(prefix="before_wipe_all")
        except Exception:
            pass
        from .workspace import delete_all_classes
        delete_all_classes()
        self._show_home()
        self.lbl_status.setText("Espace de travail réinitialisé — toutes les classes supprimées.")
        show_toast(self, "Toutes les classes ont été supprimées", kind="warning")

    def _action_toggle_theme(self) -> None:
        p = theme.cycle_palette()
        is_dark = theme.is_dark(p)
        self.sidebar.set_theme_icon(is_dark)
        icon = "fa5s.sun" if is_dark else "fa5s.moon"

    def _on_home_refresh_requested(self) -> None:
        previous = self.class_switcher.current_class_name() if hasattr(self, 'class_switcher') else None
        if hasattr(self, 'class_switcher'):
            self.class_switcher.refresh()
        if previous and hasattr(self, 'class_switcher'):
            self.class_switcher.select_class_silent(previous)
        self._refresh_sidebar_classes()
        self.lbl_status.setText("Liste des classes rafraîchie.")
        show_toast(self, "Liste des classes rafraîchie", kind="info")

    def _on_home_sync_requested(self, class_name: str) -> None:
        info = discover_class(class_name)
        if info is None:
            return
        current = self.class_switcher.current_class_name() if hasattr(self, 'class_switcher') else None
        if current != class_name:
            self._on_class_changed(class_name)
        else:
            self._action_sync(silent=False)

    # -- Export Profs --
    def _export_class_profs(
        self, db: Database, class_info: "ClassInfo",
        out_dir: Path | None = None,
    ) -> int:
        """Exporte les feuilles profs d'une seule classe.

        Si ``out_dir`` est fourni, il est utilisé comme destination
        (mode global). Sinon, utilise le dossier configuré dans la DB
        de la classe.

        Retourne le nombre de feuilles exportées.
        """
        from .models import load_subjects, load_students
        from .widgets.export_settings import ensure_export_dir

        subjects = load_subjects(db)
        students = load_students(db)
        if not subjects:
            return 0

        if out_dir is None:
            out_dir = ensure_export_dir(db, "export_profs_path")
        else:
            # Mode global : export prof/<division>/<classe>/
            div_name = "College" if class_info.division == "COLLEGE" else "Lycée" if class_info.division == "LYCEE" else "Primaire"
            out_dir = out_dir / "export prof" / div_name / class_info.name
        try:
            import openpyxl
            from openpyxl.styles import Alignment, Font, PatternFill
        except ImportError:
            return 0

        etab = db.get_setting("etablissement", "")
        classe = db.get_setting("classe", class_info.display_name)
        annee = db.get_setting("annee_scolaire", "")
        nb_ex = int(db.get_setting("nb_examens", "6") or 6)

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="4F46E5")

        exported = 0
        for s in subjects:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = s.name[:31]

            ws["B2"] = etab
            ws["B2"].font = Font(bold=True, size=14)
            ws["E2"] = f"Matière : {s.name}"
            ws["E2"].font = Font(bold=True, size=12)
            ws["B3"] = f"Classe : {classe}"
            ws["C3"] = f"Coef : {s.coeff:g}"
            ws["F3"] = f"Prof : {s.teacher or '—'}"
            ws["B4"] = f"Année scolaire : {annee}"
            ws["B4"].font = Font(italic=True, color="666666")

            headers = ["N°", "Nom et Prénoms"]
            for n in range(1, nb_ex + 1):
                from .widgets.table_helpers import label_for_exam
                label, _ = label_for_exam(n)
                headers.append(label)
            for c, h in enumerate(headers, 1):
                cell = ws.cell(row=6, column=c, value=h)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")

            for r, st in enumerate(students, 7):
                ws.cell(row=r, column=1, value=st.num)
                ws.cell(row=r, column=2, value=st.full_name)
                for n in range(1, nb_ex + 1):
                    v = db.get_grade(st.id, s.id, n)
                    if v is not None:
                        ws.cell(row=r, column=2 + n, value=v)

            ws.column_dimensions["A"].width = 5
            ws.column_dimensions["B"].width = 30
            for n in range(1, nb_ex + 1):
                col_letter = openpyxl.utils.get_column_letter(2 + n)
                ws.column_dimensions[col_letter].width = 12

            safe_name = "".join(
                c if c.isalnum() or c in " -_." else "_"
                for c in s.name
            ).strip()
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{safe_name}.xlsx"
            wb.save(out_path)
            exported += 1

        return exported

    def _action_export_profs(self) -> None:
        cls = discover_class_by_db_path(self.db.path)

        if cls is None:
            # Accueil → exporter toutes les classes
            from .workspace import discover_classes, get_global_config, set_global_config
            from qtpy.QtWidgets import QFileDialog

            saved = get_global_config("export_profs_global_path", str(Path.home()))
            chosen = QFileDialog.getExistingDirectory(
                self,
                "Dossier de destination pour l'export global",
                saved,
            )
            if not chosen:
                return
            export_dir = chosen
            set_global_config("export_profs_global_path", export_dir)

            all_classes = discover_classes()
            if not all_classes:
                show_toast(self, "Aucune classe trouvée.", "info")
                return

            out_path = Path(export_dir)
            total = 0
            per_class: list[str] = []
            for info in all_classes:
                db = Database(str(info.db_path))
                try:
                    n = self._export_class_profs(db, info, out_dir=out_path)
                    total += n
                    per_class.append(f"  {info.display_name} : {n} feuille(s)")
                except Exception as exc:
                    log.exception("Export failed for %s", info.name)
                    per_class.append(f"  {info.display_name} : erreur — {exc}")
                finally:
                    db.close()

            msg = (
                f"Export global terminé : {total} feuille(s)\n\n"
                + f"Dossier : {export_dir}\n\n"
                + "\n".join(per_class)
            )
            self.lbl_status.setText(f"Exportation des professeurs globale : {total} feuilles")
            show_toast(self, f"{total} feuille(s) exportée(s)", kind="success")
            return

        from .widgets.export_settings import ensure_export_dir
        from qtpy.QtWidgets import QFileDialog

        saved_dir = ensure_export_dir(self.db, "export_profs_path")
        folder = QFileDialog.getExistingDirectory(
            self, "Dossier de destination pour l'export", str(saved_dir),
        )
        if not folder:
            return
        n = self._export_class_profs(self.db, cls, out_dir=Path(folder))
        if n == 0:
            show_toast(self, "Aucune matière configurée.", "info")
            return
        self.lbl_status.setText(f"Export profs : {n} feuilles")
        show_toast(self, f"{n} feuille(s) exportée(s) dans {folder}", kind="success")

    # -- Export All Results --
    def _export_class_all_results(
        self, db: Database, class_info: "ClassInfo", base_dir: Path,
    ) -> int:
        """Exporte totaux, moyennes et compte rendu d'une classe.

        Structure créée :
            <base_dir>/<ClassName>/
                Matieres/
                    Anglais.xlsx, Français.xlsx …
                Totalisation/
                    totalisation1.xlsx … totalisation6.xlsx
                Moyennes/
                    Moyenne_T1.xlsx, Moyenne_T2.xlsx, Moyenne_T3.xlsx
                    Moyenne_Annuelle.xlsx
                Compte_Rendu/
                    compte_rendu_trimestres.pdf

        Retourne le nombre de fichiers exportés.
        """
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill

        from .models import (
            compute_annuelle,
            compute_stats,
            compute_totalisation,
            compute_trimestre,
            load_subjects,
        )
        from .widgets.table_helpers import fmt_value, label_for_exam

        subjects = load_subjects(db)
        students_raw = db.list_students()
        if not subjects or not students_raw:
            return 0

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="4F46E5")
        title_font = Font(bold=True, size=14)

        etab = db.get_setting("etablissement", "")
        classe = db.get_setting("classe", class_info.display_name)
        annee = db.get_setting("annee_scolaire", "")

        class_dir = base_dir / class_info.name
        exported = 0

        # ── Matières (feuilles profs) ──────────────────────────────
        mat_dir = class_dir / "Matieres"
        mat_dir.mkdir(parents=True, exist_ok=True)
        nb_ex = int(db.get_setting("nb_examens", "6") or 6)
        for s in subjects:
            wb_m = openpyxl.Workbook()
            ws_m = wb_m.active
            ws_m.title = s.name[:31]

            ws_m["B2"] = etab
            ws_m["B2"].font = Font(bold=True, size=14)
            ws_m["E2"] = f"Matière : {s.name}"
            ws_m["E2"].font = Font(bold=True, size=12)
            ws_m["B3"] = f"Classe : {classe}"
            ws_m["C3"] = f"Coef : {s.coeff:g}"
            ws_m["F3"] = f"Prof : {s.teacher or '—'}"
            ws_m["B4"] = f"Année scolaire : {annee}"
            ws_m["B4"].font = Font(italic=True, color="666666")

            mat_headers = ["N°", "Nom et Prénoms"]
            for n in range(1, nb_ex + 1):
                label, _ = label_for_exam(n)
                mat_headers.append(label)
            for c, h in enumerate(mat_headers, 1):
                cell = ws_m.cell(row=6, column=c, value=h)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")

            for r, st_raw in enumerate(students_raw, 7):
                ws_m.cell(row=r, column=1, value=st_raw["num"])
                full = f"{st_raw['nom']} {st_raw['prenoms'] if 'prenoms' in st_raw.keys() else ''}".strip()
                ws_m.cell(row=r, column=2, value=full)
                for n in range(1, nb_ex + 1):
                    v = db.get_grade(st_raw["id"], s.id, n)
                    if v is not None:
                        ws_m.cell(row=r, column=2 + n, value=v)

            ws_m.column_dimensions["A"].width = 5
            ws_m.column_dimensions["B"].width = 30
            for n in range(1, nb_ex + 1):
                ws_m.column_dimensions[openpyxl.utils.get_column_letter(2 + n)].width = 12

            safe_name = "".join(
                c if c.isalnum() or c in " -_." else "_"
                for c in s.name
            ).strip()
            wb_m.save(mat_dir / f"{safe_name}.xlsx")
            exported += 1

        # ── Totalisation (6 fichiers) ──────────────────────────────
        tot_dir = class_dir / "Totalisation"
        tot_dir.mkdir(parents=True, exist_ok=True)
        for n in range(1, 7):
            rows, subjs, total_coeff = compute_totalisation(db, n)
            lbl_exam, _ = label_for_exam(n)
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = f"totalisation{n}"

            ws["A1"] = etab
            ws["A1"].font = title_font
            ws["B2"] = f"Matière : RELEVE DE NOTES"
            ws["B2"].font = Font(bold=True, size=12)
            ws["A2"] = f"Classe : {classe}"
            ws["B3"] = f"Année : {annee}"
            ws["A3"] = f"Examen : {lbl_exam}"
            ws["A4"] = f"Coefficients totaux : {total_coeff:g}"

            headers = ["N°", "Prénoms"]
            for s in subjs:
                headers.append(f"{s.name} ({s.coeff:g})")
            headers.extend(["Total", "Moyenne", "Rang"])
            for c, h in enumerate(headers, 1):
                cell = ws.cell(row=6, column=c, value=h)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")

            for i, r in enumerate(rows):
                row = 7 + i
                ws.cell(row=row, column=1, value=r["student"].num)
                ws.cell(row=row, column=2, value=r["student"].full_name)
                for c, s in enumerate(subjs, 3):
                    v = r["notes"].get(s.id)
                    if v is not None:
                        ws.cell(row=row, column=c, value=v)
                if r["valid"]:
                    ws.cell(row=row, column=3 + len(subjs), value=r["total"])
                    ws.cell(row=row, column=4 + len(subjs), value=r["moy"])
                    ws.cell(row=row, column=5 + len(subjs), value=r["rank"])
                else:
                    for c in range(3 + len(subjs), 6 + len(subjs)):
                        ws.cell(row=row, column=c, value="NC")

            ws.column_dimensions["A"].width = 5
            ws.column_dimensions["B"].width = 25
            for c in range(3, 3 + len(subjs)):
                ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = 12
            ws.column_dimensions[openpyxl.utils.get_column_letter(3 + len(subjs))].width = 10
            ws.column_dimensions[openpyxl.utils.get_column_letter(4 + len(subjs))].width = 10
            ws.column_dimensions[openpyxl.utils.get_column_letter(5 + len(subjs))].width = 6

            wb.save(tot_dir / f"totalisation{n}.xlsx")
            exported += 1

        # ── Moyennes (4 fichiers) ──────────────────────────────────
        moy_dir = class_dir / "Moyennes"
        moy_dir.mkdir(parents=True, exist_ok=True)

        for t in (1, 2, 3):
            trim_rows = compute_trimestre(db, t)
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = f"Moyenne T{t}"

            ws["A1"] = etab
            ws["A1"].font = title_font
            ws["A2"] = f"Classe : {classe}  —  Année : {annee}"
            ws["A3"] = f"MOYENNES TRIMESTRE {t}"
            ws["A3"].font = Font(bold=True, size=12)

            headers = [
                "N°", "Prénoms", "M.J. (×1)", "Comp. (×2)",
                "Total M.J", "Total C", "Total/40", "Moyenne/20", "Rang"
            ]
            for c, h in enumerate(headers, 1):
                cell = ws.cell(row=5, column=c, value=h)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")

            for i, r in enumerate(trim_rows):
                row = 6 + i
                ws.cell(row=row, column=1, value=r.student.num)
                ws.cell(row=row, column=2, value=r.student.full_name)
                for c, val in enumerate([r.m_moy, r.c_moy, r.m_total, r.c_total, r.tot, r.moy], 3):
                    ws.cell(row=row, column=c, value=fmt_value(val))
                ws.cell(row=row, column=9, value=str(r.rank) if r.rank else "NC")

            ws.column_dimensions["A"].width = 5
            ws.column_dimensions["B"].width = 25
            for c in range(3, 10):
                ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = 12

            wb.save(moy_dir / f"Moyenne_T{t}.xlsx")
            exported += 1

        # Annuelle
        ann_rows = compute_annuelle(db)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Moyenne Annuelle"

        ws["A1"] = etab
        ws["A1"].font = title_font
        ws["A2"] = f"Classe : {classe}  —  Année : {annee}"
        ws["A3"] = "MOYENNES ANNUELLES"
        ws["A3"].font = Font(bold=True, size=12)

        headers = [
            "N°", "Prénoms",
            "M.J.1", "Comp.1", "M.J.2", "Comp.2", "M.J.3", "Comp.3",
            "TOTAL/120", "MGA/20", "Rang"
        ]
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=5, column=c, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")

        for i, r in enumerate(ann_rows):
            row = 6 + i
            ws.cell(row=row, column=1, value=r.student.num)
            ws.cell(row=row, column=2, value=r.student.full_name)
            for c, val in enumerate([r.mj1, r.co1, r.mj2, r.co2, r.mj3, r.co3], 3):
                ws.cell(row=row, column=c, value=fmt_value(val))
            ws.cell(row=row, column=9, value=fmt_value(r.total))
            ws.cell(row=row, column=10, value=fmt_value(r.mga))
            ws.cell(row=row, column=11, value=str(r.rank) if r.rank else "NC")

        ws.column_dimensions["A"].width = 5
        ws.column_dimensions["B"].width = 25
        for c in range(3, 12):
            ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = 12

        wb.save(moy_dir / "Moyenne_Annuelle.xlsx")
        exported += 1

        # ── Compte Rendu (1 PDF) ───────────────────────────────────
        cr_dir = class_dir / "Compte_Rendu"
        cr_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = cr_dir / "compte_rendu_trimestres.pdf"

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )

        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                                topMargin=2 * cm, bottomMargin=2 * cm)
        elems = []
        elems.append(Paragraph(f"<b>{etab}</b>", styles["Title"]))
        elems.append(Paragraph("COMPTE RENDU TRIMESTRES", styles["Heading2"]))
        elems.append(Paragraph(
            f"Classe : {classe} — Année : {annee}",
            styles["Normal"],
        ))
        elems.append(Spacer(1, 0.5 * cm))

        for t in (1, 2, 3):
            n_mj = 2 * t - 1
            n_co = 2 * t
            stats_mj = compute_stats(db, n_mj)
            stats_co = compute_stats(db, n_co)
            lbl_mj = label_for_exam(n_mj)[0]
            lbl_co = label_for_exam(n_co)[0]

            elems.append(Paragraph(
                f"<b>Trimestre {t} — {lbl_mj} + {lbl_co}</b>",
                styles["Heading3"],
            ))

            def _fmt_avg(v):
                return f"{v:.2f}" if v is not None else "NC"

            moy_mj = stats_mj.moyenne_classe
            moy_co = stats_co.moyenne_classe
            classes_ens = max(stats_mj.classes, stats_co.classes)
            data = [
                ["Indicateur", lbl_mj, lbl_co, "Ensemble"],
                ["Effectif",
                 str(stats_mj.effectif), str(stats_co.effectif),
                 str(stats_mj.effectif)],
                ["Classés",
                 str(stats_mj.classes), str(stats_co.classes),
                 str(classes_ens)],
                ["Moyenne classe",
                 _fmt_avg(moy_mj), _fmt_avg(moy_co),
                 _fmt_avg((moy_mj + moy_co) / 2
                          if moy_mj is not None and moy_co is not None
                          else moy_mj or moy_co)],
            ]
            t1 = Table(data, colWidths=[4 * cm, 3 * cm, 3 * cm, 3 * cm])
            t1.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]))
            elems.append(t1)
            elems.append(Spacer(1, 0.2 * cm))

            elems.append(Paragraph("<b>Élèves ≥ 10/20 par matière</b>", styles["Heading4"]))
            data2 = [["Matière", lbl_mj, lbl_co, "Ensemble"]]
            for s in subjects:
                n_mj_val = stats_mj.nb_above_avg_per_subject.get(s.id, 0)
                n_co_val = stats_co.nb_above_avg_per_subject.get(s.id, 0)
                data2.append([s.name, str(n_mj_val), str(n_co_val),
                              str(max(n_mj_val, n_co_val))])
            t2 = Table(data2, colWidths=[4 * cm, 3 * cm, 3 * cm, 3 * cm])
            t2.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]))
            elems.append(t2)
            elems.append(Spacer(1, 0.5 * cm))

        doc.build(elems)
        exported += 1

        return exported

    def _action_export_all_results(self) -> None:
        """Exporte totaux, moyennes et compte rendu — une classe ou toutes."""
        cls = discover_class_by_db_path(self.db.path)

        if cls is None:
            # Accueil → exporter toutes les classes
            from .workspace import discover_classes, get_global_config, set_global_config
            from qtpy.QtWidgets import QFileDialog

            saved = get_global_config("export_all_results_global_path", str(Path.home()))
            chosen = QFileDialog.getExistingDirectory(
                self,
                "Dossier de destination pour l'export global",
                saved,
            )
            if not chosen:
                return
            export_dir = Path(chosen)
            set_global_config("export_all_results_global_path", chosen)

            all_classes = discover_classes()
            if not all_classes:
                show_toast(self, "Aucune classe trouvée.", "info")
                return

            overlay = ProgressOverlay(self, "Export global des résultats…")
            overlay.start()
            total = 0
            per_class: list[str] = []
            for info in all_classes:
                db = Database(str(info.db_path))
                try:
                    n = self._export_class_all_results(db, info, export_dir)
                    n += self._export_class_profs(db, info, out_dir=export_dir)
                    total += n
                    per_class.append(f"  {info.display_name} : {n} fichier(s)")
                except Exception as exc:
                    log.exception("Export all results failed for %s", info.name)
                    per_class.append(f"  {info.display_name} : erreur — {exc}")
                finally:
                    db.close()
            overlay.stop()

            self.lbl_status.setText(f"Export global résultats : {total} fichier(s)")
            show_toast(self, f"Résultats exportés pour {len(all_classes)} classe(s) dans {chosen}", "success")
            return

        # Classe unique
        from .widgets.export_settings import ensure_export_dir
        from qtpy.QtWidgets import QFileDialog

        out_dir = ensure_export_dir(self.db, "export_totalisation_path")
        folder = QFileDialog.getExistingDirectory(
            self, "Dossier de destination pour l'export", str(out_dir),
        )
        if not folder:
            return

        overlay = ProgressOverlay(self, "Export des résultats…")
        overlay.start()
        try:
            n = self._export_class_all_results(self.db, cls, Path(folder))
            n += self._export_class_profs(self.db, cls, out_dir=Path(folder))
            if n == 0:
                show_toast(self, "Aucune donnée à exporter.", "info")
                return
            self.lbl_status.setText(f"Export résultats : {cls.display_name} — {n} fichier(s)")
            show_toast(self, f"Résultats exportés dans {folder}/{cls.name}/", "success")
        except Exception as e:
            log.exception("Export all results failed")
            show_toast(self, "Erreur lors de l'export. Vérifiez que le fichier n'est pas ouvert.", "error")
        finally:
            overlay.stop()

    def _action_sync_settings(self) -> None:
        """Dialogue des paramètres de synchronisation."""
        from .workspace import get_global_config, set_global_config
        from qtpy.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog

        dlg = QDialog(self)
        dlg.setWindowTitle("Paramètres de synchronisation")
        dlg.setMinimumWidth(500)

        lay = QVBoxLayout(dlg)
        lay.setSpacing(12)

        title = QLabel("Dossier de synchronisation des notes")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        lay.addWidget(title)

        desc = QLabel(
            "Ce dossier contient les fichiers exportés que les enseignants\n"
            "remplissent. La synchronisation lira les notes depuis ce dossier.\n\n"
            "Structure attendue :\n"
            "  <dossier>/export prof/College/<classe>/<matiere>.xlsx\n"
            "  <dossier>/export prof/Lycée/<classe>/<matiere>.xlsx\n\n"
            "L'exportation globale crée automatiquement cette structure."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{theme.current().on_surface_variant};")
        lay.addWidget(desc)

        current_path = get_global_config("export_profs_global_path", "")

        path_lay = QHBoxLayout()
        self._sync_path_field = QLineEdit(current_path)
        self._sync_path_field.setPlaceholderText("Aucun dossier configuré")
        self._sync_path_field.setMinimumHeight(32)
        path_lay.addWidget(self._sync_path_field, 1)

        btn_browse = QPushButton(qta.icon("fa5s.folder-open"), "")
        btn_browse.setFixedSize(32, 32)
        btn_browse.clicked.connect(
            lambda: self._sync_path_field.setText(
                QFileDialog.getExistingDirectory(
                    self, "Dossier de synchronisation",
                    self._sync_path_field.text() or str(Path.home()),
                ) or self._sync_path_field.text()
            )
        )
        path_lay.addWidget(btn_browse)
        lay.addLayout(path_lay)

        # Boutons
        btn_lay = QHBoxLayout()
        btn_lay.addStretch(1)
        btn_save = QPushButton(qta.icon("fa5s.save"), "Enregistrer")
        from .widgets.common import set_kind
        set_kind(btn_save, "primary")
        btn_save.clicked.connect(lambda: self._save_sync_settings(dlg))
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(dlg.reject)
        btn_lay.addWidget(btn_save)
        btn_lay.addWidget(btn_cancel)
        lay.addLayout(btn_lay)

        dlg.exec()

    def _save_sync_settings(self, dlg: QDialog) -> None:
        from .workspace import set_global_config
        path = self._sync_path_field.text().strip()
        if path:
            set_global_config("export_profs_global_path", path)
        from .widgets.common import show_toast
        show_toast(self, "Dossier de synchronisation enregistré", kind="success")
        dlg.accept()

    def _about(self) -> None:
        QMessageBox.about(
            self, "À propos",
            "<b>Bulletin</b> v1.0<br><br>"
            "Lycée Saint Joseph — 2025-2026",
        )

    # ------------------------------------------------------------------
    # Import XLSX
    # ------------------------------------------------------------------
    def _action_import_xlsx_from_home(self) -> None:
        from qtpy.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importer une liste d'élèves (multi-classes possible)",
            "",
            "Excel (*.xlsx *.xls)",
        )
        if not path:
            return

        from .widgets.import_helpers import read_all_sheets
        from .widgets.import_xlsx_wizard import ImportXlsxWizardDialog

        overlay = ProgressOverlay(self.centralWidget(), "Lecture du fichier…")
        overlay.start()
        try:
            wb = read_all_sheets(path)
        except Exception as exc:
            show_toast(self, "Impossible de lire le fichier. Vérifiez qu'il n'est pas corrompu ou ouvert dans un autre programme.", "error")
            return
        finally:
            overlay.stop()
        n_sheets = len(wb.sheets)
        if n_sheets == 0:
            show_toast(self, "Aucune feuille exploitable trouvée.", "warning")
            return

        mode = "multi"
        if n_sheets == 1:
            if self.db is not None and self.db.path and Path(str(self.db.path)).exists():
                mode = "single"
            else:
                mode = "multi"

        dlg = ImportXlsxWizardDialog(
            db=self.db if mode == "single" else None,
            path=path,
            parent=self,
            mode=mode,
        )
        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted:
            show_toast(self, "Importation terminée — accueil rafraîchi",
                       kind="success")
            self.home_dashboard.refresh()
            if hasattr(self, "class_switcher"):
                self.class_switcher.refresh()
            try:
                if hasattr(self, "students"):
                    self.students.refresh()
            except Exception:
                pass
            self._refresh_sidebar_classes()
            self.lbl_status.setText(
                f"Importation terminée depuis {Path(path).name}."
            )

    # ------------------------------------------------------------------
    # Backup / Restore / Wipe
    # ------------------------------------------------------------------
    def _action_open_backup_manager(self) -> None:
        if self.db is None or not self.db.path:
            show_toast(self, "Aucune base active. Ouvrez ou créez une classe d'abord.", "info")
            return
        dlg = BackupManagerDialog(self.db, self)
        dlg.databaseReplaced.connect(self._on_database_replaced)
        dlg.databaseMerged.connect(self._on_database_merged)
        dlg.databaseWiped.connect(self._on_database_wiped)
        dlg.workspaceWiped.connect(self._on_workspace_wiped)
        dlg.exec()
        self._refresh_all_tabs()
        self.home_dashboard.refresh()
        self._refresh_sidebar_classes()
        self.lbl_status.setText("Gestion des sauvegardes fermée.")

    def _action_full_reset_direct(self) -> None:
        from .widgets.backup_dialog import BackupManagerDialog

        if self.db is None or not self.db.path:
            show_toast(self, "Aucune base active.", "info")
            return
        dlg = BackupManagerDialog(self.db, self)
        dlg._tabs.setCurrentIndex(3)
        dlg.databaseReplaced.connect(self._on_database_replaced)
        dlg.databaseMerged.connect(self._on_database_merged)
        dlg.databaseWiped.connect(self._on_database_wiped)
        dlg.workspaceWiped.connect(self._on_workspace_wiped)
        dlg.exec()
        self._refresh_all_tabs()
        self.home_dashboard.refresh()
        self._refresh_sidebar_classes()

    def _action_full_reset_from_home(self) -> None:
        if self.db is None or not self.db.path:
            show_toast(self, "Aucune base active. La réinitialisation est possible depuis une classe.", "info")
            return
        self._action_full_reset_direct()

    def _on_database_replaced(self) -> None:
        self._swap_database_inplace()
        show_toast(self, "Base restaurée — onglets rechargés", kind="info")

    def _on_database_merged(self) -> None:
        self._refresh_all_tabs()
        self.home_dashboard.refresh()
        self._refresh_sidebar_classes()
        show_toast(self, "Fusion terminée", kind="success")

    def _on_database_wiped(self) -> None:
        self._swap_database_inplace()
        show_toast(self, "Base réinitialisée", kind="warning")

    def _on_workspace_wiped(self) -> None:
        self._stack.setCurrentIndex(0)
        self.home_dashboard.refresh()
        if self.db is not None:
            try:
                self.db.close()
            except Exception:
                pass
            self.db = None
        self._refresh_sidebar_classes()
        show_toast(self, "Réinitialisation totale : espace de travail vide", kind="warning")
        self.lbl_status.setText("Réinitialisation totale de l'espace de travail effectuée.")

    # ------------------------------------------------------------------
    # Database swap / refresh
    # ------------------------------------------------------------------
    def _swap_database_inplace(self) -> None:
        if self.db is None or not self.db.path:
            return
        path = self.db.path
        try:
            self.db.close()
        except Exception:
            pass
        self.db = Database(path)
        self._rebuild_tabs()
        self.home_dashboard.set_db(self.db)
        self.home_dashboard.refresh()
        self._refresh_sidebar_classes()
        self._on_tab_changed_breadcrumb(self.tabs.currentIndex())

    def _rebuild_tabs(self) -> None:
        while self.tabs.count():
            w = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if w:
                w.deleteLater()
        self.subject_tabs.clear()
        self._build_class_tabs()

    def _swap_database(self, new_db: Database) -> None:
        try:
            if self.db is not None and self.db.path:
                self.db.close()
        except Exception:
            log.exception("Failed to close previous DB")
        self.db = new_db
        self._rebuild_tabs()
        self.home_dashboard.set_db(self.db)
        self.home_dashboard.refresh()

    def _on_config_changed(self) -> None:
        self._rebuild_tabs()

    def _refresh_all_tabs(self) -> None:
        for attr in ("dashboard", "config", "students",
                     "totalisation", "moyennes", "cr"):
            w = getattr(self, attr, None)
            if w is not None and hasattr(w, "refresh"):
                try:
                    w.refresh()
                except Exception:
                    pass
        for w in self.subject_tabs.values():
            try:
                w.refresh()
            except Exception:
                pass

    def _refresh_class_list(self) -> None:
        previous = self.class_switcher.current_class_name()
        self.class_switcher.refresh()
        if previous:
            self.class_switcher.select_class_silent(previous)
        self._refresh_sidebar_classes()
        self.home_dashboard.refresh()

    def _action_save(self) -> None:
        """Ctrl+S : sauvegarde la configuration courante."""
        for attr in ("config", "students"):
            w = getattr(self, attr, None)
            if w is not None and hasattr(w, "_save"):
                try:
                    w._save()
                except Exception:
                    pass

    def _action_search(self) -> None:
        """Ctrl+F : focus le champ de recherche de l'onglet actif."""
        tab = self.tabs.currentWidget()
        if tab is None:
            return
        for child in tab.findChildren((QLineEdit,)):
            obj = child
            if hasattr(obj, "setFocus") and hasattr(obj, "placeholderText"):
                txt = obj.placeholderText().lower()
                if "cherch" in txt or "filtr" in txt or "recher" in txt:
                    obj.setFocus()
                    obj.selectAll()
                    return
