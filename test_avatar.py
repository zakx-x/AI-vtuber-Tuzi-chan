import os
import sys
import live2d.v3 as live2d
from PySide6.QtCore import QTimer
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication, QMainWindow

# Path model
BASE_DIR = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
MODEL_PATH = f"{BASE_DIR}/Assets/model/tuzi_mian.model3.json"


class SimpleCanvas(QOpenGLWidget):

  def __init__(self, parent=None):
    super().__init__(parent)
    self.model = None
    self.is_loaded = False

  def initializeGL(self):
    self.makeCurrent()

    # Inisialisasi GLEW wajib dipanggil pada Windows setelah makeCurrent()
    if hasattr(live2d, "glewInit"):
      live2d.glewInit()

    try:
      self.model = live2d.LAppModel()
      self.model.LoadModelJson(MODEL_PATH)
      self.model.Resize(self.width(), self.height())
      self.is_loaded = True
      print("\n==========================================")
      print(" [SUCCESS] Model Live2D Berhasil Dimuat! ")
      print("==========================================\n")
    except Exception as e:
      print(f"[ERROR] Gagal memuat model: {e}")
      self.is_loaded = False

  def resizeGL(self, w, h):
    if self.model and self.is_loaded:
      self.model.Resize(w, h)

  def paintGL(self):
    if not self.model or not self.is_loaded:
      return

    live2d.clearBuffer()
    self.model.Update()
    self.model.Draw()


class SimpleWindow(QMainWindow):

  def __init__(self):
    super().__init__()
    self.setWindowTitle("Live2D Avatar Test")
    self.resize(500, 700)

    self.canvas = SimpleCanvas(self)
    self.setCentralWidget(self.canvas)

    # 60 FPS loop
    self.timer = QTimer(self)
    self.timer.timeout.connect(self.canvas.update)
    self.timer.start(16)


if __name__ == "__main__":
  if not os.path.exists(MODEL_PATH):
    print(f"[ERROR] File tidak ditemukan di: {MODEL_PATH}")
    sys.exit(1)

  # Panggil init Live2D sebelum inisialisasi QApplication
  live2d.init()

  app = QApplication(sys.argv)
  win = SimpleWindow()
  win.show()

  exit_code = app.exec()
  live2d.dispose()
  sys.exit(exit_code)