"""Dialogue de paramétrage des exports."""
from __future__ import annotations

from pathlib import Path

import qtawesome as qta
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .common import set_kind, show_toast
from ..db import Database

_SUBDIRS = {
    "export_profs_path": "Feuilles Profs",
    "export_totalisation_path": "Totalisation",
    "export_moyennes_path": "Moyennes",
    "export_cr_path": "Compte Rendu",
}


class ExportSettingsDialog(QDialog):
    """Fenêtre de paramétrage des dossiers de destination d'export."""

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Paramètres d'exportation")
        self.setMinimumWidth(420)
        self._fields: dict[str, QLineEdit] = {}
        self._build()
        self._load()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(16)

        title = QLabel("Dossiers de destination des exports")
        title.setStyleSheet("font-size: 16px; font-weight: 700; padding: 8px 0;")
        root.addWidget(title)

        desc = QLabel(
            "Laissez vide pour utiliser le dossier par défaut de la classe. "
            "Les sous-dossiers sont créés automatiquement."
        )
        desc.setObjectName("ExportSettingsDesc")
        desc.setWordWrap(True)
        root.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(10)

        labels = {
            "export_profs_path": "Feuilles profs :",
            "export_totalisation_path": "Totalisation :",
            "export_moyennes_path": "Moyennes :",
            "export_cr_path": "Compte rendu :",
        }
        for key, label_text in labels.items():
            field = QLineEdit()
            field.setPlaceholderText("Dossier par défaut de la classe")
            field.setMinimumHeight(32)
            btn = QPushButton(qta.icon("fa5s.folder-open"), "")
            btn.setFixedSize(32, 32)
            btn.clicked.connect(lambda _, f=field: self._pick_folder(f))
            row = QHBoxLayout()
            row.addWidget(field, 1)
            row.addWidget(btn)
            form.addRow(label_text, row)
            self._fields[key] = field

        root.addLayout(form)

        # Boutons
        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_save = QPushButton(qta.icon("fa5s.save"), "Enregistrer")
        set_kind(btn_save, "primary")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)
        root.addLayout(btns)

    def _pick_folder(self, field: QLineEdit) -> None:
        current = field.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choisir un dossier", current)
        if folder:
            field.setText(folder)

    def _load(self) -> None:
        for key, field in self._fields.items():
            field.setText(self.db.get_setting(key, ""))

    def _save(self) -> None:
        for key, field in self._fields.items():
            self.db.set_setting(key, field.text().strip())
        show_toast(self, "Paramètres d'exportation enregistrés", "success")
        self.accept()


def show_export_settings_dialog(parent, db: Database) -> None:
    dlg = ExportSettingsDialog(db, parent)
    dlg.exec()


def ensure_export_dir(db: Database, setting_key: str) -> Path:
    """Retourne le dossier de destination pour un type d'export,
    crée automatiquement le sous-dossier si un chemin racine est configuré.
    """
    root = db.get_setting(setting_key, "").strip()
    if root:
        sub = _SUBDIRS.get(setting_key)
        dst = Path(root) / "Bulletin" / sub if sub else Path(root)
    else:
        from ..db import discover_class_by_db_path
        cls = discover_class_by_db_path(db.path)
        if cls is not None:
            dst = cls.folder
        else:
            dst = Path.cwd()
    dst.mkdir(parents=True, exist_ok=True)
    return dst
