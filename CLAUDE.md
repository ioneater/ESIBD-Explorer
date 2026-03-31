# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ESIBD Explorer is a PyQt6 desktop application for data acquisition and analysis in Electrospray Ion-Beam Deposition experiments. It provides hardware control, real-time data monitoring, and experimental analysis through a plugin-based architecture.

- **Python** >= 3.11, **PyQt6** 6.6, **matplotlib**, **pyqtgraph**
- Docs: https://esibd-explorer.readthedocs.io/
- Source: https://github.com/ioneater/ESIBD-Explorer

## Common Commands

```bash
# Run the application
python -m esibd.explorer

# Simulate fresh install (clears registry settings)
python -m esibd.reset

# Lint and format
ruff check esibd/
ruff format esibd/

# Build documentation (Sphinx)
sphinx-build docs docs/_build

# Build package for PyPI
python -m build
twine check dist/*

# Environment setup (conda)
cd setup && ./create_env.bat   # Windows
cd setup && ./create_env.sh    # Linux/Mac
conda activate esibd
```

## Testing

There is no pytest/unittest suite. Testing is built into the plugin system:
- Each plugin has a `.test()` method run from the Console plugin
- `PluginManager.test()` runs all plugin tests (accessible from the in-app Console)
- Hardware integration testing is manual
- Test with all/no plugins enabled, and after `python -m esibd.reset`

## Version Bumping

Version must be updated manually in 4 files:
1. `pyproject.toml` — `version`
2. `esibd/config.py` — `PROGRAM_VERSION`
3. `docs/conf.py` — `release`
4. `EsibdExplorer.ifp` — Product Version (InstallForge GUI)

## Architecture

### Core Files

- **`esibd/core.py`** (~6000 LOC): Main framework — `EsibdExplorer` (QMainWindow), `PluginManager`, `Parameter`, `Channel`, `Setting`, custom widgets, `Logger`, threading primitives (`TimeoutLock`, `SignalCommunicate`)
- **`esibd/plugins.py`** (~8000 LOC): Plugin base classes — `Plugin`, `Device`, `Scan`, `StaticDisplay`, `LiveDisplay`, `ChannelManager`, and built-in plugins (`Console`, `Browser`, `Explorer`, `UCM`, `PID`, etc.)
- **`esibd/const.py`**: Enums (`PARAMETERTYPE`, `PLUGINTYPE`, `PRINT`, `INOUT`), utility functions (`smooth`, `synchronized`, `plotting`, `dynamicImport`)
- **`esibd/config.py`**: Program identity constants (`PROGRAM_NAME`, `PROGRAM_VERSION`, paths)
- **`esibd/provide_plugins.py`**: Defines core plugin load order
- **`esibd/extended.py`**: Customized `Settings` plugin (`ESIBDSettings`)

### Plugin System

Plugins are discovered from multiple directories in order: `provide_plugins.py` (core) -> `examples/` -> `devices/` -> `scans/` -> `displays/` -> user `pluginPath`. Each plugin directory contains subdirectories with a `.py` file exporting `providePlugins() -> list[type[Plugin]]`.

Plugin types (`PLUGINTYPE` enum): `CONSOLE`, `CONTROL`, `INPUTDEVICE`, `OUTPUTDEVICE`, `CHANNELMANAGER`, `DISPLAY`, `LIVEDISPLAY`, `SCAN`, `DEVICEMGR`, `INTERNAL`.

Plugin lifecycle: `__init__` -> `finalizeInit()` -> `provideDock()` -> runtime -> `test()`.

### Key Patterns

- **camelCase naming** is used throughout for PyQt compatibility (ruff N802/N803/N806 rules are disabled)
- **Star imports** are used (`F405` disabled) — be aware of namespace collisions
- **`@synchronized(timeout)`** decorator for thread-safe method execution
- **`@plotting`** decorator prevents concurrent matplotlib updates
- **`SignalCommunicate`**: Thread-safe Qt signal emission from worker threads
- **`makeSettingWrapper()` / `makeWrapper()`**: Property factories that decouple value storage from UI

### Threading Model

- Main thread: UI updates and Qt event loop
- Worker threads: Hardware communication and long-running scans
- Use `TimeoutLock` (reentrant with timeout) to avoid deadlocks
- Emit signals via `SignalCommunicate` to update UI from worker threads

### Data Storage

- **Settings**: `QSettings` (Windows Registry / macOS plist / Linux .conf)
- **Scan data**: HDF5 (`.h5`) files with hierarchical metadata
- **Plugin state**: INI files

## Code Style

Configured in `ruff.toml`:
- Line length: 180 characters
- Single quotes for inline strings (`ruff check`), double quotes for formatted output (`ruff format`)
- `select = ["ALL"]` with targeted ignores — see `ruff.toml` for rationale
- Annotations required only in core files (`config.py`, `const.py`, `core.py`, `plugins.py`)
- TODOs in device/example plugins don't need author/issue links (they are instructions for plugin developers)
