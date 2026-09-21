"""Assistant de création d'une nouvelle classe.

Workflow en 7 étapes (implémentées comme pages d'un :class:`QWizard`) :

    1. Section          (Maternelle / Primaire / Collège / Lycée)
    2. Niveau           (dépend de la section : 6ème-3ème pour Collège, etc.)
    3. Sous-classes     (nombre + pattern de nommage : 1/2/3, I/II/III, A/B/C, custom)
    4. Détails classe   (nom, prof responsable, effectif, année scolaire)
    5. Matières         (pré-remplies depuis le catalogue, décochables)
    6. Coefficients     (ajustement des coefficients par matière)
    7. Élèves           (génération de la liste + édition rapide)

Chaque page implémente ``initializePage`` pour se configurer quand on
arrive dessus, et ``validatePage`` pour bloquer le passage à la page
suivante tant que les données ne sont pas valides.

À la fin, :meth:`ClassWizard.accept` crée physiquement :
- le dossier ``BULLETIN/<section>/<classe>/``
- la base SQLite ``<classe>/data/bulletin.db`` (paramètres + matières + élèves)
- un sous-dossier ``<classe>/bulletin/`` vide
- des fichiers ``<classe>/<Matière>.xlsx`` vides prêts à être remplis
  par les enseignants.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from qtpy.QtCore import Qt
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from .. import db as db_module
from ..workspace import find_bulletin_root
from ..screen_utils import get_scale
from ..widgets.common import set_kind
from .subjects_catalog import (
    SECTIONS,
    SectionDef,
    expand_pattern,
    list_sections,
)

import qtawesome as qta

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Données collectées par l'assistant
# ---------------------------------------------------------------------------
@dataclass
class ClassDraft:
    """Résultat intermédiaire du wizard. Les champs sont remplis au fur
    et à mesure par les pages.
    """

    section_key: str = ""
    level_key: str = ""
    sub_count: int = 1
    pattern: str = "numeric"
    custom_suffixes: list[str] = field(default_factory=list)
    sub_class_names: list[str] = field(default_factory=list)
    # Détails par sous-classe
    classes: list[dict] = field(default_factory=list)
    # Matières sélectionnées (avec coefficients ajustés)
    subjects: list[tuple[str, float]] = field(default_factory=list)
    # Élèves (par sous-classe, indexé par num)
    students_by_class: dict[str, list[dict]] = field(default_factory=dict)
    # Paramètres globaux (collectés dans _ClassDetailsPage)
    etablissement: str = "Lycée Saint Joseph"
    annee_scolaire: str = ""


# ---------------------------------------------------------------------------
#  Pages de l'assistant
# ---------------------------------------------------------------------------
def _title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(QFont("", 14, QFont.Bold))
    lbl.setStyleSheet("color: palette(highlight);")
    return lbl


def _sub(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color: palette(placeholder-text);")
    lbl.setWordWrap(True)
    return lbl


class _SectionPage(QWizardPage):
    """Étape 1 : choix de la section."""

    def __init__(self, draft: ClassDraft) -> None:
        super().__init__()
        self.draft = draft
        self.setTitle("Section")
        self.setSubTitle("Choisissez la section de la classe à créer.")
        v = QVBoxLayout(self)
        v.addWidget(_sub(
            "La section détermine les niveaux disponibles (6ème à 3ème "
            "pour le Collège, par exemple) et la liste de matières par défaut."
        ))
        self.listw = QListWidget()
        for s in list_sections():
            it = QListWidgetItem(f"{s.label}    —    {s.description}")
            it.setData(Qt.ItemDataRole.UserRole, s.key)
            self.listw.addItem(it)
        self.listw.setCurrentRow(0)
        v.addWidget(self.listw, 1)
        self.listw.currentItemChanged.connect(self._on_change)

    def _on_change(self, *_):
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return self.listw.currentItem() is not None

    def validatePage(self) -> bool:
        it = self.listw.currentItem()
        if it is None:
            return False
        self.draft.section_key = str(it.data(Qt.ItemDataRole.UserRole))
        return True


class _LevelPage(QWizardPage):
    """Étape 2 : choix du niveau (dépend de la section)."""

    def __init__(self, draft: ClassDraft) -> None:
        super().__init__()
        self.draft = draft
        self.setTitle("Niveau")
        self.setSubTitle("Choisissez le niveau de la classe.")
        v = QVBoxLayout(self)
        self.lbl_help = _sub("Sélectionnez d'abord une section.")
        v.addWidget(self.lbl_help)
        self.listw = QListWidget()
        v.addWidget(self.listw, 1)
        self.listw.currentItemChanged.connect(
            lambda *_: self.completeChanged.emit()
        )

    def initializePage(self) -> None:
        section = SECTIONS.get(self.draft.section_key)
        if not section:
            return
        self.lbl_help.setText(
            f"Section sélectionnée : <b>{section.label}</b>. "
            f"Choisissez le niveau de la classe."
        )
        self.listw.clear()
        for key, label in section.levels:
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, key)
            self.listw.addItem(it)
        self.listw.setCurrentRow(0)

    def isComplete(self) -> bool:
        return self.listw.currentItem() is not None

    def validatePage(self) -> bool:
        it = self.listw.currentItem()
        if it is None:
            return False
        self.draft.level_key = str(it.data(Qt.ItemDataRole.UserRole))
        return True


class _SubClassPage(QWizardPage):
    """Étape 3 : nombre + pattern de sous-classes."""

    def __init__(self, draft: ClassDraft) -> None:
        super().__init__()
        self.draft = draft
        self.setTitle("Sous-classes")
        self.setSubTitle("Combien de sous-classes et quel pattern de nommage ?")
        v = QVBoxLayout(self)
        v.addWidget(_sub(
            "Exemple : pour une 6ème avec deux sous-classes nommées « 1 » et « 2 », "
            "choisissez 2 sous-classes avec le pattern numérique. Les dossiers "
            "seront nommés 6EME1 et 6EME2."
        ))

        gb = QGroupBox("Nombre de sous-classes")
        h = QHBoxLayout(gb)
        self.sb_count = QSpinBox()
        self.sb_count.setRange(1, 20)
        self.sb_count.setValue(1)
        self.sb_count.valueChanged.connect(self._recompute_preview)
        h.addWidget(QLabel("Nombre :"))
        h.addWidget(self.sb_count)
        h.addStretch()
        v.addWidget(gb)

        gb2 = QGroupBox("Pattern de nommage")
        v2 = QVBoxLayout(gb2)
        self.cb_pattern = QComboBox()
        from .subjects_catalog import PATTERNS
        for key, label in PATTERNS:
            self.cb_pattern.addItem(label, key)
        self.cb_pattern.currentIndexChanged.connect(self._on_pattern_change)
        v2.addWidget(self.cb_pattern)

        self.custom_widget = QWidget()
        cw_v = QVBoxLayout(self.custom_widget)
        cw_v.setContentsMargins(0, 8, 0, 0)
        cw_v.addWidget(QLabel(
            "<i>Une ligne par sous-classe. Laissez vide pour générer automatiquement.</i>"
        ))
        self.custom_edit = QLineEdit()
        self.custom_edit.setPlaceholderText("Ex : LI, LII, S")
        self.custom_edit.textChanged.connect(self._recompute_preview)
        cw_v.addWidget(self.custom_edit)
        v2.addWidget(self.custom_widget)
        v.addWidget(gb2)

        # Prévisualisation
        self.lbl_preview_title = QLabel("<b>Aperçu :</b>")
        v.addWidget(self.lbl_preview_title)
        self.lbl_preview = QLabel()
        self.lbl_preview.setStyleSheet(
            "background:palette(midlight);padding:8px;border-radius:4px;"
            "font-family:monospace;"
        )
        self.lbl_preview.setWordWrap(True)
        v.addWidget(self.lbl_preview)
        v.addStretch()
        self._on_pattern_change(0)

    def _on_pattern_change(self, _idx: int) -> None:
        is_custom = self.cb_pattern.currentData() == "custom"
        self.custom_widget.setVisible(is_custom)
        self._recompute_preview()

    def _recompute_preview(self) -> None:
        self.draft.sub_count = int(self.sb_count.value())
        self.draft.pattern = str(self.cb_pattern.currentData() or "numeric")
        suffixes = None
        if self.draft.pattern == "custom":
            raw = self.custom_edit.text().strip()
            suffixes = [s.strip() for s in raw.split(",") if s.strip()]
            # On tolère que l'utilisateur n'ait pas encore tout saisi
            # (on complète avec des lettres par défaut)
            while suffixes and len(suffixes) < self.draft.sub_count:
                idx = len(suffixes)
                suffixes.append(chr(ord("A") + idx))
        try:
            names = expand_pattern(
                self.draft.level_key or "?",
                self.draft.pattern,
                self.draft.sub_count,
                suffixes,
            )
            self.draft.custom_suffixes = suffixes or []
            self.draft.sub_class_names = names
            self.lbl_preview.setText(", ".join(names))
        except Exception as exc:  # noqa: BLE001
            self.lbl_preview.setText(f"<span style='color:#b91c1c;'>{exc}</span>")

    def validatePage(self) -> bool:
        if not self.draft.sub_class_names:
            QMessageBox.warning(self, "Sous-classes",
                                "Impossible de générer les noms de sous-classes.")
            return False
        if self.draft.pattern == "custom":
            raw = self.custom_edit.text().strip()
            if not raw:
                QMessageBox.warning(
                    self, "Sous-classes",
                    "Saisissez les suffixes séparés par des virgules "
                    "(ex : LI, LII, S)."
                )
                return False
        return True


class _ClassDetailsPage(QWizardPage):
    """Étape 4 : détails par sous-classe (nom, prof, effectif)."""

    def __init__(self, draft: ClassDraft) -> None:
        super().__init__()
        self.draft = draft
        self.setTitle("Détails des classes")
        self.setSubTitle("Renseignez l'établissement et les classes à créer.")
        self._widgets: list[dict] = []
        v = QVBoxLayout(self)
        self.help_label = _sub("")
        v.addWidget(self.help_label)

        # Paramètres généraux : établissement, année scolaire
        general_box = QGroupBox("Paramètres généraux")
        general_grid = QFormLayout(general_box)
        self.ed_etablissement = QLineEdit()
        self.ed_etablissement.setPlaceholderText("Lycée Saint Joseph")
        general_grid.addRow("Établissement :", self.ed_etablissement)
        self.ed_annee = QLineEdit()
        self.ed_annee.setPlaceholderText("2025-2026")
        general_grid.addRow("Année scolaire :", self.ed_annee)
        v.addWidget(general_box)

        self.form_holder = QWidget()
        self.form_layout = QVBoxLayout(self.form_holder)
        v.addWidget(self.form_holder, 1)
        v.addStretch()

    def initializePage(self) -> None:
        # Reconstruction forcée à chaque visite pour refléter les
        # changements du nombre de sous-classes (aller-retour page 3)
        for w in self._widgets:
            for child in w.values():
                if isinstance(child, QWidget):
                    child.deleteLater()
        self._widgets.clear()
        # Vider le layout
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # En-tête commun
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("<b>Sous-classe</b>"), 1)
        header_row.addWidget(QLabel("<b>Nom complet</b>"), 2)
        header_row.addWidget(QLabel("<b>Prof responsable</b>"), 2)
        header_row.addWidget(QLabel("<b>Effectif</b>"), 1)
        header_row.addWidget(QLabel("<b>Nb filles</b>"), 1)
        header_row.addWidget(QLabel("<b>Nb garçons</b>"), 1)
        wrap = QWidget()
        wrap.setLayout(header_row)
        self.form_layout.addWidget(wrap)

        for name in self.draft.sub_class_names:
            row = QHBoxLayout()
            lbl = QLabel(f"<code>{name}</code>")
            lbl.setMinimumWidth(80)
            row.addWidget(lbl, 1)
            ed_classe = QLineEdit(name)
            ed_classe.setPlaceholderText("Nom complet de la classe")
            row.addWidget(ed_classe, 2)
            ed_prof = QLineEdit()
            ed_prof.setPlaceholderText("Nom du prof principal")
            row.addWidget(ed_prof, 2)
            sb_eff = QSpinBox()
            sb_eff.setRange(0, 200)
            sb_eff.setValue(40)
            row.addWidget(sb_eff, 1)
            sb_f = QSpinBox()
            sb_f.setRange(0, 200)
            row.addWidget(sb_f, 1)
            sb_g = QSpinBox()
            sb_g.setRange(0, 200)
            row.addWidget(sb_g, 1)
            wrap = QWidget()
            wrap.setLayout(row)
            self.form_layout.addWidget(wrap)
            self._widgets.append({
                "name": name, "classe": ed_classe, "prof": ed_prof,
                "effectif": sb_eff, "filles": sb_f, "garcons": sb_g,
            })
        if not self.ed_etablissement.text().strip():
            self.ed_etablissement.setText("Lycée Saint Joseph")
        if not self.ed_annee.text().strip():
            self.ed_annee.setText("2025-2026")
        self.help_label.setText(
            f"Vous allez créer <b>{len(self.draft.sub_class_names)} "
            f"classe(s)</b> au sein du niveau "
            f"<b>{self.draft.level_key}</b> ({SECTIONS[self.draft.section_key].label})."
        )

    def validatePage(self) -> bool:
        self.draft.etablissement = self.ed_etablissement.text().strip() or "Lycée Saint Joseph"
        self.draft.annee_scolaire = self.ed_annee.text().strip() or "2025-2026"
        classes: list[dict] = []
        for w in self._widgets:
            classes.append({
                "folder_name": w["name"],
                "display_name": w["classe"].text().strip() or w["name"],
                "prof": w["prof"].text().strip(),
                "effectif": int(w["effectif"].value()),
                "filles": int(w["filles"].value()),
                "garcons": int(w["garcons"].value()),
            })
        self.draft.classes = classes
        return True


class _SubjectsPage(QWizardPage):
    """Étape 5 : sélection des matières (pré-remplies, modifiables)."""

    def __init__(self, draft: ClassDraft) -> None:
        super().__init__()
        self.draft = draft
        self.setTitle("Matières")
        self.setSubTitle(
            "Cochez les matières enseignées dans cette classe. "
            "Vous pourrez ajuster les coefficients à l'étape suivante."
        )
        self._checkboxes: list[QCheckBox] = []
        v = QVBoxLayout(self)
        v.addWidget(_sub(
            "Les matières ci-dessous sont issues du catalogue de la section. "
            "Décochez celles qui ne sont pas enseignées dans votre classe."
        ))
        self.scroll = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll)
        v.addWidget(self.scroll, 1)

    def initializePage(self) -> None:
        if self._checkboxes:
            return
        section = SECTIONS[self.draft.section_key]
        for name, coeff in section.subjects:
            cb = QCheckBox(f"{name}    (coeff. recommandé : {coeff:g})")
            cb.setChecked(True)
            cb.setProperty("_subject_name", name)
            cb.setProperty("_subject_coeff", float(coeff))
            self.scroll_layout.addWidget(cb)
            self._checkboxes.append(cb)
        self.scroll_layout.addStretch()

    def validatePage(self) -> bool:
        if not any(cb.isChecked() for cb in self._checkboxes):
            QMessageBox.warning(self, "Matières",
                                "Sélectionnez au moins une matière.")
            return False
        self.draft.subjects = [
            (
                cb.property("_subject_name"),
                float(cb.property("_subject_coeff")),
            )
            for cb in self._checkboxes if cb.isChecked()
        ]
        return True


class _CoefficientsPage(QWizardPage):
    """Étape 6 : coefficients ajustables."""

    def __init__(self, draft: ClassDraft) -> None:
        super().__init__()
        self.draft = draft
        self.setTitle("Coefficients")
        self.setSubTitle("Ajustez les coefficients de chaque matière.")
        v = QVBoxLayout(self)
        v.addWidget(_sub(
            "Les coefficients servent au calcul des moyennes. "
            "Augmentez le coefficient des matières principales ( Maths, Français, … )."
        ))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Matière", "Coefficient", "Enseignant"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table, 1)

    def initializePage(self) -> None:
        if self.table.rowCount() > 0:
            return
        for name, coeff in self.draft.subjects:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(name))
            spin = QDoubleSpinBox()
            spin.setRange(0, 20)
            spin.setDecimals(1)
            spin.setSingleStep(0.5)
            spin.setValue(float(coeff))
            self.table.setCellWidget(r, 1, spin)
            self.table.setItem(r, 2, QTableWidgetItem(""))

    def validatePage(self) -> bool:
        new_subjects: list[tuple[str, float]] = []
        teachers: dict[str, str] = {}
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0).text() if self.table.item(r, 0) else ""
            spin = self.table.cellWidget(r, 1)
            coeff = float(spin.value()) if spin else 1.0
            teacher = self.table.item(r, 2).text() if self.table.item(r, 2) else ""
            new_subjects.append((name, coeff))
            if teacher.strip():
                teachers[name] = teacher.strip()
        self.draft.subjects = new_subjects
        self.draft._teachers = teachers  # consommé par l'étape finale
        return True


class _StudentsPage(QWizardPage):
    """Étape 7 : génération / édition de la liste des élèves."""

    def __init__(self, draft: ClassDraft) -> None:
        super().__init__()
        self.draft = draft
        self.setTitle("Élèves")
        self.setSubTitle("Génération de la liste des élèves.")
        v = QVBoxLayout(self)
        v.addWidget(_sub(
            "Pour chaque sous-classe, indiquez l'effectif puis complétez "
            "les noms (double-clic sur une cellule pour éditer). "
            "Les élèves peuvent être renommés ou ajoutés/supprimés plus tard."
        ))
        # Sélecteur de sous-classe
        h = QHBoxLayout()
        h.addWidget(QLabel("Sous-classe :"))
        self.cb_class = QComboBox()
        for c in draft.classes:
            self.cb_class.addItem(c["display_name"], c["folder_name"])
        self.cb_class.currentIndexChanged.connect(self._on_class_change)
        h.addWidget(self.cb_class, 1)
        h.addStretch()
        v.addLayout(h)
        # Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["N°", "Matricule", "Nom", "Prénoms"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        v.addWidget(self.table, 1)
        # Boutons
        h2 = QHBoxLayout()
        self.btn_add = QPushButton(qta.icon("fa5s.plus"), " Ajouter une ligne")
        set_kind(self.btn_add, "tonal")
        self.btn_add.clicked.connect(self._add_row)
        h2.addWidget(self.btn_add)
        self.btn_del = QPushButton(qta.icon("fa5s.trash-alt"), " Supprimer la ligne")
        set_kind(self.btn_del, "danger")
        self.btn_del.clicked.connect(self._del_row)
        h2.addWidget(self.btn_del)
        h2.addStretch()
        v.addLayout(h2)
        self._current_class = None
        self._dirty: set[str] = set()

    def initializePage(self) -> None:
        if not self._dirty:
            # Première entrée : on remplit toutes les sous-classes
            for c in self.draft.classes:
                rows = []
                for i in range(1, c["effectif"] + 1):
                    rows.append({
                        "num": i,
                        "matricule": "",
                        "nom": "",
                        "prenoms": "",
                    })
                self.draft.students_by_class[c["folder_name"]] = rows
                self._dirty.add(c["folder_name"])
        self._on_class_change(0)

    def _on_class_change(self, _idx: int) -> None:
        # Sauver l'état précédent
        if self._current_class is not None:
            self._save_current()
        name = self.cb_class.currentData()
        if not name:
            return
        self._current_class = name
        rows = self.draft.students_by_class.get(name, [])
        self.table.setRowCount(0)
        for r in rows:
            self._insert_row_widgets(r)

    def _insert_row_widgets(self, data: dict) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        items = [
            QTableWidgetItem(str(data.get("num", r + 1))),
            QTableWidgetItem(data.get("matricule", "")),
            QTableWidgetItem(data.get("nom", "")),
            QTableWidgetItem(data.get("prenoms", "")),
        ]
        items[0].setFlags(items[0].flags() & ~Qt.ItemFlag.ItemIsEditable)
        for c, it in enumerate(items):
            self.table.setItem(r, c, it)

    def _save_current(self) -> None:
        if self._current_class is None:
            return
        rows = []
        for r in range(self.table.rowCount()):
            try:
                num = int(self.table.item(r, 0).text())
            except (TypeError, ValueError):
                num = r + 1
            rows.append({
                "num": num,
                "matricule": self.table.item(r, 1).text() if self.table.item(r, 1) else "",
                "nom": self.table.item(r, 2).text() if self.table.item(r, 2) else "",
                "prenoms": self.table.item(r, 3).text() if self.table.item(r, 3) else "",
            })
        self.draft.students_by_class[self._current_class] = rows

    def _add_row(self) -> None:
        if self._current_class is None:
            return
        n = self.table.rowCount() + 1
        self._insert_row_widgets({"num": n, "matricule": "", "nom": "", "prenoms": ""})

    def _del_row(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def validatePage(self) -> bool:
        self._save_current()
        return True


# ---------------------------------------------------------------------------
#  L'assistant
# ---------------------------------------------------------------------------
class ClassWizard(QWizard):
    """Assistant de création d'une ou plusieurs sous-classes.

    Le résultat de l'assistant est un objet :class:`ClassDraft` ;
    l'appelant peut alors appeler :func:`create_workspace_from_draft`
    pour créer physiquement les dossiers et bases SQLite.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.draft = ClassDraft()
        self.setWindowTitle("Assistant — Création d'une nouvelle classe")
        self.setMinimumSize(*get_scale().min_window_size)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)

        self.addPage(_SectionPage(self.draft))
        self.addPage(_LevelPage(self.draft))
        self.addPage(_SubClassPage(self.draft))
        self.addPage(_ClassDetailsPage(self.draft))
        self.addPage(_SubjectsPage(self.draft))
        self.addPage(_CoefficientsPage(self.draft))
        self.addPage(_StudentsPage(self.draft))
        # Page de fin "synthèse"
        self.setOption(QWizard.WizardOption.IndependentPages, False)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)

    def accept(self) -> None:
        # Sauver TOUTES les sous-classes (pas seulement la courante)
        for page in self.findChildren(_StudentsPage):
            for name in page.draft.sub_class_names:
                page._current_class = name
                page._save_current()
        # Créer physiquement les workspaces
        try:
            created = create_workspaces_from_draft(self.draft)
        except Exception as exc:  # noqa: BLE001
            log.exception("Workspace creation failed")
            QMessageBox.critical(
                self, "Création échouée",
                f"Impossible de créer les classes :\n\n{exc}"
            )
            return
        QMessageBox.information(
            self, "Classes créées",
            f"{len(created)} classe(s) créée(s) avec succès :\n\n"
            + "\n".join(f"  • {c}" for c in created)
        )
        super().accept()


# ---------------------------------------------------------------------------
#  Création physique du workspace
# ---------------------------------------------------------------------------
def create_workspaces_from_draft(draft: ClassDraft) -> list[str]:
    """Crée les dossiers + bases SQLite + fichiers .xlsx vides.

    Retourne la liste des noms de classes effectivement créées.
    Lève :class:`FileExistsError` si une classe portant le même nom
    existe déjà (l'appelant doit avoir vérifié au préalable).
    """
    if not draft.classes:
        raise ValueError("Aucune classe à créer.")
    section = SECTIONS[draft.section_key]
    root = find_bulletin_root()
    section_dir = root / section.label
    section_dir.mkdir(exist_ok=True)
    created: list[str] = []
    teachers = getattr(draft, "_teachers", {}) or {}
    for c in draft.classes:
        folder = section_dir / c["folder_name"]
        if folder.exists():
            raise FileExistsError(
                f"Le dossier {folder} existe déjà. "
                f"Choisissez un autre nom ou supprimez-le d'abord."
            )
        (folder / "data").mkdir(parents=True)
        (folder / "bulletin").mkdir(parents=True)
        db_path = folder / "data" / "bulletin.db"
        # Crée la base et seed les matières
        d = db_module.Database(str(db_path))
        d.set_setting("etablissement", draft.etablissement)
        d.set_setting("directeur", "Directeur")
        d.set_setting("annee_scolaire", draft.annee_scolaire)
        d.set_setting("classe", c["display_name"])
        d.set_setting("nb_examens", "6")
        d.set_setting("effectif", str(c["effectif"]))
        d.set_setting("nb_filles", str(c["filles"]))
        d.set_setting("nb_garcons", str(c["garcons"]))
        d.set_setting("nb_min_examens", "3")
        d.set_setting("prof_principal", c["prof"])
        d.set_setting("section", section.label)
        d.set_setting("niveau", draft.level_key)
        # Reseed les matières avec coefficients + enseignants
        # (clear_subjects au préalable pour éviter le doublon avec
        # l'auto-seed de Database._init_defaults)
        subjects_rows = [
            (name, coeff, teachers.get(name, ""))
            for name, coeff in draft.subjects
        ]
        d.set_subjects(subjects_rows)
        # Importe les élèves
        rows = draft.students_by_class.get(c["folder_name"], [])
        if rows:
            # Complète les colonnes manquantes (genre, naissance) avec
            # des valeurs vides — elles ne sont pas demandées à
            # l'assistant mais la DB les attend.
            for r in rows:
                r.setdefault("genre", "")
                r.setdefault("naissance", "")
            d.bulk_update_students(rows)
        d.close()
        # Génère des fichiers .xlsx vides pour chaque matière
        _create_blank_subject_xlsx(folder, section, draft, c)
        created.append(c["folder_name"])
    return created


def _create_blank_subject_xlsx(
    folder: Path,
    section: SectionDef,
    draft: ClassDraft,
    class_info: dict,
) -> None:
    """Crée un fichier ``<Matière>.xlsx`` vide pour chaque matière.

    Le fichier contient 4 lignes d'en-tête (métadonnées : établissement,
    classe, prof, année) + 1 ligne d'en-têtes de colonnes + N lignes
    vides (une par élève). Les profs n'ont qu'à remplir les notes.
    """
    import openpyxl  # noqa: WPS433
    from openpyxl.styles import Font

    students = draft.students_by_class.get(class_info["folder_name"], [])
    teachers = getattr(draft, "_teachers", {}) or {}

    # Les matières = celles qui ont été retenues
    for name, coeff in draft.subjects:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        # Métadonnées (lignes 2-4)
        ws["B2"] = draft.etablissement
        ws["E2"] = name
        ws["B3"] = class_info["display_name"]
        ws["C3"] = "Coeff"
        ws["F3"] = "Prof"
        ws["B4"] = f"Année scolaire : {draft.annee_scolaire}"
        ws["C4"] = float(coeff)
        ws["F4"] = teachers.get(name, class_info["prof"])
        # Ligne d'en-têtes
        headers = ["Num", "Nom et Prénoms",
                   "M.J 1", "Compo 1", "M.J 2", "Compo 2", "M.J 3", "Compo 3"]
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=5, column=c, value=h)
            cell.font = Font(bold=True)
        # Lignes élèves
        for r, st in enumerate(students, start=6):
            ws.cell(row=r, column=1, value=int(st.get("num", r - 5)))
            full = (
                f"{st.get('nom', '')} {st.get('prenoms', '')}".strip()
                or f"Élève {st.get('num', r - 5)}"
            )
            ws.cell(row=r, column=2, value=full)
        out = folder / f"{name}.xlsx"
        wb.save(out)


# ---------------------------------------------------------------------------
#  Helper d'invocation
# ---------------------------------------------------------------------------
def run_wizard(parent: Optional[QWidget] = None) -> Optional[ClassDraft]:
    """Lance l'assistant modalement. Retourne le :class:`ClassDraft`
    en cas de succès, ``None`` si l'utilisateur a annulé.
    """
    wiz = ClassWizard(parent)
    if wiz.exec() == QWizard.DialogCode.Accepted:
        return wiz.draft
    return None
