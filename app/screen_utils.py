from __future__ import annotations

from qtpy.QtCore import QRect
from qtpy.QtGui import QScreen
from qtpy.QtWidgets import QApplication


class ScreenScale:
    """Détecte la résolution et fournit des facteurs d'échelle.

    Référence : 1920×1080 → scale = 1.0
    Sur écran plus petit, les widgets sont rétrécis proportionnellement.
    """

    REF_W = 1920
    REF_H = 1080

    def __init__(self, screen: QScreen | None = None) -> None:
        if screen is None:
            screen = QApplication.primaryScreen()
        self._geo: QRect = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

    @property
    def width(self) -> int:
        return self._geo.width()

    @property
    def height(self) -> int:
        return self._geo.height()

    @property
    def scale_w(self) -> float:
        return max(0.5, self.width / self.REF_W)

    @property
    def scale_h(self) -> float:
        return max(0.5, self.height / self.REF_H)

    @property
    def scale_avg(self) -> float:
        return (self.scale_w + self.scale_h) / 2

    def sw(self, value: int) -> int:
        """Scale width-wise."""
        return max(int(value * self.scale_w), 1)

    def sh(self, value: int) -> int:
        """Scale height-wise."""
        return max(int(value * self.scale_h), 1)

    def s(self, value: int) -> int:
        """Uniform scale (average)."""
        return max(int(value * self.scale_avg), 1)

    @property
    def is_small(self) -> bool:
        return self.width < 1280 or self.height < 800

    @property
    def is_tiny(self) -> bool:
        return self.width < 1024 or self.height < 700

    @property
    def min_window_size(self) -> tuple[int, int]:
        if self.is_tiny:
            return (800, 560)
        if self.is_small:
            return (960, 640)
        return (1100, 700)

    @property
    def sidebar_width(self) -> int:
        if self.is_tiny:
            return 140
        if self.is_small:
            return 160
        return 200

    @property
    def switcher_width(self) -> int:
        if self.is_tiny:
            return 100
        if self.is_small:
            return 130
        return 160


# singleton global
_SCALE: ScreenScale | None = None


def get_scale() -> ScreenScale:
    global _SCALE
    if _SCALE is None:
        _SCALE = ScreenScale()
    return _SCALE
