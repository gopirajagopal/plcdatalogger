"""
Boiler PLC Monitor — Entry Point
Run this script to launch the application.
"""

import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from ui_main import BoilerMonitorWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Boiler PLC Monitor")
    app.setOrganizationName("ERP Factory")
    app.setFont(QFont("Segoe UI", 9))

    window = BoilerMonitorWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
