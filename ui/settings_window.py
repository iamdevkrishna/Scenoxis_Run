from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QComboBox, QMessageBox, QGroupBox, QFormLayout
)
from PySide6.QtCore import Qt
import core.config as config

class SettingsWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scenoxis Run - Settings")
        self.setMinimumWidth(400)
        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # API Keys Group
        api_group = QGroupBox("API Keys")
        api_layout = QFormLayout(api_group)

        self.groq_key_input = QLineEdit()
        self.groq_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.groq_key_input.setPlaceholderText("gsk_...")
        api_layout.addRow("Groq API Key:", self.groq_key_input)

        self.tavily_key_input = QLineEdit()
        self.tavily_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.tavily_key_input.setPlaceholderText("tvly-...")
        api_layout.addRow("Tavily API Key:", self.tavily_key_input)

        layout.addWidget(api_group)

        # Appearance Group
        appearance_group = QGroupBox("Appearance")
        app_layout = QFormLayout(appearance_group)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System", "Dark", "Light"])
        app_layout.addRow("Theme:", self.theme_combo)

        layout.addWidget(appearance_group)

        # Buttons
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._save_config)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def _load_config(self):
        # Load API keys
        self.groq_key_input.setText(config.get("GROQ_API_KEY", ""))
        self.tavily_key_input.setText(config.get("TAVILY_API_KEY", ""))

        # Load theme
        theme = config.get("theme", "system").lower()
        if theme == "dark":
            self.theme_combo.setCurrentIndex(1)
        elif theme == "light":
            self.theme_combo.setCurrentIndex(2)
        else:
            self.theme_combo.setCurrentIndex(0)

    def _save_config(self):
        config.set("GROQ_API_KEY", self.groq_key_input.text().strip())
        config.set("TAVILY_API_KEY", self.tavily_key_input.text().strip())
        
        idx = self.theme_combo.currentIndex()
        if idx == 1:
            config.set("theme", "dark")
        elif idx == 2:
            config.set("theme", "light")
        else:
            config.set("theme", "system")

        QMessageBox.information(self, "Settings Saved", "Your settings have been saved successfully.")
        self.accept()
