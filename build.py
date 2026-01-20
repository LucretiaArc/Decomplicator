import pathlib
import subprocess
import tomllib
from PyInstaller.utils.win32.versioninfo import *


project_path = pathlib.Path(__file__).parent


def get_version_number() -> str:
    proj_text = (project_path / "pyproject.toml").read_text()
    proj = tomllib.loads(proj_text)
    return proj["project"]["version"]


def get_commit_id() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except FileNotFoundError, subprocess.CalledProcessError:
        return None


def get_version_file_content(version_number: str, commit_id: str) -> str:
    if not version_number:
        version_number = "0.0.0"

    if commit_id:
        version_text = f"{version_number} (Build {commit_id})"
    else:
        version_text = version_number

    version_parts_str = version_number.split(".")
    version_parts = []
    for i in range(4):
        if i < len(version_parts_str):
            v = int(version_parts_str[i])
        else:
            v = 0

        version_parts.append(v & 0xffff)

    version_info = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=version_parts,
            prodvers=version_parts,
        ),
        kids=[
            StringFileInfo([StringTable("040904B0",[
                StringStruct("CompanyName", "Lucretia"),
                StringStruct("FileDescription", "Decomplicator"),
                StringStruct("FileVersion", version_text),
                StringStruct("InternalName", "Decomplicator"),
                StringStruct("OriginalFilename", "decomplicator.exe"),
                StringStruct("ProductName", "Decomplicator"),
                StringStruct("ProductVersion", version_text),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0409, 0x04B0])])
        ]
    )

    return str(version_info)


def build():
    build_command = [
        "pyinstaller",
        "--name",                   "decomplicator",
        "--contents-directory",     "application",
        "--add-data",               "config:config",
        "--add-data",               "assets/icon.png:assets",
        "--add-data",               "version.txt:.",
        "--icon",                   "assets/icon.png",
        "--version-file",           "version_win.txt",
        "--noconsole",
        "--noconfirm",
        "src/main.py"
    ]

    subprocess.run(build_command, cwd=project_path)


def main():
    version = get_version_number()
    commit = get_commit_id() or ""
    version_file = project_path / "version.txt"
    version_file.write_text(f"{version}\n{commit}")

    win_version_file = project_path / "version_win.txt"
    win_version_file.write_text(get_version_file_content(version, commit))

    build()


if __name__ == '__main__':
    main()