"""Tableau de bord (première page de l'app).

Style eco_paiement : TopContainer + 4 StatCards + Panneaux d'info.
Présente un aperçu rapide de la classe active : effectif, matières,
élèves, dernière synchronisation.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import qtawesome as qta
from qtpy.QtCore import Qt
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from .common import Panel, StatCard, TopContainer, set_kind
from .table_helpers import wrap_layout as _wrap
from ..db import Database


log = logging.getLogger(__name__)


class DashboardWidget(QWidget):
    """Tableau de bord de la classe active."""

    def __init__(self, db: Database, main_window=None, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self._main = main_window
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(14)

        # --- En-tête de page ---
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self._btn_sync = QPushButton(qta.icon("fa5s.cloud-download-alt"), "Synchroniser")
        self._btn_sync.setCursor(Qt.CursorShape.PointingHandCursor)
        set_kind(self._btn_sync, "primary")
        self._btn_sync.clicked.connect(self._action_sync)
        actions.addWidget(self._btn_sync)

        self._btn_new_class = QPushButton(qta.icon("fa5s.plus"), "Nouvelle classe")
        self._btn_new_class.setCursor(Qt.CursorShape.PointingHandCursor)
        set_kind(self._btn_new_class, "tonal")
        self._btn_new_class.clicked.connect(self._action_new_class)
        actions.addWidget(self._btn_new_class)
        actions.addStretch(1)

        self._top = TopContainer(
            "TB",
            "Tableau de bord",
            "Aperçu rapide de la classe active",
        )
        # Injecte les actions à droite du TopContainer
        for w in (self._btn_sync, self._btn_new_class):
            self._top.add_action(w)
        root.addWidget(self._top)

        # --- 4 StatCards ---
        cards = QHBoxLayout()
        cards.setSpacing(10)
        self._card_class = StatCard("Classe", "—", accent="#4F46E5")
        self._card_students = StatCard("Élèves", "—", accent="#0D9488")
        self._card_subjects = StatCard("Matières", "—", accent="#D97706")
        self._card_sync = StatCard("Dernière sync", "—", accent="#059669")
        for c in (self._card_class, self._card_students, self._card_subjects, self._card_sync):
            cards.addWidget(c)
        root.addLayout(cards)

        # --- Panneaux d'info ---
        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        # Panneau identité de la classe
        panel_info = Panel("Informations de la classe", icon=qta.icon("fa5s.school"))
        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)
        self._lbl_etab = QLabel("Établissement : —")
        self._lbl_etab.setObjectName("DashInfoLabel")
        self._lbl_annee = QLabel("Année scolaire : —")
        self._lbl_annee.setObjectName("DashInfoLabel")
        self._lbl_classe = QLabel("Classe : —")
        self._lbl_classe.setObjectName("DashInfoLabel")
        self._lbl_effectif = QLabel("Effectif : —")
        self._lbl_effectif.setObjectName("DashInfoLabel")
        self._lbl_prof = QLabel("Professeur principal : —")
        self._lbl_prof.setObjectName("DashInfoLabel")
        for lbl in (self._lbl_etab, self._lbl_annee, self._lbl_classe,
                    self._lbl_effectif, self._lbl_prof):
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl.setStyleSheet("font-size: 13px; padding: 4px 0;")
            info_layout.addWidget(lbl)
        info_layout.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(info_layout)
        panel_info.body_layout().addWidget(wrap)
        bottom.addWidget(panel_info, 2)

        # Panneau actions rapides
        panel_actions = Panel("Actions rapides", icon=qta.icon("fa5s.bolt"))
        actions_layout = QVBoxLayout()
        actions_layout.setSpacing(8)

        quick_actions = [
            ("fa5s.users", "Gérer les élèves", self._action_students),
            ("fa5s.cog", "Configurer la classe", self._action_config),
            ("fa5s.chart-line", "Voir les moyennes", self._action_moyennes),
            ("fa5s.file-alt", "Générer le compte rendu", self._action_cr),
        ]
        for icon_name, label, slot in quick_actions:
            btn = QPushButton(qta.icon(icon_name), "  " + label)
            btn.setObjectName("DashAction")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(36)
            btn.clicked.connect(slot)
            actions_layout.addWidget(btn)
        actions_layout.addStretch(1)
        wrap2 = QWidget()
        wrap2.setLayout(actions_layout)
        panel_actions.body_layout().addWidget(wrap2)
        bottom.addWidget(panel_actions, 1)

        root.addLayout(bottom)

        # Panneau des dernières modifications
        panel_recent = Panel("Activité récente", icon=qta.icon("fa5s.clock"))
        self._lbl_recent = QLabel("Aucune activité récente.")
        self._lbl_recent.setWordWrap(True)
        self._lbl_recent.setStyleSheet(
            "color: palette(placeholder-text); font-size: 13px; padding: 8px 4px;"
        )
        panel_recent.body_layout().addWidget(self._lbl_recent)
        root.addWidget(panel_recent)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Met à jour les stats et infos depuis la DB."""
        def _s(key: str, default: str = "—") -> str:
            try:
                v = self.db.get_setting(key, default)
                return v if v else default
            except Exception:  # noqa: BLE001
                return default

        classe = _s("classe", "—")
        etab = _s("etablissement", "—")
        annee = _s("annee_scolaire", "—")
        prof = _s("prof_principal", "—")
        try:
            effectif = int(_s("effectif", "0") or 0)
            nb_filles = int(_s("nb_filles", "0") or 0)
            nb_garcons = int(_s("nb_garcons", "0") or 0)
        except ValueError:
            effectif = nb_filles = nb_garcons = 0

        try:
            students = self.db.list_students()
        except Exception:  # noqa: BLE001
            students = []
        try:
            subjects = self.db.list_subjects()
        except Exception:  # noqa: BLE001
            subjects = []

        # StatCards
        self._card_class.set_value(classe)
        self._card_students.set_value(
            str(len(students)),
            hint=f"{nb_filles} filles · {nb_garcons} garçons" if (nb_filles or nb_garcons) else "",
        )
        self._card_subjects.set_value(str(len(subjects)))

        # Cherche la date de dernière sync (mtime le plus récent des .xlsx)
        last_sync = "—"
        try:
            from .class_switcher import ClassSwitcher  # noqa: F401
            from ..workspace import discover_class_by_db_path
            cls = discover_class_by_db_path(self.db.path)
            if cls and cls.subject_files:
                mtimes = []
                for xlsx in cls.subject_files:
                    try:
                        mtimes.append(xlsx.stat().st_mtime)
                    except OSError:
                        pass
                if mtimes:
                    last = max(mtimes)
                    last_sync = datetime.fromtimestamp(last).strftime("%d/%m/%Y %H:%M")
        except Exception:  # noqa: BLE001
            pass
        self._card_sync.set_value(last_sync)

        # Panneau identité
        self._lbl_etab.setText(f"Établissement : {etab}")
        self._lbl_annee.setText(f"Année scolaire : {annee}")
        self._lbl_classe.setText(f"Classe : {classe}")
        self._lbl_effectif.setText(
            f"Effectif : {effectif}  "
            f"({nb_filles} filles, {nb_garcons} garçons)"
        )
        self._lbl_prof.setText(f"Professeur principal : {prof}")

        # Activité récente
        if not students:
            self._lbl_recent.setText(
                "Aucun élève. Allez dans l'onglet « Élèves » pour en importer."
            )
        elif not subjects:
            self._lbl_recent.setText(
                "Aucune matière. Allez dans l'onglet « Configuration »."
            )
        else:
            self._lbl_recent.setText(
                f"{len(students)} élèves et {len(subjects)} matières chargés. "
                f"Utilisez le bouton « Synchroniser » pour mettre à jour les notes."
            )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _action_sync(self) -> None:
        if self._main is not None and hasattr(self._main, "_action_sync"):
            self._main._action_sync(silent=False)

    def _action_new_class(self) -> None:
        if self._main is not None and hasattr(self._main, "_action_new_class"):
            self._main._action_new_class()

    def _action_students(self) -> None:
        if self._main is not None and hasattr(self._main, "go_to_tab"):
            self._main.go_to_tab("students")

    def _action_config(self) -> None:
        if self._main is not None and hasattr(self._main, "go_to_tab"):
            self._main.go_to_tab("config")

    def _action_moyennes(self) -> None:
        if self._main is not None and hasattr(self._main, "go_to_tab"):
            self._main.go_to_tab("moyennes")

    def _action_cr(self) -> None:
        if self._main is not None and hasattr(self._main, "go_to_tab"):
            self._main.go_to_tab("compte_rendu")


# ---------------------------------------------------------------------------
# Helpers (importés ici pour éviter la dépendance circulaire)
# ---------------------------------------------------------------------------


def set_kind_for_button(btn: QPushButton, kind: str) -> None:
    """Wrapper local pour set_kind (alias conservé pour rétrocompat)."""
    set_kind(btn, kind)
