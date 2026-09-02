import math
import os
import random
import time
import live2d.v3 as live2d
from PySide6.QtCore import QTimer, Qt
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QMainWindow


class Live2DCanvas(QOpenGLWidget):

  def __init__(self, model_json_path, parent=None):
    super().__init__(parent)
    # Konversi path ke format forward slash Unix agar kompatibel dengan C++ SDK
    self.model_json_path = os.path.abspath(model_json_path).replace("\\", "/")
    self.model_dir = os.path.dirname(self.model_json_path)
    self.model = None

    # Parameter Gerakan
    self.mouth_open = 0.0
    self.target_angle_x = 0.0
    self.target_angle_y = 0.0
    self.curr_angle_x = 0.0
    self.curr_angle_y = 0.0
    self.last_look_time = time.time()

  def initializeGL(self):
    self.makeCurrent()

    # Pindahkan working directory sementara ke folder model agar file .moc3 & textures terbaca
    orig_cwd = os.getcwd()
    os.chdir(self.model_dir)

    try:
      live2d.init()
      self.model = live2d.LAppModel()
      self.model.LoadModelJson(self.model_json_path)
      self.model.Resize(self.width(), self.height())
    finally:
      os.chdir(orig_cwd)

  def resizeGL(self, w, h):
    if self.model:
      self.model.Resize(w, h)

  def paintGL(self):
    if not self.model:
      return

    live2d.clearBuffer()

    # 1. Animasi Idle Menoleh
    now = time.time()
    if now - self.last_look_time > random.uniform(3.0, 5.0):
      self.target_angle_x = random.uniform(-20.0, 20.0)
      self.target_angle_y = random.uniform(-10.0, 10.0)
      self.last_look_time = now

    self.curr_angle_x += (self.target_angle_x - self.curr_angle_x) * 0.05
    self.curr_angle_y += (self.target_angle_y - self.curr_angle_y) * 0.05

    # 2. Pernapasan Otomatis
    breath_val = (math.sin(now * 2.5) + 1.0) / 2.0

    # 3. Kirim Parameter ke Model
    self.model.SetParameterValue("ParamAngleX", self.curr_angle_x, 1.0)
    self.model.SetParameterValue("ParamAngleY", self.curr_angle_y, 1.0)
    self.model.SetParameterValue(
        "ParamBodyAngleX", self.curr_angle_x * 0.5, 1.0
    )
    self.model.SetParameterValue("ParamBreath", breath_val, 1.0)
    self.model.SetParameterValue("ParamMouthOpenY", self.mouth_open, 1.0)

    self.model.Update()
    self.model.Draw()

  def set_mouth(self, value: float):
    self.mouth_open = max(0.0, min(1.0, float(value)))


class AvatarWindow(QMainWindow):

  def __init__(self, model_json_path):
    super().__init__()
    self.setWindowTitle("AI Avatar")
    self.resize(500, 700)

    # Window Transparan & Frameless
    self.setAttribute(Qt.WA_TranslucentBackground, True)
    self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

    self.canvas = Live2DCanvas(model_json_path, self)
    self.setCentralWidget(self.canvas)

    # Loop Render 60 FPS
    self.timer = QTimer(self)
    self.timer.timeout.connect(self.canvas.update)
    self.timer.start(16)

    self.drag_position = None

  def mousePressEvent(self, event):
    if event.button() == Qt.LeftButton:
      self.drag_position = (
          event.globalPosition().toPoint() - self.frameGeometry().topLeft()
      )
      event.accept()

  def mouseMoveEvent(self, event):
    if event.buttons() == Qt.LeftButton and self.drag_position:
      self.move(event.globalPosition().toPoint() - self.drag_position)
      event.accept()