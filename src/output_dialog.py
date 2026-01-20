import enum
import html
import itertools
import re
import typing

from PySide6 import QtCore, QtWidgets, QtGui


class AnsiTextFormatter:
    """
    Formats text with inline ANSI escape sequences, outputting a subset of HTML. Supports a limited number of sequences,
    unsupported sequences are discarded.
    """

    class Attr(enum.Enum):
        FOREGROUND_COLOR = "foreground_color"
        BACKGROUND_COLOR = "background_color"
        FONT_WEIGHT = "font_weight"
        ITALIC = "italic"
        UNDERLINE = "underline"
        STRIKETHROUGH = "strikethrough"

    COLORS = ["#000", "#F44", "#2E2", "#FF0", "#48F", "#F4D", "#0DF", "#CCC"]

    # See https://en.wikipedia.org/wiki/ANSI_escape_code#Select_Graphic_Rendition_parameters
    PARAM_MAP: list[None | tuple[AnsiTextFormatter.Attr, typing.Any]] = [None] * 108
    PARAM_MAP[1] = (Attr.FONT_WEIGHT, 800)
    PARAM_MAP[2] = (Attr.FONT_WEIGHT, 200)
    PARAM_MAP[3] = (Attr.ITALIC, True)
    PARAM_MAP[4] = (Attr.UNDERLINE, True)
    PARAM_MAP[9] = (Attr.STRIKETHROUGH, True)
    PARAM_MAP[22] = (Attr.FONT_WEIGHT, 400)
    PARAM_MAP[23] = (Attr.ITALIC, False)
    PARAM_MAP[24] = (Attr.UNDERLINE, False)
    PARAM_MAP[29] = (Attr.STRIKETHROUGH, False)
    PARAM_MAP[39] = (Attr.FOREGROUND_COLOR, 7)
    PARAM_MAP[49] = (Attr.BACKGROUND_COLOR, 0)

    for i in range(8):
        PARAM_MAP[30 + i] = (Attr.FOREGROUND_COLOR, i)
        PARAM_MAP[40 + i] = (Attr.BACKGROUND_COLOR, i)
        PARAM_MAP[90 + i] = (Attr.FOREGROUND_COLOR, i)
        PARAM_MAP[100 + i] = (Attr.BACKGROUND_COLOR, i)

    def __init__(self):
        self.reset()

    # noinspection PyAttributeOutsideInit
    def reset(self):
        """
        Resets all display attributes to their default values.
        """
        self.foreground_color = 7
        self.background_color = 0
        self.font_weight = 400
        self.italic = False
        self.underline = False
        self.strikethrough = False

    def format(self, text: str) -> str:
        """
        Formats text according to the current display attributes. These attributes can be updated using inline ANSI
        escape sequences.
        :param text: Text to format.
        :return: Inline HTML fragment, styled according to embedded ANSI escape sequences and initial state.
        """
        output_html = ""
        escaped_text = html.escape(text)
        text_sections = itertools.batched(["", ""] + re.split(r"\x1b\[([\d;:]*)([a-zA-z])", escaped_text), 3)
        for args, final, plain_text in text_sections:
            if final == "m":
                if args == "":
                    self.reset()
                else:
                    for arg in re.split(r"\D", args):
                        v = int(arg)
                        if v < len(self.PARAM_MAP):
                            action = self.PARAM_MAP[v]
                            if action:
                                attribute, value = action
                                setattr(self, attribute.value, value)
                            elif v == 0:
                                self.reset()
                            elif v == 38 or v == 48:
                                continue  # Discard the rest of the args, since they are extended colour params

            if plain_text:
                style = []
                # Simple readability override: either background or foreground colour must be black
                if self.background_color == 0:
                    style.append(f"color: {self.COLORS[7 if self.foreground_color == 0 else self.foreground_color]}")
                else:
                    style.append(f"color: {self.COLORS[0]}")
                    style.append(f"background-color: {self.COLORS[self.background_color]}")

                if self.font_weight != 400:
                    style.append(f"font-weight: {self.font_weight}")
                if self.italic:
                    style.append("font-style: italic")

                if self.underline and self.strikethrough:
                    style.append("text-decoration: underline line-through")
                elif self.underline:
                    style.append("text-decoration: underline")
                elif self.strikethrough:
                    style.append("text-decoration: line-through")

                output_html += f'<span style="{'; '.join(style)}">{plain_text}</span>'

        return output_html


class TerminalOutputWidget(QtWidgets.QPlainTextEdit):
    def __init__(self, parent: QtWidgets.QWidget | None, width: int = 120, height: int = 20):
        """
        A text area displaying terminal-styled output. Supports a basic subset of ANSI escape sequences.
        :param parent: Parent ``QWidget``, see ``QWidget``.
        :param width: Minimum width of the widget, in columns.
        :param height: Minimum height of the widget, in lines.
        """
        super().__init__(parent, readOnly=True, tabChangesFocus=True)
        self.scrolling_paused = False
        self.replace_line = False
        self.text_style = AnsiTextFormatter()

        self.setLayout(QtWidgets.QVBoxLayout(self))
        self.layout().setAlignment(QtCore.Qt.AlignmentFlag.AlignBottom | QtCore.Qt.AlignmentFlag.AlignHCenter)

        background_color = self.palette().color(QtGui.QPalette.ColorGroup.All, QtGui.QPalette.ColorRole.Base).name()
        self.scroll_reset_button = QtWidgets.QPushButton("Resume Scrolling", self)
        self.scroll_reset_button.setFixedWidth(150)
        self.scroll_reset_button.setStyleSheet(f"background-color: {background_color}")
        self.scroll_reset_button.hide()
        self.layout().addWidget(self.scroll_reset_button)

        font = QtGui.QFont("Cascadia Mono", 10, 400)
        font.setHintingPreference(QtGui.QFont.HintingPreference.PreferNoHinting)
        font.setLetterSpacing(QtGui.QFont.SpacingType.PercentageSpacing, 96)
        self.setFont(font)
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        self.setUndoRedoEnabled(False)

        pal = self.palette()
        pal.setColor(QtGui.QPalette.ColorGroup.All, QtGui.QPalette.ColorRole.Base, "#000")
        self.setPalette(pal)

        self.document().setDefaultStyleSheet("* {white-space: pre}")

        self.set_output_size(width, height)

        self.verticalScrollBar().valueChanged.connect(self.on_scroll_changed)
        self.scroll_reset_button.clicked.connect(self.resume_scrolling)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        scrollbar = self.verticalScrollBar()
        scroll_value = scrollbar.value()
        cur = self.textCursor()
        cur.clearSelection()
        self.setTextCursor(cur)
        scrollbar.setValue(scroll_value)

    def set_output_size(self, column_count: int = 120, line_count: int = 20):
        """
        Sets the minimum output size, in columns and lines.
        :param column_count: Minimum width, in columns.
        :param line_count: Minimum height, in lines.
        """
        scroll_bar_width = self.style().pixelMetric(QtWidgets.QStyle.PixelMetric.PM_ScrollBarExtent)

        fm = self.fontMetrics()
        text_area_width = fm.horizontalAdvance(" " * column_count) + 12 + scroll_bar_width
        text_area_height = fm.lineSpacing() * line_count + 12
        self.setMinimumSize(text_area_width, text_area_height)

    def on_scroll_changed(self, new_value):
        if not self.scrolling_paused and new_value != self.verticalScrollBar().maximum():
            self.scrolling_paused = True
            self.scroll_reset_button.show()
        elif self.scrolling_paused and new_value == self.verticalScrollBar().maximum():
            self.scrolling_paused = False
            self.scroll_reset_button.hide()

    def resume_scrolling(self):
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def add_line(self, line: str):
        """
        Adds a line to the display. If the line ends with a carriage return (\r), the line will be replaced by the next
        line to be added, unless that line is empty.
        :param line: Line to add.
        """
        if line == "\r":
            return

        line_text = line.rstrip("\r\n")
        line_html = ""
        if line_text:
            line_html = self.text_style.format(line_text)
            if self.replace_line:
                block = self.document().lastBlock()
                cur = QtGui.QTextCursor(block)
                cur.select(QtGui.QTextCursor.SelectionType.BlockUnderCursor)
                cur.removeSelectedText()

        if line_text or not self.replace_line:
            self.appendHtml(line_html)
            if not self.scrolling_paused:
                scrollbar = self.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())

        self.replace_line = line.endswith("\r")

    def add_command_line(self, command_text: str):
        """
        Adds a line to the output, styled as a command to be executed.
        :param command_text: Text of the command.
        """
        self.replace_line = False
        output_html = self.text_style.format(f"\x1b[0;33m$ \x1b[0m{command_text}")
        self.appendHtml(output_html)


class OutputProgressDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None, title: str):
        """
        A dialog intended to display stdout and stderr of a shell command, to monitor its progress.

        Lines should be added to the stdout and stderr displays by calling ``stdout.add_line()`` and
        ``stderr.add_line()``.

        :param parent: Parent ``QWidget``, see ``QWidget``.
        :param title: Window title.
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        self.setLayout(QtWidgets.QVBoxLayout())

        self.label_row = QtWidgets.QWidget(self)
        self.label_row.setLayout(QtWidgets.QHBoxLayout(self.label_row))
        self.label_row.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.label_row)

        self.activity_label = QtWidgets.QLabel("Working...", self.label_row)
        self.label_row.layout().addWidget(self.activity_label)

        self.button = QtWidgets.QPushButton("Cancel", self.label_row)
        self.button.clicked.connect(self.close)
        self.button.setFixedWidth(100)
        self.label_row.layout().addWidget(self.button)

        self.progress_bar = QtWidgets.QProgressBar(self, minimum=0, maximum=0)
        self.progress_bar.setTextVisible(False)
        self.layout().addWidget(self.progress_bar)

        self.stdout_label = QtWidgets.QLabel("Output:", self)
        self.layout().addWidget(self.stdout_label)

        self.stdout = TerminalOutputWidget(self, 120, 12)
        self.layout().addWidget(self.stdout)

        self.stderr_label = QtWidgets.QLabel("Errors:", self)
        self.layout().addWidget(self.stderr_label)

        self.stderr = TerminalOutputWidget(self, 120, 12)
        self.layout().addWidget(self.stderr)
