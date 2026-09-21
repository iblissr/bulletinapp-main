"""Assistant d'import XLSX (pattern eco_paiement premium).

Différences avec ``ImportPreviewDialog`` simple :
- **Tree-view** avec checkboxes par élève (cocher / décocher
  individuellement).
- Détection des doublons **vs la base existante** (par N° ou par
  Nom+Prénoms).
- Statuts visuels : nouveau / doublon / ignoré (couleurs + icônes).
- Boutons « Tout cocher / Tout décocher » + résumé en direct.
- **Multi-sheets** : un classeur avec N feuilles = N classes
  (l'utilisateur coche les feuilles à importer et chaque feuille va
  dans la classe active ou dans la classe qu'il a sélectionnée).
- **Onglet CSV legacy** : coller ou charger un CSV simple
  (``num,nom,prenoms,genre,naissance``).

L'utilisateur voit clairement ce qui sera importé et peut annuler
un ou plusieurs élèves problématiques avant l'import final.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Optional

import qtawesome as qta
from qtpy.QtCore import Qt
from qtpy.QtGui import QBrush, QColor, QFont
from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..db import Database
from .common import set_kind
from ..workspace import (
    create_class_folder,
    discover_class,
    find_bulletin_root,
    import_xlsx_sheet_to_class,
    normalize_class_name,
)
from .import_helpers import (
    ParsedSheet,
    ParsedWorkbook,
    clean_text,
    read_all_sheets,
    split_full_name,
)


# Couleurs sémantiques (cohérence avec eco_paiement premium)
_COLOR_NEW = QColor("#059669")      # vert
_COLOR_DUP = QColor("#D97706")      # orange
_COLOR_IGNORED = QColor("#94A3B8")  # gris
_COLOR_HEADER = QColor("#1F497D")   # bleu foncé
_COLOR_NEW_CLASS = QColor("#0EA5A4")  # teal pour nouvelle classe


# Roles pour stocker des données sur les QTreeWidgetItem
_ROLE_SHEET_IDX = Qt.UserRole + 1
_ROLE_ROW_IDX = Qt.UserRole + 2
_ROLE_SHEET_NAME = Qt.UserRole + 3


class ImportXlsxWizardDialog(QDialog):
    """Wizard d'import XLSX avec tree-view multi-sheets + onglet CSV.

    Étapes (XLSX) :
    1. Choisir un .xlsx
    2. Cliquer « Analyser »
    3. Cocher / décocher les feuilles et les élèves à importer
    4. Cliquer « Importer »

    Les doublons sont détectés en comparant soit le N° soit le
    couple (nom + prenoms).

    Si le classeur a 1 seule feuille : mode « classe unique » (le
    tree-view montre directement les élèves).

    Si le classeur a N feuilles : mode « multi-classes ». Chaque
    feuille est un groupe dans le tree, et l'utilisateur peut :
    - cocher la classe entière (ou non)
    - décocher des élèves individuellement
    - choisir la classe cible via un menu contextuel
    """

    HEADERS = ["✓", "Statut", "N°", "Matricule", "Nom", "Prénoms",
               "Genre", "Naissance"]
    # En mode multi-classes, on ajoute 2 colonnes en tête : classe
    # cible et division.
    MULTI_HEADERS = ["✓", "Classe", "Division", "Statut", "N°",
                     "Matricule", "Nom", "Prénoms", "Genre", "Naissance"]

    def __init__(
        self,
        db: Optional[Database] = None,
        path: str = "",
        parent: QWidget | None = None,
        mode: str = "single",  # "single" | "multi"
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.path = path
        self.mode = mode
        # En mode multi, ``db`` peut être None (pas de classe active).
        self.wb: Optional[ParsedWorkbook] = None
        self._loading_tree = False
        self._set_ui()
        self._build()
        # Auto-analyse si on a un path
        if path:
            self._xlsx_path = Path(path)
            self._xlsx_lbl_file.setText(
                f"Fichier : {self._xlsx_path.name}"
            )
            self._xlsx_analyze()

    def _set_ui(self) -> None:
        self.setWindowTitle("Assistant d'import d'élèves")
        self.resize(900, 620)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 2 onglets : XLSX wizard + CSV legacy
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_xlsx_tab(), "Excel (.xlsx)")
        self._tabs.addTab(self._build_csv_tab(), "CSV (coller)")
        root.addWidget(self._tabs, 1)

        # Boutons du bas
        bottom = QHBoxLayout()
        bottom.setContentsMargins(12, 8, 12, 12)
        bottom.addStretch(1)
        btn_cancel = QPushButton("Fermer")
        set_kind(btn_cancel, "outlined")
        btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(btn_cancel)
        root.addLayout(bottom)

    # ==================================================================
    # Onglet 1 : XLSX wizard
    # ==================================================================
    def _build_xlsx_tab(self) -> QWidget:
        wrap = QWidget(self)
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # Intro
        if self.mode == "multi":
            intro_text = (
                "<b>Import multi-classes</b> — Le classeur Excel peut "
                "contenir <b>plusieurs feuilles</b> (une par classe). "
                "Chaque feuille sera importée dans la classe "
                "correspondante (créée automatiquement si elle "
                "n'existe pas). Vous pouvez décocher les classes ou "
                "les élèves que vous ne voulez pas importer."
            )
        else:
            intro_text = (
                "<b>Import XLSX</b> — Choisissez un classeur Excel "
                "contenant la liste des élèves de la classe active. "
                "Si le classeur contient plusieurs feuilles, chacune "
                "sera traitée comme une classe."
            )
        intro = QLabel(intro_text)
        intro.setWordWrap(True)
        intro.setStyleSheet("color: palette(placeholder-text); font-size: 12px;")
        lay.addWidget(intro)

        # Ligne : sélecteur de fichier
        row1 = QHBoxLayout()
        self._btn_pick = QPushButton(qta.icon("fa5s.folder-open"),
                                     "  Choisir…")
        set_kind(self._btn_pick, "outlined")
        self._btn_pick.clicked.connect(self._xlsx_pick_file)
        self._xlsx_lbl_file = QLabel("(aucun fichier)")
        self._xlsx_lbl_file.setStyleSheet("color: palette(placeholder-text);")
        self._xlsx_lbl_file.setWordWrap(True)
        self._btn_analyze = QPushButton(qta.icon("fa5s.search"),
                                       "  Analyser")
        set_kind(self._btn_analyze, "primary")
        self._btn_analyze.setEnabled(False)
        self._btn_analyze.clicked.connect(self._xlsx_analyze)
        row1.addWidget(self._btn_pick)
        row1.addWidget(self._xlsx_lbl_file, 1)
        row1.addWidget(self._btn_analyze)
        lay.addLayout(row1)

        # Tree-view
        self._xlsx_tree = QTreeWidget()
        if self.mode == "multi":
            headers = self.MULTI_HEADERS
        else:
            headers = self.HEADERS
        self._xlsx_tree.setColumnCount(len(headers))
        self._xlsx_tree.setHeaderLabels(headers)
        self._xlsx_tree.setAlternatingRowColors(True)
        self._xlsx_tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._xlsx_tree.itemChanged.connect(self._xlsx_on_item_changed)
        header = self._xlsx_tree.header()
        for i in range(len(headers)):
            if i in (0, 1, 2, 3, 5, 6, 8, 9):
                header.setSectionResizeMode(
                    i, QHeaderView.ResizeMode.ResizeToContents
                )
            else:
                header.setSectionResizeMode(
                    i, QHeaderView.ResizeMode.Stretch
                )
        lay.addWidget(self._xlsx_tree, 1)

        # Option « créer les classes manquantes » (multi seulement)
        if self.mode == "multi":
            from qtpy.QtWidgets import QCheckBox
            opts = QHBoxLayout()
            self._chk_create_missing = QCheckBox(
                "Créer automatiquement les classes manquantes"
            )
            self._chk_create_missing.setChecked(True)
            self._chk_create_missing.setToolTip(
                "Si coché, les classes qui n'existent pas encore dans "
                "BULLETIN/ seront créées (dossier + DB + bulletin/). "
                "Sinon, seules les classes existantes seront "
                "remplies ; les autres seront ignorées."
            )
            opts.addWidget(self._chk_create_missing)
            opts.addStretch(1)
            lay.addLayout(opts)

        # Barre d'outils (cocher / décocher / inverser)
        tools = QHBoxLayout()
        self._btn_check_all = QPushButton("Tout cocher")
        set_kind(self._btn_check_all, "outlined")
        self._btn_check_all.clicked.connect(
            lambda: self._xlsx_set_all_checked(True)
        )
        self._btn_uncheck_all = QPushButton("Tout décocher")
        set_kind(self._btn_uncheck_all, "outlined")
        self._btn_uncheck_all.clicked.connect(
            lambda: self._xlsx_set_all_checked(False)
        )
        self._btn_invert = QPushButton("Inverser")
        set_kind(self._btn_invert, "outlined")
        self._btn_invert.clicked.connect(self._xlsx_invert)
        self._lbl_summary = QLabel("")
        self._lbl_summary.setStyleSheet("color: palette(placeholder-text); font-size: 12px;")
        tools.addWidget(self._btn_check_all)
        tools.addWidget(self._btn_uncheck_all)
        tools.addWidget(self._btn_invert)
        tools.addStretch(1)
        tools.addWidget(self._lbl_summary)
        lay.addLayout(tools)

        # Action row
        actions = QHBoxLayout()
        actions.addStretch(1)
        if self.mode == "multi":
            btn_label = "  Importer les classes sélectionnées"
        else:
            btn_label = "  Importer la sélection"
        self._btn_import = QPushButton(qta.icon("fa5s.file-import"),
                                       btn_label)
        set_kind(self._btn_import, "primary")
        self._btn_import.setEnabled(False)
        self._btn_import.clicked.connect(self._xlsx_apply)
        actions.addWidget(self._btn_import)
        lay.addLayout(actions)

        self._xlsx_path: Optional[Path] = None
        return wrap

    def _xlsx_pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir un fichier Excel",
            "", "Excel (*.xlsx *.xlsm)",
        )
        if not path:
            return
        self._xlsx_path = Path(path)
        self._xlsx_lbl_file.setText(
            f"Fichier : {self._xlsx_path.name}"
        )
        self._btn_analyze.setEnabled(True)
        # Reset preview
        self.wb = None
        self._xlsx_tree.clear()
        self._btn_import.setEnabled(False)
        self._lbl_summary.setText("")

    def _xlsx_analyze(self) -> None:
        if not self._xlsx_path:
            return
        self._btn_analyze.setEnabled(False)
        self._lbl_summary.setText("Analyse en cours…")
        try:
            self.wb = read_all_sheets(self._xlsx_path)
        except Exception as exc:  # noqa: BLE001
            log_msg = str(exc)
            QMessageBox.critical(
                self, "Analyse XLSX",
                f"Erreur lors de l'analyse du fichier :\n{log_msg}"
            )
            self._btn_analyze.setEnabled(True)
            self._lbl_summary.setText("")
            return
        if not self.wb.sheets:
            QMessageBox.warning(
                self, "Analyse XLSX",
                "Aucun onglet n'a pu être analysé comme une liste "
                f"d'élèves.\nOnglets ignorés : {', '.join(self.wb.skipped_sheets)}"
            )
            self._btn_analyze.setEnabled(True)
            self._lbl_summary.setText("")
            return
        self._xlsx_populate_tree()
        self._btn_analyze.setEnabled(True)
        self._btn_analyze.setText("  Re-analyser")

    def _xlsx_populate_tree(self) -> None:
        if self.wb is None:
            return
        self._loading_tree = True
        try:
            self._xlsx_tree.clear()
            multi = len(self.wb.sheets) > 1
            for ci, sheet in enumerate(self.wb.sheets):
                if multi:
                    top = QTreeWidgetItem(self._xlsx_tree)
                    top.setData(0, _ROLE_SHEET_IDX, ci)
                    top.setData(0, _ROLE_ROW_IDX, -1)
                    top.setData(0, _ROLE_SHEET_NAME, sheet.sheet_name)
                    top.setIcon(0, qta.icon("fa5s.file-alt"))
                    top.setText(0, sheet.sheet_name)
                    top.setText(1, f"{len(sheet.rows)} élèves")
                    top.setForeground(0, QBrush(_COLOR_HEADER))
                    f = QFont()
                    f.setBold(True)
                    top.setFont(0, f)
                    # Tristate
                    top.setFlags(
                        top.flags() | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsAutoTristate
                    )
                    top.setCheckState(0, Qt.CheckState.Checked)
                    self._xlsx_populate_sheet(top, sheet)
                    top.setExpanded(True)
                else:
                    # Single-sheet : pas de niveau intermédiaire
                    self._xlsx_populate_sheet(self._xlsx_tree, sheet)
            if not multi:
                self._xlsx_tree.expandAll()
        finally:
            self._loading_tree = False
        self._xlsx_refresh_summary()
        self._btn_import.setEnabled(self.wb is not None)

    def _xlsx_populate_sheet(
        self, parent: QTreeWidgetItem, sheet: ParsedSheet
    ) -> None:
        """Ajoute les élèves d'un sheet sous ``parent``."""
        # Index de décalage pour les colonnes en mode multi
        # multi : 0=✓, 1=Classe, 2=Division, 3=Statut, 4=N°, …
        # single: 0=✓, 1=Statut, 2=N°, …
        col_offset = 2 if self.mode == "multi" else 0
        col_statut = 3 if self.mode == "multi" else 1
        col_num = col_offset + 2
        col_mat = col_offset + 3
        col_nom = col_offset + 4
        col_pre = col_offset + 5
        col_genre = col_offset + 6
        col_nais = col_offset + 7

        # En mode multi, on calcule la classe cible et l'existence
        target_class_name: Optional[str] = None
        target_division: Optional[str] = None
        target_exists = False
        if self.mode == "multi":
            target_class_name = normalize_class_name(sheet.sheet_name)
            from ..workspace import infer_division
            target_division = infer_division(target_class_name)
            target_exists = discover_class(target_class_name) is not None
            # Met à jour l'en-tête de groupe
            if parent is not self._xlsx_tree.invisibleRootItem():
                status = (
                    "existe ✓" if target_exists else "sera créée ✚"
                )
                parent.setText(
                    1, f"{target_class_name} [{target_division}]"
                )
                parent.setText(3, f"{len(sheet.rows)} élèves")
                # Tooltip-like via status tip :
                parent.setStatusTip(
                    1, f"Classe cible : {target_class_name} "
                    f"({target_division}) — {status}"
                )
                if not target_exists:
                    parent.setForeground(0, QBrush(_COLOR_NEW_CLASS))

        # Détection des élèves existants dans la base (mode single)
        existing: set[int] = set()
        existing_names: set[tuple[str, str]] = set()
        if self.db is not None:
            students = self.db.list_students()
            existing = {s["num"] for s in students}
            existing_names = {
                (s["nom"].strip().lower(), s["prenoms"].strip().lower())
                for s in students
            }
        for ri, row in enumerate(sheet.rows):
            leaf = QTreeWidgetItem(parent)
            leaf.setData(0, _ROLE_SHEET_IDX, -1)
            leaf.setData(0, _ROLE_ROW_IDX, ri)
            leaf.setData(0, _ROLE_SHEET_NAME, sheet.sheet_name)
            leaf.setFlags(
                leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable
            )
            is_dup = (
                row.get("num") in existing
                or (row.get("nom", "").strip().lower(),
                    row.get("prenoms", "").strip().lower())
                in existing_names
            )
            leaf.setText(col_num, str(row.get("num", "")))
            leaf.setText(col_mat, str(row.get("matricule", "")))
            leaf.setText(col_nom, str(row.get("nom", "")))
            leaf.setText(col_pre, str(row.get("prenoms", "")))
            leaf.setText(col_genre, str(row.get("genre", "")))
            leaf.setText(col_nais, str(row.get("naissance", "")))
            if is_dup:
                leaf.setText(col_statut, "Doublon")
                leaf.setForeground(0, QBrush(_COLOR_IGNORED))
                leaf.setForeground(col_statut, QBrush(_COLOR_DUP))
                leaf.setCheckState(0, Qt.CheckState.Unchecked)
            else:
                leaf.setText(col_statut, "Nouveau")
                leaf.setForeground(col_statut, QBrush(_COLOR_NEW))
                leaf.setCheckState(0, Qt.CheckState.Checked)

    def _xlsx_on_item_changed(
        self, item: QTreeWidgetItem, _column: int
    ) -> None:
        if self._loading_tree:
            return
        self._xlsx_refresh_summary()

    def _xlsx_set_all_checked(self, checked: bool) -> None:
        if self.wb is None:
            return
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._loading_tree = True
        try:
            for i in range(self._xlsx_tree.topLevelItemCount()):
                top = self._xlsx_tree.topLevelItem(i)
                # Tristate auto pour les groupes
                if top.childCount() > 0:
                    top.setCheckState(0, state)
                else:
                    top.setCheckState(0, state)
                for j in range(top.childCount()):
                    leaf = top.child(j)
                    leaf.setCheckState(0, state)
        finally:
            self._loading_tree = False
        self._xlsx_refresh_summary()

    def _xlsx_invert(self) -> None:
        if self.wb is None:
            return
        self._loading_tree = True
        try:
            for i in range(self._xlsx_tree.topLevelItemCount()):
                top = self._xlsx_tree.topLevelItem(i)
                # Ne pas inverser les groupes (laissé à l'utilisateur)
                for j in range(top.childCount()):
                    leaf = top.child(j)
                    cur = leaf.checkState(0)
                    new = (Qt.CheckState.Unchecked
                           if cur == Qt.CheckState.Checked
                           else Qt.CheckState.Checked)
                    leaf.setCheckState(0, new)
        finally:
            self._loading_tree = False
        self._xlsx_refresh_summary()

    def _xlsx_collect_selection(self) -> dict[str, list[dict]]:
        """Collecte les élèves cochés, groupés par sheet_name."""
        if self.wb is None:
            return {}
        out: dict[str, list[dict]] = {}
        for i in range(self._xlsx_tree.topLevelItemCount()):
            top = self._xlsx_tree.topLevelItem(i)
            sheet_idx = top.data(0, _ROLE_SHEET_IDX)
            # Groupe (multi-sheets) : on lit les enfants
            if sheet_idx is not None and int(sheet_idx) >= 0:
                sheet_name = self.wb.sheets[int(sheet_idx)].sheet_name
                for j in range(top.childCount()):
                    leaf = top.child(j)
                    if leaf.checkState(0) != Qt.CheckState.Checked:
                        continue
                    ri = leaf.data(0, _ROLE_ROW_IDX)
                    if ri is None:
                        continue
                    out.setdefault(sheet_name, []).append(
                        self.wb.sheets[int(sheet_idx)].rows[int(ri)]
                    )
            else:
                # Single-sheet : top est lui-même l'élève
                if top.checkState(0) != Qt.CheckState.Checked:
                    continue
                ri = top.data(0, _ROLE_ROW_IDX)
                if ri is None:
                    continue
                out.setdefault(
                    self.wb.sheets[0].sheet_name, []
                ).append(self.wb.sheets[0].rows[int(ri)])
        return out

    def _xlsx_refresh_summary(self) -> None:
        if self.wb is None:
            self._lbl_summary.setText("")
            return
        sel = self._xlsx_collect_selection()
        total_new = sum(len(v) for v in sel.values())
        n_sheets = len(sel)
        if n_sheets == 0:
            self._lbl_summary.setText("Aucun élève sélectionné.")
        elif n_sheets == 1:
            sk = next(iter(sel.keys()))
            self._lbl_summary.setText(
                f"Feuille « {sk} » : {total_new} élève(s) à importer."
            )
        else:
            self._lbl_summary.setText(
                f"{n_sheets} feuille(s) : {total_new} élève(s) à importer."
            )

    def _xlsx_apply(self) -> None:
        """Importe les élèves sélectionnés.

        Mode ``single`` : tous les élèves vont dans la DB active.
        Mode ``multi`` : chaque feuille est importée dans la classe
        correspondante (créée si absente).
        """
        sel = self._xlsx_collect_selection()
        if not sel:
            QMessageBox.information(
                self, "Importation",
                "Aucun élève sélectionné."
            )
            return

        if self.mode == "multi":
            self._xlsx_apply_multi(sel)
        else:
            self._xlsx_apply_single(sel)

    def _xlsx_apply_single(self, sel: dict) -> None:
        """Mode single-class : tout dans la DB active."""
        if self.db is None:
            QMessageBox.critical(
                self, "Importation",
                "Aucune classe active."
            )
            return
        all_rows: list[dict] = []
        for sheet_name, rows in sel.items():
            for r in rows:
                r2 = dict(r)
                r2["_sheet"] = sheet_name
                all_rows.append(r2)
        n_before = len(self.db.list_students())
        try:
            self.db.bulk_update_students(all_rows)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, "Importation",
                f"Erreur lors de l'importation :\n{exc}"
            )
            return
        n_after = len(self.db.list_students())
        n_added = max(0, n_after - n_before)
        QMessageBox.information(
            self, "Importation",
            f"{n_added} élève(s) ajouté(s) / mis à jour.\n"
            f"Total dans la classe : {n_after} élève(s)."
        )
        self.accept()

    def _xlsx_apply_multi(self, sel: dict) -> None:
        """Mode multi-classes : chaque sheet → sa classe."""
        if self.wb is None:
            return
        create_missing = (
            getattr(self, "_chk_create_missing", None) is not None
            and self._chk_create_missing.isChecked()
        )
        # Map sheet_name → ParsedSheet
        sheets_by_name = {s.sheet_name: s for s in self.wb.sheets}

        classes_created: list[str] = []
        classes_filled: list[str] = []
        classes_skipped: list[str] = []
        errors: list[str] = []
        total_added = 0
        total_in_db = 0

        for sheet_name, rows in sel.items():
            sheet = sheets_by_name.get(sheet_name)
            if sheet is None:
                continue
            target_name = normalize_class_name(sheet_name)
            if not target_name:
                classes_skipped.append(
                    f"{sheet_name!r} (nom non reconnu)"
                )
                continue
            target_info = discover_class(target_name)
            if target_info is None:
                if not create_missing:
                    classes_skipped.append(
                        f"{target_name} (n'existe pas)"
                    )
                    continue
                # Crée la classe
                try:
                    target_info = create_class_folder(target_name)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{target_name} : {exc}")
                    continue
                if target_info is None:
                    errors.append(
                        f"{target_name} : impossible de créer"
                    )
                    continue
                classes_created.append(target_info.name)
            else:
                classes_filled.append(target_info.name)
            # Importe
            try:
                stats = import_xlsx_sheet_to_class(sheet, target_info)
                total_added += stats.get("added", 0)
                total_in_db += stats.get("total", 0)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{target_info.name} : {exc}")

        # Message de bilan
        msg_lines = []
        if classes_created:
            msg_lines.append(
                f"✚ {len(classes_created)} classe(s) créée(s) : "
                f"{', '.join(classes_created)}"
            )
        if classes_filled:
            msg_lines.append(
                f"✓ {len(classes_filled)} classe(s) mise(s) à jour : "
                f"{', '.join(classes_filled)}"
            )
        if classes_skipped:
            msg_lines.append(
                f"⤴ {len(classes_skipped)} classe(s) ignorée(s) : "
                f"{', '.join(classes_skipped)}"
            )
        msg_lines.append("")
        msg_lines.append(
            f"Total : {total_added} élève(s) ajouté(s) / mis à jour, "
            f"{total_in_db} dans toutes les classes."
        )
        if errors:
            msg_lines.append("")
            msg_lines.append(
                "⚠ Erreurs :\n" + "\n".join(errors[:10])
            )
        QMessageBox.information(
            self,
            "Import multi-classes",
            "\n".join(msg_lines),
        )
        self.accept()

    # ==================================================================
    # Onglet 2 : CSV legacy (coller)
    # ==================================================================
    def _build_csv_tab(self) -> QWidget:
        wrap = QWidget(self)
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        intro = QLabel(
            "<b>Import CSV</b> — Collez ci-dessous un CSV avec les "
            "colonnes : <code>num, matricule, nom, prenoms, genre, "
            "naissance</code>. Séparateur <code>;</code> ou <code>,</code>."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: palette(placeholder-text); font-size: 12px;")
        lay.addWidget(intro)

        # Bouton charger fichier
        row = QHBoxLayout()
        btn_load = QPushButton(qta.icon("fa5s.folder-open"),
                               "  Charger un CSV…")
        set_kind(btn_load, "outlined")
        btn_load.clicked.connect(self._csv_load_file)
        row.addWidget(btn_load)
        row.addStretch(1)
        lay.addLayout(row)

        # Zone de texte
        self._csv_text = QTextEdit()
        self._csv_text.setPlaceholderText(
            "num;matricule;nom;prenoms;genre;naissance\n"
            "1;A001;RAKOTO;Jean;M;12/03/2008\n"
            "2;A002;RABE;Marie;F;05/07/2008\n"
            "…"
        )
        lay.addWidget(self._csv_text, 1)

        # Action row
        actions = QHBoxLayout()
        self._lbl_csv_summary = QLabel("")
        self._lbl_csv_summary.setStyleSheet(
            "color: palette(placeholder-text); font-size: 12px;"
        )
        actions.addWidget(self._lbl_csv_summary)
        actions.addStretch(1)
        btn_import_csv = QPushButton(qta.icon("fa5s.file-import"),
                                     "  Importer le CSV")
        set_kind(btn_import_csv, "primary")
        btn_import_csv.clicked.connect(self._csv_import)
        actions.addWidget(btn_import_csv)
        lay.addLayout(actions)

        return wrap

    def _csv_load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Charger un CSV",
            "", "CSV (*.csv *.txt)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                self._csv_text.setPlainText(f.read())
        except OSError as exc:
            QMessageBox.warning(self, "CSV", str(exc))

    def _csv_import(self) -> None:
        raw = self._csv_text.toPlainText().strip()
        if not raw:
            QMessageBox.information(self, "CSV", "Aucune donnée.")
            return
        if self.db is None:
            QMessageBox.critical(
                self, "CSV",
                "Aucune classe active. L'import CSV nécessite une "
                "classe ouverte (utilisez l'onglet XLSX pour créer "
                "plusieurs classes en une fois)."
            )
            return
        # Détection du séparateur
        sep = ";" if ";" in raw.splitlines()[0] else ","
        reader = csv.DictReader(io.StringIO(raw), delimiter=sep)
        rows: list[dict] = []
        skipped = 0
        for i, row in enumerate(reader, start=1):
            try:
                num = int(str(row.get("num", "")).strip())
            except (TypeError, ValueError):
                skipped += 1
                continue
            nom = clean_text(row.get("nom", ""))
            if not nom:
                # Si on a une colonne "nom_et_prenoms" on split
                full = clean_text(row.get("nom_et_prenoms", ""))
                if full:
                    nom, prenoms = split_full_name(full)
                else:
                    skipped += 1
                    continue
            else:
                prenoms = clean_text(row.get("prenoms", ""))
            rows.append({
                "num": num,
                "matricule": clean_text(row.get("matricule", "")),
                "nom": nom,
                "prenoms": prenoms,
                "genre": clean_text(row.get("genre", "")),
                "naissance": clean_text(row.get("naissance", "")),
            })
        if not rows:
            QMessageBox.warning(
                self, "CSV",
                f"Aucune ligne valide (séparateur '{sep}'). "
                f"{skipped} ligne(s) ignorée(s)."
            )
            return
        try:
            n_before = len(self.db.list_students())
            self.db.bulk_update_students(rows)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "CSV", f"Erreur : {exc}")
            return
        n_after = len(self.db.list_students())
        n_added = max(0, n_after - n_before)
        QMessageBox.information(
            self, "CSV",
            f"{n_added} élève(s) ajouté(s) / mis à jour "
            f"({skipped} ligne(s) ignorée(s)).\n"
            f"Total dans la classe : {n_after} élève(s)."
        )
        self.accept()


# ---------------------------------------------------------------------------
# Helper de lancement
# ---------------------------------------------------------------------------
def run(
    db: Database, path: str, parent: QWidget | None = None
) -> int:
    """Lance le wizard et retourne le nombre d'élèves importés
    (0 si annulé).
    """
    dlg = ImportXlsxWizardDialog(db, path, parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        # L'accept est appelé après l'import ; le nombre est
        # déjà affiché dans le message. Pour des raisons de
        # simplicité on retourne 1 (l'appelant rafraîchira).
        return 1
    return 0
