import datetime
import logging
import sys

from PySide6 import QtGui
from PySide6.QtWidgets import *

import files
import gui_common
import page_start
import page_setup_template
import page_setup_directory
import page_setup_rom
import page_setup_progress
import page_setup_complete
import page_actions


log = logging.getLogger(__name__)
exception_logger = logging.getLogger().getChild("_EXCEPTION_LOGGING")


class MainWindow(QWizard):
    def __init__(self):
        super().__init__()

        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setWindowTitle("Decomplicator")

        setup_context = gui_common.SetupContext()
        project_context = gui_common.ProjectContext()

        self.setOption(QWizard.WizardOption.NoCancelButton, True)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setOption(QWizard.WizardOption.NoBackButtonOnLastPage, True)

        self.setPage(gui_common.PageId.START, page_start.StartPage(setup_context, project_context))
        self.setPage(gui_common.PageId.SETUP_TEMPLATE, page_setup_template.SetupTemplatePage(setup_context))
        self.setPage(gui_common.PageId.SETUP_DIRECTORY, page_setup_directory.SetupDirectoryPage(setup_context))
        self.setPage(gui_common.PageId.SETUP_BASEROM, page_setup_rom.SetupBaseromPage(setup_context))

        self.setPage(
            gui_common.PageId.SETUP_PROGRESS_FROM_TEMPLATE,
            page_setup_progress.SetupFromTemplateProgressPage(setup_context, project_context)
        )

        self.setPage(
            gui_common.PageId.SETUP_PROGRESS_FROM_REPO,
            page_setup_progress.SetupFromRepoProgressPage(setup_context, project_context)
        )

        self.setPage(gui_common.PageId.SETUP_COMPLETE, page_setup_complete.SetupCompletePage(project_context))
        self.setPage(gui_common.PageId.PROJECT_ACTIONS, page_actions.ProjectActionsPage(project_context))

        self.currentIdChanged.connect(self.log_page_changed)

        # The "Back" button can't be used from the project actions page after project setup, since it would lead to the
        # setup progress page. Since it's always the last page, the "Finish" button is repurposed to restart the wizard.
        self.setButtonText(QWizard.WizardButton.FinishButton, self.buttonText(QWizard.WizardButton.BackButton))
        finish_button = self.button(QWizard.WizardButton.FinishButton)
        finish_button.clicked.disconnect()
        finish_button.clicked.connect(self.restart)

        self.setMinimumSize(640, 480)
        self.show()

    def restart(self):
        self.page(gui_common.PageId.START).initializePage()
        super().restart()

    @staticmethod
    def log_page_changed(page_id: gui_common.PageId):
        if page_id not in gui_common.PageId:
            return

        log.debug(f"User switched to page {gui_common.PageId(page_id).name}")


class LogFormatter(logging.Formatter):
    def format(self, record):
        if record.name == exception_logger.name:
            original_format = self._style._fmt
            self._style._fmt = "[{levelname}] {asctime}.{msecs:03.0f}: {message}"
            s = super().format(record)
            self._style._fmt = original_format
        else:
            s = super().format(record)
        return s.replace("\n", "\n\t")


class ErrorMessageHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.window: QWidget | None = None

    def set_window(self, window: QWidget):
        self.window = window

    def emit(self, record):
        if record.name == exception_logger.name:
            gui_common.error(self.window, "A fatal error occurred. See the log file for more information.")
            sys.exit(1)


def exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
    else:
        exception_logger.error("", exc_info=(exc_type, exc_value, exc_traceback))


def main():
    files.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_files = sorted(files.LOGS_DIR.iterdir())
    while len(log_files) >= 100:
        log_files.pop(0).unlink()

    log_file_name = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f.log")
    file_handler = logging.FileHandler(files.LOGS_DIR / log_file_name, encoding="utf-8", delay=True)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(LogFormatter(
        fmt="[{levelname}] {module} @ {asctime}.{msecs:03.0f}: {message}",
        datefmt="%Y-%b-%d %H:%M:%S",
        style="{")
    )

    error_handler = ErrorMessageHandler()

    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
    root_logger.setLevel(logging.DEBUG)
    sys.excepthook = exception_handler

    app = QApplication([])
    app.setWindowIcon(QtGui.QIcon(str(files.ASSETS_DIR / "icon.png")))
    window = MainWindow()
    error_handler.set_window(window)
    app.exec()


if __name__ == "__main__":
    # Make requests use system SSL certificates
    # See https://pypi.org/project/pip-system-certs/
    import pip_system_certs.wrapt_requests
    pip_system_certs.wrapt_requests.inject_truststore()

    main()
