# Decomplicator
Decomplicator sets up development environments for Nintendo 64 decompilation projects on Windows. The process is almost
entirely automatic, and you only need to select a project template, project folder, and the project's base ROM to begin.

To begin, [download the most recent release](https://github.com/LucretiaArc/Decomplicator/releases).

# Why?
Under normal circumstances, software developers can set up their own development environment. However, Nintendo 64
decompilation projects offer benefits even to the casual romhacker who is not interested in writing code. Traditionally,
setting up a development environment has presented a challenge for these users, with inscrutable errors creating
barriers to entry. Decomplicator's seeks to remove these barriers, making decompilation projects accessible to the
casual romhacker.

# Caution: Project Templates
Decomplicator's project templates are used to download and run external software. A malicious project template could be
harmful to your computer, and put your personal data at risk. Only use a third-party project template if you fully trust
the author.

# Building
Use `uv` to set up the project environment, then run `build.py` in the project environment:
```
uv sync
uv run build.py
```

