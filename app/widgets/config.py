"""Widget Configuration (équivalent de la feuille « principale »).

Refonte visuelle style eco_paiement : TopContainer + Panels,
icônes qtawesome, plus d'émojis inline.
Le panneau identité est en mode lecture par défaut et bascule
en édition via le bouton « Modifier ».
"""
from __future__ import annotations

import qtawesome as qta
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .common import Panel, TopContainer, set_kind, show_toast
from .table_helpers import wrap_layout as _wrap
from ..db import Database


class ConfigWidget(QWidget):
    """Onglet Configuration : infos établissement + tableau matières."""

    changed = Signal()

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self._edit_mode = False
        self._snapshot: dict = {}
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(14)

        # --- En-tête de page ---
        self._btn_save_subj = QPushButton(qta.icon("fa5s.save"), "Enregistrer les matières")
        set_kind(self._btn_save_subj, "primary")
        self._btn_save_subj.clicked.connect(self._save)

        self._top = TopContainer(
            "CF",
            "Configuration",
            "Identité de l'établissement et matières enseignées",
        )
        self._top.add_action(self._btn_save_subj)
        root.addWidget(self._top)

        # ---------- Panel identité (lecture/édition) ----------
        self._panel_info = Panel(
            "Informations de l'établissement", icon=qta.icon("fa5s.school")
        )
        # Bouton Modifier en haut à droite du panel (dans l'en-tête)
        self._btn_edit = QPushButton(qta.icon("fa5s.pen"), "Modifier")
        set_kind(self._btn_edit, "tonal")
        self._btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_edit.clicked.connect(self._enter_edit_mode)
        self._panel_info.add_header_action(self._btn_edit)

        # Conteneur du corps (wrap dans QWidget pour addLayout→addWidget)
        body_holder = QWidget()
        body = QVBoxLayout(body_holder)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)

        # Vue lecture (par défaut)
        self._view_read = QWidget()
        grid = QGridLayout(self._view_read)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)
        # Colonnes : 6 paires label/valeur
        self._lbl_etablissement = self._make_value_label()
        self._lbl_directeur = self._make_value_label()
        self._lbl_annee = self._make_value_label()
        self._lbl_classe = self._make_value_label()
        self._lbl_logo = self._make_value_label()
        self._lbl_logo.setStyleSheet("color: palette(placeholder-text); font-size: 12px;")
        self._lbl_nb_examens = self._make_value_label()
        self._lbl_effectif = self._make_value_label()
        self._lbl_filles = self._make_value_label()
        self._lbl_garcons = self._make_value_label()
        self._lbl_nb_min = self._make_value_label()
        self._lbl_nb_matieres = self._make_value_label()
        self._lbl_prof_principal = self._make_value_label()  # bulletin premium

        # Colonne gauche
        grid.addWidget(self._field_label("Établissement"), 0, 0)
        grid.addWidget(self._lbl_etablissement,            0, 1)
        grid.addWidget(self._field_label("Directeur"),     1, 0)
        grid.addWidget(self._lbl_directeur,                1, 1)
        grid.addWidget(self._field_label("Année scolaire"), 2, 0)
        grid.addWidget(self._lbl_annee,                    2, 1)
        # Colonne droite
        grid.addWidget(self._field_label("Classe"),         0, 2)
        grid.addWidget(self._lbl_classe,                    0, 3)
        grid.addWidget(self._field_label("Examens"),        1, 2)
        grid.addWidget(self._lbl_nb_examens,                1, 3)
        grid.addWidget(self._field_label("Effectif"),       2, 2)
        grid.addWidget(self._lbl_effectif,                  2, 3)
        # Ligne du bas
        grid.addWidget(self._field_label("Filles / Garçons"), 3, 0)
        grid.addWidget(self._lbl_filles,                      3, 1)
        grid.addWidget(self._field_label("Min. examens"),     3, 2)
        grid.addWidget(self._lbl_nb_min,                      3, 3)
        grid.addWidget(self._field_label("Matières (auto)"),  4, 0)
        grid.addWidget(self._lbl_nb_matieres,                 4, 1)
        grid.addWidget(self._field_label("Logo"),             4, 2)
        grid.addWidget(self._lbl_logo,                        4, 3)
        # Bulletin premium : prof_principal sur une 5ᵉ ligne
        grid.addWidget(self._field_label("Professeur principal(e)"), 5, 0)
        grid.addWidget(self._lbl_prof_principal,                5, 1, 1, 3)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(3, 3)
        body.addWidget(self._view_read)

        # Vue édition (cachée par défaut) — grille dense 4 colonnes
        self._view_edit = QWidget()
        self._view_edit.setVisible(False)
        edit_grid = QGridLayout(self._view_edit)
        edit_grid.setHorizontalSpacing(14)
        edit_grid.setVerticalSpacing(6)
        edit_grid.setContentsMargins(0, 0, 0, 0)

        self.ed_etablissement = QLineEdit()
        self.ed_directeur = QLineEdit()
        self.ed_annee = QLineEdit()
        self.ed_classe = QLineEdit()
        self.sb_nb_examens = QSpinBox()
        self.sb_nb_examens.setRange(1, 6)
        self.sb_effectif = QSpinBox()
        self.sb_effectif.setRange(0, 500)
        self.sb_filles = QSpinBox()
        self.sb_filles.setRange(0, 500)
        self.sb_garcons = QSpinBox()
        self.sb_garcons.setRange(0, 500)
        self.sb_nb_matieres = QSpinBox()
        self.sb_nb_matieres.setRange(0, 20)
        self.sb_nb_matieres.setReadOnly(True)
        self.sb_nb_matieres.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.dsb_nb_min = QDoubleSpinBox()
        self.dsb_nb_min.setRange(0, 6)
        self.dsb_nb_min.setDecimals(0)
        self.ed_logo = QLineEdit()
        self.ed_prof_principal = QLineEdit()  # bulletin premium
        self.ed_prof_principal.setPlaceholderText("Nom du professeur principal")

        # Ligne 0 : identité (2 paires large)
        edit_grid.addWidget(self._field_label("Établissement"), 0, 0)
        edit_grid.addWidget(self.ed_etablissement,                0, 1, 1, 3)
        edit_grid.addWidget(self._field_label("Directeur"),     1, 0)
        edit_grid.addWidget(self.ed_directeur,                    1, 1, 1, 3)
        # Ligne 2 : 4 petits champs
        edit_grid.addWidget(self._field_label("Année"),          2, 0)
        edit_grid.addWidget(self.ed_annee,                        2, 1)
        edit_grid.addWidget(self._field_label("Classe"),         2, 2)
        edit_grid.addWidget(self.ed_classe,                       2, 3)
        # Ligne 3 : 4 petits champs
        edit_grid.addWidget(self._field_label("Examens"),        3, 0)
        edit_grid.addWidget(self.sb_nb_examens,                   3, 1)
        edit_grid.addWidget(self._field_label("Min."),           3, 2)
        edit_grid.addWidget(self.dsb_nb_min,                      3, 3)
        # Ligne 4 : effectif / filles / garçons
        edit_grid.addWidget(self._field_label("Effectif"),       4, 0)
        edit_grid.addWidget(self.sb_effectif,                     4, 1)
        edit_grid.addWidget(self._field_label("Filles"),         4, 2)
        edit_grid.addWidget(self.sb_filles,                       4, 3)
        # Ligne 5 : garçons + matières (auto, read-only)
        edit_grid.addWidget(self._field_label("Garçons"),        5, 0)
        edit_grid.addWidget(self.sb_garcons,                      5, 1)
        edit_grid.addWidget(self._field_label("Matières"),        5, 2)
        edit_grid.addWidget(self.sb_nb_matieres,                  5, 3)
        # Ligne 6 : logo (pleine largeur)
        self.btn_logo = QPushButton(qta.icon("fa5s.image"), "Choisir…")
        set_kind(self.btn_logo, "outlined")
        self.btn_logo.clicked.connect(self._pick_logo)
        logo_row = QHBoxLayout()
        logo_row.setSpacing(6)
        logo_row.addWidget(self.ed_logo, 1)
        logo_row.addWidget(self.btn_logo)
        edit_grid.addWidget(self._field_label("Logo (PNG)"),     6, 0)
        edit_grid.addLayout(logo_row,                              6, 1, 1, 3)
        # Bulletin premium : prof_principal en ligne 7
        edit_grid.addWidget(self._field_label("Professeur principal(e)"), 7, 0)
        edit_grid.addWidget(self.ed_prof_principal,                7, 1, 1, 3)
        edit_grid.setColumnStretch(1, 2)
        edit_grid.setColumnStretch(3, 2)
        body.addWidget(self._view_edit)

        # Boutons Enregistrer / Annuler (cachés en mode lecture)
        self._edit_actions = QWidget()
        self._edit_actions.setVisible(False)
        self._edit_actions.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        edit_actions = QHBoxLayout(self._edit_actions)
        edit_actions.setContentsMargins(0, 0, 0, 0)
        edit_actions.setSpacing(8)
        edit_actions.addStretch(1)
        self._btn_cancel = QPushButton(qta.icon("fa5s.times"), "Annuler")
        self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancel.setMinimumWidth(80)
        set_kind(self._btn_cancel, "outlined")
        self._btn_cancel.clicked.connect(self._cancel_edit)
        self._btn_save_info = QPushButton(qta.icon("fa5s.check"), "Enregistrer")
        self._btn_save_info.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save_info.setMinimumWidth(100)
        set_kind(self._btn_save_info, "primary")
        self._btn_save_info.clicked.connect(self._save_info)
        edit_actions.addWidget(self._btn_cancel)
        edit_actions.addWidget(self._btn_save_info)
        body.addWidget(self._edit_actions)

        self._panel_info.body_layout().addWidget(body_holder)
        root.addWidget(self._panel_info)

        # ---------- Panel matières ----------
        panel_subj = Panel(
            "Matières, coefficients et enseignants",
            icon=qta.icon("fa5s.book"),
        )
        v = QVBoxLayout()
        v.setSpacing(8)
        self.table = QTableWidget(0, 4)
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(
            ["Matière", "Coefficient", "Enseignant", ""]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        v.addWidget(self.table)

        row_btns = QHBoxLayout()
        self.btn_add = QPushButton(qta.icon("fa5s.plus"), "Ajouter matière")
        set_kind(self.btn_add, "tonal")
        self.btn_add.clicked.connect(self._add_row)
        row_btns.addWidget(self.btn_add)
        row_btns.addStretch(1)
        v.addLayout(row_btns)
        wrap_subj = QWidget()
        wrap_subj.setLayout(v)
        panel_subj.body_layout().addWidget(wrap_subj)
        root.addWidget(panel_subj, 1)

    # ------------------------------------------------------------------
    # Helpers d'affichage
    # ------------------------------------------------------------------
    def _field_label(self, text: str) -> QLabel:
        lbl = QLabel(text + " :")
        # Utilise PlaceholderText (rôle Qt standard) pour un gris lisible
        # dans les deux thèmes. Fallback rgba en dur au cas où.
        lbl.setStyleSheet(
            "color: palette(placeholder-text); "
            "font-size: 11px; font-weight: 700; "
            "letter-spacing: 0.4px;"
        )
        lbl.setProperty("role", "muted")
        return lbl

    def _make_value_label(self, accent: bool = False) -> QLabel:
        lbl = QLabel("—")
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setStyleSheet(
            "color: palette(window-text); font-size: 13px; font-weight: 600;"
        )
        return lbl

    # ------------------------------------------------------------------
    # Modes lecture / édition
    # ------------------------------------------------------------------
    def _enter_edit_mode(self) -> None:
        self._snapshot = {
            "etablissement": self.ed_etablissement.text(),
            "directeur": self.ed_directeur.text(),
            "annee_scolaire": self.ed_annee.text(),
            "classe": self.ed_classe.text(),
            "nb_examens": self.sb_nb_examens.value(),
            "effectif": self.sb_effectif.value(),
            "nb_filles": self.sb_filles.value(),
            "nb_garcons": self.sb_garcons.value(),
            "nb_min_examens": self.dsb_nb_min.value(),
            "logo_path": self.ed_logo.text(),
            "prof_principal": self.ed_prof_principal.text(),
        }
        self._edit_mode = True
        self._view_read.setVisible(False)
        self._view_edit.setVisible(True)
        self._edit_actions.setVisible(True)
        self._btn_edit.setVisible(False)
        # Re-set kind + polish pour forcer le QSS sur boutons créés cachés
        for btn, kind in ((self._btn_cancel, "outlined"), (self._btn_save_info, "primary")):
            btn.setProperty("kind", kind)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        # Repaint en différé (laisse le show event terminer)
        from qtpy.QtCore import QTimer
        QTimer.singleShot(0, lambda: (
            self._btn_cancel.repaint(),
            self._btn_save_info.repaint(),
        ))
        self.ed_etablissement.setFocus()

    def _cancel_edit(self) -> None:
        # Restaurer
        for k, v in self._snapshot.items():
            if k == "nb_examens":
                self.sb_nb_examens.setValue(v)
            elif k == "effectif":
                self.sb_effectif.setValue(v)
            elif k == "nb_filles":
                self.sb_filles.setValue(v)
            elif k == "nb_garcons":
                self.sb_garcons.setValue(v)
            elif k == "nb_min_examens":
                self.dsb_nb_min.setValue(v)
            elif k == "etablissement":
                self.ed_etablissement.setText(v)
            elif k == "directeur":
                self.ed_directeur.setText(v)
            elif k == "annee_scolaire":
                self.ed_annee.setText(v)
            elif k == "classe":
                self.ed_classe.setText(v)
            elif k == "logo_path":
                self.ed_logo.setText(v)
            elif k == "prof_principal":
                self.ed_prof_principal.setText(v)
        self._exit_edit_mode()

    def _exit_edit_mode(self) -> None:
        self._edit_mode = False
        self._view_read.setVisible(True)
        self._view_edit.setVisible(False)
        self._edit_actions.setVisible(False)
        self._btn_edit.setVisible(True)
        self.refresh()

    def _save_info(self) -> None:
        self._save_settings()
        self._exit_edit_mode()
        show_toast(self, "Informations enregistrées", "success")
        self.changed.emit()

    # ------------------------------------------------------------------
    def _pick_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir un logo", "", "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self.ed_logo.setText(path)

    def _add_row(self) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem("Nouvelle matière"))
        self.table.setItem(r, 1, QTableWidgetItem("1"))
        self.table.setItem(r, 2, QTableWidgetItem(""))
        del_btn = QPushButton(qta.icon("fa5s.trash-alt"), "")
        del_btn.setToolTip("Supprimer")
        set_kind(del_btn, "danger")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setFixedWidth(36)
        del_btn.clicked.connect(lambda _, b=del_btn: self._delete_row(b))
        self.table.setCellWidget(r, 3, del_btn)
        self._update_count()

    def _delete_row(self, btn: QPushButton) -> None:
        for r in range(self.table.rowCount()):
            if self.table.cellWidget(r, 3) is btn:
                item = self.table.item(r, 0)
                subject_name = item.text() if item else "cette matière"
                if QMessageBox.question(
                    self, "Supprimer",
                    f"Supprimer la matière « {subject_name} » ?\n"
                    "Ses notes associées seront aussi supprimées.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                ) != QMessageBox.StandardButton.Yes:
                    return
                if item and item.data(Qt.ItemDataRole.UserRole):
                    self.db.delete_subject(int(item.data(Qt.ItemDataRole.UserRole)))
                self.table.removeRow(r)
                self._update_count()
                self.changed.emit()
                show_toast(self, f"Matière « {subject_name} » supprimée", "success")
                break

    def _update_count(self) -> None:
        self.sb_nb_matieres.setValue(self.table.rowCount())

    # ------------------------------------------------------------------
    def _clear_field_errors(self) -> None:
        for field in (self.sb_effectif, self.sb_filles, self.sb_garcons):
            field.setStyleSheet("")

    def _highlight_field_error(self, field: QSpinBox) -> None:
        field.setStyleSheet("QSpinBox { border: 1px solid red; background: #ffebee; }")

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._clear_field_errors()
        try:
            s = self.db.all_settings()
        except Exception:
            s = {}
        # Champs
        self.ed_etablissement.setText(s.get("etablissement", ""))
        self.ed_directeur.setText(s.get("directeur", ""))
        self.ed_annee.setText(s.get("annee_scolaire", ""))
        self.ed_classe.setText(s.get("classe", ""))
        self.ed_logo.setText(s.get("logo_path", ""))
        self.ed_prof_principal.setText(s.get("prof_principal", ""))
        self.sb_nb_examens.setValue(int(s.get("nb_examens", 6) or 6))
        self.sb_effectif.setValue(int(s.get("effectif", 0) or 0))
        self.sb_filles.setValue(int(s.get("nb_filles", 0) or 0))
        self.sb_garcons.setValue(int(s.get("nb_garcons", 0) or 0))
        self.dsb_nb_min.setValue(float(s.get("nb_min_examens", 1) or 1))
        # Labels lecture
        self._lbl_etablissement.setText(s.get("etablissement", "") or "—")
        self._lbl_directeur.setText(s.get("directeur", "") or "—")
        self._lbl_annee.setText(s.get("annee_scolaire", "") or "—")
        self._lbl_classe.setText(s.get("classe", "") or "—")
        self._lbl_prof_principal.setText(s.get("prof_principal", "") or "—")
        self._lbl_nb_examens.setText(str(int(s.get("nb_examens", 6) or 6)))
        self._lbl_effectif.setText(str(int(s.get("effectif", 0) or 0)))
        self._lbl_filles.setText(str(int(s.get("nb_filles", 0) or 0)))
        self._lbl_garcons.setText(str(int(s.get("nb_garcons", 0) or 0)))
        self._lbl_nb_min.setText(str(int(float(s.get("nb_min_examens", 1) or 1))))

        # Matières
        self.table.setRowCount(0)
        for sub in self.db.list_subjects():
            r = self.table.rowCount()
            self.table.insertRow(r)
            it_name = QTableWidgetItem(sub["name"])
            it_name.setData(Qt.ItemDataRole.UserRole, sub["id"])
            self.table.setItem(r, 0, it_name)
            self.table.setItem(r, 1, QTableWidgetItem(str(sub["coeff"])))
            self.table.setItem(r, 2, QTableWidgetItem(sub["teacher"] or ""))
            del_btn = QPushButton(qta.icon("fa5s.trash-alt"), "")
            del_btn.setToolTip("Supprimer")
            set_kind(del_btn, "danger")
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setFixedWidth(36)
            del_btn.clicked.connect(lambda _, b=del_btn: self._delete_row(b))
            self.table.setCellWidget(r, 3, del_btn)
        self._update_count()
        # Label "Matières (auto)"
        self._lbl_nb_matieres.setText(str(len(self.db.list_subjects())))
        # Logo : afficher juste le nom de fichier
        logo = s.get("logo_path", "") or ""
        if logo:
            try:
                from pathlib import Path
                self._lbl_logo.setText(Path(logo).name)
            except Exception:  # noqa: BLE001
                self._lbl_logo.setText(logo)
        else:
            self._lbl_logo.setText("—")

    # ------------------------------------------------------------------
    def _save_settings(self) -> None:
        self._clear_field_errors()
        # Bulletin premium : validation des champs critiques
        effectif = self.sb_effectif.value()
        nb_filles = self.sb_filles.value()
        nb_garcons = self.sb_garcons.value()
        if nb_filles + nb_garcons > effectif:
            for field in (self.sb_effectif, self.sb_filles, self.sb_garcons):
                self._highlight_field_error(field)
            show_toast(
                self,
                f"Somme filles ({nb_filles}) + garçons ({nb_garcons}) > "
                f"effectif ({effectif}).",
                kind="warning",
            )
            return
        if effectif < 0 or nb_filles < 0 or nb_garcons < 0:
            show_toast(self, "Valeurs négatives interdites.", kind="warning")
            return
        s = {
            "etablissement": self.ed_etablissement.text().strip(),
            "directeur": self.ed_directeur.text().strip(),
            "annee_scolaire": self.ed_annee.text().strip(),
            "classe": self.ed_classe.text().strip(),
            "nb_examens": str(self.sb_nb_examens.value()),
            "effectif": str(effectif),
            "nb_filles": str(nb_filles),
            "nb_garcons": str(nb_garcons),
            "nb_min_examens": str(int(self.dsb_nb_min.value())),
            "logo_path": self.ed_logo.text().strip(),
            "prof_principal": self.ed_prof_principal.text().strip(),
        }
        for k, v in s.items():
            self.db.set_setting(k, v)
        self.changed.emit()

    def _save(self) -> None:
        # Synchronisation des matières
        existing = {s["id"]: s for s in self.db.list_subjects()}
        seen_ids: set[int] = set()
        for r in range(self.table.rowCount()):
            name = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            coeff_item = self.table.item(r, 1)
            try:
                coeff = float(coeff_item.text().replace(",", ".")) if coeff_item else 1.0
            except (TypeError, ValueError):
                coeff = 1.0
            teacher = (self.table.item(r, 2).text() if self.table.item(r, 2) else "").strip()
            if not name:
                continue
            sid_item = self.table.item(r, 0)
            data = sid_item.data(Qt.ItemDataRole.UserRole) if sid_item else None
            sid = int(data) if data is not None else None
            if sid and sid in existing:
                self.db.update_subject(sid, name, coeff, teacher)
                seen_ids.add(sid)
            else:
                new_id = self.db.add_subject(name, coeff, teacher)
                self.table.item(r, 0).setData(Qt.ItemDataRole.UserRole, new_id)
                seen_ids.add(new_id)
        for sid in existing.keys() - seen_ids:
            self.db.delete_subject(sid)
        show_toast(self, "Matières enregistrées", "success")
        self.refresh()
        self.changed.emit()
