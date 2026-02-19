"""
File Eraser Tool - Securely erases files by overwriting content in multiple steps.
"""

import os
import sys
import json
import random
import string
import logging
from datetime import datetime
from pathlib import Path
from typing import List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QTabWidget, QLabel, QProgressBar,
    QFileDialog, QMessageBox
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt


# Setup logging
LOG_FILE = Path(__file__).parent / "eraser.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).parent / "config.json"
DEFAULT_CONFIG = {
    "folders_to_erase": [],
    "files_to_erase": []
}


def load_config() -> dict:
    """Load configuration from JSON file."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """Save configuration to JSON file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info("Config saved successfully")
    except Exception as e:
        logger.error(f"Error saving config: {e}")


def get_all_files(paths: List[str]) -> List[Path]:
    """Get all files from the given paths (files and folders)."""
    all_files = []
    for path_str in paths:
        path = Path(path_str)
        if path.is_file():
            all_files.append(path)
        elif path.is_dir():
            for file_path in path.rglob('*'):
                if file_path.is_file():
                    all_files.append(file_path)
    return all_files


def erase_file(file_path: Path, progress_callback=None) -> bool:
    """
    Securely erase a file by overwriting its content in multiple steps.
    Returns True if successful, False otherwise.
    """
    try:
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return False

        # Read original content
        with open(file_path, 'rb') as f:
            original_content = f.read()
        
        original_size = len(original_content)
        if original_size == 0:
            logger.info(f"File is empty, skipping: {file_path}")
            return True

        # Step 1: Remove 10% of the content
        if progress_callback:
            progress_callback(f"Step 1/4: Removing 10% of content from {file_path.name}")
        new_size = int(original_size * 0.9)
        with open(file_path, 'wb') as f:
            f.write(original_content[:new_size])
        f.flush()
        os.fsync(f.fileno()) if hasattr(f, 'fileno') else None
        logger.info(f"Step 1 complete: Removed 10% from {file_path}")

        # Step 2: Replace remaining bytes with random letters
        if progress_callback:
            progress_callback(f"Step 2/4: Replacing with random letters in {file_path.name}")
        random_letters = ''.join(random.choices(string.ascii_letters, k=new_size)).encode()
        with open(file_path, 'wb') as f:
            f.write(random_letters)
            f.flush()
            os.fsync(f.fileno())
        logger.info(f"Step 2 complete: Replaced with random letters in {file_path}")

        # Step 3: Overwrite with "hello world" repeated
        if progress_callback:
            progress_callback(f"Step 3/4: Overwriting with 'hello world' in {file_path.name}")
        hello_data = (b"hello world " * (new_size // 12 + 1))[:new_size]
        with open(file_path, 'wb') as f:
            f.write(hello_data)
            f.flush()
            os.fsync(f.fileno())
        logger.info(f"Step 3 complete: Overwrote with 'hello world' in {file_path}")

        # Step 4: Overwrite with empty content
        if progress_callback:
            progress_callback(f"Step 4/4: Clearing content of {file_path.name}")
        with open(file_path, 'wb') as f:
            f.write(b'')
            f.flush()
            os.fsync(f.fileno())
        logger.info(f"Step 4 complete: Cleared content of {file_path}")

        logger.info(f"Successfully erased: {file_path}")
        return True

    except Exception as e:
        logger.error(f"Error erasing {file_path}: {e}")
        return False


class EraseWorker(QThread):
    """Worker thread for erasing files."""
    progress = pyqtSignal(str)
    file_progress = pyqtSignal(int, int)  # current, total
    finished_signal = pyqtSignal(int, int)  # success_count, fail_count
    
    def __init__(self, files: List[Path]):
        super().__init__()
        self.files = files
        self.is_running = True
    
    def run(self):
        success_count = 0
        fail_count = 0
        total = len(self.files)
        
        for i, file_path in enumerate(self.files):
            if not self.is_running:
                self.progress.emit("Erasing stopped by user")
                break

            self.file_progress.emit(i + 1, total)
            self.progress.emit(f"Processing file {i + 1}/{total}: {file_path.name}")

            if erase_file(file_path, self.progress.emit):
                success_count += 1
            else:
                fail_count += 1

        self.finished_signal.emit(success_count, fail_count)

    def stop(self):
        self.is_running = False


class FileEraserApp(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Eraser Tool")
        self.setMinimumSize(700, 500)

        self.config = load_config()
        self.worker = None

        self.setup_ui()

    def setup_ui(self):
        """Setup the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Eraser
        eraser_tab = QWidget()
        eraser_layout = QVBoxLayout(eraser_tab)

        # Buttons row
        btn_layout = QHBoxLayout()

        self.add_files_btn = QPushButton("📁 Add Files")
        self.add_files_btn.clicked.connect(self.add_files)
        btn_layout.addWidget(self.add_files_btn)

        self.add_folder_btn = QPushButton("📂 Add Folder")
        self.add_folder_btn.clicked.connect(self.add_folder)
        btn_layout.addWidget(self.add_folder_btn)

        self.clear_btn = QPushButton("🗑️ Clear List")
        self.clear_btn.clicked.connect(self.clear_list)
        btn_layout.addWidget(self.clear_btn)

        eraser_layout.addLayout(btn_layout)

        # Start/Stop buttons
        action_layout = QHBoxLayout()

        self.start_btn = QPushButton("▶️ Start Erasing")
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        self.start_btn.clicked.connect(self.start_erasing)
        action_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹️ Stop Erasing")
        self.stop_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 10px;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_erasing)
        action_layout.addWidget(self.stop_btn)

        eraser_layout.addLayout(action_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        eraser_layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Ready")
        eraser_layout.addWidget(self.status_label)

        # Log display
        eraser_layout.addWidget(QLabel("Log:"))
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        eraser_layout.addWidget(self.log_display)

        self.tabs.addTab(eraser_tab, "🔥 Eraser")

        # Tab 2: Config Editor
        config_tab = QWidget()
        config_layout = QVBoxLayout(config_tab)

        config_layout.addWidget(QLabel("Configuration (JSON):"))
        self.config_editor = QTextEdit()
        self.config_editor.setPlainText(json.dumps(self.config, indent=2))
        config_layout.addWidget(self.config_editor)

        save_config_btn = QPushButton("💾 Save Config")
        save_config_btn.clicked.connect(self.save_config_from_editor)
        config_layout.addWidget(save_config_btn)

        self.tabs.addTab(config_tab, "⚙️ Config")

    def log(self, message: str):
        """Add message to log display."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_display.append(f"[{timestamp}] {message}")

    def add_files(self):
        """Add files to the erase list."""
        files, _ = QFileDialog.getOpenFileNames(self, "Select Files to Erase")
        if files:
            self.config["files_to_erase"].extend(files)
            save_config(self.config)
            self.update_config_editor()
            self.log(f"Added {len(files)} file(s) to erase list")

    def add_folder(self):
        """Add folder to the erase list."""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Erase")
        if folder:
            self.config["folders_to_erase"].append(folder)
            save_config(self.config)
            self.update_config_editor()
            self.log(f"Added folder: {folder}")

    def clear_list(self):
        """Clear the erase list."""
        self.config["files_to_erase"] = []
        self.config["folders_to_erase"] = []
        save_config(self.config)
        self.update_config_editor()
        self.log("Cleared erase list")

    def update_config_editor(self):
        """Update config editor with current config."""
        self.config_editor.setPlainText(json.dumps(self.config, indent=2))

    def save_config_from_editor(self):
        """Save config from editor text."""
        try:
            self.config = json.loads(self.config_editor.toPlainText())
            save_config(self.config)
            self.log("Config saved successfully")
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Invalid JSON", f"Config is not valid JSON: {e}")

    def start_erasing(self):
        """Start the erasing process."""
        all_paths = self.config.get("files_to_erase", []) + self.config.get("folders_to_erase", [])
        if not all_paths:
            QMessageBox.warning(self, "No Files", "No files or folders configured for erasing.")
            return

        files = get_all_files(all_paths)
        if not files:
            QMessageBox.warning(self, "No Files", "No files found in the configured paths.")
            return

        # Confirm
        reply = QMessageBox.question(
            self, "Confirm Erase",
            f"Are you sure you want to erase {len(files)} file(s)?\n\nThis will overwrite all content and cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.log(f"Starting erase of {len(files)} files...")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(files))
        self.progress_bar.setValue(0)

        self.worker = EraseWorker(files)
        self.worker.progress.connect(self.log)
        self.worker.file_progress.connect(self.update_progress)
        self.worker.finished_signal.connect(self.on_erase_finished)
        self.worker.start()

    def stop_erasing(self):
        """Stop the erasing process."""
        if self.worker:
            self.worker.stop()
            self.log("Stopping erase process...")

    def update_progress(self, current: int, total: int):
        """Update progress bar."""
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Processing {current}/{total}")

    def on_erase_finished(self, success: int, fail: int):
        """Handle erase completion."""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Ready")
        self.log(f"Erase complete: {success} succeeded, {fail} failed")
        QMessageBox.information(self, "Complete", f"Erasing complete!\n\nSuccess: {success}\nFailed: {fail}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FileEraserApp()
    window.show()
    sys.exit(app.exec())

