import hashlib
import pathlib
import logging

from PySide6 import QtCore
from PySide6.QtWidgets import *

import files
import gui_common


log = logging.getLogger(__name__)


class SetupBaseromPage(QWizardPage):
    def __init__(self, setup_context: gui_common.SetupContext):
        super().__init__()
        self.setup_context = setup_context

        self.setSubTitle("Select project base ROM")
        self.setCommitPage(True)
        self.setButtonText(QWizard.WizardButton.CommitButton, "Create Project")
        self.setLayout(QVBoxLayout())
        self.layout().setSpacing(16)

        self.instruction_text = QLabel("", self)
        self.instruction_text.setWordWrap(True)
        self.layout().addWidget(self.instruction_text)

        self.browse_container = QWidget(self)
        self.browse_container.setLayout(QHBoxLayout())
        self.browse_container.layout().setContentsMargins(8, 0, 0, 0)
        self.browse_container.layout().setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.layout().addWidget(self.browse_container)

        self.browse_button = QPushButton("Select ROM...", self.browse_container)
        self.browse_button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.browse_container.layout().addWidget(self.browse_button)

        self.browse_button.clicked.connect(self.select_file)

    def initializePage(self):
        if self.setup_context.setup_from_repo:
            self.setTitle(f"Project: {self.setup_context.project_path.name}")
        else:
            self.setTitle("New Project")

        self.set_rom_available(False)
        self.completeChanged.emit()

    def isComplete(self):
        baserom_hash = self.setup_context.template_config.baserom_hash
        baserom_cache_path = (files.ROM_CACHE_DIR / baserom_hash)
        return baserom_cache_path.exists()

    def nextId(self) -> gui_common.PageId:
        if self.setup_context.setup_from_repo:
            return gui_common.PageId.SETUP_PROGRESS_FROM_REPO
        else:
            return gui_common.PageId.SETUP_PROGRESS_FROM_TEMPLATE

    def set_rom_available(self, available: bool):
        baserom_name = self.setup_context.template_config.baserom_name
        label_text = (f"This project requires you to supply the ROM for {baserom_name}.\n"
                      f"\n"
                      f"A copy of this ROM will be provided automatically to future projects that need it.")

        if available:
            label_text += "\n\nThe correct ROM was selected. Click Create Project to continue."

        self.browse_container.setHidden(available)
        self.instruction_text.setText(label_text)

    def check_rom(self, rom_path: pathlib.Path) -> bool:
        """
        Check whether the ROM at the given path matches the expected SHA-256 hash, and cache it if it does.

        This method transforms the ROM three times such that, for each group of four bytes ABCD, the bytes will be
        ordered as BADC, DCBA, and CDAB. Any ROM in z64, n64, or v64 format will be available in all three formats,
        either as the input ROM, or as one of the transformed ROMs.

        If any transformed version of the ROM is a match, all transformed versions will be cached.
        :param rom_path: Path to the candidate ROM.
        :return: True if the ROM matched the expected hash and was cached, False otherwise.
        """

        byte_order_transforms = (
            (1, 0, 3, 2),
            (3, 2, 1, 0),
            (2, 3, 0, 1),
        )

        rom_data = bytearray(rom_path.read_bytes())
        transform_data = [rom_data]

        for byte_order in byte_order_transforms:
            rom_data_transformed = bytearray(len(rom_data))
            rom_data_transformed[0::4] = rom_data[byte_order[0]::4]
            rom_data_transformed[1::4] = rom_data[byte_order[1]::4]
            rom_data_transformed[2::4] = rom_data[byte_order[2]::4]
            rom_data_transformed[3::4] = rom_data[byte_order[3]::4]
            transform_data.append(rom_data_transformed)

        transform_hash = [hashlib.sha256(d).hexdigest() for d in transform_data]

        if self.setup_context.template_config.baserom_hash in transform_hash:
            for t_data, t_hash in zip(transform_data, transform_hash):
                f = files.ROM_CACHE_DIR / t_hash
                f.write_bytes(t_data)
            return True
        else:
            return False

    def select_file(self):
        baserom_hash = self.setup_context.template_config.baserom_hash
        baserom_cache_path = files.ROM_CACHE_DIR / baserom_hash
        baserom_cache_path.parent.mkdir(parents=True, exist_ok=True)
        while not baserom_cache_path.exists():
            file_name, _ = QFileDialog.getOpenFileName(
                self,
                "Select ROM...",
                dir=str(files.get_default_directory()),
                filter="N64 ROM (*.z64 *.n64 *.v64)"
            )

            if not file_name:
                break

            file_path = pathlib.Path(file_name)
            log.info(f"User selected ROM {file_path}")

            try:
                rom_matches = self.check_rom(file_path)
            except OSError as e:
                gui_common.error(self, f"Error reading the selected file.\n\n{e.strerror}")
                continue

            if rom_matches:
                log.info("ROM hash matched expected hash")
                self.set_rom_available(True)
                self.completeChanged.emit()
            else:
                gui_common.warning(
                    self,
                    "The selected file doesn't match the required ROM. Please select the correct ROM."
                )
