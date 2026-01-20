import enum
import logging
import pathlib

from PySide6.QtWidgets import *

import project


log = logging.getLogger(__name__)


class PageId(enum.IntEnum):
    START = 0
    SETUP_TEMPLATE = 1
    SETUP_DIRECTORY = 2
    SETUP_BASEROM = 3
    SETUP_PROGRESS_FROM_TEMPLATE = 4
    SETUP_PROGRESS_FROM_REPO = 5
    PROJECT_ACTIONS = 6


class ProjectContext:
    def __init__(self):
        self.project: project.Project | None = None


class SetupContext:
    def __init__(self):
        self.setup_from_repo: bool = False
        self.project_path: pathlib.Path | None = None
        self.template_config_path: pathlib.Path | None = None
        self.template_config: project.Config | None = None


def info(parent: QWidget, text: str):
    log.info(f"Information dialog shown: {text}")
    QMessageBox.information(parent, "Information", text)


def warning(parent: QWidget, text: str):
    log.info(f"Warning dialog shown: {text}")
    QMessageBox.warning(parent, "Warning", text)


def error(parent: QWidget, text: str):
    log.info(f"Error dialog shown: {text}")
    QMessageBox.critical(parent, "Error", text)