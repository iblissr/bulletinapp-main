"""Widget Notes par matière (équivalent des feuilles <Matière> du modèle).

Refonte visuelle style eco_paiement : TopContainer + Panel,
icônes qtawesome au lieu des émojis, bandeau de sync en
``PanelSubtitle`` clair.

**Auto-save (bulletin premium)** : les notes saisies sont
sauvegardées automatiquement après 600 ms d'inactivité (debounce),
sans avoir à cliquer sur « Enregistrer ». Le bouton reste
disponible pour forcer la sauvegarde.
"""
from __future__ import annotations

import qtawesome as qta
from typing import Sequence

from qtpy.QtCore import Qt, QTimer, Signal
from qtpy.QtGui import QBrush, QColor
from qtpy.QtWidgets import (
    QAbstractSpinBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStyleOptionHeader,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class GradeSpinBox(QDoubleSpinBox):
    """Spinbox d'entrée de note avec look Material 3.

    - Pas de flèches haut/bas (saisie clavier uniquement)
    - Bordure qui change quand une valeur est saisie (primary)
    - Centre le texte
    - Hauteur fixe pour s'aligner sur la table
    """

    def __init__(self, max_value: float = 20.0, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GradeSpin")
        self.setRange(0.0, max_value)
        self.setDecimals(2)
        self.setSingleStep(0.5)
        self.setSpecialValueText("—")
        # Pas de flèches
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        # Centrage et style
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(60)
        self.setMinimumHeight(38)
        # Propriété dynamique : a-t-on une note ?
        self._has_value = False
        self._refresh_state()

    # ------------------------------------------------------------------
    def set_value_or_blank(self, v: float | None) -> None:
        """Met la valeur ou remet l'état vide (spécialValueText).
        
        - ``None`` → état vide (pas de note)
        - ``0``   → note valide de 0/20 (distinct de "pas de note")
        - ``>0``  → note normale
        """
        if v is None:
            self.setValue(0)  # affiche "—"
            self._has_value = False
        else:
            self.setValue(v)
            self._has_value = True
        self._refresh_state()

    def has_value(self) -> bool:
        return self._has_value

    # ------------------------------------------------------------------
    def _refresh_state(self) -> None:
        self.setProperty("filled", "1" if self._has_value else "0")
        # Repolish pour appliquer le QSS
        self.style().unpolish(self)
        self.style().polish(self)

    def valueFromText(self, text: str) -> float:  # noqa: N802 (Qt API)
        # Si le texte est le specialValueText ("—"), retourner 0
        if text == self.specialValueText():
            return 0.0
        return super().valueFromText(text)

    def textFromValue(self, value: float) -> str:  # noqa: N802 (Qt API)
        if value == 0 and self.specialValueText():
            return self.specialValueText()
        return super().textFromValue(value)

    # ------------------------------------------------------------------
    # À chaque changement de valeur, mettre à jour l'état "filled"
    def clear(self) -> None:
        """Force l'état vide (pas de note)."""
        self.setValue(0)
        self._has_value = False
        self._refresh_state()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        # Détecter effacement : Backspace ou Suppr sur champ vide/valeur
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            if self.value() == 0 and not self._has_value:
                super().keyPressEvent(event)
                return
            self.clear()
            return
        super().keyPressEvent(event)
        new = self.value()
        self._has_value = new != 0
        self._refresh_state()

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt API)
        event.ignore()


class _ColoredHeader(QHeaderView):
    """QHeaderView qui peint le fond des sections selon ``exam_kinds``."""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._exam_kinds: list[str] = []
        self._exam_col_start = 2  # colonnes 0=N°, 1=Nom, 2..N=examens

    def set_exam_kinds(self, kinds: list[str], col_start: int = 2) -> None:
        self._exam_kinds = kinds
        self._exam_col_start = col_start

    def paintSection(self, painter, rect, logical_index):  # noqa: N802
        idx = logical_index - self._exam_col_start
        if 0 <= idx < len(self._exam_kinds):
            kind = self._exam_kinds[idx]
            color = QColor(COLOR_SUBJECT_MJ() if kind == "mj" else COLOR_SUBJECT_COMPO())
            painter.save()
            painter.fillRect(rect, color)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(
                rect.adjusted(8, 0, -8, 0),
                Qt.AlignmentFlag.AlignCenter,
                self.model().headerData(
                    logical_index, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
                ) or "",
            )
            painter.restore()
            return
        super().paintSection(painter, rect, logical_index)

from .common import Panel, ProgressOverlay, TopContainer, set_kind, show_toast
from .table_helpers import COLOR_SUBJECT_MJ, COLOR_SUBJECT_COMPO, color_for_average, label_for_exam  # type: ignore[attr-defined]
from ..db import Database, discover_class_by_db_path
from ..models import Subject, load_students, load_subjects


COL_N = 0
COL_NAME = 1
COL_NOTES_START = 2


def _resolve_subject_xlsx(db: Database, subject_name: str) -> str | None:
    """Trouve le chemin ``<classe>/<Matière>.xlsx`` si la classe est connue.

    Retourne ``None`` si la base n'est pas dans un workspace (cas legacy
    ou DB par défaut à la racine du projet).
    """
    cls = discover_class_by_db_path(db.path)
    if cls is None:
        return None
    if not cls.has_subject(subject_name):
        return None
    return str(cls.subject_path(subject_name))


class SubjectGradesWidget(QWidget):
    """Onglet de saisie des notes pour 1 matière."""

    changed = Signal()

    def __init__(self, db: Database, subject: Subject, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.subject = subject
        self._xlsx_path = _resolve_subject_xlsx(db, subject.name)
        # --- Auto-save (bulletin premium) ---
        # Liste des notes modifiées depuis le dernier flush. Chaque
        # note est un (student_id, exam_num, value). On debounce 600 ms
        # pour ne pas écrire en base à chaque frappe.
        self._dirty: set[tuple[int, int]] = set()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._flush_dirty)
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(14)

        # --- En-tête de page ---
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.btn_save = QPushButton(qta.icon("fa5s.save"), "Enregistrer")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        set_kind(self.btn_save, "primary")
        self.btn_save.clicked.connect(self._save)
        actions.addWidget(self.btn_save)

        self.btn_sync = QPushButton(qta.icon("fa5s.cloud-download-alt"), "Synchroniser")
        self.btn_sync.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sync.setToolTip(
            "Synchroniser ce sujet depuis <classe>/<Matière>.xlsx"
        )
        set_kind(self.btn_sync, "tonal")
        self.btn_sync.clicked.connect(self._sync_from_class)
        actions.addWidget(self.btn_sync)

        self.btn_import = QPushButton(qta.icon("fa5s.file-import"), "Importer")
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.clicked.connect(self._import)
        set_kind(self.btn_import, "outlined")
        actions.addWidget(self.btn_import)

        self.btn_export = QPushButton(qta.icon("fa5s.file-export"), "Exporter")
        self.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export.clicked.connect(self._export)
        set_kind(self.btn_export, "outlined")
        actions.addWidget(self.btn_export)

        self.btn_clear = QPushButton(qta.icon("fa5s.eraser"), "Vider")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self._clear)
        set_kind(self.btn_clear, "outlined")
        actions.addWidget(self.btn_clear)
        actions.addStretch(1)

        subtitle = (
            f"Coefficient : {self.subject.coeff:g}    "
            f"Professeur : {self.subject.teacher or '—'}    "
            f"6 examens (3 M.J + 3 Compo)"
        )
        # Première lettre en majuscule comme icône de page
        icon_letter = (self.subject.name[:2] or "•").upper()
        self._top = TopContainer(icon_letter, self.subject.name, subtitle)
        for w in (self.btn_save, self.btn_sync, self.btn_import, self.btn_export, self.btn_clear):
            self._top.add_action(w)
        root.addWidget(self._top)

        # ---------- Indicateur de synchronisation ----------
        self._lbl_sync = QLabel()
        self._lbl_sync.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_sync.setProperty("chip", "grey")
        self._lbl_sync.setStyleSheet("padding: 4px 10px;")
        root.addWidget(self._lbl_sync)
        self._last_sync_mtime: float | None = None
        self._refresh_sync_status()

        # ---------- Panel table avec titre et légende ----------
        panel = Panel(
            f"Notes — {self.subject.name}",
            icon=qta.icon("fa5s.table"),
        )
        # Légende M.J (teal) vs Compo (amber)
        legend_row = QHBoxLayout()
        legend_row.setSpacing(16)
        from ..theme import current as _t
        _tp = _t()
        legend_mj = QLabel()
        legend_mj.setText(
            "<span style='background:" + _tp.secondary + ";color:" + _tp.on_secondary + ";padding:2px 8px;"
            "border-radius:4px;font-weight:600;'>M.J</span> "
            f"<span style='color:{_tp.on_surface};font-size:13px;'>"
            "Moyennes Journalières (3)</span>"
        )
        legend_compo = QLabel()
        legend_compo.setText(
            "<span style='background:" + _tp.tertiary + ";color:" + _tp.on_tertiary + ";padding:2px 8px;"
            "border-radius:4px;font-weight:600;'>COMPO</span> "
            f"<span style='color:{_tp.on_surface};font-size:13px;'>"
            "Compositions trimestrielles (3)</span>"
        )
        legend_row.addWidget(legend_mj)
        legend_row.addWidget(legend_compo)
        legend_row.addStretch(1)
        # Indicateur d'échelle
        scale_lbl = QLabel(
            f"<span style='color:{_tp.on_surface};font-size:13px;'>"
            "Note sur 20 · Coef " f"{self.subject.coeff:g}" "</span>"
        )
        legend_row.addWidget(scale_lbl)
        panel.body_layout().addLayout(legend_row)

        nb_ex = int(self.db.get_setting("nb_examens", "6") or 6)
        self.nb_exams = nb_ex
        cols = 2 + nb_ex + 1  # Num, Nom, N notes, Moy (calculée live)
        self.table = QTableWidget(0, cols)
        headers = ["N°", "Nom et Prénoms"]
        self._exam_kinds: list[str] = []
        for n in range(1, nb_ex + 1):
            label, kind = label_for_exam(n)
            headers.append(label)
            self._exam_kinds.append(kind)
        headers += ["Moy."]
        self.table.setHorizontalHeaderLabels(headers)
        # Header custom pour M.J (teal) vs Compo (amber)
        custom_h = _ColoredHeader(Qt.Orientation.Horizontal, self.table)
        self.table.setHorizontalHeader(custom_h)
        custom_h.set_exam_kinds(self._exam_kinds, col_start=2)
        custom_h.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        custom_h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        panel.body_layout().addWidget(self.table)
        root.addWidget(panel, 1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self.table.setRowCount(0)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.verticalHeader().setVisible(False)
        students = load_students(self.db)
        if not students:
            self.table.setColumnCount(1)
            self.table.setRowCount(1)
            from .table_helpers import make_item as _empty_item
            self.table.setItem(0, 0, _empty_item(
                "Aucun élève — Ajoutez des élèves dans l'onglet Élèves",
                center=True,
            ))
            return
        for st in students:
            r = self.table.rowCount()
            self.table.insertRow(r)
            it_num = QTableWidgetItem(str(st.num))
            it_num.setData(Qt.ItemDataRole.UserRole, st.id)
            it_num.setFlags(it_num.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, COL_N, it_num)
            self.table.setItem(r, COL_NAME, QTableWidgetItem(st.full_name))

            for n in range(1, self.nb_exams + 1):
                v = self.db.get_grade(st.id, self.subject.id, n)
                spin = GradeSpinBox(max_value=20 * self.subject.coeff)
                spin.set_value_or_blank(v)
                spin.setProperty("exam_num", n)
                self.table.setCellWidget(r, COL_NOTES_START + n - 1, spin)

            self._refresh_avg(r)
        # Connexions : recalcul moyenne live + auto-save debouncé
        for r in range(self.table.rowCount()):
            item = self.table.item(r, COL_N)
            if item is None:
                continue
            sid_data = item.data(Qt.ItemDataRole.UserRole)
            if sid_data is None:
                continue
            sid = int(sid_data)
            for n in range(1, self.nb_exams + 1):
                spin = self.table.cellWidget(r, COL_NOTES_START + n - 1)
                if spin:
                    try:
                        spin.valueChanged.disconnect()
                    except TypeError:
                        pass
                    spin.valueChanged.connect(
                        lambda *_, row=r: self._refresh_avg(row)
                    )
                    # Auto-save : enregistre le (sid, exam_num) dans
                    # le set dirty, puis (re)démarre le timer.
                    spin.valueChanged.connect(
                        lambda *_, s=sid, e=n: self._mark_dirty(s, e)
                    )

    def _refresh_avg(self, r: int) -> None:
        notes = []
        for n in range(1, self.nb_exams + 1):
            spin = self.table.cellWidget(r, COL_NOTES_START + n - 1)
            if spin and spin.has_value():
                notes.append(spin.value())
        if not notes:
            from .table_helpers import make_grade_item
            it = make_grade_item(None, default="NC")
        else:
            avg = sum(notes) / len(notes)
            from .table_helpers import make_grade_item
            it = make_grade_item(round(avg, 2), default="NC")
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(r, self.table.columnCount() - 1, it)

    # ------------------------------------------------------------------
    # Auto-save (bulletin premium)
    # ------------------------------------------------------------------
    def _mark_dirty(self, student_id: int, exam_num: int) -> None:
        """Marque la note (student, exam) comme modifiée et relance
        le timer de debounce.
        """
        self._dirty.add((student_id, exam_num))
        # (re)démarre le timer
        self._save_timer.start()

    def _flush_dirty(self) -> None:
        """Sauvegarde en base toutes les notes modifiées depuis le
        dernier flush. Émet ``changed`` si au moins une note a été
        écrite.
        """
        if not self._dirty:
            return
        # Snapshot pour éviter les modifications concurrentes
        to_save = list(self._dirty)
        self._dirty.clear()
        nb = 0
        for r in range(self.table.rowCount()):
            sid = int(self.table.item(r, COL_N).data(Qt.ItemDataRole.UserRole))
            for n in range(1, self.nb_exams + 1):
                if (sid, n) not in to_save:
                    continue
                spin = self.table.cellWidget(r, COL_NOTES_START + n - 1)
                if spin and spin.has_value():
                    self.db.set_grade(sid, self.subject.id, n, spin.value())
                    nb += 1
                else:
                    self.db.set_grade(sid, self.subject.id, n, None)
        if nb > 0:
            # Indicateur discret dans la status bar
            try:
                win = self.window()
                if hasattr(win, "lbl_status"):
                    win.lbl_status.setText(
                        f"Auto-enregistré : {nb} note(s) — {self.subject.name}"
                    )
            except Exception:  # noqa: BLE001
                pass
            self.changed.emit()

    # ------------------------------------------------------------------
    def _save(self) -> None:
        # Forçage : flush immédiat du buffer dirty (s'il y en a)
        # puis écriture de TOUTES les notes (équivalent de l'ancien
        # comportement pour l'utilisateur qui clique manuellement).
        self._save_timer.stop()
        self._flush_dirty()
        nb = 0
        for r in range(self.table.rowCount()):
            sid = int(self.table.item(r, COL_N).data(Qt.ItemDataRole.UserRole))
            for n in range(1, self.nb_exams + 1):
                spin = self.table.cellWidget(r, COL_NOTES_START + n - 1)
                if spin and spin.has_value():
                    self.db.set_grade(sid, self.subject.id, n, spin.value())
                    nb += 1
                else:
                    self.db.set_grade(sid, self.subject.id, n, None)
        show_toast(self, f"{nb} note(s) enregistrée(s)", "success")
        self.changed.emit()

    def hideEvent(self, event):  # noqa: N802 (Qt API)
        # Quand l'onglet est masqué, on flush les modifs en attente
        # (sinon on risque de perdre 1 note si on clique ailleurs).
        self._save_timer.stop()
        self._flush_dirty()
        super().hideEvent(event)

    def _clear(self) -> None:
        from qtpy.QtWidgets import QMessageBox
        if QMessageBox.question(
            self, "Vider", f"Supprimer toutes les notes de {self.subject.name} ?"
        ) != QMessageBox.StandardButton.Yes:
            return
        for r in range(self.table.rowCount()):
            sid = int(self.table.item(r, COL_N).data(Qt.ItemDataRole.UserRole))
            for n in range(1, self.nb_exams + 1):
                self.db.set_grade(sid, self.subject.id, n, None)
        self.refresh()
        self.changed.emit()
        show_toast(self, f"Notes de {self.subject.name} vidées", "info")

    # ------------------------------------------------------------------
    def _export(self) -> None:
        # Vide d'abord le buffer des notes non flushées
        self._save_timer.stop()
        self._flush_dirty()
        # Si on est dans un workspace de classe et que le fichier
        # ``<classe>/<Matière>.xlsx`` existe, on propose par défaut
        # d'écrire dedans (le prof récupère son fichier à jour).
        default_path = self._xlsx_path or f"{self.subject.name}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter", default_path, "Excel (*.xlsx)"
        )
        if not path:
            return
        overlay = ProgressOverlay(self, "Export en cours…")
        overlay.start()
        try:
            import openpyxl  # noqa: WPS433
            from openpyxl.styles import Alignment, Font, PatternFill  # noqa: WPS433

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Sheet1"
            ws["B2"] = self.db.get_setting("etablissement", "")
            ws["E2"] = self.subject.name
            ws["B3"] = self.db.get_setting("classe", "")
            ws["C3"] = "Coeff"
            ws["F3"] = "Prof"
            ws["B4"] = f"Année scolaire : {self.db.get_setting('annee_scolaire', '')}"
            ws["C4"] = self.subject.coeff
            headers = ["Num", "Nom et Prénoms"]
            for n in range(1, self.nb_exams + 1):
                label, _ = label_for_exam(n)
                headers.append(label)
            for c, h in enumerate(headers, 1):
                ws.cell(row=5, column=c, value=h).font = Font(bold=True)
            for r in range(self.table.rowCount()):
                ws.cell(row=6 + r, column=1, value=int(self.table.item(r, 0).text()))
                ws.cell(row=6 + r, column=2, value=self.table.item(r, 1).text())
                for n in range(1, self.nb_exams + 1):
                    spin = self.table.cellWidget(r, COL_NOTES_START + n - 1)
                    if spin and spin.has_value():
                        ws.cell(row=6 + r, column=2 + n, value=spin.value())
            import os
            wb.save(path)
            show_toast(self, f"Exporté vers {os.path.basename(path)}", "success")
        except Exception as e:  # noqa: BLE001
            show_toast(self, "Erreur lors de l'export du fichier Excel. Vérifiez que le fichier n'est pas ouvert dans un autre programme.", "error")
        finally:
            overlay.stop()

    def _import(self) -> None:
        from ..sync import sync_subject_from_xlsx
        from pathlib import Path
        default_path = self._xlsx_path or ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer", default_path, "Excel (*.xlsx *.xls)"
        )
        if not path:
            return
        overlay = ProgressOverlay(self, "Import en cours…")
        overlay.start()
        try:
            result = sync_subject_from_xlsx(
                self.db, self.subject.name, Path(path)
            )
        except Exception as e:  # noqa: BLE001
            show_toast(self, "Erreur lors de l'import du fichier. Vérifiez le format et le contenu.", "error")
            return
        finally:
            overlay.stop()
        if result.errors:
            show_toast(self, "\n".join(result.errors), "warning")
        # Met à jour la table et l'indicateur de sync
        if self._xlsx_path and Path(path).resolve() == Path(self._xlsx_path).resolve():
            self._last_sync_mtime = Path(path).stat().st_mtime
            self._refresh_sync_status()
        self.refresh()
        msg = (
            f"+{result.notes_added} nouvelles, "
            f"~{result.notes_updated} maj, "
            f"={result.notes_unchanged} inchangées"
        )
        show_toast(self, msg, "success")
        self.changed.emit()

    def _refresh_sync_status(self) -> None:
        """Met à jour le bandeau d'état de synchronisation.

        Affiche :
        - le chemin du fichier .xlsx de la classe (si on est dans un
          workspace) ;
        - la date de modification du fichier ;
        - un badge « modifié depuis la dernière sync » si la mtime
          du fichier est plus récente que celle de la dernière sync
          enregistrée.
        """
        from pathlib import Path
        if not hasattr(self, "_lbl_sync"):
            return
        from ..theme import current as _theme
        t = _theme()
        if not self._xlsx_path:
            self._lbl_sync.setText(
                "<span style='color:" + t.on_surface_variant + ";'>"
                "Aucun fichier associé à cette matière."
                "</span>"
            )
            return
        p = Path(self._xlsx_path)
        if not p.is_file():
            self._lbl_sync.setText(
                "<span style='color:" + t.danger + ";'>Fichier introuvable : "
                f"<code>{p}</code></span>"
            )
            return
        import datetime as _dt
        mtime = p.stat().st_mtime
        when = _dt.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
        text = (
            f"<span style='color:{t.on_surface};font-weight:600;'>"
            f"{p.name}</span>  "
            f"<span style='color:{t.on_surface_variant};'>"
            f"modifié le {when}</span>"
        )
        if self._last_sync_mtime is not None and mtime > self._last_sync_mtime:
            text += (
                "  <span style='background:" + t.warning_container + ";"
                "color:" + t.on_warning_container + ";"
                "padding:2px 6px;border-radius:3px;'>"
                "modifié depuis la dernière sync</span>"
            )
        self._lbl_sync.setText(text)

    def _sync_from_class(self) -> None:
        """Importe les notes depuis le fichier ``.xlsx`` de la classe."""
        from ..sync import sync_subject_from_xlsx
        from pathlib import Path
        if not self._xlsx_path:
            show_toast(self, "Aucun fichier associé à cette matière", "info")
            return
        overlay = ProgressOverlay(self, "Synchronisation…")
        overlay.start()
        try:
            result = sync_subject_from_xlsx(
                self.db, self.subject.name, Path(self._xlsx_path)
            )
        except Exception as exc:  # noqa: BLE001
            show_toast(self, "Échec de la synchronisation. Vérifiez les fichiers sources.", "error")
            return
        finally:
            overlay.stop()
        if result.errors:
            show_toast(self, "\n".join(result.errors), "warning")
        self._last_sync_mtime = Path(self._xlsx_path).stat().st_mtime
        self._refresh_sync_status()
        self.refresh()
        # Status bar via MainWindow
        try:
            win = self.window()
            if hasattr(win, "lbl_status"):
                win.lbl_status.setText(
                    f"Sync {self.subject.name} : "
                    f"+{result.notes_added} ~{result.notes_updated} "
                    f"={result.notes_unchanged}"
                )
        except Exception:  # noqa: BLE001
            pass


def _wrap(layout) -> QWidget:
    """Wrap un layout dans un QWidget transparent (helper local)."""
    w = QWidget()
    w.setLayout(layout)
    w.setStyleSheet("background: transparent;")
    return w
