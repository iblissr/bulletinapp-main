"""Sélecteur de classe (QComboBox enrichi) affiché dans la toolbar.

Émet le signal :pyattr:`classChanged` quand l'utilisateur choisit une
classe. Le ``MainWindow`` écoute ce signal pour :
1. Fermer la ``Database`` courante
2. En ouvrir une nouvelle sur le chemin de la classe
3. Reconstruire tous les onglets

Le widget est volontairement *stupide* : il ne fait que présenter la
liste des :class:`ClassInfo` fournies par :mod:`workspace` et prévenir
quand une nouvelle classe est sélectionnée.
"""
from __future__ import annotations

from typing import Optional

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import QComboBox, QWidget

from ..workspace import ClassInfo, discover_classes


class ClassSwitcher(QComboBox):
    """Combo box affichant les classes détectées dans BULLETIN/.

    Les items sont groupés par division (LYCEE / COLLEGE) via
    :py:meth:`addItem` avec un user-data. Le label humain
    (``"3ème 1"``) est affiché, le nom de dossier (``"3EME1"``) est
    stocké dans le :class:`Qt.ItemDataRole.UserRole` pour la résolution
    d'identifiant.
    """

    classChanged = Signal(str)  # émet le nom de la nouvelle classe

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(100)
        self.setMaximumWidth(180)
        self.setToolTip("Sélectionner la classe à éditer")
        self._populate()
        self.currentIndexChanged.connect(self._on_change)

    # ------------------------------------------------------------------
    def _populate(self) -> None:
        self.blockSignals(True)
        self.clear()
        classes = discover_classes()
        if not classes:
            self.addItem("— Aucune classe détectée —", None)
            self.setEnabled(False)
            self.blockSignals(False)
            return
        self.setEnabled(True)
        # Item placeholder — sélectionné quand on est sur l'accueil
        self.addItem("  — Choisir une classe —", None)
        idx0 = self.count() - 1
        from qtpy.QtGui import QStandardItem
        model0 = self.model()
        if isinstance(model0.item(idx0), QStandardItem):
            model0.item(idx0).setEnabled(True)
            model0.item(idx0).setSelectable(True)
        last_division: Optional[str] = None
        for c in classes:
            if c.division != last_division:
                # Séparateur visuel entre divisions
                self.addItem(f"── {c.division} ──", None)
                self.setItemData(
                    self.count() - 1, 0,
                    Qt.ItemDataRole.UserRole + 1,  # data rôle non utilisé
                )
                # Désactiver la sélection sur le séparateur
                sep_idx = self.count() - 1
                model = self.model()
                if isinstance(model.item(sep_idx), QStandardItem):
                    model.item(sep_idx).setEnabled(False)
                    model.item(sep_idx).setSelectable(False)
                last_division = c.division
            self.addItem(f"  {c.display_name}", c.name)
        # Par défaut, le placeholder est sélectionné
        self.setCurrentIndex(0)
        self.blockSignals(False)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Re-scanne le dossier BULLETIN/ et reconstruit la liste.

        Utilise ``select_class_silent`` pour ne pas redéclencher
        ``_on_class_changed`` (et donc un swap de DB) — c'est
        l'appelant qui décide quand basculer.
        """
        current = self.currentData()
        self._populate()
        if current is not None:
            self.select_class_silent(current)

    # ------------------------------------------------------------------
    def select_class(self, name: str) -> bool:
        """Sélectionne la classe ``name`` (nom de dossier). Émet le
        signal :pyattr:`classChanged` si la sélection change."""
        for i in range(self.count()):
            if self.itemData(i) == name:
                if self.currentIndex() == i:
                    return True
                self.setCurrentIndex(i)
                return True
        return False

    def select_class_silent(self, name: str) -> bool:
        """Comme :meth:`select_class` mais **n'émet pas** le signal.

        Utilisé au démarrage de l'app pour synchroniser le sélecteur
        avec la DB fournie par ``main.py`` sans redéclencher un swap
        qui fermerait la connexion tout juste ouverte.
        """
        for i in range(self.count()):
            if self.itemData(i) == name:
                self.blockSignals(True)
                try:
                    self.setCurrentIndex(i)
                finally:
                    self.blockSignals(False)
                return True
        return False

    # ------------------------------------------------------------------
    def clear_selection(self) -> None:
        """Réinitialise la sélection : aucun item de classe actif
        (sélectionne le placeholder « Choisir une classe »),
        sans émettre de signal.
        """
        self.blockSignals(True)
        try:
            self.setCurrentIndex(0)
        finally:
            self.blockSignals(False)

    def current_class_name(self) -> Optional[str]:
        data = self.currentData()
        return data if isinstance(data, str) else None

    def current_class_info(self) -> Optional[ClassInfo]:
        from ..workspace import discover_class
        name = self.current_class_name()
        if not name:
            return None
        return discover_class(name)

    # ------------------------------------------------------------------
    def _on_change(self, _index: int) -> None:
        name = self.current_class_name()
        if name:
            self.classChanged.emit(name)
