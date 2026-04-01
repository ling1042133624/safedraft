# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SafeDraft** is a Windows desktop application (input safety/backup tool) that automatically saves text input to prevent data loss from application crashes. It monitors active windows and auto-pops up when users are working in specified applications (like Word, ChatGPT, etc.).

## Common Commands

### Run in Development
```bash
python main.py
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Build Executable (Windows)
```bash
# Development build (faster, creates folder)
python -m nuitka --standalone --windows-disable-console --enable-plugin=tk-inter --jobs=8 main.py

# Release build (single file)
python -m nuitka --standalone --onefile --jobs=8 --windows-disable-console --enable-plugin=tk-inter --enable-plugin=anti-bloat --lto=yes --no-pyi-file --output-filename=SafeDraft.exe main.py

# Or use the build script
build.bat
```

### Build Executable (macOS)
```bash
python -m nuitka --standalone --onefile --enable-plugin=tk-inter --macos-create-app-bundle --macos-app-icon=icon.icns --output-filename=SafeDraft main.py
```

## Architecture

### Core Modules

| File | Purpose |
|------|---------|
| `main.py` | Entry point. Contains `SafeDraftApp` (main GUI), `GlobalHotKeys` (keyboard shortcuts), and tray icon setup |
| `storage.py` | `StorageManager` class - SQLite database operations for drafts, triggers, settings, and notebook data. Includes SSH smart merge sync via paramiko |
| `watcher.py` | `WindowWatcher` class - Background thread monitoring active window title and process name against trigger rules |
| `windows.py` | `HistoryWindow` (time machine/history browser with PanedWindow preview) and `SettingsDialog` (settings tabs) |
| `notebook.py` | `NotebookWindow` - Three-pane notebook system with folders, notes list, and editor |
| `utils.py` | `ThemeManager` (Deep/Light themes), `StartupManager` (Windows registry auto-start), icon loading |
| `icon_data.py` | Base64 encoded application icon |
| `save_his.py` | Utility to convert SafeDraft database to NoteGen format |

### Key Data Flow

1. **Auto-save**: Text changes in main window trigger `on_text_change()` -> debounced 1s -> `perform_auto_save()` -> `StorageManager.save_content()`
2. **Window Monitoring**: `WindowWatcher._loop()` runs every 1s, checks active window against `triggers_v2` table rules, calls callback on match
3. **Draft Segmentation**: Time-based (10 min gap creates new record). Content with same `draft_id` updates existing record
4. **SSH Smart Merge Sync**: Bidirectional merge via SFTP. Upload downloads remote DB first, merges+deduplicates both ways, then pushes. Download does same merge. See `merge_database()`, `sync_upload_merge()`, `sync_download_merge()` in `storage.py`
5. **History Preview**: `HistoryWindow` uses `PanedWindow` for resizable left (list) / right (preview) layout. Single click shows content in preview pane, double click restores to main window

### Database Schema (SQLite - `safedraft.db`)

- `drafts`: id, content, created_at, last_updated_at
- `triggers_v2`: id, rule_type (title/process), value, enabled
- `settings`: key, value
- `folders`: uuid, name, is_deleted, updated_at
- `notes`: uuid, folder_uuid, title, content, is_deleted, updated_at, source_draft_id

### Merge Strategy (SSH Sync)

| Table | Key | Merge Rule |
|-------|-----|-----------|
| `drafts` | content | Group by content, keep latest `last_updated_at` |
| `notes` | uuid | Match by uuid, keep latest `updated_at` |
| `folders` | uuid | Match by uuid, keep latest `updated_at` |
| `triggers_v2` | (rule_type, value) | Insert if not exists |

### Platform Dependencies

- **Windows**: `win32gui`, `win32process` (pywin32) for window monitoring
- **macOS**: `pyobjc-framework-Quartz`, `pyobjc-framework-Cocoa` (optional, for Mac builds)
- **Cross-platform**: `psutil` for process info, `pynput` for global hotkeys, `pystray` for system tray

## Important Implementation Notes

- Database uses thread-safe locking (`threading.Lock`) for all operations
- Tkinter `after()` for thread-safe UI updates from background threads
- Auto-topmost timer: 2 minutes (`_start_auto_topmost` sets 120000ms timer)
- Global hotkey `Ctrl+`` toggles main window visibility
- Child windows share the same `StorageManager` instance via `existing_db` parameter
- `HistoryWindow` caches query results in `self.history_data` to avoid repeated DB queries on click/delete/preview
