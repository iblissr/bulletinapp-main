"""Panel de configuration de classe avec navigation multi-classes."""
from __future__ import annotations

from typing import Any, Optional

import qtawesome as qta
from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .common import Panel, set_kind, show_toast
from ..db import Database
from ..workspace import ClassInfo, discover_classes


class ClassConfigPanel(QFrame):
    """Panel de configuration avec navigation entre classes."""

    classChanged = Signal()

    def __init__(
        self,
        db: Optional[Database] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._classes = discover_classes()
        self._active_class: Optional[ClassInfo] = None
        self._db: Optional[Database] = None
        self._edit_mode = False
        self._edit_mode_subjects = False
        self._snapshot: dict[str, str] = {}
        self._nav_buttons: list[QPushButton] = []
        self._build()
        self._select_initial_class(db)

    # ==================================================================
    #  INITIALISATION
    # ==================================================================

    def _select_initial_class(self, db: Optional[Database]) -> None:
        if not self._classes:
            return
        if db is not None:
            db_path = str(getattr(db, "path", ""))
            for c in self._classes:
                if str(c.db_path) == db_path:
                    self._select_class(c)
                    return
        self._select_class(self._classes[0])

    # ==================================================================
    #  LAYOUT
    # ==================================================================

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_nav_sidebar(root)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: palette(mid);")
        root.addWidget(sep)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        self._current_class_label = QLabel("")
        self._current_class_label.setStyleSheet(
            "font-size: 16px; font-weight: 800; color: palette(on-surface);"
            " padding: 12px 16px 0 16px;"
        )
        right.addWidget(self._current_class_label)

        content = QHBoxLayout()
        content.setContentsMargins(12, 8, 12, 12)
        content.setSpacing(12)

        self._build_class_info_panel(content)
        self._build_subjects_panel(content)

        right.addLayout(content, 1)
        root.addLayout(right, 1)

    # ==================================================================
    #  NAV SIDEBAR (vertical)
    # ==================================================================

    def _build_nav_sidebar(self, parent_layout: QHBoxLayout) -> None:
        sidebar = QWidget()
        sidebar.setObjectName("ConfigNav")
        sidebar.setFixedWidth(170)
        sidebar.setStyleSheet(
            "QWidget#ConfigNav { background: palette(window); }"
        )

        sidebar_lay = QVBoxLayout(sidebar)
        sidebar_lay.setContentsMargins(8, 12, 8, 12)
        sidebar_lay.setSpacing(2)

        title = QLabel("Classes")
        title.setStyleSheet("font-weight: 800; font-size: 13px; color: palette(on-surface);"
                           " padding: 4px 8px 8px 8px;")
        sidebar_lay.addWidget(title)

        if not self._classes:
            empty_lbl = QLabel("Aucune classe trouvée")
            empty_lbl.setStyleSheet("color: palette(placeholder-text); font-size: 12px;"
                                   " padding: 8px;")
            empty_lbl.setWordWrap(True)
            sidebar_lay.addWidget(empty_lbl)
            sidebar_lay.addStretch(1)
            parent_layout.addWidget(sidebar)
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_lay = QVBoxLayout(scroll_content)
        scroll_lay.setContentsMargins(0, 0, 0, 0)
        scroll_lay.setSpacing(2)

        self._nav_buttons = []
        for cls_info in self._classes:
            btn = QPushButton(cls_info.display_name)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(34)
            self._style_nav_btn(btn, False)
            btn.clicked.connect(lambda checked, c=cls_info: self._select_class(c))
            scroll_lay.addWidget(btn)
            self._nav_buttons.append(btn)

        scroll_lay.addStretch(1)
        scroll.setWidget(scroll_content)
        sidebar_lay.addWidget(scroll, 1)

        parent_layout.addWidget(sidebar)

    def _style_nav_btn(self, btn: QPushButton, active: bool) -> None:
        if active:
            btn.setStyleSheet(
                "QPushButton { background: palette(highlight); color: palette(highlighted-text);"
                " border: none; border-radius: 6px; padding: 4px 12px;"
                " font-size: 12px; font-weight: 700; text-align: left; }"
            )
        else:
            btn.setStyleSheet(
                "QPushButton { background: transparent; color: palette(on-surface);"
                " border: none; border-radius: 6px; padding: 4px 12px;"
                " font-size: 12px; font-weight: 500; text-align: left; }"
                "QPushButton:hover { background: palette(surface-container-low);"
                " color: palette(primary); }"
            )

    def _update_nav(self) -> None:
        if self._active_class is None:
            return
        for btn, cls_info in zip(self._nav_buttons, self._classes):
            active = cls_info.db_path == self._active_class.db_path
            btn.setChecked(active)
            self._style_nav_btn(btn, active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ==================================================================
    #  CLASS INFO PANEL
    # ==================================================================

    def _build_class_info_panel(self, parent_layout: QHBoxLayout) -> None:
        panel = Panel(
            "Informations de la classe",
            icon=qta.icon("fa5s.info-circle"),
        )
        panel.setMinimumWidth(240)

        self._btn_edit = QPushButton(qta.icon("fa5s.pen"), " Modifier")
        self._btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_edit.setFixedHeight(30)
        set_kind(self._btn_edit, "tonal")
        panel.add_header_action(self._btn_edit)
        self._btn_edit.clicked.connect(self._enter_edit_mode)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        # -- Read mode --
        self._view_read = QWidget()
        rl = QVBoxLayout(self._view_read)
        rl.setContentsMargins(8, 4, 8, 4)
        rl.setSpacing(0)

        fields = [
            ("Classe", ""),
            ("Division", ""),
            ("Année scolaire", ""),
            ("Professeur principal", ""),
            ("Coefficient par défaut", ""),
            ("Effectif", ""),
            ("Filles", ""),
            ("Garçons", ""),
        ]
        self._read_labels: dict[str, QLabel] = {}
        for label, _ in fields:
            row, val_label = self._make_read_row(label)
            self._read_labels[label] = val_label
            rl.addWidget(row)

        body_lay.addWidget(self._view_read)

        # -- Edit mode --
        self._view_edit = QWidget()
        el = QVBoxLayout(self._view_edit)
        el.setContentsMargins(8, 4, 8, 4)
        el.setSpacing(6)

        self.ed_classe = QLineEdit()
        el.addWidget(self._make_edit_row("Classe", self.ed_classe))

        self.ed_annee_scolaire = QLineEdit()
        el.addWidget(self._make_edit_row("Année scolaire", self.ed_annee_scolaire))

        self.ed_prof_principal = QLineEdit()
        el.addWidget(self._make_edit_row("Professeur principal", self.ed_prof_principal))

        self.ed_coeff_default = QLineEdit()
        el.addWidget(self._make_edit_row("Coefficient par défaut", self.ed_coeff_default))

        self.ed_effectif = QLineEdit()
        el.addWidget(self._make_edit_row("Effectif", self.ed_effectif))

        self.ed_filles = QLineEdit()
        el.addWidget(self._make_edit_row("Filles", self.ed_filles))

        self.ed_garcons = QLineEdit()
        el.addWidget(self._make_edit_row("Garçons", self.ed_garcons))

        body_lay.addWidget(self._view_edit)
        self._view_edit.setVisible(False)

        # Edit actions
        self._edit_actions = QWidget()
        self._edit_actions.setVisible(False)
        ab = QHBoxLayout(self._edit_actions)
        ab.setContentsMargins(8, 4, 8, 4)
        ab.setSpacing(6)
        ab.addStretch(1)
        self._btn_cancel = QPushButton(qta.icon("fa5s.times"), " Annuler")
        self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancel.setFixedHeight(30)
        set_kind(self._btn_cancel, "outlined")
        self._btn_cancel.clicked.connect(self._cancel_edit)
        ab.addWidget(self._btn_cancel)

        self._btn_save = QPushButton(qta.icon("fa5s.check"), " Enregistrer")
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save.setFixedHeight(30)
        set_kind(self._btn_save, "primary")
        self._btn_save.clicked.connect(self._save)
        ab.addWidget(self._btn_save)

        body_lay.addWidget(self._edit_actions)

        panel.body_layout().addWidget(body)
        parent_layout.addWidget(panel, 1)

    def _make_read_row(self, label: str) -> tuple[QWidget, QLabel]:
        w = QWidget()
        w.setObjectName("ConfigRow")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(8)

        lbl = QLabel(label + " :")
        lbl.setObjectName("ConfigLabel")
        lbl.setFixedWidth(110)
        lay.addWidget(lbl)

        val = QLabel("")
        val.setObjectName("ConfigValue")
        val.setWordWrap(True)
        lay.addWidget(val, 1)

        return w, val

    def _make_edit_row(self, label: str, editor: QLineEdit) -> QWidget:
        w = QWidget()
        w.setObjectName("ConfigRow")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(8)

        lbl = QLabel(label + " :")
        lbl.setObjectName("ConfigLabel")
        lbl.setFixedWidth(110)
        lay.addWidget(lbl)

        editor.setStyleSheet(
            "QLineEdit { border: 1px solid palette(mid); border-radius: 5px;"
            " padding: 5px 8px; font-size: 12px; background: palette(base); }"
            "QLineEdit:focus { border: 2px solid palette(highlight); padding: 4px 7px; }"
        )
        lay.addWidget(editor, 1)

        return w

    # ==================================================================
    #  SUBJECTS PANEL
    # ==================================================================

    def _build_subjects_panel(self, parent_layout: QHBoxLayout) -> None:
        panel = Panel(
            "Configuration des matières",
            icon=qta.icon("fa5s.book"),
        )
        panel.setMinimumWidth(260)

        self._btn_edit_subjects = QPushButton(qta.icon("fa5s.pen"), " Modifier")
        self._btn_edit_subjects.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_edit_subjects.setFixedHeight(30)
        set_kind(self._btn_edit_subjects, "tonal")
        panel.add_header_action(self._btn_edit_subjects)
        self._btn_edit_subjects.clicked.connect(self._enter_edit_mode_subjects)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        # Scroll area for subjects
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_lay = QVBoxLayout(scroll_content)
        scroll_lay.setContentsMargins(0, 0, 0, 0)
        scroll_lay.setSpacing(0)

        # -- Read mode --
        self._view_read_subjects = QWidget()
        self._subjects_read_lay = QVBoxLayout(self._view_read_subjects)
        self._subjects_read_lay.setContentsMargins(8, 4, 8, 4)
        self._subjects_read_lay.setSpacing(6)

        self._subjects_empty_label = QLabel("Aucune matière configurée")
        self._subjects_empty_label.setObjectName("ConfigValue")
        self._subjects_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subjects_empty_label.setStyleSheet("padding: 20px; color: palette(placeholder-text);")
        self._subjects_read_lay.addWidget(self._subjects_empty_label)

        self._subjects_card_widget = QWidget()
        self._subjects_card_lay = QVBoxLayout(self._subjects_card_widget)
        self._subjects_card_lay.setContentsMargins(0, 0, 0, 0)
        self._subjects_card_lay.setSpacing(6)
        self._subjects_read_lay.addWidget(self._subjects_card_widget)

        scroll_lay.addWidget(self._view_read_subjects)

        # -- Edit mode --
        self._subjects_view_edit = QWidget()
        self._subjects_edit_lay = QVBoxLayout(self._subjects_view_edit)
        self._subjects_edit_lay.setContentsMargins(8, 4, 8, 4)
        self._subjects_edit_lay.setSpacing(4)

        self._subjects_edit_form = QWidget()
        self._subjects_edit_form_lay = QVBoxLayout(self._subjects_edit_form)
        self._subjects_edit_form_lay.setContentsMargins(0, 0, 0, 0)
        self._subjects_edit_form_lay.setSpacing(4)
        self._subjects_edit_lay.addWidget(self._subjects_edit_form)

        scroll_lay.addWidget(self._subjects_view_edit)
        self._subjects_view_edit.setVisible(False)

        scroll.setWidget(scroll_content)
        body_lay.addWidget(scroll, 1)

        # Edit actions
        self._edit_actions_subjects = QWidget()
        self._edit_actions_subjects.setVisible(False)
        sb = QHBoxLayout(self._edit_actions_subjects)
        sb.setContentsMargins(8, 4, 8, 4)
        sb.setSpacing(6)
        sb.addStretch(1)
        self._btn_cancel_subjects = QPushButton(qta.icon("fa5s.times"), " Annuler")
        self._btn_cancel_subjects.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancel_subjects.setFixedHeight(30)
        set_kind(self._btn_cancel_subjects, "outlined")
        self._btn_cancel_subjects.clicked.connect(self._cancel_edit_subjects)
        sb.addWidget(self._btn_cancel_subjects)
        self._btn_save_subjects = QPushButton(qta.icon("fa5s.check"), " Enregistrer")
        self._btn_save_subjects.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save_subjects.setFixedHeight(30)
        set_kind(self._btn_save_subjects, "primary")
        self._btn_save_subjects.clicked.connect(self._save_subjects)
        sb.addWidget(self._btn_save_subjects)

        body_lay.addWidget(self._edit_actions_subjects)

        panel.body_layout().addWidget(body)
        parent_layout.addWidget(panel, 1)

    # ==================================================================
    #  CLASS NAVIGATION
    # ==================================================================

    def _select_class(self, class_info: ClassInfo) -> None:
        if self._active_class is not None and class_info.db_path == self._active_class.db_path:
            return
        self._exit_edit_mode(quiet=True)
        self._exit_edit_mode_subjects(quiet=True)
        if self._db is not None:
            self._db.close()
            self._db = None
        self._active_class = class_info
        try:
            self._db = Database(str(class_info.db_path))
            self._update_nav()
            self._load_class_data()
        except Exception:
            self._db = None
            self._active_class = None
        QApplication.processEvents()

    def _load_class_data(self) -> None:
        if self._db is None or self._active_class is None:
            return

        settings = self._db.all_settings()
        display = self._active_class.display_name

        self._current_class_label.setText(
            f"Configuration — {display} ({self._active_class.division})"
        )

        self._read_labels["Classe"].setText(display)
        self._read_labels["Division"].setText(self._active_class.division)
        self._read_labels["Année scolaire"].setText(settings.get("annee_scolaire", ""))
        self._read_labels["Professeur principal"].setText(settings.get("prof_principal", ""))
        self._read_labels["Coefficient par défaut"].setText(settings.get("coeff_default", "1"))
        self._read_labels["Effectif"].setText(settings.get("effectif", ""))
        self._read_labels["Filles"].setText(settings.get("nb_filles", ""))
        self._read_labels["Garçons"].setText(settings.get("nb_garcons", ""))

        setting_classe = settings.get("classe", "")
        self.ed_classe.setText(setting_classe if setting_classe else display)
        self.ed_annee_scolaire.setText(settings.get("annee_scolaire", ""))
        self.ed_prof_principal.setText(settings.get("prof_principal", ""))
        self.ed_coeff_default.setText(settings.get("coeff_default", "1"))
        self.ed_effectif.setText(settings.get("effectif", ""))
        self.ed_filles.setText(settings.get("nb_filles", ""))
        self.ed_garcons.setText(settings.get("nb_garcons", ""))

        self._refresh_subjects()

    # ==================================================================
    #  SUBJECTS DATA
    # ==================================================================

    @staticmethod
    def _get_subject_value(sub: Any, key: str, default: str = "") -> Any:
        try:
            return sub[key]
        except (KeyError, IndexError, TypeError):
            return default

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _refresh_subjects(self) -> None:
        self._clear_layout(self._subjects_card_lay)

        if self._db is None:
            self._subjects_empty_label.show()
            self._subjects_card_widget.hide()
            self._subjects_empty_label.setText("Base de données non disponible")
            return

        subjects = self._db.list_subjects()
        if not subjects:
            self._subjects_empty_label.show()
            self._subjects_card_widget.hide()
            return

        self._subjects_empty_label.hide()
        self._subjects_card_widget.show()

        for sub in subjects:
            card = self._make_subject_card(sub)
            self._subjects_card_lay.addWidget(card)

        self._subjects_card_lay.addStretch(1)

        # Rebuild edit rows
        self._clear_layout(self._subjects_edit_form_lay)
        self.ed_subjects = []
        for i, sub in enumerate(subjects):
            sid = self._get_subject_value(sub, "id")
            name = self._get_subject_value(sub, "name", "")
            coeff = self._get_subject_value(sub, "coeff", "")
            teacher = self._get_subject_value(sub, "teacher", "")

            row = QWidget()
            row.setObjectName("ConfigRow")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 2, 4, 2)
            rl.setSpacing(6)

            lbl = QLabel(f"M{i + 1} :")
            lbl.setObjectName("ConfigLabel")
            lbl.setFixedWidth(28)
            rl.addWidget(lbl)

            name_input = QLineEdit(str(name))
            name_input.setStyleSheet(
                "QLineEdit { border: 1px solid palette(mid); border-radius: 5px;"
                " padding: 5px 8px; font-size: 12px; background: palette(base); }"
                "QLineEdit:focus { border: 2px solid palette(highlight); padding: 4px 7px; }"
            )
            rl.addWidget(name_input, 1)

            sep_c = QLabel("C:")
            sep_c.setObjectName("ConfigLabel")
            rl.addWidget(sep_c)

            coeff_str = str(coeff) if coeff is not None else ""
            coeff_input = QLineEdit(coeff_str)
            coeff_input.setFixedWidth(50)
            if not coeff_str and self._db is not None:
                coeff_input.setPlaceholderText(
                    self._db.get_setting("coeff_default", "1")
                )
            coeff_input.setStyleSheet(
                "QLineEdit { border: 1px solid palette(mid); border-radius: 5px;"
                " padding: 5px 6px; font-size: 12px; background: palette(base); }"
                "QLineEdit:focus { border: 2px solid palette(highlight); padding: 4px 5px; }"
            )
            rl.addWidget(coeff_input)

            sep_p = QLabel("P:")
            sep_p.setObjectName("ConfigLabel")
            rl.addWidget(sep_p)

            teacher_input = QLineEdit(str(teacher))
            teacher_input.setFixedWidth(110)
            teacher_input.setStyleSheet(
                "QLineEdit { border: 1px solid palette(mid); border-radius: 5px;"
                " padding: 5px 6px; font-size: 12px; background: palette(base); }"
                "QLineEdit:focus { border: 2px solid palette(highlight); padding: 4px 5px; }"
            )
            rl.addWidget(teacher_input)
            teacher_input.setPlaceholderText("Professeur")

            self.ed_subjects.append({
                "sid": sid,
                "name_input": name_input,
                "coeff_input": coeff_input,
                "teacher_input": teacher_input,
            })

            self._subjects_edit_form_lay.addWidget(row)

    def _make_subject_card(self, subject: Any) -> QFrame:
        card = QFrame()
        card.setObjectName("SubjectCard")
        card.setMinimumHeight(64)
        card.setMaximumHeight(72)
        card.setStyleSheet(
            "QFrame#SubjectCard {"
            "  background: palette(window);"
            "  border: 1px solid palette(mid);"
            "  border-radius: 8px;"
            "}"
            "QFrame#SubjectCard:hover {"
            "  border-color: palette(highlight);"
            "}"
        )

        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(8)

        ico = QLabel()
        ico.setPixmap(qta.icon("fa5s.book", color=QColor(100, 116, 139)).pixmap(16, 16))
        lay.addWidget(ico, 0, Qt.AlignmentFlag.AlignVCenter)

        v = QVBoxLayout()
        v.setSpacing(0)

        name = QLabel(str(self._get_subject_value(subject, "name", "?")))
        name.setStyleSheet("font-weight: 700; font-size: 13px;")
        v.addWidget(name)

        coeff = self._get_subject_value(subject, "coeff", "")
        coeff_txt = f"Coefficient. {coeff}" if coeff else ""
        coeff_lbl = QLabel(coeff_txt)
        coeff_lbl.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        v.addWidget(coeff_lbl)

        lay.addLayout(v, 1)

        teacher = self._get_subject_value(subject, "teacher", "")
        if teacher:
            t = QLabel(teacher[:16])
            t.setStyleSheet(
                "color: palette(placeholder-text); font-size: 11px; padding: 2px 8px;"
                " background: palette(window); border: 1px solid palette(mid); border-radius: 4px;"
            )
            lay.addWidget(t, 0, Qt.AlignmentFlag.AlignVCenter)

        return card

    # ==================================================================
    #  CLASS INFO — EDIT FLOW
    # ==================================================================

    def _enter_edit_mode(self) -> None:
        self._edit_mode = True
        self._view_read.setVisible(False)
        self._view_edit.setVisible(True)
        self._edit_actions.setVisible(True)
        self._btn_edit.setVisible(False)
        self._snapshot = {k: v.text() for k, v in self._read_labels.items()}

    def _cancel_edit(self) -> None:
        for k, v in self._snapshot.items():
            if k in self._read_labels:
                self._read_labels[k].setText(v)
        self._load_class_data()
        self._exit_edit_mode()

    def _save(self) -> None:
        if self._db is None:
            return

        self._db.set_setting("classe", self.ed_classe.text())
        self._db.set_setting("annee_scolaire", self.ed_annee_scolaire.text())
        self._db.set_setting("prof_principal", self.ed_prof_principal.text())
        self._db.set_setting("coeff_default", self.ed_coeff_default.text())
        self._db.set_setting("effectif", self.ed_effectif.text())
        self._db.set_setting("nb_filles", self.ed_filles.text())
        self._db.set_setting("nb_garcons", self.ed_garcons.text())

        val_classe = self.ed_classe.text()
        self._read_labels["Classe"].setText(val_classe if val_classe else self._active_class.display_name)
        self._read_labels["Année scolaire"].setText(self.ed_annee_scolaire.text())
        self._read_labels["Professeur principal"].setText(self.ed_prof_principal.text())
        self._read_labels["Coefficient par défaut"].setText(self.ed_coeff_default.text())
        self._read_labels["Effectif"].setText(self.ed_effectif.text())
        self._read_labels["Filles"].setText(self.ed_filles.text())
        self._read_labels["Garçons"].setText(self.ed_garcons.text())

        display = val_classe if val_classe else self._active_class.display_name
        self._current_class_label.setText(
            f"Configuration — {display} ({self._active_class.division})"
        )

        self.classChanged.emit()
        self._exit_edit_mode()

    def _exit_edit_mode(self, quiet: bool = False) -> None:
        self._edit_mode = False
        self._view_read.setVisible(True)
        self._view_edit.setVisible(False)
        self._edit_actions.setVisible(False)
        self._btn_edit.setVisible(True)

    # ==================================================================
    #  SUBJECTS — EDIT FLOW
    # ==================================================================

    def _enter_edit_mode_subjects(self) -> None:
        self._edit_mode_subjects = True
        self._view_read_subjects.setVisible(False)
        self._subjects_view_edit.setVisible(True)
        self._edit_actions_subjects.setVisible(True)
        self._btn_edit_subjects.setVisible(False)

    def _cancel_edit_subjects(self) -> None:
        self._exit_edit_mode_subjects()

    def _save_subjects(self) -> None:
        if self._db is None:
            return
        subjects = self._db.list_subjects()
        for i, sub in enumerate(subjects):
            if i >= len(self.ed_subjects):
                continue
            data = self.ed_subjects[i]
            name = data["name_input"].text()
            coeff_str = data["coeff_input"].text()
            teacher = data["teacher_input"].text()
            try:
                coeff = float(coeff_str) if coeff_str else 1.0
            except ValueError:
                coeff = 1.0
            self._db.update_subject(sub["id"], name, coeff, teacher)
        self._refresh_subjects()
        self.classChanged.emit()
        self._exit_edit_mode_subjects()

    def _exit_edit_mode_subjects(self, quiet: bool = False) -> None:
        self._edit_mode_subjects = False
        self._view_read_subjects.setVisible(True)
        self._subjects_view_edit.setVisible(False)
        self._edit_actions_subjects.setVisible(False)
        self._btn_edit_subjects.setVisible(True)
