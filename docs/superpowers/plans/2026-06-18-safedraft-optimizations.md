# SafeDraft 功能优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 SafeDraft 5 项优化（强制推送、超集去重、防抖 15s、默认值调整、时间显示加年份）

**Architecture:** 沿用现有模块边界（`storage.py`/`main.py`/`windows.py`）。新增 2 个 `StorageManager` 方法（`force_push_overwrite`、`deduplicate_drafts_superset`），新增 1 个设置页按钮，改造 1 个去重按钮逻辑，修改若干默认值字面量与一处时间格式。

**Tech Stack:** Python 3 + Tkinter + SQLite + paramiko；测试用 pytest（已安装 9.0.2，无现成测试目录，本计划创建 `tests/`）

**对应 spec:** `docs/superpowers/specs/2026-06-18-safedraft-optimizations-design.md`

---

## 文件结构

| 文件 | 责任 | 本计划改动 |
|------|------|-----------|
| `storage.py` | SQLite 持久化 + SSH 同步 | 新增 2 个方法；修改 `DEFAULT_TRIGGERS`、`_init_db` 默认 theme、`add_trigger` 默认 enabled |
| `main.py` | 主 GUI、自动保存 | 修改防抖时长 1s→15s；修改 `theme` fallback "Deep"→"Light" |
| `windows.py` | 设置对话框、历史窗口 | 新增"强制推送"按钮和回调；改造 `on_deduplicate`；修改多处默认值字面量；修改时间格式 |
| `tests/conftest.py` | pytest fixture | 新建 |
| `tests/test_default_triggers.py` | DEFAULT_TRIGGERS / add_trigger 默认值测试 | 新建 |
| `tests/test_deduplicate_superset.py` | 超集去重算法测试 | 新建 |
| `tests/test_force_push_overwrite.py` | 强制推送 SFTP 备份逻辑（mock） | 新建 |

**Phase 划分**（每 Phase 可独立提交、独立验证）：
- **Phase 1: 默认值与防抖**（Task 1–4）—— 影响新用户首启体验
- **Phase 2: 超集去重**（Task 5–7）—— storage 层 + UI 层 + 测试
- **Phase 3: 强制推送**（Task 8–10）—— storage 层 + UI 层 + 测试

---

## Phase 1: 默认值与防抖

### Task 1: 修改防抖时间 1s → 15s

**Files:**
- Modify: `main.py:365`

**说明：** 单行修改，无需单元测试。手动验证即可。

- [ ] **Step 1: 修改防抖时长**

打开 `main.py`，定位 `on_text_change` 方法（约 line 358-366），将 `self.root.after(1000, self.perform_auto_save)` 改为 `self.root.after(15000, self.perform_auto_save)`。

修改后该函数应为：

```python
def on_text_change(self, event):
    if self.text_area.edit_modified():
        content = self.text_area.get("1.0", "end-1c")
        if content != self.last_content:
            self.last_content = content
            if self.auto_save_timer:
                self.root.after_cancel(self.auto_save_timer)
            self.auto_save_timer = self.root.after(15000, self.perform_auto_save)
        self.text_area.edit_modified(False)
```

- [ ] **Step 2: 手动验证**

```bash
python main.py
```

在主窗口输入文字，停顿，确认约 15 秒后触发保存（观察 `safedraft.db` 文件的 `last_updated_at` 是否更新）。然后输入更多文字，快速 `Ctrl+\`` 隐藏主窗口或关闭主窗口（选 tray），重新打开，确认最新内容已落盘（`on_sub_window_close` 与 `manual_save` 路径仍即时保存）。

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: 防抖时长从 1s 调整为 15s"
```

---

### Task 2: 修改历史归档时间显示格式（加年份）

**Files:**
- Modify: `windows.py:487`（在 `_do_refresh` 方法内）

**说明：** 单行修改。手动验证。

- [ ] **Step 1: 修改时间格式**

打开 `windows.py`，定位 `_do_refresh` 方法（line 475-492），找到 line 487 的时间格式化语句：

旧代码：
```python
time_str = dt.strftime("%H:%M") if dt.date() == datetime.now().date() else dt.strftime("%m/%d %H:%M")
```

新代码：
```python
time_str = dt.strftime("%Y/%m/%d %H:%M")
```

修改后该函数内对应片段：

```python
for row in self.history_data:
    try:
        dt = datetime.fromisoformat(row[3])
        time_str = dt.strftime("%Y/%m/%d %H:%M")
        content = row[1].strip().replace("\n", " ")
        if len(content) > 30: content = content[:30] + "..."
        self.listbox.insert("end", f"[{time_str}] {content}")
    except:
        pass
```

- [ ] **Step 2: 手动验证**

```bash
python main.py
```

打开主窗口输入任意文字，等待保存（或 `Ctrl+S`）。点击"历史"打开历史归档窗口，确认列表项前缀显示为 `[2026/06/18 14:30]` 格式（带年份）。

- [ ] **Step 3: Commit**

```bash
git add windows.py
git commit -m "feat: 历史归档时间显示加年份"
```

---

### Task 3: 修改默认主题为 Light（含初始化显式 INSERT）

**Files:**
- Modify: `storage.py:121`（`_init_db` 中显式 INSERT theme）
- Modify: `main.py:71`（`theme` fallback）
- Modify: `windows.py:742`（设置对话框主题下拉默认）

**说明：** `storage.py:121` 在新数据库初始化时**显式**插入 `theme="Deep"`，覆盖任何 fallback。三处必须一起改，否则新用户首次启动仍是 Deep 主题。手动验证。

- [ ] **Step 1: 修改 `storage.py:121`**

打开 `storage.py`，定位 `_init_db` 方法（约 line 68-122），找到 line 121：

旧：
```python
self.cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ("theme", "Deep"))
```

新：
```python
self.cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ("theme", "Light"))
```

- [ ] **Step 2: 修改 `main.py:71`**

旧（line 71）：
```python
self.current_theme_name = self.db.get_setting("theme", "Deep")
```

新：
```python
self.current_theme_name = self.db.get_setting("theme", "Light")
```

- [ ] **Step 3: 修改 `windows.py:742`**

打开 `windows.py`，定位 `setup_general_ui` 方法（约 line 719-785），找到 line 742：

旧：
```python
current_theme = self.db.get_setting("theme", "Deep")
```

新：
```python
current_theme = self.db.get_setting("theme", "Light")
```

- [ ] **Step 4: 手动验证**

模拟新用户：删除本地 `safedraft.db`（备份后），运行 `python main.py`，确认启动后是 Light 主题（白底）。

恢复老 DB 后再次启动，确认已存在的 `theme` 设置不被覆盖（仍是用户原主题）。

- [ ] **Step 5: Commit**

```bash
git add storage.py main.py windows.py
git commit -m "feat: 默认主题从 Deep 改为 Light"
```

---

### Task 4: 修改其它默认值（透明度、关闭行为、智能感知、触发器默认状态）

**Files:**
- Modify: `windows.py:752`（透明度 fallback `0.95` → `1.0`）
- Modify: `windows.py:779`（`exit_action` fallback `"ask"` → `"tray"`）
- Modify: `windows.py:817`（`master_monitor` fallback `"1"` → `"0"`）
- Modify: `storage.py:78`（`triggers_v2.enabled` 列 `DEFAULT 1` → `DEFAULT 0`）
- Modify: `storage.py:14-28`（`DEFAULT_TRIGGERS` 所有 enabled 从 1 改为 0）
- Modify: `storage.py:610`（`add_trigger` 中显式 `enabled=1` → `enabled=0`）

**说明：** SQLite 无法直接 ALTER 列 DEFAULT，所以已有 DB 不会自动获得新 DEFAULT。必须把 `DEFAULT_TRIGGERS` 列表项的 enabled 和 `add_trigger` 的 INSERT 显式改为 0，才能覆盖所有用户（含已有 DB）。

- [ ] **Step 1: 修改 `windows.py:752`**

定位 `setup_general_ui` 内的透明度 Scale（line 748-758），找到 line 752：

旧：
```python
current_alpha = float(self.db.get_setting("window_alpha", "0.95"))
```

新：
```python
current_alpha = float(self.db.get_setting("window_alpha", "1.0"))
```

- [ ] **Step 2: 修改 `windows.py:779`**

定位 `exit_action` 的 Combobox（line 776-785），找到 line 779：

旧：
```python
current_exit = self.db.get_setting("exit_action", "ask")
```

新：
```python
current_exit = self.db.get_setting("exit_action", "tray")
```

- [ ] **Step 3: 修改 `windows.py:817`**

定位 `setup_rules_ui`（line 813-847），找到 line 817：

旧：
```python
current_master = self.db.get_setting("master_monitor", "1")
```

新：
```python
current_master = self.db.get_setting("master_monitor", "0")
```

- [ ] **Step 4: 修改 `storage.py:78`**

打开 `storage.py`，定位 `_init_db` 中的 `triggers_v2` 建表语句（line 76-80）：

旧：
```python
self.cursor.execute('''CREATE TABLE IF NOT EXISTS triggers_v2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_type TEXT, value TEXT, enabled INTEGER DEFAULT 1,
        UNIQUE(rule_type, value)
    )''')
```

新：
```python
self.cursor.execute('''CREATE TABLE IF NOT EXISTS triggers_v2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_type TEXT, value TEXT, enabled INTEGER DEFAULT 0,
        UNIQUE(rule_type, value)
    )''')
```

- [ ] **Step 5: 修改 `storage.py:14-28`（DEFAULT_TRIGGERS）**

定位模块顶部常量（line 14-28），将所有元组中第三项从 `1` 改为 `0`：

旧：
```python
DEFAULT_TRIGGERS = [
    ("title", "ChatGPT", 1),
    ("title", "Claude", 1),
    ("title", "DeepSeek", 1),
    ("title", "Gemini", 1),
    ("title", "Copilot", 1),
    ("title", "文心一言", 1),
    ("title", "通义千问", 1),
    ("title", "Kimi", 1),
    ("process", "winword.exe", 1),
    ("process", "wps.exe", 1),
    ("process", "notepad.exe", 1),
    ("process", "feishu.exe", 1),
    ("process", "dingtalk.exe", 1),
]
```

新：
```python
DEFAULT_TRIGGERS = [
    ("title", "ChatGPT", 0),
    ("title", "Claude", 0),
    ("title", "DeepSeek", 0),
    ("title", "Gemini", 0),
    ("title", "Copilot", 0),
    ("title", "文心一言", 0),
    ("title", "通义千问", 0),
    ("title", "Kimi", 0),
    ("process", "winword.exe", 0),
    ("process", "wps.exe", 0),
    ("process", "notepad.exe", 0),
    ("process", "feishu.exe", 0),
    ("process", "dingtalk.exe", 0),
]
```

- [ ] **Step 6: 修改 `storage.py:610`（add_trigger）**

定位 `add_trigger` 方法（line 608-612）：

旧：
```python
def add_trigger(self, rtype, val):
    with self.lock:
        self.cursor.execute('INSERT OR IGNORE INTO triggers_v2 (rule_type, value, enabled) VALUES (?, ?, 1)',
                            (rtype, val))
        self.conn.commit()
```

新：
```python
def add_trigger(self, rtype, val):
    with self.lock:
        self.cursor.execute('INSERT OR IGNORE INTO triggers_v2 (rule_type, value, enabled) VALUES (?, ?, 0)',
                            (rtype, val))
        self.conn.commit()
```

- [ ] **Step 7: 手动验证**

模拟新用户：删除本地 `safedraft.db`（备份），运行 `python main.py`：
1. 确认窗口不透明（100%）
2. 点关闭按钮，确认直接最小化到托盘（不再弹询问框）
3. 设置 → 监控规则，确认"启用智能感知"未勾选；列表里的预置规则全部未勾选
4. 点"➕ 添加网址/标题"，输入任意关键字确认添加；刷新后确认该新规则也是未勾选状态

- [ ] **Step 8: Commit**

```bash
git add windows.py storage.py
git commit -m "feat: 默认不透明度 100%、关闭最小化到托盘、智能感知默认关闭、新触发器默认未勾选"
```

---

## Phase 2: 超集去重

### Task 5: 创建 pytest 基础设施（conftest.py）

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**说明：** 后续 Task 会用到 `tmp_db` fixture，提供独立的临时 `StorageManager`。

- [ ] **Step 1: 创建 `tests/__init__.py`（空文件）**

写入空内容（占位，使 tests 目录成为 Python package）。

- [ ] **Step 2: 创建 `tests/conftest.py`**

```python
import os
import sys
import tempfile
import pytest
from pathlib import Path

# 让 pytest 能找到项目根目录的模块
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storage import StorageManager


@pytest.fixture
def tmp_db():
    """提供一个临时 StorageManager，测试结束自动清理。"""
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "test.db")
        base_path = d
        # StorageManager 构造时接收 (db_path=None, base_path=None)
        sm = StorageManager(db_path=db_path, base_path=base_path)
        yield sm
        try:
            sm.conn.close()
        except Exception:
            pass
```

**注意：** 需要先确认 `StorageManager.__init__` 的签名是否兼容 `db_path` 和 `base_path` 参数。先执行下面这步验证。

- [ ] **Step 3: 验证 StorageManager 构造签名**

```bash
python -c "from storage import StorageManager; import inspect; print(inspect.signature(StorageManager.__init__))"
```

如果输出包含 `db_path` 和 `base_path` 参数，直接进入 Step 4。如果签名不同（如只接收 `db_path`），调整 `conftest.py` 中的实例化代码以匹配真实签名。

- [ ] **Step 4: 验证 fixture 可用**

```bash
python -m pytest tests/ --collect-only
```

预期：能成功收集（虽然此时还没有测试用例，会输出 `no tests ran`，但不应有 ImportError）。

- [ ] **Step 5: Commit**

```bash
git add tests/__init__.py tests/conftest.py
git commit -m "test: 添加 pytest 基础设施与 tmp_db fixture"
```

---

### Task 6: 实现 `deduplicate_drafts_superset` 方法（TDD）

**Files:**
- Create: `tests/test_deduplicate_superset.py`
- Modify: `storage.py`（在 `deduplicate_drafts` 方法后新增 `deduplicate_drafts_superset`）

**算法边界（与 spec 一致）：**
- 链式 `A⊂B⊂C` → 只保留 `C`
- 互不为子集 → 都保留
- 多最大超集（`A⊂B`、`A⊂C`，`B∩C` 不互含）→ 保留 `B` 和 `C`，删 `A`
- 空白记录（`content.strip() == ""` 或 `None`）→ 直接删除
- 大小写敏感、不 strip、用 Python `in` 运算符判定子串

- [ ] **Step 1: 写失败测试**

创建 `tests/test_deduplicate_superset.py`：

```python
"""超集去重算法测试。"""


class TestDeduplicateSuperset:
    def test_basic_subset(self, tmp_db):
        """A 是 B 的子串，删除 A。"""
        tmp_db.save_content_forced("AAAABBC")
        tmp_db.save_content_forced("AAAABBCGWERER")

        deleted = tmp_db.deduplicate_drafts_superset()

        assert deleted == 1
        contents = [r[1] for r in tmp_db.get_history()]
        assert "AAAABBCGWERER" in contents
        assert "AAAABBC" not in contents

    def test_chain(self, tmp_db):
        """A⊂B⊂C，只保留 C。"""
        tmp_db.save_content_forced("abc")
        tmp_db.save_content_forced("abcd")
        tmp_db.save_content_forced("abcde")

        deleted = tmp_db.deduplicate_drafts_superset()

        assert deleted == 2
        contents = [r[1] for r in tmp_db.get_history()]
        assert contents == ["abcde"]

    def test_multi_maximal(self, tmp_db):
        """A⊂B、A⊂C，B 与 C 不互含；保留 B、C，删除 A。"""
        tmp_db.save_content_forced("abc")      # A
        tmp_db.save_content_forced("abcd")     # B
        tmp_db.save_content_forced("abcef")    # C

        deleted = tmp_db.deduplicate_drafts_superset()

        assert deleted == 1
        contents = sorted(r[1] for r in tmp_db.get_history())
        assert contents == ["abcd", "abcef"]

    def test_case_sensitive(self, tmp_db):
        """严格区分大小写：'abc' 和 'ABC' 互不为子串，都保留。"""
        tmp_db.save_content_forced("abc")
        tmp_db.save_content_forced("ABC")

        deleted = tmp_db.deduplicate_drafts_superset()

        assert deleted == 0
        contents = sorted(r[1] for r in tmp_db.get_history())
        assert contents == ["ABC", "abc"]

    def test_blank_records_removed(self, tmp_db):
        """空白记录直接删除。"""
        tmp_db.save_content_forced("hello")
        # 直接写一条空白到 drafts 表
        tmp_db.cursor.execute(
            "INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)",
            ("   ", "2026-06-18T10:00:00", "2026-06-18T10:00:00"),
        )
        tmp_db.cursor.execute(
            "INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)",
            ("", "2026-06-18T10:00:00", "2026-06-18T10:00:00"),
        )
        tmp_db.conn.commit()

        deleted = tmp_db.deduplicate_drafts_superset()

        assert deleted == 2
        contents = [r[1] for r in tmp_db.get_history()]
        assert contents == ["hello"]

    def test_no_duplicates(self, tmp_db):
        """没有子集关系，全部保留。"""
        tmp_db.save_content_forced("hello")
        tmp_db.save_content_forced("world")

        deleted = tmp_db.deduplicate_drafts_superset()

        assert deleted == 0
        contents = sorted(r[1] for r in tmp_db.get_history())
        assert contents == ["hello", "world"]

    def test_empty_db(self, tmp_db):
        """空数据库返回 0。"""
        deleted = tmp_db.deduplicate_drafts_superset()
        assert deleted == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_deduplicate_superset.py -v
```

预期：所有 7 个测试 FAIL，错误信息为 `AttributeError: 'StorageManager' object has no attribute 'deduplicate_drafts_superset'`。

- [ ] **Step 3: 实现 `deduplicate_drafts_superset`**

打开 `storage.py`，定位 `deduplicate_drafts` 方法（line 551-567）。在该方法之后、`get_history` 方法之前，插入新方法：

```python
def deduplicate_drafts_superset(self):
    """删除被其它记录包含的子集记录，以及空白记录。
    严格大小写、不 strip；空白记录直接删除。
    返回删除条数。"""
    with self.lock:
        self.cursor.execute('SELECT id, content FROM drafts ORDER BY id ASC')
        rows = self.cursor.fetchall()

        to_delete = set()
        non_blank = []

        # 1. 空白记录直接删除
        for rid, content in rows:
            if content is None or content.strip() == "":
                to_delete.add(rid)
            else:
                non_blank.append((rid, content))

        # 2. 超集判定：a 是 b 的严格子串 → 删除 a
        n = len(non_blank)
        for i in range(n):
            id_a, content_a = non_blank[i]
            if id_a in to_delete:
                continue
            for j in range(n):
                if i == j:
                    continue
                id_b, content_b = non_blank[j]
                if id_b in to_delete:
                    continue
                if content_a != content_b and content_a in content_b:
                    to_delete.add(id_a)
                    break

        if to_delete:
            placeholders = ",".join("?" * len(to_delete))
            self.cursor.execute(
                f'DELETE FROM drafts WHERE id IN ({placeholders})',
                tuple(to_delete),
            )
            self.conn.commit()

        deleted_count = len(to_delete)

    self._notify_observers()
    return deleted_count
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_deduplicate_superset.py -v
```

预期：7 个测试全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add tests/test_deduplicate_superset.py storage.py
git commit -m "feat: 添加超集去重方法 deduplicate_drafts_superset"
```

---

### Task 7: 改造 `on_deduplicate` 按钮（整合超集去重）

**Files:**
- Modify: `windows.py:334-344`（`on_deduplicate` 方法）

**说明：** UI 修改，手动验证。

- [ ] **Step 1: 改造 `on_deduplicate` 方法**

打开 `windows.py`，定位 `on_deduplicate` 方法（line 334-344）。

旧：
```python
def on_deduplicate(self):
    if messagebox.askyesno("清理确认", "确定要扫描并删除所有内容重复的记录吗？\n\n仅保留最新的一条记录。"):
        try:
            count = self.db.deduplicate_drafts()
            if count > 0:
                messagebox.showinfo("完成", f"清理成功！\n共删除了 {count} 条重复记录。")
            else:
                messagebox.showinfo("完成", "没有发现重复记录，列表很干净。")
            self.refresh_data()
        except Exception as e:
            messagebox.showerror("错误", f"清理失败: {str(e)}")
```

新：
```python
def on_deduplicate(self):
    if messagebox.askyesno(
        "清理确认",
        "确定要扫描并清理重复记录吗？\n\n"
        "• 步骤1：删除内容完全相同的记录（保留最新）\n"
        "• 步骤2：删除被其它记录包含的子集记录（保留最大超集）\n"
        "• 步骤3：删除空白记录\n\n"
        "此操作不可撤销。"
    ):
        try:
            count1 = self.db.deduplicate_drafts()
            count2 = self.db.deduplicate_drafts_superset()
            total = count1 + count2
            if total > 0:
                messagebox.showinfo(
                    "完成",
                    f"清理成功！\n完全重复删除 {count1} 条\n超集/空白删除 {count2} 条"
                )
            else:
                messagebox.showinfo("完成", "没有需要清理的记录。")
            self.refresh_data()
        except Exception as e:
            messagebox.showerror("错误", f"清理失败: {str(e)}")
```

- [ ] **Step 2: 手动验证**

```bash
python main.py
```

构造测试数据：
1. 在主窗口输入 `AAAABBC`，按"💾 保存"归档（清空）。
2. 在主窗口输入 `AAAABBCGWERER`，按"💾 保存"归档。
3. 在主窗口输入 `hello`，按 `Ctrl+S` 快照（不清空）。
4. 在主窗口输入 `hello`，按"💾 保存"归档（产生完全重复）。

打开历史归档窗口，应能看到 4 条记录。点击"🧹 去重"按钮，确认弹窗显示三步骤说明。确认后：
- 完全重复 `hello` 删除 1 条
- 超集 `AAAABBC` 删除 1 条
- 共删除 2 条，剩余 `AAAABBCGWERER` 和 `hello`

- [ ] **Step 3: Commit**

```bash
git add windows.py
git commit -m "feat: 去重按钮整合完全去重+超集去重+空白清理"
```

---

## Phase 3: 强制推送

### Task 8: 实现 `force_push_overwrite` 方法（含 mock 测试）

**Files:**
- Create: `tests/test_force_push_overwrite.py`
- Modify: `storage.py`（在 `sync_download_merge` 方法后新增 `force_push_overwrite`）

**说明：** 测试用 `unittest.mock.MagicMock` 替代真实 SSH/SFTP，验证备份和上传调用顺序。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_force_push_overwrite.py`：

```python
"""强制推送（覆盖远程）测试。SFTP 用 mock 替代。"""
from unittest.mock import patch, MagicMock
import os


class TestForcePushOverwrite:
    def test_calls_rename_when_remote_exists(self, tmp_db):
        """远程存在 DB 时，先备份再上传。"""
        tmp_db.save_content_forced("local data")

        with patch.object(tmp_db, '_get_ssh_client') as mock_ssh_ctor:
            ssh = MagicMock()
            sftp = MagicMock()
            ssh.open_sftp.return_value = sftp
            mock_ssh_ctor.return_value = ssh

            # 远程 stat 成功（文件存在）
            sftp.stat.return_value = MagicMock()
            # listdir 返回空（无旧 md5）
            sftp.listdir.return_value = []

            tmp_db.force_push_overwrite("user@host", "/remote/path")

            # 验证调用了 rename（备份）
            assert sftp.rename.called, "应该调用 sftp.rename 备份远程 DB"
            # 验证上传了本地 DB
            assert sftp.put.called, "应该调用 sftp.put 上传 DB"
            # 第一次 put 是 DB，第二次是 md5
            assert sftp.put.call_count >= 1
            ssh.open_sftp.assert_called_once()

    def test_skips_rename_when_remote_missing(self, tmp_db):
        """远程不存在 DB 时，跳过备份，直接上传。"""
        tmp_db.save_content_forced("local data")

        with patch.object(tmp_db, '_get_ssh_client') as mock_ssh_ctor:
            ssh = MagicMock()
            sftp = MagicMock()
            ssh.open_sftp.return_value = sftp
            mock_ssh_ctor.return_value = ssh

            # 远程 stat 抛 FileNotFoundError（文件不存在）
            sftp.stat.side_effect = FileNotFoundError("not found")
            sftp.listdir.return_value = []

            tmp_db.force_push_overwrite("user@host", "/remote/path")

            # 没备份
            assert not sftp.rename.called, "远程不存在时不应调用 rename"
            # 但有上传
            assert sftp.put.called

    def test_raises_on_empty_config(self, tmp_db):
        """server_ip 或 remote_path 为空时抛 ValueError。"""
        try:
            tmp_db.force_push_overwrite("", "/remote/path")
            assert False, "应抛 ValueError"
        except ValueError:
            pass

        try:
            tmp_db.force_push_overwrite("user@host", "")
            assert False, "应抛 ValueError"
        except ValueError:
            pass

    def test_removes_old_md5_files(self, tmp_db):
        """远程有旧 md5 文件时，应被删除。"""
        tmp_db.save_content_forced("local data")

        with patch.object(tmp_db, '_get_ssh_client') as mock_ssh_ctor:
            ssh = MagicMock()
            sftp = MagicMock()
            ssh.open_sftp.return_value = sftp
            mock_ssh_ctor.return_value = ssh

            sftp.stat.side_effect = FileNotFoundError("not found")
            sftp.listdir.return_value = [
                "safedraft_oldhash1.md5",
                "safedraft_oldhash2.md5",
                "other_file.txt",
            ]

            tmp_db.force_push_overwrite("user@host", "/remote/path")

            # 验证调用了 sftp.remove 删除旧 md5
            removed_paths = [call.args[0] for call in sftp.remove.call_args_list]
            assert any("safedraft_oldhash1.md5" in p for p in removed_paths)
            assert any("safedraft_oldhash2.md5" in p for p in removed_paths)
            assert not any("other_file.txt" in p for p in removed_paths), "不应删除无关文件"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_force_push_overwrite.py -v
```

预期：4 个测试全部 FAIL，错误信息为 `AttributeError: 'StorageManager' object has no attribute 'force_push_overwrite'`（除 `test_raises_on_empty_config` 可能因为方法不存在而以不同方式失败）。

- [ ] **Step 3: 实现 `force_push_overwrite`**

打开 `storage.py`，定位 `sync_download_merge` 方法（line 411 起，到 `_get_ssh_client` 之前）。在该方法之后插入新方法：

```python
def force_push_overwrite(self, server_ip, remote_path):
    """强制推送：用本地 DB 完全覆盖远程。
    1. 远程现有 safedraft.db 备份为 safedraft.db.bak.YYYYMMDD_HHMMSS
    2. 上传本地 safedraft.db 覆盖远程
    3. 更新本地 MD5 状态文件
    4. 删除远程所有旧 safedraft_*.md5
    5. 上传新的 safedraft_{hash}.md5
    """
    if not server_ip or not remote_path:
        raise ValueError("配置不完整")

    ssh = self._get_ssh_client(server_ip)
    sftp = ssh.open_sftp()

    try:
        remote_base = remote_path.rstrip('/')
        remote_file = f"{remote_base}/safedraft.db"

        # 1. 备份远程（若存在）
        try:
            sftp.stat(remote_file)
            backup_name = f"safedraft.db.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            remote_backup = f"{remote_base}/{backup_name}"
            sftp.rename(remote_file, remote_backup)
        except FileNotFoundError:
            pass
        except IOError:
            pass

        # 2. 提交本地 + 上传
        with self.lock:
            self.conn.commit()
        sftp.put(self.db_path, remote_file)

        # 3. 更新本地 MD5 状态文件
        md5_hash = self.update_md5_status()

        # 4. 删除远程所有旧的 safedraft_*.md5
        for fname in sftp.listdir(remote_base):
            if fname.startswith("safedraft_") and fname.endswith(".md5"):
                try:
                    sftp.remove(f"{remote_base}/{fname}")
                except Exception:
                    pass

        # 5. 上传新的 .md5 校验文件
        local_status = os.path.join(self.base_path, f"safedraft_{md5_hash}.md5")
        remote_md5 = f"{remote_base}/safedraft_{md5_hash}.md5"
        sftp.put(local_status, remote_md5)

    finally:
        sftp.close()
        ssh.close()
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_force_push_overwrite.py -v
```

预期：4 个测试全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add tests/test_force_push_overwrite.py storage.py
git commit -m "feat: 添加强制推送方法 force_push_overwrite（含远程备份）"
```

---

### Task 9: 在设置页 → 服务器同步 tab 新增"强制推送"按钮

**Files:**
- Modify: `windows.py`（`setup_sync_ui` 末尾追加 UI；新增 `on_force_push` 方法）

**说明：** UI 修改，手动验证。

- [ ] **Step 1: 在 `setup_sync_ui` 末尾追加 UI**

打开 `windows.py`，定位 `setup_sync_ui` 方法（line 558-658）。在方法末尾（`_save_sync_config` 按钮和提示文字之后）追加：

```python
        # --- 强制推送（覆盖远程） ---
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=15)

        tk.Label(f, text="强制推送（覆盖远程）",
                 bg=self.colors["bg"], fg="#e74c3c",
                 font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 5))

        tk.Button(f, text="⬆️ 强制推送（覆盖远程）",
                  command=self.on_force_push,
                  bg="#e74c3c", fg="white", relief="flat", padx=10).pack(anchor="w", pady=5)

        tk.Label(f, text="* 此操作会用本地数据库完全覆盖远程。\n"
                         "* 推送前会自动备份远程现有数据为 safedraft.db.bak.YYYYMMDD_HHMMSS。\n"
                         "* 不会合并任何数据。",
                 bg=self.colors["bg"], fg="#888888", justify="left").pack(anchor="w")
```

注意保持该方法的缩进（方法内顶层，缩进为 8 空格）。

- [ ] **Step 2: 新增 `on_force_push` 方法**

在 `setup_sync_ui` 方法之后（即下一个方法 `toggle_ssh_enabled` 之前），插入新方法：

```python
    def on_force_push(self):
        if self.db.get_setting("ssh_enabled", "0") != "1":
            messagebox.showerror("未启用", "请先勾选'启用服务器同步功能'")
            return
        ip = self.db.get_setting("ssh_ip", "")
        path = self.db.get_setting("ssh_path", "")
        if not ip or not path:
            messagebox.showerror("配置不完整", "请先填写服务器 IP 和远程目录路径")
            return
        if not messagebox.askyesno(
            "危险操作确认",
            "此操作会用本地数据库完全覆盖远程数据。\n\n"
            "远程现有数据将被备份为 safedraft.db.bak.YYYYMMDD_HHMMSS。\n"
            "此操作不可撤销。确定继续？"
        ):
            return
        self.app._run_async_sync(
            self.db.force_push_overwrite, ip, path,
            "强制推送成功（远程已覆盖并备份）"
        )
```

- [ ] **Step 3: 手动验证**

需要一台测试 SSH 服务器。若没有，可跳过实际推送，仅验证按钮和确认对话框：

```bash
python main.py
```

1. 打开设置 → 服务器同步 tab
2. 滚动到底部，确认新增"强制推送（覆盖远程）"区块和红色按钮
3. 暂不勾选"启用服务器同步功能"，点按钮，确认弹"未启用"错误
4. 勾选启用并填好 IP/路径（可以填假值），点按钮，确认弹"危险操作确认"对话框，文字与设计一致
5. 点"否"取消，确认没有触发推送

如果有测试服务器，进一步：
6. 在远程放一份 `safedraft.db`（可以放空 DB 或带几条数据）
7. 本地新建几条草稿（含脏数据）
8. 点强制推送 → 确认 → 等待成功提示
9. SSH 到远程，确认：原 `safedraft.db` 被改名为 `safedraft.db.bak.YYYYMMDD_HHMMSS`；新 `safedraft.db` 内容与本地一致；旧的 `safedraft_*.md5` 被删除；新的 `safedraft_{hash}.md5` 已上传

- [ ] **Step 4: Commit**

```bash
git add windows.py
git commit -m "feat: 设置页服务器同步 tab 新增强制推送按钮"
```

---

### Task 10: 全量回归测试与最终提交

**Files:** 无新增改动，仅运行验证

- [ ] **Step 1: 运行所有单元测试**

```bash
python -m pytest tests/ -v
```

预期：所有测试 PASS（共约 11 个测试：7 个超集去重 + 4 个强制推送）。

- [ ] **Step 2: 端到端手动回归**

```bash
python main.py
```

按以下顺序测试，确认所有功能正常：

1. **新用户场景**：备份并删除 `safedraft.db`，启动应用
   - Light 主题、100% 不透明、智能感知关闭、预置触发器全部未勾选
2. **监控规则**：勾选一个规则，关闭智能感知开关，确认状态被保存
3. **关闭窗口**：点关闭按钮，确认直接最小化到托盘
4. **历史归档时间**：写一条草稿，打开历史窗口，确认时间格式 `[2026/06/18 14:30]`
5. **去重按钮**：构造渐进式草稿，点"🧹 去重"，确认三步骤执行
6. **强制推送**：在设置 → 服务器同步 tab，确认按钮存在；触发一次推送（需要测试服务器）
7. **防抖 15s**：连续输入文字，停顿，观察约 15s 后才保存

- [ ] **Step 3: 验证现有同步功能不受影响**

```bash
python main.py
```

主界面 `☁️⬆️` 和 `☁️⬇️` 按钮：点击后确认仍走 `sync_upload_merge` / `sync_download_merge`（合并模式），行为与改动前一致。

- [ ] **Step 4: 最终 commit（如有遗留改动）**

```bash
git status
# 如果有未提交改动：
git add -A
git commit -m "test: 全量回归验证通过"
```

---

## Self-Review 自审清单

**1. Spec 覆盖检查：**

| Spec 模块 | 覆盖任务 |
|----------|---------|
| 模块 1 强制推送 | Task 8（storage 层）+ Task 9（UI） |
| 模块 2 超集去重 | Task 6（storage 层）+ Task 7（UI） |
| 模块 3 防抖 15s | Task 1 |
| 模块 4 默认值（主题） | Task 3 |
| 模块 4 默认值（其它） | Task 4 |
| 模块 5 时间显示 | Task 2 |

补充覆盖（spec 未显式提及但实现必须的）：
- `DEFAULT_TRIGGERS` 所有 enabled=0 → Task 4 Step 5
- `storage.py:121` `_init_db` 显式 INSERT theme="Light" → Task 3 Step 1
- `add_trigger` 显式 enabled=0 → Task 4 Step 6
- pytest 基础设施 → Task 5

**2. Placeholder 扫描：** ✅ 所有 step 都有完整代码或具体命令。

**3. 类型/签名一致性：**
- `force_push_overwrite(server_ip, remote_path)` — Task 8 定义，Task 9 调用，签名一致 ✅
- `deduplicate_drafts_superset()` — Task 6 定义，Task 7 调用，签名一致 ✅
- `_run_async_sync(func, ip, path, success_msg)` — Task 9 调用，与 main.py:222 现有签名一致 ✅
- `_get_ssh_client(ip_input)` — Task 8 调用，与 storage.py:125 现有签名一致 ✅

**4. 顺序依赖：**
- Task 5（pytest fixture）必须在 Task 6、8 之前
- Task 6（storage 方法）必须在 Task 7（UI 改造）之前
- Task 8（storage 方法）必须在 Task 9（UI）之前
- Task 1–4 互相独立，可任意顺序

---

## 执行计划摘要

| Task | Phase | 文件 | 测试方式 | TDD? |
|------|-------|------|---------|------|
| 1 | 默认值与防抖 | `main.py` | 手动 | 否（单行改） |
| 2 | 默认值与防抖 | `windows.py` | 手动 | 否（单行改） |
| 3 | 默认值与防抖 | `storage.py`, `main.py`, `windows.py` | 手动 | 否 |
| 4 | 默认值与防抖 | `storage.py`, `windows.py` | 手动 | 否 |
| 5 | 超集去重 | `tests/` | pytest | — |
| 6 | 超集去重 | `tests/`, `storage.py` | pytest | ✅ |
| 7 | 超集去重 | `windows.py` | 手动 | 否 |
| 8 | 强制推送 | `tests/`, `storage.py` | pytest + mock | ✅ |
| 9 | 强制推送 | `windows.py` | 手动 | 否 |
| 10 | 回归 | — | 全量 | — |
