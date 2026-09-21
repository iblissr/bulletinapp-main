"""Dialog « Ajouter 1 élève » (pattern eco_paiement premium).

Présente un formulaire avec validation :
- N°            (auto-suggéré : dernier + 1)
- Matricule     (optionnel)
- Nom           (requis)
- Prénoms       (optionnel)
- Genre         (M / F / "")
- Date naissance (JJ/MM/AAAA, validée)

Bulletin premium : ce dialog permet l'ajout **unitaire**, complémentaire
à l'import XLSX massif (``ImportXlsxWizardDialog``).
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Optional

from qtpy.QtCore import Qt
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import qtawesome as qta

from ..db import Database
from .common import set_kind


# Format JJ/MM/AAAA — on accepte aussi JJ-MM-AAAA et JJ.MM.AAAA
_DATE_RE = re.compile(r"^\s*(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})\s*$")


def _parse_date(text: str) -> _dt.date | None:
    """Renvoie un :class:`datetime.date` ou ``None`` si invalide."""
    if not text:
        return None
    m = _DATE_RE.match(text)
    if not m:
        return None
    try:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000 if y < 70 else 1900
        return _dt.date(y, mo, d)
    except ValueError:
        return None


def _format_date(d: _dt.date | None) -> str:
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y")


class AddStudentDialog(QDialog):
    """Formulaire d'ajout d'un élève unique."""

    def __init__(
        self,
        db: Database,
        parent: Optional[QWidget] = None,
        preset_num: Optional[int] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Ajouter un élève")
        self.setModal(True)
        self.resize(420, 320)
        self._build(preset_num)

    # ------------------------------------------------------------------
    def _build(self, preset_num: Optional[int]) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # En-tête
        title_icon = QLabel()
        title_icon.setPixmap(qta.icon("fa5s.user-plus").pixmap(20, 20))
        title_text = QLabel("Nouvel élève")
        title_text.setFont(QFont("", 12, QFont.Weight.Bold))
        title_layout = QHBoxLayout()
        title_layout.setSpacing(8)
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_text)
        title_layout.addStretch(1)
        root.addLayout(title_layout)

        sub = QLabel("Renseignez les informations puis cliquez sur Enregistrer.")
        sub.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # Formulaire
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        # N° — auto-suggéré si non fourni
        self.ed_num = QSpinBox()
        self.ed_num.setRange(1, 9999)
        if preset_num is not None:
            self.ed_num.setValue(int(preset_num))
        else:
            # Suggestion : max(num) + 1
            existing = [int(s["num"]) for s in self.db.list_students() if s["num"]]
            self.ed_num.setValue(max(existing, default=0) + 1)
        form.addRow(self._lbl("N°", required=True), self.ed_num)

        # Matricule
        self.ed_mat = QLineEdit()
        self.ed_mat.setPlaceholderText("Optionnel")
        form.addRow(self._lbl("Matricule"), self.ed_mat)

        # Nom
        self.ed_nom = QLineEdit()
        self.ed_nom.setPlaceholderText("Nom de famille (MAJUSCULES)")
        form.addRow(self._lbl("Nom", required=True), self.ed_nom)

        # Prénoms
        self.ed_prenoms = QLineEdit()
        self.ed_prenoms.setPlaceholderText("Prénom(s)")
        form.addRow(self._lbl("Prénoms"), self.ed_prenoms)

        # Genre
        self.cb_genre = QComboBox()
        self.cb_genre.addItem("—", "")
        self.cb_genre.addItem("M", "M")
        self.cb_genre.addItem("F", "F")
        form.addRow(self._lbl("Genre"), self.cb_genre)

        # Date de naissance — champ texte + QDateEdit caché pour
        # faciliter la saisie (le calendrier est accessible via un
        # petit bouton "📅").
        self.ed_naissance = QLineEdit()
        self.ed_naissance.setPlaceholderText("JJ/MM/AAAA")
        self.ed_naissance.setText("")
        self.de_naissance = QDateEdit()
        self.de_naissance.setCalendarPopup(True)
        self.de_naissance.setDisplayFormat("dd/MM/yyyy")
        self.de_naissance.setDate(_dt.date(2010, 1, 1))
        self.de_naissance.dateChanged.connect(self._on_date_changed)

        naiss_row = QHBoxLayout()
        naiss_row.setSpacing(6)
        naiss_row.addWidget(self.ed_naissance, 1)
        btn_cal = QPushButton(qta.icon("fa5s.calendar-alt"), "")
        btn_cal.setToolTip("Choisir via le calendrier")
        btn_cal.setFixedWidth(34)
        btn_cal.setCursor(Qt.CursorShape.PointingHandCursor)
        set_kind(btn_cal, "tonal")
        btn_cal.clicked.connect(self._open_calendar)
        naiss_row.addWidget(btn_cal)
        naiss_w = QWidget()
        naiss_w.setLayout(naiss_row)
        form.addRow(self._lbl("Naissance"), naiss_w)

        root.addLayout(form)

        # Boutons
        btns = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        btns.button(QDialogButtonBox.Save).setText("Enregistrer")
        set_kind(btns.button(QDialogButtonBox.Save), "primary")
        btns.button(QDialogButtonBox.Cancel).setText("Annuler")
        set_kind(btns.button(QDialogButtonBox.Cancel), "tonal")
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        # Focus initial
        self.ed_nom.setFocus()

    # ------------------------------------------------------------------
    def _lbl(self, text: str, required: bool = False) -> QLabel:
        if required:
            t = f"{text} <span style='color:#DC2626;'>*</span>"
        else:
            t = text
        lbl = QLabel(t)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        return lbl

    def _open_calendar(self) -> None:
        """Ouvre le popup calendrier et recopie la date."""
        self.de_naissance.showPopup()

    def _on_date_changed(self, qdate) -> None:
        self.ed_naissance.setText(qdate.toString("dd/MM/yyyy"))

    # ------------------------------------------------------------------
    def _save(self) -> None:
        """Valide les champs et insère l'élève en base."""
        nom = (self.ed_nom.text() or "").strip()
        prenoms = (self.ed_prenoms.text() or "").strip()
        matricule = (self.ed_mat.text() or "").strip()
        genre = self.cb_genre.currentData() or ""
        num = int(self.ed_num.value())

        if not nom:
            QMessageBox.warning(
                self, self.windowTitle(),
                "Le nom de famille est obligatoire."
            )
            self.ed_nom.setFocus()
            return

        # Validation de la date
        naiss_text = (self.ed_naissance.text() or "").strip()
        if naiss_text:
            d = _parse_date(naiss_text)
            if d is None:
                QMessageBox.warning(
                    self, self.windowTitle(),
                    "Date de naissance invalide. Format attendu : JJ/MM/AAAA."
                )
                self.ed_naissance.setFocus()
                return
            naiss_text = _format_date(d)

        # Vérifier l'unicité du N°
        existing_nums = {int(s["num"]) for s in self.db.list_students()}
        if num in existing_nums:
            QMessageBox.warning(
                self, self.windowTitle(),
                f"Le N° {num} est déjà utilisé par un autre élève. "
                "Veuillez en choisir un autre."
            )
            self.ed_num.setFocus()
            return

        # Insertion
        try:
            self.db.add_student(
                num=num, nom=nom, prenoms=prenoms,
                matricule=matricule, genre=genre, naissance=naiss_text,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, self.windowTitle(),
                f"Erreur lors de l'enregistrement :\n{exc}"
            )
            return

        self.accept()

    # ------------------------------------------------------------------
    @staticmethod
    def add_student(
        db: Database, parent: Optional[QWidget] = None,
        preset_num: Optional[int] = None,
    ) -> bool:
        """Helper statique : ouvre le dialog et retourne ``True`` si
        l'élève a été ajouté.
        """
        dlg = AddStudentDialog(db, parent, preset_num=preset_num)
        return dlg.exec() == QDialog.Accepted
