import pathlib
import logging

from PySide6 import QtCore
from PySide6.QtWidgets import *

import files
import gui_common


log = logging.getLogger(__name__)


class SetupDirectoryPage(QWizardPage):
    def __init__(self, setup_context: gui_common.SetupContext):
        super().__init__()
        self.setup_context = setup_context
        self.baserom_exists = False

        self.setTitle("New Project")
        self.setSubTitle("Select project folder")
        self.setButtonText(QWizard.WizardButton.CommitButton, "Create Project")
        self.setLayout(QVBoxLayout(self))

        self.instruction_text = QLabel("Please select the folder that will contain the project.", self)
        self.instruction_text.setWordWrap(True)
        self.layout().addWidget(self.instruction_text)

        self.directory_row = QWidget(self)
        self.directory_row.setLayout(QHBoxLayout(self.directory_row))
        self.directory_row.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.directory_row)

        self.browse_button = QPushButton("Browse...", self.directory_row)
        self.browse_button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.directory_row.layout().addWidget(self.browse_button)

        self.directory_text = QLabel("", self.directory_row)
        self.directory_row.layout().addWidget(self.directory_text)

        self.browse_button.clicked.connect(self.select_directory)

    def check_baserom(self) -> bool:
        if self.setup_context.template_config:
            baserom_hash = self.setup_context.template_config.baserom_hash
            baserom_cache_path = (files.ROM_CACHE_DIR / baserom_hash)
            if baserom_cache_path.exists():
                return True

        return False

    def initializePage(self):
        self.setup_context.project_path = None
        self.directory_text.setText("No folder selected.")
        self.baserom_exists = self.check_baserom()
        self.setCommitPage(self.baserom_exists)  # Next page will be a setup page
        self.completeChanged.emit()

        log.info("Cached baserom exists" if self.baserom_exists else "Cached baserom missing")

    def isComplete(self):
        if self.setup_context.project_path is None:
            return False
        else:
            return len(list(self.setup_context.project_path.iterdir())) == 0

    def nextId(self) -> gui_common.PageId:
        if self.baserom_exists:
            if self.setup_context.setup_from_repo:
                return gui_common.PageId.SETUP_PROGRESS_FROM_REPO
            else:
                return gui_common.PageId.SETUP_PROGRESS_FROM_TEMPLATE
        else:
            return gui_common.PageId.SETUP_BASEROM

    def select_directory(self):
        while True:
            result = QFileDialog.getExistingDirectory(
                self,
                "Select project folder",
                dir=str(files.get_default_directory())
            )
            if not result:
                break

            project_path = pathlib.Path(result)
            if not project_path.is_dir():
                gui_common.warning(self, "Invalid folder selected. Please select a different folder.")
                continue

            if not list(project_path.iterdir()):
                self.setup_context.project_path = project_path
                elided_text = self.directory_text.fontMetrics().elidedText(
                    str(project_path),
                    QtCore.Qt.TextElideMode.ElideMiddle,
                    self.directory_text.width()
                )
                self.directory_text.setText(elided_text)
                self.completeChanged.emit()
                log.info(f"Selected project directory {project_path}")
                break
            else:
                gui_common.warning(self, "Project folder must be empty. Please select a different folder.")
