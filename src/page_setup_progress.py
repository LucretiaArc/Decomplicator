import math
import logging

from PySide6 import QtCore
from PySide6.QtWidgets import *

import files
import project
import task_base
import task_impl
import gui_common


log = logging.getLogger(__name__)


class TaskRow(QWidget):
    def __init__(self, parent: QWidget, task: task_base.Task, level: int = 0):
        """
        A widget visually representing the status and progress of a task, including its subtasks if it is a
        TaskSequence. Subtasks are denoted using a visual indent.
        :param parent: Parent ``QWidget``, see ``QWidget``.
        :param task: Task about which to display information. Child widgets showing subtasks will be created
            automatically.
        :param level: Indent level of the task. If the indent level is negative, the task will be hidden. If the
            indent level is 1 or greater, subtasks will be hidden unless the task is in progress.
        """
        super().__init__(parent)
        self.level = level

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.task_info_row = QWidget(self)
        self.task_info_row.setLayout(QHBoxLayout(self.task_info_row))
        self.task_info_row.layout().setContentsMargins(5, 0, 5, 0)
        self.task_info_row.setFixedHeight(20)
        self.task_info_row.setObjectName("InfoRow")
        self.task_info_row.setStyleSheet("#InfoRow:hover {background-color: #20888888; border-radius: 4px}")
        self.layout().addWidget(self.task_info_row)

        self.task_label = QLabel(self.task_info_row)
        self.task_label.setWordWrap(True)
        self.task_label.setText(task.name)
        self.task_label.setIndent(max(0, level * 16))
        self.task_info_row.layout().addWidget(self.task_label)

        self.progress_container = QWidget(self.task_info_row)
        self.progress_container.setLayout(QHBoxLayout(self.progress_container))
        self.progress_container.setFixedWidth(168)
        self.progress_container.layout().setContentsMargins(0, 0, 0, 0)
        self.task_info_row.layout().addWidget(self.progress_container)

        self.progress_text = QLabel(self.progress_container)
        self.progress_container.layout().addWidget(self.progress_text)

        self.progress_bar = QProgressBar(self.progress_container)
        self.progress_bar.hide()
        self.progress_container.layout().addWidget(self.progress_bar)

        self.subtask_row = QWidget(self)
        self.subtask_row.setLayout(QVBoxLayout(self.subtask_row))
        self.subtask_row.layout().setContentsMargins(0, 0, 0, 0)
        self.subtask_row.hide()
        self.layout().addWidget(self.subtask_row)

        if level < 0:
            self.task_info_row.hide()

        task.signal_status.connect(self.update_status)
        task.signal_progress.connect(self.update_progress)

        self.has_subtasks = 0
        if isinstance(task, task_base.TaskSequence):
            for subtask in task.subtasks:
                if not subtask.hidden:
                    self.add_subtask(subtask)
                    self.has_subtasks = True

        self.update_status(task_base.Status.NOT_STARTED)
        self.update_progress(-1.0)

    def update_status(self, status: task_base.Status):
        if status == task_base.Status.WORKING:
            if self.has_subtasks:
                self.subtask_row.show()
            else:
                self.progress_text.hide()
                self.progress_bar.show()
        else:
            if status == task_base.Status.NOT_STARTED:
                self.progress_text.setText("")
            elif status == task_base.Status.SUCCESS:
                self.task_label.setStyleSheet("color: #888")
                self.progress_text.setStyleSheet("color: #090")
                self.progress_text.setText("Done")
                if self.level >= 1:
                    self.subtask_row.hide()
            elif status == task_base.Status.FAILURE:
                self.progress_text.setStyleSheet("color: #F00")
                self.progress_text.setText("ERROR")
            self.progress_bar.hide()
            self.progress_text.show()

    def update_progress(self, progress: float):
        if progress < 0:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 10000)
            self.progress_bar.setValue(math.floor(progress * 10000))

    def add_subtask(self, subtask):
        if self.level < 1:
            self.subtask_row.show()
        self.subtask_row.layout().addWidget(TaskRow(self.subtask_row, subtask, self.level + 1))


class SetupBaseProgressPage(QWizardPage):
    def __init__(self, setup_context: gui_common.SetupContext, project_context: gui_common.ProjectContext):
        super().__init__()
        self.setup_context = setup_context
        self.project_context = project_context
        self.setup_complete = False
        self.task = None

        self.setCommitPage(True)
        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(4, 9, 4, 9)

        self.scroll_container = QScrollArea(self)
        self.scroll_container.setWidgetResizable(True)
        self.scroll_container.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_container.setFrameShape(QFrame.Shape.NoFrame)
        self.layout().addWidget(self.scroll_container)

        self.task_container = QWidget(self.scroll_container)
        self.task_container.setLayout(QVBoxLayout(self.task_container))
        self.task_container.layout().setContentsMargins(0, 0, 0, 0)
        self.task_container.layout().setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.scroll_container.setWidget(self.task_container)

    def initializePage(self):
        cancel_button = self.wizard().button(QWizard.WizardButton.CancelButton)
        cancel_button.clicked.disconnect()
        cancel_button.clicked.connect(self.cancel_button)

        self.setSubTitle("Setting up project...")
        self.wizard().setOption(QWizard.WizardOption.NoCancelButton, False)
        self.wizard().button(QWizard.WizardButton.CancelButton).setEnabled(True)
        self.setButtonText(QWizard.WizardButton.CommitButton, self.buttonText(QWizard.WizardButton.NextButton))

        self.setup_complete = False

        if self.task:
            self.task.wait()
            self.task.deleteLater()

        task_container_layout = self.task_container.layout()
        while task_container_layout.count():
            child = task_container_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def isComplete(self):
        if self.task is None:
            return False
        else:
            return self.setup_complete

    def nextId(self) -> gui_common.PageId:
        return gui_common.PageId.SETUP_COMPLETE

    def _error(self, text: str):
        gui_common.error(self, text)

    def begin_setup(self):
        self.task.signal_success.connect(self.on_setup_success)
        self.task.signal_failure.connect(self.on_setup_failure)
        self.task.signal_cancelled.connect(self.on_setup_cancelled)
        self.task.signal_error.connect(self._error)
        self.task_container.layout().addWidget(TaskRow(self.task_container, self.task, -1))

        def task_tree_summary(task: task_base.Task, indent=0) -> str:
            text_out = f"{'\t' * indent}{task.name} ({task.__class__.__name__})"
            if isinstance(task, task_base.TaskSequence):
                for subtask in task.subtasks:
                    text_out += "\n" + task_tree_summary(subtask, indent + 1)

            return text_out

        log.info(f"Starting setup with following task tree:\n{task_tree_summary(self.task)}")

        self.task.start()

    def cancel_button(self):
        if not self.task.is_cancelled():
            status = self.task.get_status()
            if status == task_base.Status.WORKING:
                self.wizard().button(QWizard.WizardButton.CancelButton).setEnabled(False)
                self.setSubTitle("Cancelling...")
                self.task.cancel()
            elif status == task_base.Status.FAILURE:
                self.on_setup_cancelled()

    def on_setup_success(self):
        self.wizard().setOption(QWizard.WizardOption.NoCancelButton, True)
        self.setup_complete = True
        self.completeChanged.emit()
        QApplication.alert(self)
        QApplication.beep()
        log.info("Setup completed successfully")
        self.wizard().next()

    def on_setup_failure(self):
        self.wizard().button(QWizard.WizardButton.CancelButton).setEnabled(True)
        self.setSubTitle("Setup error")
        log.info("Setup failed")

    def on_setup_cancelled(self):
        self.wizard().setOption(QWizard.WizardOption.NoCancelButton, True)
        self.wizard().button(QWizard.WizardButton.CancelButton).setEnabled(True)
        self.wizard().restart()


class SetupFromTemplateProgressPage(SetupBaseProgressPage):
    def __init__(self, setup_context: gui_common.SetupContext, project_context: gui_common.ProjectContext):
        super().__init__(setup_context, project_context)
        self.cleanup_task = None

    def initializePage(self):
        super().initializePage()
        self.setTitle("New Project")

        self.project_context.project = project.Project(
            self.setup_context.project_path,
            self.setup_context.template_config
        )

        self.task = self.project_context.project.get_setup_task(self)
        project_file_task = task_impl.CreateProjectFileTask(
            self.task,
            "Finish project setup",
            self.setup_context.template_config_path,
            self.setup_context.project_path,
            self.project_context.project.get_env()
        )
        self.task.add_task(project_file_task)

        self.begin_setup()

    def on_setup_success(self):
        files.add_recent_project(self.setup_context.project_path / files.PROJECT_FILE_NAME)
        super().on_setup_success()

    def set_cleanup_task(self):
        if self.cleanup_task:
            self.cleanup_task.wait()
            self.cleanup_task.deleteLater()

        self.cleanup_task = task_impl.FileOperationSequenceTask(
            self,
            "Delete project directory",
            self.project_context.project.path,
            [["delete", ""]]
        )

    def on_setup_cancelled(self):
        self.wizard().button(QWizard.WizardButton.CancelButton).setEnabled(False)
        self.setSubTitle("Cleaning up...")
        self.set_cleanup_task()
        self.cleanup_task.signal_success.connect(super().on_setup_cancelled)
        self.cleanup_task.signal_failure.connect(super().on_setup_cancelled)
        self.cleanup_task.start()


class SetupFromRepoProgressPage(SetupBaseProgressPage):
    def initializePage(self):
        super().initializePage()
        self.setTitle(f"Project: {self.project_context.project.path.name}")
        self.task = self.project_context.project.get_setup_task(self, from_existing_repo=True)
        self.begin_setup()
