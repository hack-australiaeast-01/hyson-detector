"""3D Nazar avatar (three.js, built in code): follows the cursor, talks, listens (browser speech, free).

Bidirectional Streamlit component without npm: components/nazar_avatar/index.html speaks the component protocol itself.
Returns {"text", "id"} when the analyst speaks into the mic, else None.
"""
import base64
from functools import lru_cache
from pathlib import Path

import streamlit.components.v1 as components

_DIR = Path(__file__).parent
_component = components.declare_component("nazar_avatar", path=str(_DIR / "components" / "nazar_avatar"))


@lru_cache(maxsize=1)
def _logo():
    p = _DIR / "static" / "brand" / "logo_blue.png"
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


def avatar(say="", say_id=0, lang="fr", voice=False, height=380, greet=False, key="nazar_avatar"):
    return _component(say=say or "", say_id=int(say_id), lang=lang, voice=bool(voice), height=int(height), greet=bool(greet),
                      logo=_logo(), key=key, default=None)
