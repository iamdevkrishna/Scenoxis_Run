import os
import markdown
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout

class FeaturesWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scenoxis Run - Features")
        self.setMinimumSize(600, 500)
        self._setup_ui()
        self._load_readme()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        layout.addWidget(self.browser)
        
        btn_layout = QHBoxLayout()
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

    def _load_readme(self):
        # We need to find README.md either in local dir or bundled app path
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        readme_path = os.path.join(base_path, "README.md")
        
        if os.path.exists(readme_path):
            try:
                with open(readme_path, "r", encoding="utf-8") as f:
                    md_text = f.read()
                    html = markdown.markdown(md_text, extensions=['tables', 'fenced_code'])
                    self.browser.setHtml(html)
            except Exception as e:
                self.browser.setText(f"Error loading features: {e}")
        else:
            self.browser.setText("README.md not found. Cannot load features.")
