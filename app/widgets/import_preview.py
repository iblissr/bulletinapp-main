"""Boîte de prévisualisation d'import Excel.

Affiche à l'utilisateur :
- Le mapping détecté (colonne du fichier → champ cible).
- Les colonnes ignorées (avec leur nom d'origine).
- Un aperçu tabulaire des N premières lignes qui seront importées.
- Les avertissements collectés pendant l'analyse.

L'utilisateur peut alors confirmer ou annuler l'import.
"""
from __future__ import annotations

from typing import Optional

from qtpy.QtCore import Qt
from .common import set_kind
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .import_helpers import ParsedSheet, TARGET_FIELDS


# Libellé humain de chaque champ cible
_FIELD_LABELS = {
    "num":           "N°",
    "matricule":     "Matricule",
    "nom":           "Nom",
    "prenoms":       "Prénoms",
    "nom_et_prenoms": "Nom + Prénoms (combiné)",
    "genre":         "Genre",
    "naissance":     "Naissance",
}


class ImportPreviewDialog(QDialog):
    """Prévisualisation avant import."""

    def __init__(self, parsed: ParsedSheet, source_path: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.parsed = parsed
        self.source_path = source_path
        self.setWindowTitle("Aperçu de l'import")
        self.resize(820, 560)
        self._build()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)

        # --- Titre + résumé
        title = QLabel(
            f"<b>{len(self.parsed.rows)} élève(s) détecté(s)</b>"
            f" &nbsp;·&nbsp; En-têtes ligne {self.parsed.header_row}"
            f" &nbsp;·&nbsp; {self.parsed.skipped} ligne(s) ignorée(s)"
        )
        title.setFont(QFont("", 11))
        root.addWidget(title)

        sub = QLabel(f"Fichier : <code>{self.source_path}</code>")
        sub.setStyleSheet("color:palette(placeholder-text);")
        root.addWidget(sub)

        # --- Mapping
        mapping_label = QLabel("<b>Correspondance des colonnes :</b>")
        root.addWidget(mapping_label)
        mapping_text = self._render_mapping()
        mapping_box = QTextEdit()
        mapping_box.setReadOnly(True)
        mapping_box.setMaximumHeight(110)
        mapping_box.setHtml(mapping_text)
        root.addWidget(mapping_box)

        # --- Aperçu tabulaire
        preview_label = QLabel("<b>Aperçu (10 premières lignes) :</b>")
        root.addWidget(preview_label)
        self.table = QTableWidget(
            min(10, len(self.parsed.rows)),
            len(TARGET_FIELDS),
        )
        self.table.setHorizontalHeaderLabels(
            [_FIELD_LABELS[f] for f in TARGET_FIELDS]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self._fill_table()
        root.addWidget(self.table, 1)

        # --- Avertissements
        if self.parsed.warnings or self.parsed.mapping.extra:
            warn_parts = []
            if self.parsed.mapping.extra:
                warn_parts.append(
                    "<b>Colonnes ignorées :</b> " +
                    ", ".join(self.parsed.mapping.extra)
                )
            if self.parsed.warnings:
                warn_parts.append(
                    "<b>Avertissements :</b><br>" +
                    "<br>".join(self.parsed.warnings[:8])
                )
            warn = QLabel("<br>".join(warn_parts))
            warn.setStyleSheet(
                "background:palette(warning-container);border:1px solid palette(warning);"
                "padding:6px;border-radius:4px;color:palette(on-warning-container);"
            )
            warn.setWordWrap(True)
            root.addWidget(warn)

        # --- Boutons
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.button(QDialogButtonBox.Ok).setText("Importer")
        set_kind(btns.button(QDialogButtonBox.Ok), "primary")
        btns.button(QDialogButtonBox.Cancel).setText("Annuler")
        set_kind(btns.button(QDialogButtonBox.Cancel), "tonal")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    # ------------------------------------------------------------------
    def _render_mapping(self) -> str:
        """Génère un petit tableau HTML du mapping détecté."""
        lines = ["<table cellpadding='3' style='border-collapse:collapse;'>"]
        for field in TARGET_FIELDS:
            label = _FIELD_LABELS[field]
            col = self.parsed.mapping.fields.get(field, -1)
            if col < 0:
                badge = "<span style='color:#999;'>— non détecté —</span>"
            else:
                # Récupère le nom de la colonne d'origine (1-based pour l'utilisateur)
                badge = f"colonne <b>{col + 1}</b>"
            lines.append(
                f"<tr><td><b>{label}</b></td><td style='padding-left:12px;'>{badge}</td></tr>"
            )
        lines.append("</table>")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def _fill_table(self) -> None:
        # Index des champs à afficher dans le bon ordre
        for r, row in enumerate(self.parsed.rows[:10]):
            for c, field in enumerate(TARGET_FIELDS):
                v = row.get(field, "")
                if v is None:
                    v = ""
                it = QTableWidgetItem(str(v))
                if field == "num":
                    it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, it)

    # ------------------------------------------------------------------
    @staticmethod
    def confirm_and_import(parent: Optional[QWidget], parsed: ParsedSheet,
                            source_path: str) -> bool:
        """Helper statique : affiche la prévisualisation et retourne
        ``True`` si l'utilisateur a confirmé l'import.
        """
        dlg = ImportPreviewDialog(parsed, source_path, parent)
        return dlg.exec() == QDialog.Accepted
