# SafeDraft 功能优化设计

**日期**：2026-06-18
**作者**：ling1042133624（与 Claude Code 协作）
**状态**：已与用户确认设计，待生成实现计划

## 背景

SafeDraft 在日常使用中暴露出 5 个改进点：

1. 现有 `sync_upload_merge` 是双向合并同步，会把本地"不需要的笔记"污染到远程；用户希望有一个**单向覆盖式推送**入口。
2. 现有去重只清理完全相同的记录，无法处理"A 是 B 的子串"这类渐进式草稿。
3. 防抖时间 1 秒过短，连续输入期间频繁落盘，希望放宽到 15 秒。
4. 默认主题/透明度/关闭行为对部分用户不友好，希望默认更"安静"。
5. 历史归档时间只显示 `月/日 时:分`，跨年时无法区分。

## 改动范围

| 模块 | 文件 | 性质 |
|------|------|------|
| 强制推送 | `storage.py`, `windows.py` | 新增方法 + 新增 UI 按钮 |
| 超集去重 | `storage.py`, `windows.py` | 新增方法 + 改造现有按钮逻辑 |
| 防抖时长 | `main.py` | 单行修改 |
| 默认值调整 | `main.py`, `windows.py`, `storage.py` | 多处修改 |
| 时间显示 | `windows.py` | 单行修改 |

---

## 模块 1：强制推送（覆盖远程）

### 用户故事

"我本地有些不需要的草稿被存进了数据库，但现有的'上传'按钮会双向合并，导致这些脏数据被同步到远程。我希望有一个按钮，能直接把本地数据库完全覆盖到远程（远程会被备份）。"

### 设计决策

- **位置**：设置页 → 服务器同步 tab 末尾新增按钮。主界面 `☁️⬆️` 保持现状（合并模式）。
- **语义**：单向覆盖。跳过合并、跳过双向同步。
- **安全机制**：推送前自动备份远程现有 `safedraft.db` 为 `safedraft.db.bak.YYYYMMDD_HHMMSS`；执行前弹二次确认对话框。
- **校验文件**：同步覆盖 `.md5` 校验文件（删除远程所有旧 `safedraft_*.md5`，上传新的）。

### 实现

#### `storage.py:StorageManager.force_push_overwrite(server_ip, remote_path)`

```python
def force_push_overwrite(self, server_ip, remote_path):
    """
    强制推送：用本地 DB 完全覆盖远程。
    1. 备份远程现有 safedraft.db 为 safedraft.db.bak.YYYYMMDD_HHMMSS
    2. 上传本地 safedraft.db 到远程
    3. 更新本地 MD5 状态文件
    4. 删除远程所有旧的 safedraft_*.md5
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
            pass  # 远程尚无 DB，跳过备份
        except IOError:
            pass  # 兼容某些 SFTP 服务器错误类型

        # 2. 提交本地 + 上传
        with self.lock:
            self.conn.commit()
        sftp.put(self.db_path, remote_file)

        # 3. 更新本地 MD5
        md5_hash = self.update_md5_status()

        # 4. 删除远程旧的 .md5
        for fname in sftp.listdir(remote_base):
            if fname.startswith("safedraft_") and fname.endswith(".md5"):
                try:
                    sftp.remove(f"{remote_base}/{fname}")
                except:
                    pass

        # 5. 上传新的 .md5
        local_status = os.path.join(self.base_path, f"safedraft_{md5_hash}.md5")
        remote_md5 = f"{remote_base}/safedraft_{md5_hash}.md5"
        sftp.put(local_status, remote_md5)

    finally:
        sftp.close()
        ssh.close()
```

#### `windows.py:SettingsDialog.setup_sync_ui` 末尾追加

```python
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

#### `windows.py:SettingsDialog.on_force_push`

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
    # 复用 app 的异步执行机制
    self.app._run_async_sync(
        self.db.force_push_overwrite, ip, path,
        "强制推送成功（远程已覆盖并备份）"
    )
```

### 错误处理

- 远程不存在原 DB → 静默跳过备份步骤，继续上传
- SFTP 权限错误 → 异常冒泡到 `_run_async_sync`，由它弹 toast 显示错误
- 网络中断 → 同上
- 本地 DB 被锁 → `with self.lock` 会等待锁，理论上不会出错

---

## 模块 2：超集去重（整合到现有"🧹 去重"按钮）

### 用户故事

"我连续输入会产生很多渐进式草稿，比如 'AAAABBC' 和 'AAAABBCGWERER'，前者是后者的子串。去重时希望只保留最大的那条。"

### 设计决策

- **按钮形态**：合并到现有"🧹 去重"按钮（C1）。点击后顺序执行：完全去重 → 超集去重 → 删除空白。
- **算法边界**：
  - 链式（`A⊂B⊂C`）→ 只保留 `C`
  - 互不为子集 → 都保留
  - 多个最大超集（`A⊂B`、`A⊂C`，B、C 互不为子集）→ 保留 `B` 和 `C`，删除 `A`
  - 空白记录 → 直接删除
- **比较规则**：严格按存储内容比较（D1）。区分大小写，不 strip。

### 实现

#### `storage.py:StorageManager.deduplicate_drafts_superset()`

```python
def deduplicate_drafts_superset(self):
    """删除被其它记录包含的子集记录，以及空白记录。
    返回删除条数。"""
    with self.lock:
        self.cursor.execute('SELECT id, content FROM drafts ORDER BY id ASC')
        rows = self.cursor.fetchall()

        to_delete = set()

        # 1. 空白记录直接删除
        non_blank = []
        for rid, content in rows:
            if content is None or content.strip() == "":
                to_delete.add(rid)
            else:
                non_blank.append((rid, content))

        # 2. 超集判定：若 a 是 b 的严格子串，删除 a
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
                # a 严格是 b 的子串：a 包含于 b，且 a != b
                if content_a != content_b and content_a in content_b:
                    to_delete.add(id_a)
                    break  # a 已被标记删除，无需再比较

        if to_delete:
            placeholders = ",".join("?" * len(to_delete))
            self.cursor.execute(
                f'DELETE FROM drafts WHERE id IN ({placeholders})',
                tuple(to_delete)
            )
            self.conn.commit()

        deleted_count = len(to_delete)

    self._notify_observers()
    return deleted_count
```

**复杂度说明**：O(n²) 字符串包含判定。对于 SafeDraft 的典型数据量（数百到数千条草稿）可接受。若未来数据量级大幅增长，可考虑后缀自动机等高级数据结构，但当前不引入。

#### `windows.py:HistoryWindow.on_deduplicate` 改造

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
                messagebox.showinfo("完成", "没有需要清理的记录")
            self.listbox.delete(0, tk.END)
            self.load_history()
        except Exception as e:
            messagebox.showerror("错误", str(e))
```

---

## 模块 3：防抖 1 秒 → 15 秒

### 实现

`main.py:365`：
```python
# 旧
self.auto_save_timer = self.root.after(1000, self.perform_auto_save)
# 新
self.auto_save_timer = self.root.after(15000, self.perform_auto_save)
```

### 注意事项

- `on_sub_window_close`（main.py:267-272）在窗口关闭时会取消定时器并立即调用 `perform_auto_save()`，所以即使防抖时间延长到 15 秒，关闭窗口时仍能即时落盘，不会丢数据。
- 现有 `Ctrl+S`（`on_ctrl_s`）和"💾 保存"按钮（`manual_save`）是即时执行，不受影响。

---

## 模块 4：默认值调整

### 改动点

| 位置 | 旧默认 | 新默认 | 影响 |
|------|--------|--------|------|
| `main.py:71` `theme` | `"Deep"` | `"Light"` | 新用户首次启动主题 |
| `windows.py:742` 主题下拉默认 | `"Deep"` | `"Light"` | 设置对话框首次显示 |
| `windows.py:752` `window_alpha` | `0.95` | `1.0` | 新用户首次启动不透明度 |
| `windows.py:779` `exit_action` | `"ask"` | `"tray"` | 新用户关闭主窗口默认行为 |
| `windows.py:817` `master_monitor` | `"1"` | `"0"` | 新用户首次启动智能感知默认关 |
| `storage.py:78` `triggers_v2.enabled` 列 DEFAULT | `1` | `0` | 新建 DB 的表结构 |
| `storage.py:add_trigger` INSERT | 隐式使用 DEFAULT | 显式 `enabled=0` | 兼容已有 DB 的新增规则 |

### 影响范围

- **新用户首次启动**：完全应用新默认值
- **已有用户**：`get_setting` 返回已存储的值，不受影响
- **`triggers_v2.enabled` 列 DEFAULT**：SQLite 无法直接 ALTER 列的 DEFAULT，已有 DB 的列 DEFAULT 不会改变。因此必须在 `add_trigger` 中显式写入 `enabled=0`，确保**所有用户**（包括已有 DB）新增规则时默认未勾选。

### `storage.py:add_trigger` 修改

需要先查看该方法的当前实现，确保 INSERT 语句显式包含 `enabled` 列且值为 `0`：

```python
def add_trigger(self, rule_type, value):
    with self.lock:
        self.cursor.execute(
            'INSERT OR IGNORE INTO triggers_v2 (rule_type, value, enabled) VALUES (?, ?, 0)',
            (rule_type, value)
        )
        self.conn.commit()
```

---

## 模块 5：时间显示加年份

### 实现

`windows.py:487`：
```python
# 旧
time_str = dt.strftime("%H:%M") if dt.date() == datetime.now().date() else dt.strftime("%m/%d %H:%M")
# 新
time_str = dt.strftime("%Y/%m/%d %H:%M")
```

### 显示效果

- 改前：今天 → `14:30`，非今天 → `06/15 14:30`
- 改后：所有时间 → `2026/06/18 14:30`

---

## 测试计划

### 单元测试（storage.py）

1. `test_deduplicate_drafts_superset_basic`：构造 A⊂B、C⊂D、互不相干的 E、空白记录各一，验证只保留 B、D、E。
2. `test_deduplicate_drafts_superset_chain`：A⊂B⊂C，验证只保留 C。
3. `test_deduplicate_drafts_superset_multi_maximal`：A⊂B、A⊂C、B∩C 互不为子串，验证保留 B、C。
4. `test_deduplicate_drafts_superset_case_sensitive`：`"abc"` 和 `"ABC"` 都保留。
5. `test_add_trigger_default_disabled`：调用 `add_trigger` 后查询 `enabled` 应为 0。
6. `test_force_push_overwrite_backup`：mock SFTP，验证 `rename` 被调用且新文件被上传。

### 手动验证

1. **强制推送**：在测试服务器放一份远程 DB，本地新建几条草稿（含脏数据），点强制推送，确认远程被覆盖且备份文件存在。
2. **超集去重**：手动构造 5 条渐进式草稿，点去重按钮，确认只保留最大那条。
3. **防抖 15 秒**：连续输入观察保存时机；快速关闭窗口确认仍能即时落盘。
4. **默认值**：删除本地 `safedraft.db` 和 `settings`，重新启动应用，确认主题 Light、透明度 100%、关闭窗口最小化、智能感知开关关闭。
5. **时间显示**：创建一条草稿，查看历史归档，确认显示年份。

### 回归检查

- 现有 `sync_upload_merge`、`sync_download_merge` 不变，已有同步功能不受影响。
- 现有 `deduplicate_drafts` 不变，仍然保留。
- 现有用户的设置不受影响。

---

## 不在本次范围

- 不实现"定时自动强制推送"。强制推送仅为手动触发。
- 不修改 `triggers_v2` 表中已存在记录的 enabled 状态。
- 不调整 `ThemeManager` 内部主题定义，仅切换默认值。
- 不实现远程备份的自动清理（用户手动管理 `.bak.*` 文件）。
- 不修改便签、笔记系统、监控规则的匹配逻辑。

---

## 风险

| 风险 | 缓解 |
|------|------|
| 强制推送覆盖远程误操作 | 二次确认对话框 + 远程自动备份 |
| 超集去重 O(n²) 在大数据量下变慢 | 当前数据量级可接受；若用户反馈慢，后续优化 |
| 修改 `enabled DEFAULT 0` 对老 DB 无效 | 在 `add_trigger` 中显式 INSERT `enabled=0` |
| 15 秒防抖期间崩溃可能丢失数据 | 现有 `Ctrl+S`、`manual_save`、`on_sub_window_close` 均可即时落盘；窗口正常关闭路径不受影响 |
