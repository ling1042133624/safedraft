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