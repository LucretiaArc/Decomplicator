import __main__
import ctypes.wintypes
import logging
import os
import pathlib
import sys

PROJECT_FILE_NAME = "decomplicator.toml"
RECENT_PROJECT_COUNT = 8


log = logging.getLogger(__name__)


# Static data directory location changes depending on whether the application is packaged or running from source
# See https://pyinstaller.org/en/stable/runtime-information.html
is_packaged = (getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))
if is_packaged:
    STATIC_DATA_DIR = pathlib.Path(__main__.__file__).parent
else:
    STATIC_DATA_DIR = pathlib.Path(__main__.__file__).parent.parent

ASSETS_DIR = STATIC_DATA_DIR / "assets"
CONFIG_DIR = STATIC_DATA_DIR / "config"
VERSION_FILE = STATIC_DATA_DIR / "version.txt"

PERSISTENT_DATA_DIR = pathlib.Path(os.getenv("APPDATA")) / "Decomplicator"
PERSISTENT_DATA_DIR.mkdir(exist_ok=True)
RECENT_PROJECTS_FILE = PERSISTENT_DATA_DIR / "recent.txt"

VARIABLE_DATA_DIR = pathlib.Path(os.getenv("LOCALAPPDATA")) / "Decomplicator"
VARIABLE_DATA_DIR.mkdir(exist_ok=True)
DEP_CACHE_DIR = VARIABLE_DATA_DIR / "dependencies"
ROM_CACHE_DIR = VARIABLE_DATA_DIR / "baseroms"
LOGS_DIR = VARIABLE_DATA_DIR / "logs"


_CSIDL_PERSONAL = 5  # My Documents
_SHGFP_TYPE_CURRENT = 0  # Get current, not default value

# noinspection PyUnresolvedReferences
_get_folder_path = ctypes.windll.shell32.SHGetFolderPathW


def get_default_directory() -> pathlib.Path:
    buffer = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    _get_folder_path(None, _CSIDL_PERSONAL, None, _SHGFP_TYPE_CURRENT, buffer)

    return pathlib.Path(buffer.value)


def get_recent_project_files() -> list[pathlib.Path]:
    """
    Gets a list of paths to recent projects. If any of the project files can't be found, those project paths will be
    omitted from the list.
    :return: List of recent projects in reverse chronological order (most recent first).
    """
    try:
        file_text = RECENT_PROJECTS_FILE.read_text()
    except OSError:
        log.warning("Couldn't read recent projects file")
        return []

    project_paths = [pathlib.Path(line.strip()) for line in file_text.splitlines() if line]
    projects = []
    for p in project_paths:
        if p.exists():
            projects.append(p)
        else:
            log.warning(f"Couldn't locate recent project {p}")

    return projects


def add_recent_project(project_file: pathlib.Path):
    """
    Marks a project file as recently opened.
    :param project_file: Path to the project file.
    """
    old_recent_projects = get_recent_project_files()
    new_recent_projects = [project_file]
    for p in old_recent_projects:
        if p not in new_recent_projects:
            new_recent_projects.append(p)

    new_recent_projects = new_recent_projects[:RECENT_PROJECT_COUNT]
    file_text = "\n".join(str(p) for p in new_recent_projects)
    try:
        RECENT_PROJECTS_FILE.write_text(file_text)
    except OSError:
        log.warning("Couldn't write to recent projects file")
        pass
