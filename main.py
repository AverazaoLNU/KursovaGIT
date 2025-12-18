import sys
import pyqtgraph as pg
from PyQt6.QtWidgets import QApplication
from mainwindow import AudioLabeler

try:
    pg.setConfigOptions(useOpenGL=True)
    pg.setConfigOptions(enableExperimental=True)
except Exception as e:
    print(f"OpenGL warning: {e}")

pg.setConfigOptions(antialias=False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = AudioLabeler()
    window.show()
    sys.exit(app.exec())