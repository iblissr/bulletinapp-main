"""Widget Totalisation (1 onglet par note 1..6)."""
from __future__ import annotations

import qtawesome as qta
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from .common import Panel, ProgressOverlay, TopContainer, set_kind, show_toast
from .table_helpers import (
    COLOR_AVERAGE_NA,
    label_for_exam,
    make_grade_item,
    make_header as _hdr,
    make_item as _val,
    wrap_layout as _wrap,
)
from qtpy.QtGui import QColor as _QColor
from ..db import Database
from ..models import compute_totalisation


class TotalisationWidget(QWidget):
    """Affiche la totalisation pour la note sélectionnée (1..6)."""

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(14)

        # --- En-tête de page ---
        self._top = TopContainer(
            "TT",
            "Totaux",
            "Relevé de notes par examen (toutes matières)",
        )
        # Selecteur de note + export dans TopContainer
        self._top._layout.addWidget(QLabel("Note :"))
        self.cb_note = QComboBox()
        self.cb_note.setToolTip("Sélectionner le numéro d'examen à afficher")
        for n in range(1, 7):
            lbl, _ = label_for_exam(n)
            self.cb_note.addItem(f"{n} — {lbl}", n)
        self.cb_note.currentIndexChanged.connect(self.refresh)
        self._top._layout.addWidget(self.cb_note)
        self.btn_export = QPushButton(qta.icon("fa5s.file-export"), "Exporter")
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.setToolTip("Exporter le relevé de notes vers Excel")
        set_kind(self.btn_export, "tonal")
        self.btn_export.clicked.connect(self._export)
        self._top._layout.addWidget(self.btn_export)
        root.addWidget(self._top)

        # --- Panel table ---
        panel = Panel(icon=qta.icon("fa5s.table"))
        self.table = QTableWidget(0, 0)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        panel.body_layout().addWidget(self.table)
        root.addWidget(panel, 1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        exam = int(self.cb_note.currentData())
        rows, subjects, total_coeff = compute_totalisation(self.db, exam)
        nb = len(subjects)
        cols = 3 + nb + 3  # N°, Nom, Matières..., Tot, Moy, RG

        if nb == 0:
            self.table.clear()
            self.table.setColumnCount(1)
            self.table.setRowCount(1)
            self.table.setItem(0, 0, _val("Aucune matière configurée"))
            return

        self.table.clear()
        self.table.setColumnCount(cols)
        self.table.setRowCount(7 + len(rows) + 4)  # +7 en-tête + données + 4 (dont TITULAIRE)

        col_annee = max(0, cols - 8)
        col_classe = max(0, cols - 4)

        # En-tête
        self.table.setItem(0, 0, _hdr(self.db.get_setting("etablissement", "")))
        self.table.setSpan(0, 0, 1, min(4, cols))
        # Ligne "section / division" : reprend l'année scolaire + la classe
        section_line = (
            f"{self.db.get_setting('annee_scolaire', '')}  —  "
            f"{self.db.get_setting('classe', '')}"
        )
        self.table.setItem(1, 0, _hdr(section_line, size=14))
        self.table.setSpan(1, 0, 1, min(4, cols))
        self.table.setItem(2, 0, _hdr("RELEVE DE NOTES", size=20))
        self.table.setSpan(2, 0, 1, min(4, cols))
        self.table.setItem(3, col_annee, _hdr(
            f"ANNÉE SCOLAIRE : {self.db.get_setting('annee_scolaire', '')}", size=14
        ))
        self.table.setSpan(3, col_annee, 1, min(8, cols - col_annee))
        self.table.setItem(3, 0, _hdr(""))  # padding
        self.table.setItem(2, col_classe, _hdr(self.db.get_setting("classe", ""), size=18))
        self.table.setSpan(2, col_classe, 1, min(4, cols - col_classe))

        # COEFFICIENTS
        self.table.setItem(4, 2, _hdr("COEFFICIENTS"))
        self.table.setSpan(4, 2, 1, nb + 3)

        # Ligne des coefficients
        for c, s in enumerate(subjects, 3):
            self.table.setItem(5, c, _val(s.coeff, bold=True, center=True))
        self.table.setItem(5, 3 + nb, _val(total_coeff, bold=True, center=True))

        # En-têtes colonnes
        self.table.setItem(6, 0, _hdr("N°"))
        self.table.setItem(6, 1, _hdr("Prénoms"))
        for c, s in enumerate(subjects, 3):
            self.table.setItem(6, c, _hdr(s.abbrev, center=True))
        self.table.setItem(6, 3 + nb, _hdr("Tot", center=True))
        self.table.setItem(6, 4 + nb, _hdr("Moy", center=True))
        self.table.setItem(6, 5 + nb, _hdr("RG", center=True))

        # Données
        for i, r in enumerate(rows):
            row = 7 + i
            self.table.setItem(row, 0, _val(r["student"].num, center=True))
            self.table.setItem(row, 1, _val(r["student"].full_name))
            for c, s in enumerate(subjects, 3):
                v = r["notes"].get(s.id)
                if v is None:
                    self.table.setItem(row, c, _val(""))
                else:
                    self.table.setItem(row, c, _val(f"{v:.2f}", center=True))
            if r["valid"]:
                self.table.setItem(row, 3 + nb, _val(f"{r['total']:.2f}", center=True, bold=True))
                # Moyenne + Rang : couleurs sémantiques centralisées
                self.table.setItem(
                    row, 4 + nb, make_grade_item(r["moy"]),
                )
                self.table.setItem(row, 5 + nb, _val(str(r["rank"]), center=True, bold=True))
            else:
                for c in (3 + nb, 4 + nb, 5 + nb):
                    self.table.setItem(
                        row, c, _val("NC", center=True, color=_QColor(COLOR_AVERAGE_NA())),
                    )

        # TITULAIRE
        last = 7 + len(rows) + 3
        if last < self.table.rowCount():
            self.table.setItem(last, min(4, cols - 1), _val("TITULAIRE", bold=True, underline=True))

        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()

    # ------------------------------------------------------------------
    def _export(self) -> None:
        from .export_settings import ensure_export_dir
        out_dir = ensure_export_dir(self.db, "export_totalisation_path")
        default_name = f"totalisation{self.cb_note.currentData()}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter", str(out_dir / default_name),
            "Excel (*.xlsx)",
        )
        if not path:
            return
        overlay = ProgressOverlay(self, "Export en cours…")
        overlay.start()
        try:
            import openpyxl  # noqa: WPS433
            from openpyxl.styles import Font  # noqa: WPS433

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = f"totalisation{self.cb_note.currentData()}"
            # Reprise du contenu de la table
            for r in range(self.table.rowCount()):
                for c in range(self.table.columnCount()):
                    it = self.table.item(r, c)
                    if it and it.text():
                        ws.cell(row=r + 1, column=c + 1, value=it.text())
            wb.save(path)
            show_toast(self, f"Exporté vers {path}", "success")
        except Exception as e:  # noqa: BLE001
            show_toast(self, "Erreur lors de l'export du fichier. Vérifiez que le fichier n'est pas ouvert dans un autre programme.", "error")
        finally:
            overlay.stop()


def _wrap(layout) -> QWidget:
    """Compat : redirige vers :func:`table_helpers.wrap_layout`."""
    from .table_helpers import wrap_layout
    return wrap_layout(layout)
