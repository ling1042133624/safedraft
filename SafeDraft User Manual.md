# SafeDraft User Manual

**Version**: 1.0
**Core Concept**: Seamless Recording, Instant Retrieval, Never Lost.

---

## 1. Introduction

SafeDraft is a system-level input "safe box" designed to eliminate the anxiety of "typing for an hour, only to lose everything in a crash." It runs silently in the background, recording every fragment of your thoughts in real-time. Whether it's a software crash, a power outage, or an accidental deletion, you can always retrieve your lost text within SafeDraft.

It is not just a notepad; it is your **Input Airbag**.

---

## 2. Quick Start

### 2.1 Installation & Running
SafeDraft is portable software (no installation required).
1.  Download `SafeDraft.exe`.
2.  **Recommendation**: Place it in a fixed folder (because the database file `safedraft.db` will be generated in the same directory).
3.  Double-click to run.

### 2.2 Interface Overview
* **Main Input Area**: A minimalist text box supporting Markdown-style input.
* **Top Toolbar**:
    * `➕ New`: Open a new, independent input window.
    * `💾 Save & Clear`: Archive current content to history and clear the screen, ready for a new topic.
    * `⚙️ Settings`: Configure monitoring rules, appearance, and system behavior.
    * `📌 Pin`: Manually force the window to stay on top (Blue status); Countdown mode during auto-popup (Orange status).
    * `🕒 Time Machine`: View, search, and restore historical records.

---

## 3. Core Features

### 3.1 Intelligent Sensing & Auto-Popup
SafeDraft monitors the applications you are currently using.
* **Trigger Mechanism**: SafeDraft automatically pops up when you open specific applications (e.g., Word, Slack, Discord) or visit specific websites (e.g., ChatGPT, Claude, Gemini).
* **Auto-Pin**: Upon popping up, the window automatically pins itself to the top for **2 minutes** (button turns orange), facilitating reference while typing. It unpins automatically after 2 minutes to avoid blocking your view.
* **Anti-Disturbance**: If you continue working in the same application, SafeDraft will not pop up repeatedly to disturb you.

### 3.2 Seamless Auto-Save
* **Mechanism**: As long as you are typing in SafeDraft, content is saved to the local database in milliseconds.
* **Logic**: No manual save button is required. Even if you force-close the software or the computer loses power, the last input content will still be there when reopened.

### 3.3 Two Saving Modes
1.  **Automatic Streaming**: You just type. The system automatically segments recording blocks based on time intervals (10 minutes).
2.  **Snapshot Save (`Ctrl + S`)**: Pressing the shortcut while typing saves a **separate** copy of the current content as a history record **without affecting your ongoing input**. This is perfect for backing up a draft before making major edits.

### 3.4 💾 Save & Clear
When you finish a piece of writing and copy it to the target software (e.g., sending it to an AI), click this button.
* **Effect**: The current content is forcibly archived to history, and the input box is cleared.
* **Purpose**: Keeps you in a clean interface to start a new topic.

---

## 4. Time Machine

Click the `🕒 Time Machine` button on the main interface to open the history archive window.

* **Search**: Enter keywords in the top search bar to filter history records in real-time.
* **Preview**: The list shows the timestamp and a preview of the first 30 characters.
* **Restore**:
    * **Double-click** a record to overwrite the main input box with its content (the confirmation dialog can be disabled in Settings).
* **Delete**: Select a record and click "Delete Selected" at the bottom to permanently remove it.

---

## 5. Settings

Click `⚙️ Settings` to enter the configuration panel.

### 5.1 Monitoring Rules
Customize which scenarios trigger SafeDraft to pop up automatically:
* **Add App**: Click "Select App (.exe)" to choose programs like `Notion.exe` or `Discord.exe`.
* **Add URL/Title**: Enter keywords contained in the browser title bar, such as `GitHub` or `Stack Overflow`.

### 5.2 General Settings
* **Global Hotkey**: Defaults to `Ctrl + ~` (Backtick key), used to quickly show/hide the main window.
* **Auto-Start**: If checked, the software starts with Windows and minimizes to the system tray.
* **Theme**: Offers `Deep` (Dark Geek Mode) and `Light` (Bright Office Mode).
* **Transparency**: Drag the slider to adjust the main window's opacity for a "see-through" effect.
* **Font Size**: Adjust the font size of the input area and history list to suit different vision needs.
* **Exit Behavior**:
    * *Ask every time*: Popup confirmation.
    * *Minimize to tray*: Keep running in the background (Recommended).
    * *Quit*: Completely close the application.

---

## 6. Shortcuts Guide

| Feature | Shortcut | Scope |
| :--- | :--- | :--- |
| **Quick Show/Hide** | `Ctrl + ~` (Key below Esc) | **Global** (Works anywhere) |
| **Create Snapshot** | `Ctrl + S` | Inside SafeDraft window |
| **Restore History** | Double-click record | Inside Time Machine window |

---

## 7. FAQ

**Q: Why doesn't the global hotkey `Ctrl+~` work?**
A: If your current focus is on an application running as "Administrator" (e.g., Task Manager), and SafeDraft is running with normal privileges, Windows blocks the hotkey.
* **Solution**: Right-click `SafeDraft.exe` -> Properties -> Compatibility -> Check **"Run this program as an administrator"**.

**Q: Why doesn't the software pop up when I open Gemini in my browser?**
A: Please check the "Monitoring Rules" in Settings. If `Gemini` is not in the list, please add it manually. The software works by matching text in the window title bar.

**Q: Where is my data saved? Is it secure?**
A: All data is stored in the `safedraft.db` file (SQLite format) in the same directory as the software. The data is entirely **local** and is never uploaded to the cloud. If you move the software, please make sure to move the `.db` file with it.

**Q: The icon looks blurry on the taskbar.**
A: The software has built-in High DPI support. If it displays abnormally on some older systems, try changing the "High DPI settings" in the exe properties.

---

**SafeDraft**
*Secure your input, capture your inspiration.*