import pathlib
import logging

from PySide6 import QtCore
from PySide6.QtWidgets import *

import files
import project
import gui_common


log = logging.getLogger(__name__)


class TemplateItem(QListWidgetItem):
    def __init__(self, list_widget: QListWidget, template_config: project.Config):
        """
        Displays information about a template in the template list. Sets the item widget when constructed.
        :param list_widget: List widget to which this item will be added.
        :param template_config: Template configuration for which to display information.
        """
        super().__init__(list_widget)

        # Using a QTextEdit is a heavy solution for showing a little rich text, but QLabel has problems with height
        # calculation in this case. There realistically shouldn't be that many templates to display, so it shouldn't
        # be an issue. See https://doc.qt.io/qtforpython-6/overviews/qtwidgets-layout.html#layout-issues
        # > The use of rich text in a label widget can introduce some problems to the layout of its parent widget.
        # > Problems occur due to the way rich text is handled by Qt's layout managers when the label is word
        # > wrapped.
        self.text_area = QTextEdit(list_widget, readOnly=True)
        self.text_area.viewport().setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        self.text_area.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.text_area.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.NoTextInteraction)
        self.text_area.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        self.text_area.setUndoRedoEnabled(False)

        self.text_area.setFrameStyle(0)
        self.text_area.setStyleSheet("background-color: #00000000")

        self.text_area.append(f'<span style="font-size: x-large; font-weight: bold">{template_config.name}</span>')
        self.text_area.append(template_config.description)

        self.text_area.document().documentLayout().documentSizeChanged.connect(self.on_text_change)

        list_widget.setItemWidget(self, self.text_area)

    def on_text_change(self):
        doc_height = int(self.text_area.document().size().height())
        self.text_area.setFixedHeight(doc_height)
        size_hint = self.sizeHint()
        size_hint.setHeight(doc_height + 4)
        self.setSizeHint(size_hint)


class SetupTemplatePage(QWizardPage):
    def __init__(self, setup_context: gui_common.SetupContext):
        super().__init__()
        self.setup_context = setup_context

        self.setTitle("New Project")
        self.setSubTitle("Select project template")
        self.setLayout(QVBoxLayout(self))

        self.instruction_text = QLabel("What should the new project be based on?", self)
        self.layout().addWidget(self.instruction_text)

        self.list_widget = QListWidget(self)
        self.layout().addWidget(self.list_widget)

        self.list_widget.itemSelectionChanged.connect(self.completeChanged)
        self.list_widget.itemActivated.connect(lambda: self.wizard().next())

    def initializePage(self):
        self.setup_context.template_config_path = None
        self.setup_context.template_config = None

        self.list_widget.clear()

        templates: list[tuple[project.Config, pathlib.Path]] = []
        for file_path in files.CONFIG_DIR.iterdir():
            if file_path.suffix.lower() != ".toml":
                continue

            try:
                config = project.Config(file_path)
            except Exception as e:
                log.error(f"Error parsing config file {file_path.name}.", exc_info=e)
                continue

            templates.append((config, file_path))

        templates.sort(key=lambda x: (x[0].name, x[1].name))

        for (template_config, template_path) in templates:
            item = TemplateItem(self.list_widget, template_config)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, template_path)
            item.setSizeHint(item.text_area.sizeHint())

    def isComplete(self):
        return self.list_widget.currentItem() is not None

    def validatePage(self):
        config_path = self.list_widget.currentItem().data(QtCore.Qt.ItemDataRole.UserRole)
        self.setup_context.template_config_path = config_path
        self.setup_context.template_config = project.Config(config_path)
        log.info(f'Selected project template "{self.setup_context.template_config.name}" at {config_path}')
        return True

    def nextId(self) -> gui_common.PageId:
        return gui_common.PageId.SETUP_DIRECTORY
