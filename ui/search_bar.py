"""
ui/search_bar.py
Custom search input: QLineEdit subclass with an animated placeholder
and an intent-badge label that floats to the right.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import QLineEdit, QSizePolicy


class SearchBar(QLineEdit):
    """
    Full-width search input.

    Extra signals:
      - arrow_up / arrow_down  → navigate results list
      - escape_pressed         → hide the overlay
      - enter_pressed          → confirm / launch selection
    """

    arrow_up      = Signal()
    arrow_down    = Signal()
    escape_pressed = Signal()
    enter_pressed  = Signal()
    tab_pressed    = Signal()
    delete_pressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SearchBar")
        self.setFont(QFont("Segoe UI Variable Display", 15, QFont.Weight.Normal))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(38)
        self.setClearButtonEnabled(False)
        self.setPlaceholderText("Search or ask anything...")
        self.setTextMargins(2, 0, 0, 0)
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, 0)
        self.setFrame(False)

    def focusNextPrevChild(self, next: bool) -> bool:
        """Catch Tab key before Qt's default focus navigation eats it."""
        self.tab_pressed.emit()
        return True

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Up:
            self.arrow_up.emit()
            return
        if key == Qt.Key.Key_Down:
            self.arrow_down.emit()
            return
        if key == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.enter_pressed.emit()
            return
        if key == Qt.Key.Key_Delete:
            self.delete_pressed.emit()
            return
        super().keyPressEvent(event)
