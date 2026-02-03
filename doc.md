# SafeDraft - 输入安全卫士

**SafeDraft** 是一个为了消除“打字一小时，崩溃全白忙”焦虑而生的输入保险箱。它是一个无感知、可记忆、可回溯的系统级文字输入中转站。

## 核心功能

* **🛡️ 无感自动保存**：毫秒级记录每一次按键，数据存储于本地 SQLite 数据库，断电断网不丢失。
* **👀 智能窗口监控**：
    * **应用监控**：自动识别指定的 `.exe` 进程（如 Word, Feishu, Notion）。
    * **网页监控**：自动识别窗口标题中的关键词（如 ChatGPT, Claude）。
    * 当监测到目标应用活动时，SafeDraft 会自动弹出并临时置顶。
* **🕒 时光机 (Time Machine)**：
    * 提供历史记录回溯。
    * 支持“保存并归档”模式，写完一段归档一段，保持输入框清爽。
    * 双击历史记录即可恢复内容。
* **📌 智能置顶**：支持自动临时置顶（2分钟倒计时）和手动强制锁定置顶。

## 文件结构

* `main.py`: 主程序入口，包含 GUI 界面与交互逻辑。
* `storage.py`: 数据库管理模块，负责 SQLite 读写与触发器规则存储。
* `watcher.py`: 后台监控模块，使用 `psutil` 和 `win32gui` 监控活动窗口。

## 环境搭建与运行

### 1. 安装 Python
确保已安装 Python 3.8 或更高版本。

### 2. 安装依赖
在项目根目录下运行终端命令：

```bash
pip install -r requirements.txt
 ```
### 3. 生成exe
```bash
python -m nuitka --standalone --onefile --windows-disable-console --enable-plugin=tk-inter --output-filename=SafeDraft.exe main.py
```
```angular2html
# 发布方案
python -m nuitka --standalone --onefile --jobs=8 --windows-disable-console --enable-plugin=tk-inter --enable-plugin=anti-bloat --no-pyi-file --output-filename=SafeDraft.exe main.py

```

### macOS打包 (在 macOS 上操作)

**注意：你必须有一台 Mac 电脑才能打包 Mac 应用。** 你不能在 Windows 上生成 Mac 的 `.app`。

1.  **准备图标**：

      * 将你的 `icon.png` 转换为 `icon.icns` (Mac 图标格式)。你可以使用在线工具转换。

2.  **安装依赖 (在 Mac 终端中)**：

    ```bash
    pip install -r requirements.txt
    pip install nuitka
    ```

3.  **运行 Nuitka 打包命令**：
    Nuitka 在 Mac 上有一个专门的参数 `--macos-create-app-bundle` 用来生成 `.app` 文件夹。

    ```bash
    python -m nuitka --standalone --onefile --enable-plugin=tk-inter --macos-create-app-bundle --macos-app-icon=icon.icns --output-filename=SafeDraft main.py
    ```

      * `--macos-create-app-bundle`: 告诉 Nuitka 生成 Mac 应用包结构。
      * `--macos-app-icon=icon.icns`: 指定应用图标。

### 重要提示：Mac 权限问题

MacOS 的安全机制（SIP 和 辅助功能权限）比 Windows 严格得多：

1.  **键盘监听 (keyboard)**：`keyboard` 库在 Mac 上监听全局按键通常需要 **sudo (root)** 权限，或者在“系统设置 -\> 隐私与安全性 -\> 辅助功能”中授权给终端或你的 App。如果不想用 root 运行，你的快捷键功能可能会失效。
2.  **窗口标题获取**：获取其他 App 的窗口标题可能需要“屏幕录制”权限。我在上面的 `watcher.py` 代码中做了降级处理（只获取 App 名字），这样可以避免复杂的权限申请。

**建议**：
如果打包遇到困难，在 Mac 上使用 `py2app` 或 `PyInstaller` 也是非常主流的选择：

```bash
# PyInstaller 方案
pip install pyinstaller
pyinstaller --name "SafeDraft" --windowed --icon=icon.icns --onefile main.py

# 开发测试用这个（生成 dist/SafeDraft.dist 文件夹）
python -m nuitka --standalone --windows-disable-console --enable-plugin=tk-inter --jobs=8 main.py

# 发布方案
python -m nuitka --standalone --clean-cache=all --lto=yes --onefile --jobs=8 --windows-disable-console --enable-plugin=tk-inter --enable-plugin=anti-bloat --no-pyi-file --output-filename=SafeDraft.exe main.py
```

```
// 第一次
python -m nuitka --standalone --onefile --jobs=8 ^
     --windows-disable-console ^
     --enable-plugin=tk-inter ^
     --enable-plugin=anti-bloat ^
     --lto=yes ^
     --clean-cache=all ^
     --no-pyi-file ^
     --output-filename=SafeDraft.exe ^
     main.py
```

```angular2html
// 第二次
python -m nuitka --standalone --onefile --jobs=8 ^
     --windows-disable-console ^
     --enable-plugin=tk-inter ^
     --enable-plugin=anti-bloat ^
     --lto=yes ^
     --no-pyi-file ^
     --output-filename=SafeDraft.exe ^
     main.py
```

生成的应用会在 `dist/SafeDraft.app`。