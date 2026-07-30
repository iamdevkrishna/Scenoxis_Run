"""
ui/scanner_overlay.py
A full-screen transparent overlay that displays a scanning edge animation
while the vision model analyzes the screen, without blocking PC usage.
"""
from PySide6.QtCore import Qt, QPropertyAnimation, Property, QRectF
from PySide6.QtGui import QPainter, QColor, QConicalGradient, QPen, QFont
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QGuiApplication

class ScannerOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # Cover primary screen
        screen = QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())

        self._angle = 0.0
        
        self._anim = QPropertyAnimation(self, b"angle", self)
        self._anim.setDuration(2000)  # 2 seconds per rotation
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(360.0)
        self._anim.setLoopCount(-1)  # Infinite loop
        
    def showEvent(self, event):
        super().showEvent(event)
        self._anim.start()
        
    def hideEvent(self, event):
        super().hideEvent(event)
        self._anim.stop()

    def get_angle(self) -> float:
        return self._angle

    def set_angle(self, val: float):
        self._angle = val
        self.update()

    angle = Property(float, get_angle, set_angle)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        # Conical gradient for the sweeping edge light
        grad = QConicalGradient(w / 2, h / 2, self._angle)
        grad.setColorAt(0.0, QColor(0, 255, 255, 255))   # Bright cyan head
        grad.setColorAt(0.1, QColor(0, 255, 255, 100))   # Fading tail
        grad.setColorAt(0.3, QColor(0, 255, 255, 0))     # Transparent
        grad.setColorAt(1.0, QColor(0, 255, 255, 255))   # Wrap around to head
        
        # Draw border
        pen = QPen(grad, 6) # 6px border thickness
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Draw slightly inside to ensure the border isn't clipped by the monitor edge
        painter.drawRect(3, 3, w - 6, h - 6)
        
        # Draw "Analyzing screen..." box in top right
        box_w, box_h = 200, 40
        box_x = w - box_w - 40
        box_y = 40
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(20, 20, 20, 230))
        painter.drawRoundedRect(box_x, box_y, box_w, box_h, 8, 8)
        
        # Draw text
        painter.setPen(QColor(255, 255, 255, 220))
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(box_x, box_y, box_w, box_h), Qt.AlignmentFlag.AlignCenter, "Analyzing screen...")
        
        painter.end()
