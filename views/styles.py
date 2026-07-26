from __future__ import annotations

from resource_paths import resource_root
from settings.defaults import DEFAULT_ACCENT

# Every theme file (see themes/*.qss) uses these two tokens instead of a
# hardcoded accent color, so a single QSS file can render in the user's
# chosen accent rather than needing one QSS variant per color. Qt's QSS
# dialect has no variables/custom properties of its own, so this is a
# plain string substitution done at load time, not anything Qt-native.
_ACCENT_TOKEN = "@ACCENT@"
_ACCENT_HOVER_TOKEN = "@ACCENT_HOVER@"

# Recognized theme names -- also used by the Settings page's theme
# dropdown so the two never drift apart.
AVAILABLE_THEMES: tuple[tuple[str, str], ...] = (
    ("dark", "Dark"),
    ("light", "Light"),
    ("midnight_blue", "Midnight Blue"),
    ("emerald", "Emerald"),
    ("colorblind_friendly", "Colorblind Friendly"),
)


def _clamp_channel(value: int) -> int:
    return max(0, min(255, value))


def _darken_hex(hex_color: str, amount: float = 0.12) -> str:
    """Returns ``hex_color`` darkened by ``amount`` (0-1), used to derive
    a hover shade from the user's chosen accent color -- the same
    relationship the original hardcoded palette had between its accent
    (``#E62429``) and that button's hover state (``#C81E22``), just
    computed instead of hand-picked so it still looks right for any
    accent color, not only the default red."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return DEFAULT_ACCENT

    try:
        r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return DEFAULT_ACCENT

    r = _clamp_channel(round(r * (1 - amount)))
    g = _clamp_channel(round(g * (1 - amount)))
    b = _clamp_channel(round(b * (1 - amount)))
    return f"#{r:02X}{g:02X}{b:02X}"


def load_stylesheet(theme: str, accent_color: str = DEFAULT_ACCENT) -> str:
    """Load ``themes/<theme>.qss`` and substitute the accent color tokens
    every theme file uses in place of a hardcoded color, so the same
    file renders correctly for any user-chosen accent.

    Falls back to an empty stylesheet (Qt's own default look) if the
    named theme file doesn't exist, rather than raising -- a bad/missing
    theme name should never prevent the app from at least starting."""
    theme_file = resource_root() / "themes" / f"{theme}.qss"

    if not theme_file.exists():
        return ""

    accent = accent_color or DEFAULT_ACCENT
    if not accent.startswith("#"):
        accent = f"#{accent}"

    stylesheet = theme_file.read_text(encoding="utf-8")
    stylesheet = stylesheet.replace(_ACCENT_TOKEN, accent)
    stylesheet = stylesheet.replace(_ACCENT_HOVER_TOKEN, _darken_hex(accent))
    return stylesheet
