from __future__ import annotations

from PySide6.QtWidgets import QApplication

# The app's font point size before any scaling was ever applied -- captured
# once, on the first call, so re-applying a new scale later (e.g. the user
# adjusts the Settings > Appearance slider) always scales from the same
# baseline rather than compounding on top of whatever the previous scale
# already did.
_base_point_size: float | None = None


def apply_font_scale(app: QApplication, scale: float) -> None:
    """Scale the whole application's base font by `scale` (1.0 = no
    change). Safe to call repeatedly -- e.g. once at startup from
    main.py, then again every time Settings > Appearance saves a new
    font_scale value -- since the baseline is only ever captured once."""
    global _base_point_size

    font = app.font()
    if _base_point_size is None:
        _base_point_size = font.pointSizeF()

    font.setPointSizeF(_base_point_size * scale)
    app.setFont(font)
