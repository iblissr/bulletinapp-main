"""Widget Compte Rendu — version trimestres (2 examens par onglet)."""
from __future__ import annotations

import qtawesome as qta
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from .common import Panel, ProgressOverlay, SearchBar, TopContainer, install_table_sort, set_kind, show_toast
from .table_helpers import (
    label_for_exam as _label_for_exam,
    make_item as _item,
)
from ..db import Database
from ..models import compute_stats, load_subjects
from ..theme import current as theme_current


class TrimestreContent(QWidget):
    """Contenu d'un trimestre (2 examens) : sous-onglets Général, Par matière, Répartition."""

    def __init__(self, db: Database, trimestre: int, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self.trimestre = trimestre
        self.n_mj = 2 * trimestre - 1
        self.n_co = 2 * trimestre
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        subtitle = QLabel(
            f"Examens : {_label_for_exam(self.n_mj)[0]} + {_label_for_exam(self.n_co)[0]}"
        )
        subtitle.setStyleSheet(f"font-size: 14px; color: {theme_current().on_surface_variant}; padding: 0 4px;")
        root.addWidget(subtitle)

        self.tabs = QTabWidget()

        # Général (MJ | Compo | Ensemble)
        self.tbl_general = QTableWidget(3, 4)
        self.tbl_general.setHorizontalHeaderLabels(
            ["Indicateur",
             _label_for_exam(self.n_mj)[0],
             _label_for_exam(self.n_co)[0],
             "Ensemble"]
        )
        self.tbl_general.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_general.verticalHeader().setVisible(False)
        self.tbl_general.setEditTriggers(self.tbl_general.EditTrigger.NoEditTriggers)
        self.tbl_general.setAlternatingRowColors(True)
        self.tabs.addTab(self.tbl_general, "Général")

        # Par matière (MJ | Compo | Ensemble)
        self.tbl_subject = QTableWidget(0, 4)
        self.tbl_subject.setHorizontalHeaderLabels(
            ["Matière",
             f"≥ 10/20 ({_label_for_exam(self.n_mj)[0]})",
             f"≥ 10/20 ({_label_for_exam(self.n_co)[0]})",
             "≥ 10/20 (Ensemble)"]
        )
        self.tbl_subject.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_subject.verticalHeader().setVisible(False)
        self.tbl_subject.setEditTriggers(self.tbl_subject.EditTrigger.NoEditTriggers)
        self.tbl_subject.setAlternatingRowColors(True)
        self.tabs.addTab(self.tbl_subject, "Par matière")
        install_table_sort(self.tbl_subject, numeric_columns={1, 2, 3})

        # Répartition
        self.tbl_dist = QTableWidget(2, 0)
        self.tbl_dist.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_dist.verticalHeader().setVisible(False)
        self.tbl_dist.setEditTriggers(self.tbl_dist.EditTrigger.NoEditTriggers)
        self.tbl_dist.setAlternatingRowColors(True)
        self.tabs.addTab(self.tbl_dist, "Répartition")

        root.addWidget(self.tabs, 1)

    def _combined_avg(self, a: float | None, b: float | None) -> str:
        if a is not None and b is not None:
            return f"{(a + b) / 2:.2f}"
        return f"{a or b:.2f}" if (a or b) is not None else "NC"

    def refresh(self) -> None:
        stats_mj = compute_stats(self.db, self.n_mj)
        stats_co = compute_stats(self.db, self.n_co)
        subjects = load_subjects(self.db)
        lbl_mj = _label_for_exam(self.n_mj)[0]
        lbl_co = _label_for_exam(self.n_co)[0]

        if not subjects or stats_mj.effectif == 0:
            for tbl in (self.tbl_general, self.tbl_subject, self.tbl_dist):
                tbl.setColumnCount(1)
                tbl.setRowCount(1)
                tbl.setItem(0, 0, _item(
                    "Aucune donnée — Saisissez des notes puis revenez ici",
                    center=True,
                ))
            return

        # --- Général (MJ | Compo | Ensemble) ---
        effectif = stats_mj.effectif
        classes_mj = stats_mj.classes
        classes_co = stats_co.classes
        classes_ens = max(classes_mj, classes_co)
        moyenne_mj = stats_mj.moyenne_classe
        moyenne_co = stats_co.moyenne_classe
        rows = [
            ("Effectif", str(effectif), str(effectif), str(effectif)),
            ("Classés", str(classes_mj), str(classes_co), str(classes_ens)),
            (
                "Moyenne classe",
                f"{moyenne_mj:.2f}" if moyenne_mj is not None else "NC",
                f"{moyenne_co:.2f}" if moyenne_co is not None else "NC",
                self._combined_avg(moyenne_mj, moyenne_co),
            ),
        ]
        self.tbl_general.setRowCount(len(rows))
        for i, (k, v_mj, v_co, v_ens) in enumerate(rows):
            self.tbl_general.setItem(i, 0, _item(k, bold=True))
            self.tbl_general.setItem(i, 1, _item(v_mj, center=True, bold=True))
            self.tbl_general.setItem(i, 2, _item(v_co, center=True, bold=True))
            self.tbl_general.setItem(i, 3, _item(v_ens, center=True, bold=True))

        # --- Par matière (MJ | Compo | Ensemble) ---
        self.tbl_subject.setRowCount(len(subjects))
        for i, s in enumerate(subjects):
            n_mj = stats_mj.nb_above_avg_per_subject.get(s.id, 0)
            n_co = stats_co.nb_above_avg_per_subject.get(s.id, 0)
            self.tbl_subject.setItem(i, 0, _item(s.name))
            self.tbl_subject.setItem(i, 1, _item(str(n_mj), center=True, bold=True))
            self.tbl_subject.setItem(i, 2, _item(str(n_co), center=True, bold=True))
            self.tbl_subject.setItem(i, 3, _item(str(max(n_mj, n_co)), center=True, bold=True))

        # --- Répartition (MJ + Compo combiné) ---
        combined_dist: dict[float, int] = {}
        for s in (stats_mj, stats_co):
            for seuil, cnt in s.distribution.items():
                combined_dist[seuil] = combined_dist.get(seuil, 0) + cnt
        seuils = sorted(combined_dist.keys(), reverse=True)
        self.tbl_dist.setColumnCount(len(seuils))
        self.tbl_dist.setHorizontalHeaderLabels([f"≥ {int(s)}" for s in seuils])
        for c, s in enumerate(seuils):
            self.tbl_dist.setItem(0, c, _item(f"≥ {int(s)}", center=True, bold=True))
            self.tbl_dist.setItem(1, c, _item(str(combined_dist[s]), center=True, bold=True))
        self.tbl_dist.setVerticalHeaderLabels(["Tranche", "Effectif"])


class CompteRenduWidget(QWidget):
    """Onglet Compte Rendu — 3 onglets trimestres, chaque avec ses 2 examens."""

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(14)

        self._top = TopContainer(
            "CR",
            "Compte Rendu",
            "Statistiques par trimestre",
        )
        self.btn_pdf = QPushButton(qta.icon("fa5s.file-pdf"), "Exporter PDF")
        self.btn_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pdf.setToolTip("Générer le compte rendu trimestriel au format PDF")
        set_kind(self.btn_pdf, "tonal")
        self.btn_pdf.clicked.connect(self._export_pdf)
        self._top.add_action(self.btn_pdf)
        root.addWidget(self._top)

        panel = Panel(icon=qta.icon("fa5s.file-alt"))
        self._search = SearchBar("Filtrer la table active (matière / indicateur)…")
        self._search.textChanged.connect(self._apply_filter)
        panel.body_layout().addWidget(self._search)

        self._tabs = QTabWidget()
        self._trim_contents: dict[int, TrimestreContent] = {}
        for t in (1, 2, 3):
            content = TrimestreContent(self.db, t)
            self._tabs.addTab(content, f"Trimestre {t}")
            self._trim_contents[t] = content

        panel.body_layout().addWidget(self._tabs, 1)
        root.addWidget(panel, 1)

    def refresh(self) -> None:
        for c in self._trim_contents.values():
            c.refresh()
        if self._search.text():
            self._apply_filter(self._search.text())

    def _apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        idx = self._tabs.currentIndex()
        content = self._tabs.widget(idx)
        if not isinstance(content, TrimestreContent):
            return
        ct = content
        sub_idx = ct.tabs.currentIndex()
        if sub_idx == 0:
            tbl = ct.tbl_general
        elif sub_idx == 1:
            tbl = ct.tbl_subject
        else:
            tbl = ct.tbl_dist
        for r in range(tbl.rowCount()):
            it = tbl.item(r, 0)
            label = (it.text() if it else "").lower()
            match = (not text) or (text in label)
            tbl.setRowHidden(r, not match)

    def _export_pdf(self) -> None:
        from .export_settings import ensure_export_dir
        out_dir = ensure_export_dir(self.db, "export_cr_path")
        default_name = "compte_rendu_trimestres.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer PDF", str(out_dir / default_name),
            "PDF (*.pdf)",
        )
        if not path:
            return
        overlay = ProgressOverlay(self, "Génération du PDF…")
        overlay.start()
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import (
                Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
            )

            subjects = load_subjects(self.db)
            styles = getSampleStyleSheet()
            doc = SimpleDocTemplate(path, pagesize=A4,
                                    topMargin=2 * cm, bottomMargin=2 * cm)
            elems = []
            elems.append(Paragraph(
                f"<b>{self.db.get_setting('etablissement', '')}</b>",
                styles["Title"],
            ))
            elems.append(Paragraph(
                "COMPTE RENDU TRIMESTRES",
                styles["Heading2"],
            ))
            elems.append(Paragraph(
                f"Classe : {self.db.get_setting('classe', '')} — "
                f"Année : {self.db.get_setting('annee_scolaire', '')}",
                styles["Normal"],
            ))
            elems.append(Spacer(1, 0.5 * cm))

            for t in (1, 2, 3):
                n_mj = 2 * t - 1
                n_co = 2 * t
                stats_mj = compute_stats(self.db, n_mj)
                stats_co = compute_stats(self.db, n_co)
                lbl_mj = _label_for_exam(n_mj)[0]
                lbl_co = _label_for_exam(n_co)[0]
                elems.append(Paragraph(
                    f"<b>Trimestre {t} — {lbl_mj} + {lbl_co}</b>",
                    styles["Heading3"],
                ))

                def _fmt_avg(v):
                    return f"{v:.2f}" if v is not None else "NC"

                moy_mj = stats_mj.moyenne_classe
                moy_co = stats_co.moyenne_classe
                classes_ens = max(stats_mj.classes, stats_co.classes)
                data = [
                    ["Indicateur", lbl_mj, lbl_co, "Ensemble"],
                    ["Effectif",
                     str(stats_mj.effectif), str(stats_co.effectif),
                     str(stats_mj.effectif)],
                    ["Classés",
                     str(stats_mj.classes), str(stats_co.classes),
                     str(classes_ens)],
                    ["Moyenne classe",
                     _fmt_avg(moy_mj), _fmt_avg(moy_co),
                     _fmt_avg((moy_mj + moy_co) / 2 if moy_mj is not None and moy_co is not None else moy_mj or moy_co)],
                ]
                t1 = Table(data, colWidths=[4 * cm, 3 * cm, 3 * cm, 3 * cm])
                t1.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                ]))
                elems.append(t1)
                elems.append(Spacer(1, 0.2 * cm))

                elems.append(Paragraph("<b>Élèves ≥ 10/20 par matière</b>", styles["Heading4"]))
                data2 = [["Matière", lbl_mj, lbl_co, "Ensemble"]]
                for s in subjects:
                    n_mj = stats_mj.nb_above_avg_per_subject.get(s.id, 0)
                    n_co = stats_co.nb_above_avg_per_subject.get(s.id, 0)
                    data2.append([s.name, str(n_mj), str(n_co), str(max(n_mj, n_co))])
                t2 = Table(data2, colWidths=[4 * cm, 3 * cm, 3 * cm, 3 * cm])
                t2.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]))
                elems.append(t2)
                elems.append(Spacer(1, 0.5 * cm))

            doc.build(elems)
            show_toast(self, f"PDF généré : {path}", "success")
        except Exception as e:  # noqa: BLE001
            show_toast(self, "Erreur lors de la génération du PDF. Vérifiez les données.", "error")
        finally:
            overlay.stop()
