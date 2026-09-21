"""Dialogue de bilan après une synchronisation.

Affiche :
- Le nombre de matières synchronisées
- Le total notes ajoutées / mises à jour / inchangées
- Le détail par matière (ligne par ligne)
- Les erreurs et avertissements éventuels

L'utilisateur peut choisir de fermer le dialogue, de re-synchroniser
(au cas où), ou d'ouvrir le dossier de la classe dans le navigateur
de fichiers.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

from qtpy.QtCore import Qt
from qtpy.QtGui import QFont, QTextOption
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .common import set_kind

from ..sync import SyncReport
from ..theme import current as tp

import qtawesome as qta

class SyncReportDialog(QDialog):
    """Affiche un :class:`SyncReport` à l'utilisateur."""

    def __init__(self, report: SyncReport, class_folder: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.report = report
        self.class_folder = class_folder
        self.setWindowTitle("Synchronisation terminée")
        self.resize(640, 480)
        self._build()
        self._populate()

    def _build(self) -> None:
        root = QVBoxLayout(self)

        self.title = QLabel()
        self.title.setFont(QFont("", 13, QFont.Bold))
        root.addWidget(self.title)

        self.subtitle = QLabel()
        self.subtitle.setStyleSheet("color: palette(placeholder-text);")
        root.addWidget(self.subtitle)

        self.body = QTextEdit()
        self.body.setReadOnly(True)
        self.body.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        font = QFont("Menlo")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamilies(["Menlo", "Consolas", "monospace"])
        self.body.setFont(font)
        root.addWidget(self.body, 1)

        # Boutons d'action
        actions = QHBoxLayout()
        self.btn_open_folder = QPushButton(qta.icon("fa5s.folder-open"), " Ouvrir le dossier classe")
        set_kind(self.btn_open_folder, "tonal")
        self.btn_open_folder.clicked.connect(self._open_folder)
        actions.addWidget(self.btn_open_folder)
        actions.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        set_kind(btns.button(QDialogButtonBox.Ok), "primary")
        btns.accepted.connect(self.accept)
        actions.addWidget(btns)
        root.addLayout(actions)

    def _populate(self) -> None:
        r = self.report
        self.title.setText(
            f"Synchronisation : {r.class_name}"
        )
        self.subtitle.setText(
            f"{r.matched_count}/{len(r.subjects)} matière(s) synchronisée(s) "
            f"en {r.duration_seconds:.2f}s"
        )

        lines = []
        lines.append(
            f"+ {r.total_added} nouvelle(s)    "
            f"~ {r.total_updated} mise(s) à jour    "
            f"= {r.total_unchanged} inchangée(s)"
        )
        lines.append("─" * 60)
        for s in r.subjects:
            lines.append(s.summary_line())
        # Section erreurs / warnings
        errors = [s for s in r.subjects if s.errors]
        if errors:
            lines.append("")
            lines.append("⚠ Erreurs :")
            for s in errors:
                lines.append(f"  • {s.subject_name} : {' / '.join(s.errors)}")
        warned = [s for s in r.subjects if s.warnings]
        if warned:
            lines.append("")
            lines.append("⚠ Avertissements :")
            for s in warned:
                if s.matched:  # ne pas dupliquer les "fichier introuvable"
                    for w in s.warnings:
                        lines.append(f"  • {s.subject_name} : {w}")
        self.body.setPlainText("\n".join(lines))

        # Couleur du titre selon le résultat
        if r.error_count == 0:
            color = tp().primary
        elif r.matched_count > r.error_count:
            color = tp().tertiary
        else:
            color = tp().danger
        self.title.setStyleSheet(f"color:{color};")

    def _open_folder(self) -> None:
        path = self.class_folder
        if not os.path.isdir(path):
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception:  # noqa: BLE001
            pass
