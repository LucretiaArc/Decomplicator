import logging

from PySide6 import QtCore
from PySide6.QtWidgets import *

import gui_common


log = logging.getLogger(__name__)


class SetupCompletePage(QWizardPage):
    def __init__(self, project_context: gui_common.ProjectContext):
        super().__init__()
        self.project_context = project_context

        self.setCommitPage(True)
        self.setButtonText(QWizard.WizardButton.CommitButton, "Finish")
        self.setSubTitle("Setup complete")
        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(5, 5, 0, 5)

        self.scroll_container = QScrollArea(self)
        self.scroll_container.setWidgetResizable(True)
        self.scroll_container.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_container.setFrameShape(QFrame.Shape.NoFrame)
        self.layout().addWidget(self.scroll_container)

        self.content_label = QLabel(self.scroll_container)
        self.content_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.content_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.content_label.setWordWrap(True)
        self.content_label.setOpenExternalLinks(True)
        self.scroll_container.setWidget(self.content_label)

    def initializePage(self):
        self.setTitle(f"Project: {self.project_context.project.path.name}")
        content_text = self.project_context.project.config.success_splash.strip()
        self.content_label.setText(content_text)

