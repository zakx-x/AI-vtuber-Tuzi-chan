import os
import sys
import live2d.v3 as live2d
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication, QMainWindow

# Konfigurasi format OpenGL ke Compatibility Profile
fmt = QSurfaceFormat()
fmt.setRenderableType(QSurfaceFormat.OpenGL)
fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
fmt.setVersion(3, 3)
fmt.setAlphaBufferSize(8)
QSurfaceFormat.setDefaultFormat(fmt)

BASE_DIR = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
MODEL_PATH = f"{BASE_DIR}/Assets/model/tuzi_mian.model3.json"


class Live2DCanvas(QOpenGLWidget):

  def __init__(self, parent=None):
    super().__init__(parent)
    self.model = None

  def initializeGL(self):
    self.makeCurrent()
    # Inisialisasi engine tepat di dalam context OpenGL yang sudah aktif
    live2d.init()
    if hasattr(live2d, "glewInit"):
      live2d.glewInit()

    self.model = live2d.LAppModel()
    self.model.LoadModelJson(MODEL_PATH)
    self.model.Resize(self.width(), self.height())
    print("\n[SUCCESS] Model Live2D aktif di PySide6!\n")

  def resizeGL(self, w, h):
    if self.model:
      self.model.Resize(w, h)

  def paintGL(self):
    if not self.model:
      return
    live2d.clearBuffer(0.0, 0.0, 0.0, 0.0)
    self.model.Update()
    self.model.Draw()


class AvatarWindow(QMainWindow):

  def __init__(self):
    super().__init__()
    self.setWindowTitle("Live2D Desktop Pet")
    self.resize(500, 700)

    # Transparansi jendela
    self.setAttribute(Qt.WA_TranslucentBackground, True)
    self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

    self.canvas = Live2DCanvas(self)
    self.setCentralWidget(self.canvas)

    self.timer = QTimer(self)
    self.timer.timeout.connect(self.canvas.update)
    self.timer.start(16)


if __name__ == "__main__":
  app = QApplication(sys.argv)
  win = AvatarWindow()
  win.show()
  sys.exit(app.exec())