from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QT_QPA_FONTDIR",
    os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"),
)

from PyQt6.QtWidgets import QApplication


_APP: QApplication | None = None


def _ensure_app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication(sys.argv)
    return _APP


class TestDesktopApp(unittest.TestCase):
    def test_main_window_constructs(self):
        _ensure_app()

        import desktop.app as desktop_app

        with patch.object(desktop_app.DataWorker, "start", return_value=None), patch.object(
            desktop_app.DataWorker, "stop", return_value=None
        ):
            window = desktop_app.MainWindow()
            try:
                self.assertEqual(window.windowTitle(), "PRADY TRADER | Autonomous Trading Desk")
                self.assertEqual(window._stack.count(), 10)
                self.assertEqual(len(window._nav_buttons), 10)
            finally:
                window.close()
                window.deleteLater()


if __name__ == "__main__":
    unittest.main()