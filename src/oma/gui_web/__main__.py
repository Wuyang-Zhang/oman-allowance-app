from PySide6.QtWidgets import QApplication

from .app import WebApp


if __name__ == "__main__":
    app = QApplication([])
    window = WebApp()
    window.resize(1280, 800)
    window.show()
    app.exec()
