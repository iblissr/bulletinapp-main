"""Écran de démarrage avec barre de progression — style Material 3.

S'affiche pendant le chargement de l'application (imports,
initialisation de la base, détection des classes, etc.).
Utilitaire : suffit d'appeler ``show_splash()`` au tout début
du ``main()``, puis ``splash.set_progress(n, message)`` au fil
de l'initialisation.
"""
from __future__ import annotations

from typing import Optional

from qtpy.QtCore import QRect, Qt, QTimer
from qtpy.QtGui import QColor, QFont, QPainter, QPixmap
from qtpy.QtWidgets import QApplication, QSplashScreen, QWidget

from .screen_utils import get_scale
from .theme import current as tp


class SplashScreen(QSplashScreen):
    """Splash screen avec barre de progression et message."""

    def __init__(self) -> None:
        scale = get_scale()
        w = int(480 * scale.scale_avg)
        h = int(320 * scale.scale_avg)
        pixmap = QPixmap(w, h)
        pixmap.fill(QColor(tp().surface))
        super().__init__(pixmap)
        self._progress = 0
        self._message = ""
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.SplashScreen
        )
        self.setFixedSize(w, h)

    def set_progress(self, value: int, message: str = "") -> None:
        self._progress = max(0, min(100, value))
        self._message = message
        self.repaint()
        QApplication.processEvents()

    def drawContents(self, painter: QPainter) -> None:
        rect = self.rect()
        palette = tp()

        # Fond
        painter.fillRect(rect, QColor(palette.surface))

        # Icône / logo (cercle avec lettre "B")
        cx, cy = rect.center().x(), 80
        r = 36
        painter.setBrush(QColor(palette.primary))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRect(cx - r, cy - r, r * 2, r * 2))
        f_title = QFont()
        f_title.setBold(True)
        f_title.setPointSize(22)
        painter.setFont(f_title)
        painter.setPen(QColor(palette.on_primary))
        painter.drawText(QRect(cx - 30, cy - 20, 60, 40),
                         Qt.AlignmentFlag.AlignCenter, "B")

        # Titre
        f_name = QFont()
        f_name.setBold(True)
        f_name.setPointSize(18)
        painter.setFont(f_name)
        painter.setPen(QColor(palette.on_surface))
        painter.drawText(QRect(0, 140, rect.width(), 30),
                         Qt.AlignmentFlag.AlignCenter, "Bulletin Premium")

        # Message de chargement
        f_msg = QFont()
        f_msg.setPointSize(11)
        painter.setFont(f_msg)
        painter.setPen(QColor(palette.on_surface_variant))
        painter.drawText(QRect(20, 175, rect.width() - 40, 24),
                         Qt.AlignmentFlag.AlignCenter, self._message or "Chargement…")

        # Barre de progression
        bar_x, bar_y = 60, 215
        bar_w, bar_h = rect.width() - 120, 8
        painter.setBrush(QColor(palette.surface_container_highest))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 4, 4)
        if self._progress > 0:
            fill_w = int(bar_w * self._progress / 100)
            painter.setBrush(QColor(palette.primary))
            painter.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 4, 4)

        # Texte "%"
        f_pct = QFont()
        f_pct.setPointSize(10)
        painter.setFont(f_pct)
        painter.setPen(QColor(palette.on_surface_variant))
        painter.drawText(QRect(0, 230, rect.width(), 20),
                         Qt.AlignmentFlag.AlignCenter,
                         f"{self._progress}%")


def show_splash() -> SplashScreen:
    """Crée et affiche le splash screen."""
    splash = SplashScreen()
    splash.set_progress(0, "Démarrage…")
    splash.show()
    QApplication.processEvents()
    return splash
