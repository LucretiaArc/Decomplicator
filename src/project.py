import os
import pathlib
import subprocess
import tomllib

from PySide6 import QtCore

import files
import task_base
import task_impl


class Dependency:
    def __init__(self, dir_name: str, info: dict):
        """
        A single dependency of the project.
        :param dir_name: Name of the directory in the project environment in which the dependency should be set up.
        :param info: Dict representing the content of the dependency table in the config file. See the project
            config template for more information.
        """
        self.name: str = info["name"]
        self.dir_name: str = dir_name
        self.url: str = info["url"]
        self.hash: str = info["sha256"]
        self.paths: list[str] = info["include_paths"]
        self.setup_commands: list[list[str]] = info["setup"] if "setup" in info else []


class Action:
    def __init__(self, info: dict):
        """
        A single action of the project. Each action comprises a list of commands to be executed in the shell, where
        any non-zero status code from any process terminating the sequence.
        :param info: Dict representing the content of the action table in the config file. See the project config
            template for more information.
        """
        self.name = info["name"]
        self.description = info["description"]
        self.commands: list[list[str]] = info["commands"]


class Config:
    CURRENT_VERSION = 1
    MIN_VERSION = 1

    def __init__(self, config_path: pathlib.Path):
        """
        The configuration for a project, describing a build environment and actions that can be performed in it. This
        configuration may take the role of a project template or a project file. See the project config template for
        more information.
        :param config_path: Path to a config file. The file will be read to populate information about the config.
        """
        config_data_text = config_path.read_text()
        config_data = tomllib.loads(config_data_text)

        format_version = config_data["format_version"]
        if not isinstance(format_version, int) or format_version < Config.MIN_VERSION:
            raise ValueError(f"Invalid project format version {format_version}")
        if format_version > Config.CURRENT_VERSION:
            raise ValueError(
                f"Project format version {format_version} isn't supported by this version of Decomplicator."
            )

        config_info = config_data["info"]
        self.name: str = config_info["name"]
        self.description: str = config_info["description"]

        config_repo: dict = config_data["repo"]
        self.repo_url: str = config_repo["url"]
        self.repo_commit: str = config_repo["commit"]
        self.repo_env_path: str = config_repo["env_path"]

        config_rom: dict = config_data["baserom"]
        self.baserom_name: str = config_rom["name"]
        self.baserom_hash: str = config_rom["sha256"]
        self.baserom_path: str = config_rom["path"]

        config_deps: dict[str, dict] = config_data["dependency"]
        self.dependencies: list[Dependency] = []
        for dep_dir, dep_info in config_deps.items():
            dep = Dependency(dep_dir, dep_info)
            self.dependencies.append(dep)

        self.action_data: list[Action] = [Action(d) for d in config_data["action"]]


class Project:
    def __init__(self, project_path: pathlib.Path, project_config: Config):
        """
        A build environment and associated actions. May be set up already, or may need to be set up.
        :param project_path: Path to the project directory.
        :param project_config: Configuration used by the project.
        """
        self.path = project_path
        self.config = project_config

    def get_env_path(self) -> pathlib.Path:
        """
        Gets the path to the directory in which the project's dependencies are set up.
        :return: Path to the project environment directory.
        """
        return self.path / self.config.repo_env_path

    def get_env(self) -> dict[str, str]:
        """
        Gets the project environment variable configuration.
        :return: Dict mapping environment variable names to values. See ``os.environ``.
        """
        env = os.environ.copy()
        env_paths: list[str] = []
        for dep in self.config.dependencies:
            for p in dep.paths:
                added_path = self.get_env_path() / dep.dir_name / p
                env_paths.append(str(added_path.resolve()))

        env_paths += env["PATH"].split(";")
        env["COMSPEC"] = r"C:\Windows\System32\cmd.exe"
        env["PATH"] = ";".join(env_paths)
        env["PROMPT"] = "$E[32m$P$_$E[38;5;226m$$$E[m$S"
        return env

    def existing_project_requires_setup(self) -> bool:
        """
        Determines whether further setup needs to take place before the build environment is ready. Note that the state
        of the repository is not taken into account as part of this determination. If further setup is necessary,
        ``get_setup_task()`` can be called to create a task that completes the setup.
        :return: ``True`` if further setup is needed, ``False`` otherwise.
        """
        env_path = self.get_env_path()
        if not env_path.exists():
            return True

        for dep in self.config.dependencies:
            setup_path = env_path / dep.dir_name
            if not setup_path.exists():
                return True

        baserom_path = self.path / self.config.baserom_path
        if not baserom_path.exists():
            return True

        return False

    def get_setup_task(self, parent: QtCore.QObject, from_existing_repo=False) -> task_base.TaskSequence:
        """
        Gets a task that completes all remaining setup steps for the project when executed, skipping any steps that were
        already completed. There are limits to the way this is determined. For example, if a dependency directory
        exists, it is assumed that the dependency was set up correctly.
        :param parent: Parent ``QObject`` for the task, see ``QThread``.
        :param from_existing_repo: ``True`` if the git repository has been set up already, ``False`` otherwise.
        :return: Task to complete the setup.
        """
        env_path = self.get_env_path()
        root_task = task_base.TaskSequence(parent, "Create project")
        dependencies_task = task_impl.SetupDependenciesTaskSequence(root_task, "Set up dependencies", env_path)
        for dep in self.config.dependencies:
            dep_task = task_base.TaskSequence(dependencies_task, dep.name)
            dependencies_task.add_task(dep_task)
            setup_path = env_path / dep.dir_name

            if not setup_path.exists():
                cache_path = files.DEP_CACHE_DIR / dep.hash

                dep_task.add_task(
                    task_impl.DownloadAndValidateTask(dep_task, "Download archive", cache_path, dep.url, dep.hash)
                )

                dep_task.add_task(
                    task_impl.FileExtractionTask(dep_task, "Extract archive", cache_path, setup_path)
                )

                dep_task.add_task(
                    task_impl.FileOperationSequenceTask(dep_task, "Finish setup", setup_path, dep.setup_commands)
                )

        root_task.add_task(dependencies_task)

        if not from_existing_repo:
            root_task.add_task(task_impl.SetupGitRepoTask(
                root_task,
                "Set up repository",
                self.config.repo_url,
                self.config.repo_commit,
                self.path,
                self.get_env()
            ))

        baserom_path = self.path / self.config.baserom_path
        if not baserom_path.exists():
            root_task.add_task(task_impl.FileCopyTask(
                root_task,
                "Copy game ROM",
                files.ROM_CACHE_DIR / self.config.baserom_hash,
                baserom_path,
                "An error occurred when copying the game ROM to the project folder."
            ))

        return root_task

    def open_terminal(self):
        """
        Opens a terminal window which uses the project environment.
        """
        terminal_path = str(pathlib.Path.home() / "AppData/Local/Microsoft/WindowsApps/wt.exe")
        command = [
            terminal_path, "new-tab",
            "--inheritEnvironment",
            "--startingDirectory", str(self.path),
            "--title", f"Project: {self.path.name}",
            '"%COMSPEC%"'
        ]
        subprocess.run(command, env=self.get_env(), shell=True)
