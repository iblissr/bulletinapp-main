"""Dialog de gestion des sauvegardes (pattern eco_paiement premium).

Trois onglets :
1. **Sauvegardes automatiques** : liste des backups dans ``.backups/``,
   avec date, taille, et boutons « Supprimer » / « Restaurer ».
2. **Restaurer depuis un fichier** : choisir un ``.db`` arbitraire
   et choisir entre « Fusionner (additif) » et « Remplacer ».
3. **Réinitialiser la base** : confirmation double → wipe complet.

Le pattern est directement inspiré de ``SettingsPanel._do_backup /
_do_merge / _do_wipe`` dans eco_paiements premium.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import qtawesome as qta
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QBrush, QColor, QFont
from qtpy.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .common import Panel, ProgressOverlay, set_kind, show_toast
from ..db import Database
from ..workspace import delete_all_classes


# Couleurs sémantiques
_COLOR_AUTO = QColor("#059669")     # vert (auto)
_COLOR_MANUAL = QColor("#1F497D")   # bleu (manuel)
_COLOR_BEFORE_DESTRUCT = QColor("#D97706")  # orange (avant reset/replace)


def _format_size(n: int) -> str:
    """Formate une taille en octets en chaîne lisible."""
    if n < 1024:
        return f"{n} o"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} Ko"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} Mo"
    return f"{n / (1024 * 1024 * 1024):.1f} Go"


def _format_date(ts: float) -> str:
    """Formate un timestamp en JJ/MM/AAAA HH:MM:SS."""
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S")


def _open_in_file_manager(path: str) -> None:
    """Ouvre un dossier dans l'explorateur de fichiers natif."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:  # noqa: BLE001
        pass


class BackupManagerDialog(QDialog):
    """Dialog de gestion des sauvegardes.

    Émet :pyattr:`databaseReplaced` quand la base a été remplacée
    (le parent doit alors recharger les onglets).
    """

    databaseReplaced = Signal()
    databaseMerged = Signal()
    databaseWiped = Signal()
    # Bulletin premium : wipe total (toutes les classes)
    workspaceWiped = Signal()

    def __init__(
        self,
        db: Database,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Sauvegarde & restauration")
        self.resize(820, 540)
        self._build()
        self._refresh_backups_list()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # En-tête
        title_icon = QLabel()
        title_icon.setPixmap(qta.icon("fa5s.database").pixmap(22, 22))
        title_text = QLabel("Sauvegarde & restauration")
        title_text.setFont(QFont("", 13, QFont.Weight.Bold))
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.addWidget(title_icon)
        title_row.addWidget(title_text)
        title_row.addStretch(1)
        root.addLayout(title_row)

        sub = QLabel(
            "Créez des sauvegardes, fusionnez ou restaurez la base active, "
            "ou réinitialisez-la complètement."
        )
        sub.setStyleSheet(
            "color: palette(placeholder-text); font-size: 11px;"
        )
        sub.setWordWrap(True)
        root.addWidget(sub)

        # Onglets
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_backups_tab(), "Sauvegardes existantes")
        self._tabs.addTab(self._build_restore_tab(), "Restaurer / Fusionner")
        self._tabs.addTab(self._build_wipe_tab(), "Réinitialiser")
        self._tabs.addTab(self._build_wipe_all_tab(),
                          "Tout effacer (workspace)")
        root.addWidget(self._tabs, 1)

        # Bouton Fermer
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        btns.button(QDialogButtonBox.Close).setText("Fermer")
        set_kind(btns.button(QDialogButtonBox.Close), "tonal")
        root.addWidget(btns)

    # ------------------------------------------------------------------
    # Onglet 1 : Sauvegardes existantes
    # ------------------------------------------------------------------
    def _build_backups_tab(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)

        # Action row
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self._btn_backup_now = QPushButton(
            qta.icon("fa5s.plus-circle"), "  Créer une sauvegarde maintenant"
        )
        set_kind(self._btn_backup_now, "primary")
        self._btn_backup_now.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_backup_now.clicked.connect(self._do_create_backup)
        bar.addWidget(self._btn_backup_now)

        self._btn_open_folder = QPushButton(
            qta.icon("fa5s.folder-open"), "  Ouvrir le dossier"
        )
        set_kind(self._btn_open_folder, "tonal")
        self._btn_open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_open_folder.clicked.connect(self._open_backups_folder)
        bar.addWidget(self._btn_open_folder)

        bar.addStretch(1)
        self._lbl_bk_info = QLabel("0 sauvegarde(s)")
        self._lbl_bk_info.setStyleSheet(
            "color: palette(placeholder-text); font-size: 11px; "
            "font-weight: 600; padding: 0 4px;"
        )
        bar.addWidget(self._lbl_bk_info)
        lay.addLayout(bar)

        # Table des backups
        self._tbl_backups = QTableWidget(0, 4)
        self._tbl_backups.setHorizontalHeaderLabels(
            ["Nom", "Date", "Taille", "Type"]
        )
        self._tbl_backups.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._tbl_backups.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tbl_backups.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tbl_backups.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tbl_backups.verticalHeader().setVisible(False)
        self._tbl_backups.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._tbl_backups.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._tbl_backups.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._tbl_backups.setAlternatingRowColors(True)
        lay.addWidget(self._tbl_backups, 1)

        # Action row 2 : Restaurer / Supprimer
        bar2 = QHBoxLayout()
        bar2.setSpacing(6)
        self._btn_restore_selected = QPushButton(
            qta.icon("fa5s.history"), "  Restaurer la sélection"
        )
        set_kind(self._btn_restore_selected, "tonal")
        self._btn_restore_selected.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_restore_selected.clicked.connect(self._do_restore_selected)
        bar2.addWidget(self._btn_restore_selected)

        self._btn_delete_selected = QPushButton(
            qta.icon("fa5s.trash-alt"), "  Supprimer"
        )
        set_kind(self._btn_delete_selected, "danger")
        self._btn_delete_selected.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_delete_selected.clicked.connect(self._do_delete_selected)
        bar2.addWidget(self._btn_delete_selected)
        bar2.addStretch(1)
        lay.addLayout(bar2)

        return wrap

    def _refresh_backups_list(self) -> None:
        backups = self.db.list_backups()
        self._tbl_backups.setRowCount(len(backups))
        for r, bk in enumerate(backups):
            try:
                stat = bk.stat()
            except OSError:
                continue
            # Nom
            it_name = QTableWidgetItem(bk.name)
            it_name.setData(Qt.ItemDataRole.UserRole, str(bk))
            it_name.setFlags(it_name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._tbl_backups.setItem(r, 0, it_name)
            # Date
            it_date = QTableWidgetItem(_format_date(stat.st_mtime))
            it_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_date.setFlags(it_date.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._tbl_backups.setItem(r, 1, it_date)
            # Taille
            it_size = QTableWidgetItem(_format_size(stat.st_size))
            it_size.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_size.setFlags(it_size.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._tbl_backups.setItem(r, 2, it_size)
            # Type
            it_type = QTableWidgetItem(_classify_backup(bk.name))
            it_type.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_type.setFlags(it_type.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._tbl_backups.setItem(r, 3, it_type)
            # Coloration par type
            if "remplacement" in it_type.text().lower():
                it_type.setForeground(QBrush(_COLOR_BEFORE_DESTRUCT))
            elif "auto" in it_type.text().lower():
                it_type.setForeground(QBrush(_COLOR_AUTO))
            else:
                it_type.setForeground(QBrush(_COLOR_MANUAL))
        self._lbl_bk_info.setText(f"{len(backups)} sauvegarde(s)")

    def _selected_backup_path(self) -> Optional[Path]:
        rows = self._tbl_backups.selectionModel().selectedRows()
        if not rows:
            return None
        it = self._tbl_backups.item(rows[0].row(), 0)
        if it is None:
            return None
        return Path(str(it.data(Qt.ItemDataRole.UserRole)))

    # ------------------------------------------------------------------
    # Onglet 2 : Restaurer / Fusionner
    # ------------------------------------------------------------------
    def _build_restore_tab(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)

        # Description
        desc = QLabel(
            "Choisissez un fichier .db (sauvegarde d'une autre classe ou "
            "backup existant) puis sélectionnez l'action à effectuer :"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px;")
        lay.addWidget(desc)

        # Sélection du fichier
        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        self._lbl_restore_file = QLabel(
            "<i>Aucun fichier sélectionné</i>"
        )
        self._lbl_restore_file.setStyleSheet(
            "color: palette(placeholder-text); font-size: 11px;"
        )
        file_row.addWidget(self._lbl_restore_file, 1)
        btn_pick = QPushButton(qta.icon("fa5s.folder-open"), "  Choisir…")
        set_kind(btn_pick, "tonal")
        btn_pick.clicked.connect(self._pick_restore_file)
        file_row.addWidget(btn_pick)
        lay.addLayout(file_row)

        # Actions : Fusionner / Remplacer
        act_row = QHBoxLayout()
        act_row.setSpacing(6)

        self._btn_merge = QPushButton(
            qta.icon("fa5s.layer-group"),
            "  Fusionner (additif)"
        )
        self._btn_merge.setToolTip(
            "Ajoute les élèves, notes et matières manquants.\n"
            "Les paramètres de la base active sont conservés."
        )
        set_kind(self._btn_merge, "primary")
        self._btn_merge.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_merge.setEnabled(False)
        self._btn_merge.clicked.connect(self._do_merge)
        act_row.addWidget(self._btn_merge)

        self._btn_replace = QPushButton(
            qta.icon("fa5s.exchange-alt"),
            "  Remplacer (destructif)"
        )
        self._btn_replace.setToolTip(
            "Écrase totalement la base actuelle par le fichier choisi.\n"
            "Un backup de sécurité est créé automatiquement avant."
        )
        set_kind(self._btn_replace, "danger")
        self._btn_replace.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_replace.setEnabled(False)
        self._btn_replace.clicked.connect(self._do_replace)
        act_row.addWidget(self._btn_replace)
        act_row.addStretch(1)
        lay.addLayout(act_row)

        # Différences fusion / replace
        notes = QLabel(
            "<b>Fusionner</b> : ajoute ce qui manque, ne touche pas à "
            "l'existant. Recommandé pour importer une autre classe.<br><br>"
            "<b>Remplacer</b> : écrase la base active. Un backup "
            "<code>before_replace_*.bak</code> est créé avant. Annulation "
            "possible depuis l'onglet « Sauvegardes existantes »."
        )
        notes.setStyleSheet(
            "background: palette(midlight); padding: 10px; "
            "border-radius: 6px; font-size: 11px;"
        )
        notes.setWordWrap(True)
        lay.addWidget(notes, 1)

        # Mémorise le chemin choisi
        self._restore_path: Optional[Path] = None
        return wrap

    def _pick_restore_file(self) -> None:
        # Démarre dans le dossier des backups s'il existe
        start_dir = ""
        backups = self.db.list_backups()
        if backups:
            start_dir = str(backups[0].parent)
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir un fichier .db",
            start_dir,
            "Base de données (*.db *.bak);;Tous (*.*)",
        )
        if not path:
            return
        p = Path(path)
        if not self.db.validate_sqlite_file(p):
            QMessageBox.critical(
                self, self.windowTitle(),
                f"Le fichier\n{p}\nn'est pas une base de données valide."
            )
            return
        self._restore_path = p
        self._lbl_restore_file.setText(f"<code>{p}</code>")
        self._btn_merge.setEnabled(True)
        self._btn_replace.setEnabled(True)

    # ------------------------------------------------------------------
    # Onglet 3 : Réinitialiser
    # ------------------------------------------------------------------
    def _build_wipe_tab(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)

        # Description
        desc = QLabel(
            "Réinitialise <b>complètement</b> la base de la classe active :\n"
            "• Tous les élèves et toutes les notes sont supprimés\n"
            "• Les matières sont vidées (mais les paramètres — établissement, "
            "classe, année — sont conservés)\n"
            "• Un backup <code>before_wipe_*.bak</code> est créé "
            "automatiquement avant l'opération"
        )
        desc.setStyleSheet("font-size: 12px;")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        warn = QWidget()
        warn.setStyleSheet(
            "color: palette(highlighted-text); background: palette(dark); "
            "padding: 8px 12px; border-radius: 6px; font-size: 12px;"
        )
        warn_lay = QHBoxLayout(warn)
        warn_lay.setContentsMargins(0, 0, 0, 0)
        warn_ico = QLabel()
        warn_ico.setPixmap(qta.icon("fa5s.exclamation-triangle").pixmap(18, 18))
        warn_lay.addWidget(warn_ico)
        warn_txt = QLabel(
            "<b>Cette opération est irréversible</b> "
            "(mais vous pouvez restaurer le backup créé ci-dessus)."
        )
        warn_txt.setWordWrap(True)
        warn_lay.addWidget(warn_txt, 1)
        lay.addWidget(warn)

        # Bouton
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._btn_wipe = QPushButton(
            qta.icon("fa5s.trash-alt"),
            "  Tout réinitialiser"
        )
        set_kind(self._btn_wipe, "danger")
        self._btn_wipe.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_wipe.clicked.connect(self._do_wipe)
        btn_row.addWidget(self._btn_wipe)
        lay.addLayout(btn_row)
        lay.addStretch(1)
        return wrap

    def _build_wipe_all_tab(self) -> QWidget:
        """Onglet « Tout effacer » (bulletin premium, pattern
        eco_paiement).

        Supprime **toutes les classes** du workspace BULLETIN/ :
        dossiers ``data/`` (DB + .backups), ``bulletin/`` (xlsm
        générés) et ``.xlsx`` de matières. L'accueil devient
        complètement vide.
        """
        wrap = QWidget(self)
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)

        # Titre
        head = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(
            qta.icon("fa5s.exclamation-triangle").pixmap(22, 22)
        )
        head.addWidget(icon_lbl)
        title = QLabel("Tout effacer — reset total du workspace")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        head.addWidget(title)
        head.addStretch(1)
        lay.addLayout(head)

        # Description détaillée
        desc = QLabel(
            "Cette opération est <b>extrêmement destructive</b>. "
            "Elle supprime :<br>"
            "• Toutes les bases SQLite (<code>data/bulletin.db</code>) "
            "de <b>toutes</b> les classes<br>"
            "• Toutes les sauvegardes (<code>.backups/</code>) "
            "des classes<br>"
            "• Tous les bulletins générés (<code>bulletin/*.xlsm</code>)<br>"
            "• Tous les fichiers de saisie des profs "
            "(<code>*.xlsx</code> à la racine des classes)<br><br>"
            "Les dossiers vides <code>COLLEGE/&lt;Classe&gt;</code> et "
            "<code>LYCEE/&lt;Classe&gt;</code> restent en place.<br><br>"
            "À la fin, l'accueil (<b>Home</b>) sera complètement vide."
        )
        desc.setStyleSheet("font-size: 12px;")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        warn = QWidget()
        warn.setStyleSheet(
            "color: palette(highlighted-text); background: palette(dark); "
            "padding: 8px 12px; border-radius: 6px; font-size: 12px;"
        )
        warn_lay = QHBoxLayout(warn)
        warn_lay.setContentsMargins(0, 0, 0, 0)
        warn_ico = QLabel()
        warn_ico.setPixmap(qta.icon("fa5s.exclamation-triangle").pixmap(18, 18))
        warn_lay.addWidget(warn_ico)
        warn_txt = QLabel(
            "<b>Cette opération est irréversible</b> "
            "(un backup global <code>before_wipe_all_*.bak</code> de la "
            "classe active est créé, mais les autres classes ne sont "
            "pas sauvegardées)."
        )
        warn_txt.setWordWrap(True)
        warn_lay.addWidget(warn_txt, 1)
        lay.addWidget(warn)

        # Checkbox « garder les xlsx » (saisies profs)
        opts = QHBoxLayout()
        from qtpy.QtWidgets import QCheckBox
        self._chk_keep_xlsx = QCheckBox(
            "Garder les fichiers de saisie des professeurs"
        )
        self._chk_keep_xlsx.setChecked(False)
        self._chk_keep_xlsx.setToolTip(
            "Si coché, les fichiers de saisie *.xlsx à la racine "
            "des classes sont conservés. Les DB, sauvegardes et "
            "bulletins sont tout de même supprimés."
        )
        opts.addWidget(self._chk_keep_xlsx)
        opts.addStretch(1)
        lay.addLayout(opts)

        # Bouton
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._btn_wipe_all = QPushButton(
            qta.icon("fa5s.broom"),
            "  Tout effacer (reset total)"
        )
        set_kind(self._btn_wipe_all, "danger")
        self._btn_wipe_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_wipe_all.clicked.connect(self._do_wipe_all_classes)
        btn_row.addWidget(self._btn_wipe_all)
        lay.addLayout(btn_row)
        lay.addStretch(1)
        return wrap

    # ==================================================================
    # Slots
    # ==================================================================
    def _do_create_backup(self) -> None:
        try:
            target = self.db.create_backup(prefix="manual")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, self.windowTitle(),
                f"Erreur lors de la sauvegarde :\n{exc}"
            )
            return
        if target is None:
            QMessageBox.warning(
                self, self.windowTitle(),
                "Impossible de créer une sauvegarde : "
                "la base n'a pas de chemin physique."
            )
            return
        self._refresh_backups_list()
        show_toast(
            self, f"Sauvegarde créée : {target.name}", kind="success"
        )

    def _open_backups_folder(self) -> None:
        if not self.db.path:
            return
        backup_dir = Path(self.db.path).parent / ".backups"
        backup_dir.mkdir(exist_ok=True)
        _open_in_file_manager(str(backup_dir))

    def _do_restore_selected(self) -> None:
        path = self._selected_backup_path()
        if path is None:
            QMessageBox.information(
                self, self.windowTitle(),
                "Sélectionnez d'abord une sauvegarde dans la liste."
            )
            return
        if not self._confirm_replace(path):
            return
        try:
            self.db.replace_database(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, self.windowTitle(),
                f"Erreur lors de la restauration :\n{exc}"
            )
            return
        show_toast(
            self, f"Base restaurée depuis {path.name}", kind="success"
        )
        self._refresh_backups_list()
        self.databaseReplaced.emit()
        self.accept()

    def _do_delete_selected(self) -> None:
        path = self._selected_backup_path()
        if path is None:
            return
        if QMessageBox.question(
            self, self.windowTitle(),
            f"Supprimer la sauvegarde\n{path.name} ?",
        ) != QMessageBox.StandardButton.Yes:
            return
        if self.db.delete_backup(path):
            self._refresh_backups_list()
        else:
            QMessageBox.warning(
                self, self.windowTitle(),
                "Impossible de supprimer cette sauvegarde."
            )

    def _do_merge(self) -> None:
        if self._restore_path is None:
            return
        overlay = ProgressOverlay(self, "Fusion en cours…")
        overlay.start()
        try:
            result = self.db.merge_database(self._restore_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, self.windowTitle(),
                f"Erreur lors de la fusion :\n{exc}"
            )
            return
        finally:
            overlay.stop()
        msg = (
            f"Fusion terminée :\n"
            f"• Élèves ajoutés : {result['added_students']}\n"
            f"• Élèves ignorés (déjà présents) : {result['skipped_students']}\n"
            f"• Notes ajoutées : {result['added_grades']}\n"
            f"• Matières ajoutées : {result['added_subjects']}"
        )
        QMessageBox.information(self, self.windowTitle(), msg)
        self.databaseMerged.emit()
        self.accept()

    def _do_replace(self) -> None:
        if self._restore_path is None:
            return
        if not self._confirm_replace(self._restore_path):
            return
        overlay = ProgressOverlay(self, "Remplacement en cours…")
        overlay.start()
        try:
            self.db.replace_database(self._restore_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, self.windowTitle(),
                f"Erreur lors du remplacement :\n{exc}"
            )
            return
        finally:
            overlay.stop()
        show_toast(
            self, f"Base remplacée par {self._restore_path.name}",
            kind="warning",
        )
        self._refresh_backups_list()
        self.databaseReplaced.emit()
        self.accept()

    def _do_wipe(self) -> None:
        # Double confirmation (pattern eco_paiement)
        for prompt in (
            "Êtes-vous SÛR de vouloir réinitialiser cette base ?\n\n"
            "Tous les élèves et toutes les notes seront supprimés.",
            "Dernière confirmation :\n\n"
            "Voulez-vous VRAIMENT tout effacer ?\n"
            "(Un backup avant_wipe_*.bak sera créé d'abord)",
        ):
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Réinitialiser la base")
            box.setText(prompt)
            box.setStandardButtons(
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            )
            box.setDefaultButton(QMessageBox.StandardButton.No)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return
        # Backup automatique avant le wipe
        try:
            self.db.create_backup(prefix="before_wipe")
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Pre-wipe backup failed: %s", exc)
        try:
            self.db.wipe_all_data(keep_settings=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, self.windowTitle(),
                f"Erreur lors de la réinitialisation :\n{exc}"
            )
            return
        self._refresh_backups_list()
        show_toast(self, "Base réinitialisée", kind="warning")
        self.databaseWiped.emit()
        self.accept()

    def _do_wipe_all_classes(self) -> None:
        """Supprime TOUTES les classes du workspace, après triple
        confirmation (pattern eco_paiement premium).
        """
        keep_xlsx = self._chk_keep_xlsx.isChecked()
        # 3 confirmations successives
        prompts = [
            (
                "Première confirmation",
                "Cette opération va supprimer <b>TOUTES</b> les classes "
                "du workspace BULLETIN/.<br><br>"
                "Continuer ?",
            ),
            (
                "Deuxième confirmation",
                "Êtes-vous <b>vraiment sûr</b> ?<br>"
                "Toutes les bases SQLite, les bulletins générés "
                f"et {'' if keep_xlsx else 'les saisies profs '} "
                "seront effacés.<br><br>"
                "Cette action ne peut pas être annulée.",
            ),
            (
                "Dernière confirmation",
                "Tapez mentalement OUI et cliquez sur Oui :<br>"
                "<b>Supprimer définitivement TOUTES les classes ?</b>",
            ),
        ]
        for title, prompt in prompts:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle(title)
            box.setText(prompt)
            box.setStandardButtons(
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            )
            box.setDefaultButton(QMessageBox.StandardButton.No)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return
        # Backup de sécurité de la classe active (les autres ne sont
        # pas sauvegardées — c'est destructif).
        try:
            self.db.create_backup(prefix="before_wipe_all")
        except Exception:  # noqa: BLE001
            pass
        # Wipe total
        try:
            counters = delete_all_classes(keep_xlsx=keep_xlsx)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, self.windowTitle(),
                f"Erreur lors du wipe total :\n{exc}"
            )
            return
        # Résumé
        msg = (
            f"Reset total terminé :\n"
            f"• {counters['classes']} classe(s) traitée(s)\n"
            f"• {counters['data']} base(s) de données supprimée(s)\n"
            f"• {counters['backups']} sauvegarde(s) supprimée(s)\n"
            f"• {counters['bulletin']} dossier(s) bulletin/ supprimé(s)\n"
            f"• {counters['xlsx']} fichier(s) .xlsx supprimé(s)"
        )
        if counters["errors"]:
            msg += f"\n\n⚠ {len(counters['errors'])} erreur(s) :\n"
            msg += "\n".join(counters["errors"][:5])
        show_toast(self, "Reset total effectué", kind="warning")
        QMessageBox.information(self, "Réinitialisation totale", msg)
        self.workspaceWiped.emit()
        self.accept()

    def _confirm_replace(self, source: Path) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Remplacer la base")
        box.setText(
            f"Remplacer la base actuelle par\n{source}\n\n"
            "Un backup automatique sera créé. Continuer ?"
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes


def _classify_backup(name: str) -> str:
    """Classe un nom de backup (manuel, auto, before_replace, …)."""
    n = name.lower()
    if "before_replace" in n:
        return "Avant remplacement"
    if "before_wipe" in n:
        return "Avant wipe"
    if "auto" in n:
        return "Auto"
    return "Manuel"
