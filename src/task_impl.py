import copy
import hashlib
import io
import os
import pathlib
import re
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import tarfile
import tempfile
import typing
import urllib.error
import urllib.request
import zipfile

import files
from task_base import *


log = logging.getLogger(__name__)


def task_run_command(task: Task,
                     command: list[str],
                     cwd: pathlib.Path,
                     env: dict[str, str]) -> int:
    """
    Runs a command as part of a task, terminating the command if the task is cancelled. Output of the command will be
    logged to the log file.
    :param task: Task to monitor for the "cancelled" flag.
    :param command: Command to execute.
    :param cwd: Working directory of the command.
    :param env: Environment mapping for the command.
    :return: The exit status of the command.
    """
    command_text = shlex.join(command)
    log.info(f"Running command {command_text}")
    p = subprocess.Popen(command, cwd=cwd, env=env, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    while p.poll() is None:
        if task.is_cancelled():
            p.send_signal(signal.CTRL_BREAK_EVENT)
            break

    exit_status = p.wait()
    log.info(f"Output for command {command_text}:\n" + p.stdout.read().decode())

    return exit_status


class SetupDependenciesTaskSequence(TaskSequence):
    def __init__(self,
                 parent: QtCore.QObject | None,
                 name: str,
                 env_path: pathlib.Path):
        """
        A ``TaskSequence`` used for project dependencies. Creates the environment directory and .gitignore file inside.
        :param parent: Parent ``QObject``, see ``QThread``.
        :param name: Name of the task, as shown to the user.
        :param env_path: Path to the new project environment directory.
        """
        super().__init__(parent, name)
        self.env_path = env_path

    def run_impl(self):
        try:
            self.env_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise TaskFailureException(f"Could not create project environment folder.\n\n{e.strerror}")

        try:
            (self.env_path / ".gitignore").write_text("*")
        except OSError as e:
            raise TaskFailureException(f"Could not write to project environment folder.\n\n{e.strerror}")

        super().run_impl()


class DownloadAndValidateTask(Task):
    def __init__(self,
                 parent: QtCore.QObject | None,
                 name: str,
                 destination: pathlib.Path,
                 url: str,
                 expected_hash: str):
        """
        Downloads a project dependency archive, and validates that the file is not corrupt.
        :param parent: Parent ``QObject``, see ``QThread``.
        :param name: Name of the task, as shown to the user.
        :param destination: Path to the destination of the downloaded archive.
        :param url: URL of the archive to download.
        :param expected_hash: Expected SHA-256 hash of the downloaded archive. If the archive's hash doesn't match this
            value, the downloaded file will be deleted.
        """
        super().__init__(parent, name)
        self.download_url = url
        self.download_destination = destination
        self.expected_hash = expected_hash

    def _report_callback(self, block_count: int, block_size: int, file_size: int):
        if self.is_cancelled():
            raise TaskCancelledException()

        if file_size <= 0:
            self.report_progress(None)
        else:
            self.report_progress((block_count * block_size) / file_size)

    def run_impl(self):
        self.download_destination.parent.mkdir(parents=True, exist_ok=True)
        if not self.download_destination.exists():
            log.info(f"Downloading {self.download_url} -> {self.download_destination}")
            try:
                urllib.request.urlretrieve(
                    self.download_url,
                    self.download_destination,
                    reporthook=self._report_callback
                )
            except TaskCancelledException as e:
                self.download_destination.unlink(missing_ok=True)
                raise e
            except urllib.error.ContentTooShortError, ConnectionError:
                self.download_destination.unlink(missing_ok=True)
                raise TaskFailureException("Download failed. Your network connection may have been interrupted.")
            except urllib.error.HTTPError as e:
                self.download_destination.unlink(missing_ok=True)
                raise TaskFailureException(f"Download failed.\n\n{e}")
            except urllib.error.URLError as e:
                self.download_destination.unlink(missing_ok=True)
                if isinstance(e.reason, socket.gaierror) and e.reason.errno in socket.errorTab:
                    raise TaskFailureException(f"Download failed.\n\n{socket.errorTab[e.reason.errno]}")
                else:
                    raise TaskFailureException(f"Download failed.\n\n{e.reason}")
            except Exception as e:
                self.download_destination.unlink(missing_ok=True)
                raise e
            file_source = "downloaded"
        else:
            log.info(f"Found cached download for {self.download_url}")
            file_source = "cached"

        self.report_progress(None)

        log.info(f"Opening {self.download_destination} for integrity check")
        try:
            with open(self.download_destination, "rb", buffering=0) as f:
                file_hash = hashlib.file_digest(f, "sha256").hexdigest()
        except OSError as e:
            raise TaskFailureException(f"Error reading the {file_source} file.\n\n{e.strerror}")

        if file_hash != self.expected_hash:
            log.warning(f"File failed integrity check hash = {file_hash}, expected {self.expected_hash}")
            self.download_destination.unlink()
            raise TaskFailureException(f"The {file_source} file did not pass an integrity check, and was deleted.")

        log.info("File passed integrity check")


class FileExtractionTask(Task):
    def __init__(self,
                 parent: QtCore.QObject | None,
                 name: str,
                 archive_path: pathlib.Path,
                 output_path: pathlib.Path):
        """
        Extracts an archive into the specified directory. The contents of the directory will be removed before
        extraction begins.
        :param parent: Parent ``QObject``, see ``QThread``.
        :param name: Name of the task, as shown to the user.
        :param archive_path: Path to the archive file.
        :param output_path: Path to the directory into which the archive should be extracted.
        """
        super().__init__(parent, name)
        self.archive_path = archive_path
        self.output_path = output_path

    def run_impl(self):
        if self.output_path.exists():
            shutil.rmtree(self.output_path)

        log.info(f"Extracting {self.archive_path} -> {self.output_path}")
        self.output_path.mkdir(parents=True)
        if zipfile.is_zipfile(self.archive_path):
            log.info("Extracting as ZIP archive")
            self._extract_zip()
        elif tarfile.is_tarfile(self.archive_path):
            log.info("Extracting as tar archive")
            self._extract_tar()
        else:
            raise TaskFailureException("Archive format was not recognised.")

    def _extract_zip(self):
        try:
            with zipfile.ZipFile(self.archive_path) as archive:
                members = archive.infolist()
                member_count = len(members)
                for i, member in enumerate(archive.infolist()):
                    if self.is_cancelled():
                        raise TaskCancelledException()
                    self.report_progress(i / member_count)
                    archive.extract(member, self.output_path)
        except zipfile.BadZipFile:
            raise TaskFailureException("Could not extract archive, file is corrupt.")
        except OSError as e:
            raise TaskFailureException(f"Could not extract archive.\n\n{e.strerror}")

    def _extract_tar(self):
        def with_progress(member_list: list[tarfile.TarInfo]):
            member_count = len(member_list)
            for i, m in enumerate(member_list):
                if self.is_cancelled():
                    raise TaskCancelledException()
                self.report_progress(i / member_count)
                yield m

        try:
            archive: tarfile.TarFile
            with tarfile.open(self.archive_path) as archive:
                archive.extractall(self.output_path, filter="tar", members=with_progress(archive.getmembers()))
        except tarfile.FilterError:
            raise TaskFailureException("Could not extract archive due to extraction security settings.")
        except tarfile.TarError as e:
            raise TaskFailureException(f"Could not extract archive.\n\n{e}")
        except OSError as e:
            raise TaskFailureException(f"Could not extract archive.\n\n{e.strerror}")


class FileOperationSequenceTask(Task):
    def __init__(self,
                 parent: QtCore.QObject | None,
                 name: str,
                 base_path: pathlib.Path,
                 file_operations: list[list[str]]):
        """
        Allows for a sequence of basic file operations to be performed.
        :param parent: Parent ``QObject``, see ``QThread``.
        :param name: Name of the task, as shown to the user.
        :param base_path: Path to the directory into which the dependency archive was extracted
        :param file_operations: List of file operations to complete. Each operation is a list of strings, where the
            first string is the type of operation, and subsequent strings are relative file or directory path arguments
            to the operation. See the project configuration template file (or read the source) for documentation about
            the supported operations.
        """
        super().__init__(parent, name, hidden=True)
        self.base_path = base_path
        self.file_operations = copy.deepcopy(file_operations)

    def run_impl(self):
        # The obvious alternative to this, a list of shell commands, has been deliberately avoided here. This is because
        # Windows' "del" command always returns status code 0 if the command syntax was correct, even if file deletion
        # fails. This task doesn't necessarily have the benefit of running with extra dependencies like a project action
        # does, since it's used in dependency setup, so an alternate implementation wouldn't be available.
        for i, command in enumerate(self.file_operations):
            if self.is_cancelled():
                raise TaskCancelledException()

            operation_name = command[0].lower()
            args = [self.base_path / f for f in command[1:]]
            is_file_target = args[0].is_file()

            arg_count = 1 if operation_name == "delete" else 2

            if len(args) != arg_count:
                raise TaskFailureException(f'Wrong number of parameters to "{operation_name}" operation')

            operation_desc = " -> ".join(str(s) for s in args)
            try:
                log.info(f"Performing file operation: {operation_name} {operation_desc}")
                if operation_name == "copy":
                    if is_file_target:
                        args[1].parent.mkdir(parents=True, exist_ok=True)
                        args[0].copy(args[1])
                    else:
                        shutil.copytree(args[0], args[1], dirs_exist_ok=True)
                elif operation_name == "move":
                    if is_file_target:
                        args[1].parent.mkdir(parents=True, exist_ok=True)
                        args[0].move(args[1])
                    else:
                        args[1].mkdir(parents=True, exist_ok=True)
                        for obj in args[0].iterdir():
                            shutil.move(obj, args[1] / obj.name)
                        args[0].rmdir()
                elif operation_name == "delete":
                    if is_file_target:
                        args[0].unlink()
                    else:
                        shutil.rmtree(args[0], onexc=self._remove_read_only)
            except OSError as e:
                target_type = "file" if is_file_target else "directory"
                raise TaskFailureException(f"Could not {operation_name} {target_type}.\n\n"
                                           f"{operation_desc}\n\n"
                                           f"{e.strerror}")

            self.report_progress(i / len(self.file_operations))

    @staticmethod
    def _remove_read_only(func, p, _):
        # See https://docs.python.org/3/library/shutil.html#rmtree-example
        os.chmod(p, stat.S_IWRITE)
        func(p)


class MarkDependencyCompleteTask(Task):
    def __init__(self,
                 parent: QtCore.QObject | None,
                 name: str,
                 env_path: pathlib.Path,
                 dependency_name: str):
        """
        Marks a dependency as successfully set up, preventing it from being set up again the next time the project is
        opened.
        :param parent: Parent ``QObject``, see ``QThread``.
        :param name: Name of the task, as shown to the user.
        :param env_path: Path to the project environment directory
        :param dependency_name: Name of the dependency to mark as complete
        """
        super().__init__(parent, name, hidden=True)
        self.env_path = env_path
        self.dependency_name = dependency_name

    def run_impl(self):
        files.mark_project_dependency_done(self.env_path, self.dependency_name)


class SetupGitRepoTask(Task):
    def __init__(self,
                 parent: QtCore.QObject | None,
                 name: str,
                 url: str,
                 commit_id: str,
                 repo_path: pathlib.Path,
                 env: dict[str, str]):
        """
        Sets up the git repository for a project. This is a three-step process:
         * Clone the git repository into a temporary directory.
         * Move the contents of the temporary directory into the project directory.
         * Create and check out a new branch in the repository, starting at the specified commit.
        :param parent: Parent ``QObject``, see ``QThread``.
        :param name: Name of the task, as shown to the user.
        :param url: URL of the git repository to clone.
        :param commit_id: ID of the commit to base the project branch on.
        :param repo_path: Target path for the repo to be copied into.
        :param env: Project environment, from which git should be executable
        """
        super().__init__(parent, name)
        self.url = url
        self.commit_id = commit_id
        self.repo_path = repo_path
        self.env = env

    def run_impl(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            log.info(f"Cloning git repository {self.url} -> {temp_dir}")
            command = ["git", "clone", "--progress", self.url, temp_dir]
            p = subprocess.Popen(
                command,
                env=self.env,
                shell=True,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )

            progress_types = ("remote", "Receiving objects", "Resolving deltas", "Updating files")
            output_lines = []
            replace_line = False

            buf = io.TextIOWrapper(p.stderr, newline="")
            while line := buf.readline():
                line_text = line.rstrip("\r\n")
                if replace_line:
                    output_lines[-1] = line_text
                else:
                    output_lines.append(line_text)

                replace_line = line.endswith("\r")

                if self.is_cancelled():
                    p.send_signal(signal.CTRL_BREAK_EVENT)
                    break

                current_progress = 0.0
                for start_text in progress_types:
                    if line_text.startswith(start_text):
                        if search_result := re.search(r"(\d+)%", line_text):
                            current_progress += 0.25 * int(search_result.group(1))

                        self.report_progress(current_progress / 100)
                        break

                    current_progress += 25.0

            exit_status = p.wait()
            log.info("Git clone output:\n" + "\n".join(line.strip() for line in output_lines if line))

            if self.is_cancelled():
                raise TaskCancelledException()
            elif exit_status != 0:
                raise TaskFailureException("An error occurred when cloning git repository. "
                                           "See the log file for more information.")

            self.report_progress(None)

            log.info(f"Copying repository {temp_dir} -> {self.repo_path}")
            try:
                shutil.copytree(
                    temp_dir,
                    self.repo_path,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(files.PROJECT_FILE_NAME)
                )
            except shutil.Error as e:
                errors_out = []
                for details in e.args[0]:
                    src, dst, reason = details
                    errors_out.append(f"{src} -> {dst}: {reason}")
                error_desc = "Error(s) occurred when copying git repository from temporary directory.\n"
                error_list = "\n".join(errors_out)
                log.error(error_desc + error_list)
                raise TaskFailureException("Error(s) occurred when moving git repository from temporary folder. "
                                           "See the log file for more information.")

        if self.is_cancelled():
            raise TaskCancelledException()

        exit_status = task_run_command(
            self,
            ["git", "checkout", "-b", "decomplicator-project", self.commit_id],
            self.repo_path,
            self.env
        )

        if self.is_cancelled():
            raise TaskCancelledException()
        elif exit_status != 0:
            raise TaskFailureException(
                "An error occurred when checking out commit from git repository. "
                "See the log file for more information."
            )


class CreateProjectFileTask(Task):
    def __init__(self,
                 parent: QtCore.QObject | None,
                 name: str,
                 template_file_path: pathlib.Path,
                 project_path: pathlib.Path,
                 project_env: dict[str, str]):
        """
        Creates the project file for a project, and stages it for the next commit.
        :param parent: Parent ``QObject``, see ``QThread``.
        :param name: Name of the task, as shown to the user.
        :param template_file_path: Path to the project template to use.
        :param project_path: Path to the project root directory, i.e. the root directory of the repository.
        :param project_env: Mapping defining the environment variables for the project environment.
        """
        super().__init__(parent, name)
        self.template_file_path = template_file_path
        self.project_path = project_path
        self.env = project_env

    def run_impl(self):
        project_file_path = self.project_path / files.PROJECT_FILE_NAME
        log.info(f"Copy project file {self.template_file_path} -> {project_file_path}")
        try:
            self.template_file_path.copy(project_file_path)
        except OSError as e:
            raise TaskFailureException(f"Couldn't create project file.\n\n{e.strerror}")

        exit_status = task_run_command(
            self,
            ["git", "add", str(project_file_path)],
            self.project_path,
            self.env
        )

        if self.is_cancelled():
            raise TaskCancelledException()
        elif exit_status != 0:
            raise TaskFailureException(
                "An error occurred when adding the project file to the git repository. "
                "See the log file for more information."
            )


class FileCopyTask(Task):
    def __init__(self,
                 parent: QtCore.QObject | None,
                 name: str,
                 source: pathlib.Path,
                 destination: pathlib.Path,
                 error_message: str):
        """
        Copies a file from the source path to the destination path.
        :param parent: Parent ``QObject``, see ``QThread``.
        :param name: Name of the task, as shown to the user.
        :param source: Source file path.
        :param destination: Destination file path.
        :param error_message: Basic error message to be shown if the file copy fails. Details about the specific error
            will be shown on a separate line.
        """
        super().__init__(parent, name)
        self.source = source
        self.destination = destination
        self.error_message = error_message

    def run_impl(self):
        log.info(f"Copy {self.source} -> {self.destination}")
        try:
            self.source.copy(self.destination)
        except OSError as e:
            raise TaskFailureException(f"{self.error_message}\n\n{e.strerror}")


class ExecuteCommandTask(Task):
    signal_new_command = QtCore.Signal(str)
    signal_stdout = QtCore.Signal(str)
    signal_stderr = QtCore.Signal(str)

    def __init__(self,
                 parent: QtCore.QObject | None,
                 name: str,
                 command: list[str],
                 working_directory: pathlib.Path | None,
                 project_env: dict[str, str] | None):
        """
        Executes a command in the project environment. The command will be executed with the specified working
        directory. If the command returns a non-zero status code, the task will fail.

        The signals ``signal_stdout`` and ``signal_stderr`` are emitted when a line is written to stdout and stderr
        respectively, with the line content as an argument. As a convenience for operation with ``ExecuteActionTask``,
        ``signal_new_command`` is emitted when the task starts, with the command as an argument.

        :param parent: Parent ``QObject``, see ``QThread``.
        :param name: Name of the task, as shown to the user.
        :param command: Command to execute.
        :param working_directory: Path to the working directory.
        :param project_env: Mapping defining the environment variables for the project environment.
        """
        super().__init__(parent, name)
        self.command = command
        self.cwd = working_directory
        self.env = project_env

    def run_impl(self):
        self.signal_new_command.emit(shlex.join(self.command))

        p = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            env=self.env,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )

        # Use threads here, since selectors don't work for pipes on Windows
        threading.Thread(target=self.pipe_to_signal, args=(p.stdout, self.signal_stdout)).start()
        threading.Thread(target=self.pipe_to_signal, args=(p.stderr, self.signal_stderr)).start()

        while p.poll() is None:
            if self.is_cancelled():
                self.signal_stderr.disconnect()  # Avoids interrupt characters being sent through the signal
                p.send_signal(signal.CTRL_BREAK_EVENT)
                break

        exit_status = p.wait()
        if self.is_cancelled():
            raise TaskCancelledException()
        elif exit_status != 0:
            raise TaskFailureException()

    @staticmethod
    def pipe_to_signal(pipe: typing.IO, sig: QtCore.SignalInstance):
        buf = io.TextIOWrapper(pipe, newline="")
        while line := buf.readline():
            sig.emit(line)


class ExecuteActionTask(TaskSequence):
    signal_new_command = QtCore.Signal(str)
    signal_stdout = QtCore.Signal(str)
    signal_stderr = QtCore.Signal(str)

    def __init__(self,
                 parent: QtCore.QObject | None,
                 name: str,
                 action_commands: list[list[str]],
                 working_directory: pathlib.Path | None,
                 project_env: dict[str, str] | None):
        """
        Executes an action in the project environment. The commands that make up the action will be executed as a
        sequence of ExecuteCommandTask, with the specified working directory.

        The signals ``signal_stdout`` and ``signal_stderr`` are emitted when a line is written to stdout and stderr
        respectively, with the line content as an argument. Each time a new command starts, ``signal_new_command`` is
        emitted with the command as an argument.

        :param parent: Parent ``QObject``, see ``QThread``.
        :param name: Name of the task, as shown to the user.
        :param action_commands: List of commands that make up the action.
        :param working_directory: Path to the working directory.
        :param project_env: Mapping defining the environment variables for the project environment.
        """
        super().__init__(parent, name)
        self.commands = action_commands

        for command in self.commands:
            command_string = shlex.join(command)
            task = ExecuteCommandTask(
                self,
                f"Command {command_string}",
                command,
                working_directory,
                project_env
            )
            task.hidden = True
            task.signal_new_command.connect(self.signal_new_command)
            task.signal_stdout.connect(self.signal_stdout)
            task.signal_stderr.connect(self.signal_stderr)
            self.add_task(task)
