import pathlib
import logging

from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import *

import files
import project
import gui_common


log = logging.getLogger(__name__)


class StartPage(QWizardPage):
    def __init__(self, setup_context: gui_common.SetupContext, project_context: gui_common.ProjectContext):
        super().__init__()
        self.setup_context = setup_context
        self.project_context = project_context
        self.next_page_id = gui_common.PageId.SETUP_TEMPLATE

        self.setTitle("Welcome")
        self.setLayout(QVBoxLayout(self))

        self.button_group = QButtonGroup(self)

        self.new_project_radio = QRadioButton("Create new project", self)
        self.layout().addWidget(self.new_project_radio)
        self.button_group.addButton(self.new_project_radio)

        self.open_project_radio = QRadioButton("Open existing project", self)
        self.layout().addWidget(self.open_project_radio)
        self.button_group.addButton(self.open_project_radio)

        self.recent_projects_container = QWidget(self)
        self.recent_projects_container.setLayout(QVBoxLayout())
        self.recent_projects_container.layout().setContentsMargins(24, 0, 0, 0)
        self.layout().addWidget(self.recent_projects_container)

        self.recent_project_buttons: list[QRadioButton] = []
        self.recent_project_files: list[pathlib.Path] = []
        for i in range(files.RECENT_PROJECT_COUNT):
            radio = QRadioButton("", self)
            self.recent_projects_container.layout().addWidget(radio)
            self.button_group.addButton(radio)
            self.recent_project_buttons.append(radio)

        self.button_group.buttonClicked.connect(self.completeChanged)

    def initializePage(self):
        self.configure_subtitle()

        self.setCommitPage(False)

        self.button_group.setExclusive(False)
        self.new_project_radio.setChecked(False)
        self.open_project_radio.setChecked(False)

        self.recent_project_files = files.get_recent_project_files()
        for i, radio in enumerate(self.recent_project_buttons):
            radio.setChecked(False)
            if i < len(self.recent_project_files):
                proj_file = self.recent_project_files[i]
                radio.setText(proj_file.parent.name)
                radio.show()
            else:
                radio.hide()

        self.button_group.setExclusive(True)
        self.completeChanged.emit()

    def isComplete(self):
        return self.button_group.checkedButton() is not None

    def validatePage(self):
        if self.new_project_radio.isChecked():
            self.next_page_id = gui_common.PageId.SETUP_TEMPLATE
            self.setup_context.setup_from_repo = False
            self.project_context.project = None
            log.info("Creating new project from template")
            return True
        elif self.open_project_radio.isChecked():
            file_name, _ = QFileDialog.getOpenFileName(
                self,
                "Open Project...",
                dir=str(files.get_default_directory()),
                filter="Project File (*.toml)"
            )
            if not file_name:
                return False
            project_file_path = pathlib.Path(file_name)
        else:
            for i, radio in enumerate(self.recent_project_buttons):
                if radio.isChecked():
                    project_file_path = self.recent_project_files[i]
                    break
            else:
                log.error("No project button is checked")
                return False

        files.add_recent_project(project_file_path)
        proj = project.Project(project_file_path.parent, project.Config(project_file_path))
        log.info(f"Opening existing project at {project_file_path}")
        if proj.existing_project_requires_setup():
            self.setup_context.setup_from_repo = True
            log.info("Project requires setup")
            if (files.ROM_CACHE_DIR / proj.config.baserom_hash).exists():
                self.next_page_id = gui_common.PageId.SETUP_PROGRESS_FROM_REPO
                self.setCommitPage(True)
            else:
                self.next_page_id = gui_common.PageId.SETUP_BASEROM
                self.setup_context.template_config = proj.config
        else:
            self.next_page_id = gui_common.PageId.PROJECT_ACTIONS

        self.project_context.project = proj

        return True

    def nextId(self) -> gui_common.PageId:
        return self.next_page_id

    def configure_subtitle(self):
        sentinel_text = ":: Sentinel Subtitle Widget Text ::"
        self.setSubTitle(sentinel_text)
        label: QLabel | None = None
        for widget in self.wizard().findChildren(QLabel):
            if widget.text() == sentinel_text:
                label = widget

        self.setSubTitle(f'Create or open a project<div align="right"><a href="://">About Decomplicator</a></div>')

        if label:
            label.linkActivated.connect(self.on_clicked_subtitle, type=QtCore.Qt.ConnectionType.UniqueConnection)

    def on_clicked_subtitle(self):
        log.info("Showing About dialog")
        dialog = AboutDialog(self)
        dialog.show()
        dialog.exec()
        dialog.deleteLater()


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None):
        super().__init__(parent, modal=True)

        self.setWindowTitle("About Decomplicator")
        self.setLayout(layout := QVBoxLayout(self))

        pixmap = QtGui.QPixmap(files.ASSETS_DIR / "icon.png")
        self.logo_image = QLabel(self)
        self.logo_image.setPixmap(pixmap.scaled(128, 128, mode=QtCore.Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(self.logo_image, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        version_string = self.get_version_string()
        version_string = f"{version_string}<br>" if version_string else ""

        description_text = (f'<p style="font-size: xx-large; font-weight: bold">Decomplicator</p>'
                            f'A tool to set up build environments for Nintendo 64 '
                            f'decompilation projects on Windows.<br><br>'
                            f'{version_string}'
                            f'Created by Lucretia')
        self.description_label = QLabel(description_text, self)
        self.description_label.setWordWrap(True)
        self.description_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.description_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        layout.addWidget(self.description_label)

        self.button_box = QDialogButtonBox(
            QtCore.Qt.Orientation.Horizontal,
            self,
            standardButtons=QDialogButtonBox.StandardButton.Close
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.close)
        layout.addWidget(self.button_box)

        self.setFixedSize(320, 320)

    @staticmethod
    def get_version_string() -> str:
        version_file_content = files.VERSION_FILE.read_text()
        version_number, commit_id = version_file_content.split("\n")

        if commit_id:
            return f"Version {version_number} (Build {commit_id})"
        elif version_number:
            return f"Version {version_number}"
        else:
            return ""
