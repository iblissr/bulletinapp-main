"""Widget Élèves (équivalent de la feuille « Liste »).

Refonte visuelle style eco_paiement : TopContainer + icônes
qtawesome au lieu des émojis, panneau enrobant la table.

**Améliorations bulletin premium** :
- Recherche en temps réel sur nom / matricule
- Tri par clic d'en-tête de colonne
- **Drag-and-drop** d'une ligne à l'autre pour réordonner (N° auto-rewrité)
- **Bouton « + Ajouter »** : dialog unitaire (``AddStudentDialog``)
- **Bouton « Import XLSX »** : wizard avec tree-view + checkboxes
  (``ImportXlsxWizardDialog``) — pattern eco_paiement premium
"""
from __future__ import annotations

import qtawesome as qta
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .add_student_dialog import AddStudentDialog
from .common import (
    Panel,
    SearchBar,
    TopContainer,
    install_table_sort,
    set_kind,
    show_toast,
)
from .import_xlsx_wizard import ImportXlsxWizardDialog
from .table_helpers import wrap_layout as _wrap
from ..db import Database


class StudentsWidget(QWidget):
    """Onglet Liste élèves."""

    changed = Signal()

    HEADERS = ["N°", "Matricule", "Nom", "Prénoms", "Genre", "Naissance"]

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self._build()
        self.refresh()
        # Connexion du signal rowsMoved (drag-and-drop) — bulletin premium
        # Le modèle interne de QTableWidget émet ce signal quand l'user
        # glisse une ligne à un autre index.
        self.table.model().rowsMoved.connect(self._on_rows_moved)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(14)

        # --- En-tête de page ---
        # Bulletin premium : ajout des boutons "Ajouter 1 élève"
        # et "Importer" (wizard) en plus des boutons historiques.
        self.btn_add = QPushButton(qta.icon("fa5s.user-plus"), "Ajouter")
        set_kind(self.btn_add, "primary")
        self.btn_add.clicked.connect(self._add_one)

        self.btn_import = QPushButton(qta.icon("fa5s.file-import"), "Importer")
        set_kind(self.btn_import, "tonal")
        self.btn_import.setToolTip("Wizard d'import : tree-view, checkboxes, détection doublons")
        self.btn_import.clicked.connect(self._import_excel)

        # Menu déroulant pour les actions secondaires
        self._btn_more = QPushButton(qta.icon("fa5s.ellipsis-v"), "")
        self._btn_more.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_more.setFixedSize(34, 34)
        set_kind(self._btn_more, "outlined")
        from qtpy.QtWidgets import QMenu
        self._menu_more = QMenu(self)
        self._menu_more.setObjectName("MoreMenu")
        act_generate = self._menu_more.addAction(qta.icon("fa5s.magic"), "Générer N élèves")
        act_generate.triggered.connect(self._generate)
        act_delete = self._menu_more.addAction(qta.icon("fa5s.trash-alt"), "Supprimer sélection")
        act_delete.triggered.connect(self._delete_selected)
        act_save = self._menu_more.addAction(qta.icon("fa5s.save"), "Enregistrer")
        act_save.triggered.connect(self._save)
        self._btn_more.setMenu(self._menu_more)

        self._top = TopContainer(
            "EL",
            "Élèves",
            "Liste et importation des élèves de la classe",
        )
        for w in (self.btn_add, self.btn_import, self._btn_more):
            self._top.add_action(w)
        root.addWidget(self._top)

        # --- Panel table avec SearchBar (bulletin premium) ---
        panel = Panel(icon=qta.icon("fa5s.users"))
        # SearchBar au-dessus de la table
        self.search = SearchBar("Rechercher (nom, matricule, n°)…")
        self.search.textChanged.connect(self._apply_filter)
        panel.body_layout().addWidget(self.search)
        # Compteur d'élèves
        self._lbl_count = QLabel("")
        self._lbl_count.setStyleSheet(
            "color: palette(placeholder-text); font-size: 13px; "
            "font-weight: 600; padding: 0 4px;"
        )
        panel.body_layout().addWidget(self._lbl_count)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        # --- Drag-and-drop (bulletin premium) ---
        # On autorise le drop interne pour réordonner les élèves.
        # Les autres sources (externes) sont ignorées (par défaut).
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True)
        self.table.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove
        )
        self.table.setDefaultDropAction(Qt.DropAction.MoveAction)
        # On désactive le tri par header (sinon l'ordre est figé
        # par la dernière colonne triée). L'utilisateur peut
        # toujours trier en mémoire, mais à la prochaine action
        # on re-triera par N° ASC.
        # (Pour rester simple, on garde install_table_sort pour
        # la consultation, mais les drops réécrivent le N° et
        # on re-trie en interne.)
        # On garde aussi l'install_table_sort (cosmétique, mais
        # le « vrai » ordre est toujours contrôlé par le N°).
        install_table_sort(
            self.table,
            numeric_columns={0},  # N° est numérique
        )
        panel.body_layout().addWidget(self.table)
        root.addWidget(panel, 1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self.table.setRowCount(0)
        for st in self.db.list_students():
            r = self.table.rowCount()
            self.table.insertRow(r)
            self._fill_row(r, st)
        # Stocker toutes les lignes en mémoire pour le filtrage
        self._all_rows = []
        for r in range(self.table.rowCount()):
            row_data = []
            for c in range(self.table.columnCount()):
                it = self.table.item(r, c)
                row_data.append(it.text() if it else "")
            row_data.append(int(self.table.item(r, 0).data(Qt.ItemDataRole.UserRole))
                           if self.table.item(r, 0) else 0)
            self._all_rows.append(row_data)
        self._update_count()
        self._show_empty_if_needed()

    def _show_empty_if_needed(self) -> None:
        if self.table.rowCount() == 0:
            self.table.setRowCount(1)
            self.table.setSpan(0, 0, 1, self.table.columnCount())
            item = QTableWidgetItem("Aucun élève — Cliquez sur « + Ajouter » ou importez une liste Excel")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
            self.table.setItem(0, 0, item)

    def _update_count(self) -> None:
        n = self.table.rowCount()
        total = len(self._all_rows) if hasattr(self, "_all_rows") else n
        if n == total:
            self._lbl_count.setText(f"{n} élève{'s' if n > 1 else ''}")
        else:
            self._lbl_count.setText(f"{n} / {total} élève(s) affiché(s)")

    def _apply_filter(self, text: str) -> None:
        """Filtre la table selon ``text`` (insensible à la casse)."""
        if not hasattr(self, "_all_rows"):
            return
        text = (text or "").strip().lower()
        self.table.setRowCount(0)
        if not text:
            for row_data in self._all_rows:
                self.table.insertRow(self.table.rowCount())
                self._refill_row(self.table.rowCount() - 1, row_data)
            self._update_count()
            return
        # Match sur n'importe quel champ texte (num, matricule, nom, prénoms)
        for row_data in self._all_rows:
            haystack = " ".join(str(v) for v in row_data[:6]).lower()
            if text in haystack:
                self.table.insertRow(self.table.rowCount())
                self._refill_row(self.table.rowCount() - 1, row_data)
        self._update_count()

    def _refill_row(self, r: int, row_data: list) -> None:
        """Remplit une ligne depuis le cache (utilisé par le filtre)."""
        from .table_helpers import make_item
        # row_data = [num, matricule, nom, prenoms, genre, naissance, id]
        for c, value in enumerate(row_data[:6]):
            it = make_item(value)
            if c == 0:
                it.setData(Qt.ItemDataRole.UserRole, row_data[6])
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, c, it)

    def _fill_row(self, r: int, st) -> None:
        items = [
            QTableWidgetItem(str(st["num"])),
            QTableWidgetItem(st["matricule"] or ""),
            QTableWidgetItem(st["nom"] or ""),
            QTableWidgetItem(st["prenoms"] or ""),
            QTableWidgetItem(st["genre"] or ""),
            QTableWidgetItem(st["naissance"] or ""),
        ]
        items[0].setData(Qt.ItemDataRole.UserRole, st["id"])
        items[0].setFlags(items[0].flags() & ~Qt.ItemFlag.ItemIsEditable)
        for c, it in enumerate(items):
            self.table.setItem(r, c, it)

    # ------------------------------------------------------------------
    def _generate(self) -> None:
        eff = self.db.get_setting("effectif", "0")
        try:
            n = int(eff)
        except ValueError:
            n = 0
        if n <= 0:
            show_toast(self, "Renseignez l'effectif dans l'onglet Configuration.", "warning")
            return
        existing = {s["num"] for s in self.db.list_students()}
        skipped = len([i for i in range(1, n + 1) if i in existing])
        added = 0
        for i in range(1, n + 1):
            if i not in existing:
                self.db.add_student(i, f"Élève {i}")
                added += 1
        # Feedback clair : on indique les ajoutés ET les déjà existants
        from .common import show_toast
        msg = f"{added} élève(s) ajouté(s)"
        if skipped:
            msg += f", {skipped} déjà présent(s) (ignorés)"
        # Bulletin premium : toast au lieu de QMessageBox
        kind = "success" if added and not skipped else "warning" if skipped else "info"
        show_toast(self, msg, kind=kind)
        self.refresh()
        self.changed.emit()

    def _import_excel(self) -> None:
        """Ouvre le wizard d'import XLSX (tree-view + checkboxes).

        Pattern eco_paiement premium : tree-view avec statut
        nouveau/doublon par élève, l'utilisateur coche/décoche
        individuellement, puis « Importer ».
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer une liste d'élèves", "", "Excel (*.xlsx *.xls)"
        )
        if not path:
            return

        n = ImportXlsxWizardDialog.run(self.db, path, self)
        if n > 0:
            show_toast(self, f"{n} élève(s) importé(s)", kind="success")
            self.refresh()
            self.changed.emit()
        # Si n == 0 et pas d'erreur, l'utilisateur a annulé
        # (rien à signaler).

    # ------------------------------------------------------------------
    # Bulletin premium : drag-and-drop + add unitaire
    # ------------------------------------------------------------------
    def _add_one(self) -> None:
        """Ouvre le dialog « Ajouter 1 élève »."""
        if AddStudentDialog.add_student(self.db, self):
            show_toast(self, "Élève ajouté", kind="success")
            self.refresh()
            self.changed.emit()

    def _on_rows_moved(self, parent, src_start: int, src_end: int,
                        dest_parent, dest_row: int) -> None:
        """Slot appelé après un drag-and-drop de lignes.

        On réécrit le N° de chaque élève pour qu'il reflète la
        nouvelle position (1, 2, 3, …) et on persiste en base.
        """
        # Si l'utilisateur a filtré, on ne touche pas au N°
        if (hasattr(self, "search") and self.search.text().strip()):
            show_toast(
                self,
                "Drag-drop désactivé pendant un filtre. "
                "Effacez la recherche d'abord.",
                kind="warning",
            )
            # Recharger l'ordre DB (annulation visuelle du move)
            self.refresh()
            return
        # Renumérote selon l'ordre visuel actuel
        renumbered = 0
        for new_pos in range(self.table.rowCount()):
            it = self.table.item(new_pos, 0)
            if it is None:
                continue
            try:
                new_num = new_pos + 1
                old_num = int(it.text())
                if new_num != old_num:
                    sid = it.data(Qt.ItemDataRole.UserRole)
                    if sid:
                        self.db.update_student(int(sid), num=new_num)
                        it.setText(str(new_num))
                        renumbered += 1
            except (TypeError, ValueError):
                continue
        if renumbered > 0:
            show_toast(
                self,
                f"{renumbered} élève(s) réordonné(s)",
                kind="success",
            )
            # Recalcule les onglets dépendants
            self.changed.emit()

    def _save(self) -> None:
        updated = 0
        for r in range(self.table.rowCount()):
            it0 = self.table.item(r, 0)
            if not it0:
                continue
            sid = it0.data(Qt.ItemDataRole.UserRole)
            if not sid:
                # nouvelle ligne
                try:
                    num = int(it0.text())
                except ValueError:
                    continue
                nom = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
                prenoms = self.table.item(r, 3).text() if self.table.item(r, 3) else ""
                self.db.add_student(
                    num, nom, prenoms,
                    matricule=self.table.item(r, 1).text() if self.table.item(r, 1) else "",
                    genre=self.table.item(r, 4).text() if self.table.item(r, 4) else "",
                    naissance=self.table.item(r, 5).text() if self.table.item(r, 5) else "",
                )
                updated += 1
            else:
                try:
                    num = int(it0.text())
                except ValueError:
                    continue
                self.db.update_student(
                    sid,
                    num=num,
                    matricule=self.table.item(r, 1).text() if self.table.item(r, 1) else "",
                    nom=self.table.item(r, 2).text() if self.table.item(r, 2) else "",
                    prenoms=self.table.item(r, 3).text() if self.table.item(r, 3) else "",
                    genre=self.table.item(r, 4).text() if self.table.item(r, 4) else "",
                    naissance=self.table.item(r, 5).text() if self.table.item(r, 5) else "",
                )
                updated += 1
        from .common import show_toast
        show_toast(self, f"{updated} ligne(s) enregistrée(s)", kind="success")
        self.refresh()
        self.changed.emit()

    def _delete_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        if QMessageBox.question(
            self, "Suppression", f"Supprimer {len(rows)} élève(s) ?"
        ) != QMessageBox.StandardButton.Yes:
            return
        for r in rows:
            it = self.table.item(r, 0)
            if it and it.data(Qt.ItemDataRole.UserRole):
                self.db.delete_student(int(it.data(Qt.ItemDataRole.UserRole)))
        self.refresh()
        self.changed.emit()
