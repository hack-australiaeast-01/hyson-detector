"""Every page of the app renders without exception, in French and English, on the committed snapshot (as on Streamlit Cloud)."""
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app" / "app.py"
PAGES = re.search(r"^PAGES = \[(.*?)\]", APP.read_text(encoding="utf-8"), re.M).group(1).replace('"', "").replace(" ", "").split(",")


@pytest.mark.parametrize("lang", ["fr", "en"])
@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page, lang):
    at = AppTest.from_file(str(APP), default_timeout=300)
    at.session_state["page"] = page
    at.session_state["welcomed"] = True
    at.session_state["lang"] = lang
    at.run()
    assert not at.exception, at.exception[0].message if at.exception else ""
