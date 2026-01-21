import logging

from PySide6 import QtCore
from PySide6.QtWidgets import *

import project
import task_base
import task_impl
import gui_common
import output_dialog


log = logging.getLogger(__name__)


class ProjectActionConsoleOutputDialog(output_dialog.OutputProgressDialog):
    def __init__(self, parent: QWidget | None, proj: project.Project, action: project.Action):
        """
        Creates a dialog that performs a project action, displaying stdout and stderr. The underlying task is started
        when the dialog is shown.
        :param parent: Parent ``QWidget``, see ``QWidget``.
        :param proj: Project for which the action should be performed.
        :param action: Action to be performed.
        """
        super().__init__(parent, action.name)
        self.project = project
        self.action = action

        self.task = task_impl.ExecuteActionTask(self, self.action.name, self.action.commands, proj.path, proj.get_env())
        self.task.signal_new_command.connect(self.stdout.add_command_line)
        self.task.signal_stdout.connect(self.stdout.add_line)
        self.task.signal_stderr.connect(self.stderr.add_line)
        self.task.signal_status.connect(self.on_task_status_change)
        self.task.signal_error.connect(self._error)

    def show(self):
        self.task.start()
        super().show()

    def closeEvent(self, ev: QtCore.QEvent):
        task_status = self.task.get_status()
        if task_status == task_base.Status.WORKING or task_status == task_base.Status.NOT_STARTED:
            self.activity_label.setText("Stopping...")
            self.task.cancel()
        self.button.setEnabled(False)
        self.setWindowFlag(QtCore.Qt.WindowType.WindowCloseButtonHint, False)
        self.task.wait()

    def on_task_status_change(self, status: task_base.Status):
        if status == task_base.Status.WORKING:
            return

        self.button.setText("Close")
        self.button.setEnabled(True)
        self.progress_bar.setRange(0, 1)

        if status == task_base.Status.SUCCESS:
            self.progress_bar.setValue(1)
            self.activity_label.setText("Finished.")
        elif status == task_base.Status.FAILURE:
            self.progress_bar.setValue(0)
            self.activity_label.setText("An error occurred.")
        elif status == task_base.Status.CANCELLED:
            self.progress_bar.setValue(0)
            self.activity_label.setText("Cancelled.")

    def _error(self, text: str):
        gui_common.error(self, text)


class BaseActionRow(QWidget):
    def __init__(self, parent: QWidget, name: str, description: str):
        super().__init__(parent)

        self.setLayout(QHBoxLayout(self))
        self.setFixedHeight(36)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(12)

        self.action_button = QPushButton(name, self)
        self.action_button.setFixedWidth(150)
        self.layout().addWidget(self.action_button)

        self.description_label = QLabel(description, self)
        self.description_label.setWordWrap(True)
        self.layout().addWidget(self.description_label)

class ProjectActionRow(BaseActionRow):
    def __init__(self, parent: QWidget, proj: project.Project, action: project.Action):
        super().__init__(parent, action.name, action.description)
        self.project: project.Project = proj
        self.action: project.Action = action
        self.dialog: ProjectActionConsoleOutputDialog | None = None

        self.action_button.clicked.connect(self.exec_action)

    def exec_action(self):
        if self.dialog:
            self.dialog.deleteLater()

        log.info(f"Executing action {self.action.name}")
        self.dialog = ProjectActionConsoleOutputDialog(self, self.project, self.action)
        self.dialog.show()


class ProjectActionsPage(QWizardPage):
    def __init__(self, project_context: gui_common.ProjectContext):
        super().__init__()
        self.project_context = project_context

        self.setTitle("")
        self.setSubTitle("Project Actions")
        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 5, 0, 5)

        self.scroll_container = QScrollArea(self)
        self.scroll_container.setWidgetResizable(True)
        self.scroll_container.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_container.setFrameShape(QFrame.Shape.NoFrame)
        self.layout().addWidget(self.scroll_container)

        self.action_container = QWidget(self.scroll_container)
        self.action_container.setLayout(QVBoxLayout(self.action_container))
        self.action_container.layout().setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.action_container.layout().setContentsMargins(0, 0, 0, 0)
        self.scroll_container.setWidget(self.action_container)

        self.predefined_action_container = QWidget(self.action_container)
        self.predefined_action_container.setLayout(QVBoxLayout(self.predefined_action_container))
        self.predefined_action_container.layout().setContentsMargins(0, 0, 0, 0)
        self.action_container.layout().addWidget(self.predefined_action_container)

        console_action = BaseActionRow(
            self.predefined_action_container,
            "Open Terminal",
            "Opens a terminal session in the environment used to build the ROM."
        )
        console_action.action_button.clicked.connect(self.open_terminal)
        self.predefined_action_container.layout().addWidget(console_action)

        self.project_action_container = QWidget(self.action_container)
        self.project_action_container.setLayout(QVBoxLayout(self.project_action_container))
        self.project_action_container.layout().setContentsMargins(0, 0, 0, 0)
        self.action_container.layout().addWidget(self.project_action_container)

    def initializePage(self):
        self.setTitle(f"Project: {self.project_context.project.path.name}")

        log.info(f"Opened project at {self.project_context.project.path}")
        env = self.project_context.project.get_env()
        path_desc = "\n".join(filter(None, env["PATH"].split(";")))
        log.info(f"Project PATH:\n{path_desc}")

        while self.project_action_container.layout().count():
            child = self.project_action_container.layout().takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        actions = self.project_context.project.config.action_data
        for action in actions:
            log.info(f"Adding action {action.name}")
            self.project_action_container.layout().addWidget(ProjectActionRow(
                self.project_action_container,
                self.project_context.project,
                action
            ))

    def open_terminal(self):
        log.debug("Opened project environment terminal")
        self.project_context.project.open_terminal()
