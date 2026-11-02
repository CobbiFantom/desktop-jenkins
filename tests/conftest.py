import os
import sys

# Windows needs its native font database when generating selectable PDF text.
os.environ.setdefault("QT_QPA_PLATFORM", "windows" if sys.platform == "win32" else "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    yield app
