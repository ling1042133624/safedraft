import sqlite3
import os
import sys
import threading
import uuid
import time
from datetime import datetime, timedelta
import hashlib  # <--- 新增这行


# 默认触发器配置
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


class ClickHouseManager:
    def __init__(self, db_manager):
        self.local_db = db_manager
        self.client = None
        self.machine_id = str(uuid.uuid1())

    def get_config(self):
        with self.local_db.lock:
            return {
                'host': self.local_db.get_setting_no_lock("ch_host", ""),
                'port': self.local_db.get_setting_no_lock("ch_port", "9000"),
                'user': self.local_db.get_setting_no_lock("ch_user", "default"),
                'password': self.local_db.get_setting_no_lock("ch_password", ""),
                'database': self.local_db.get_setting_no_lock("ch_database", "default"),
                'enabled': self.local_db.get_setting_no_lock("ch_enabled", "0") == "1"
            }

    def connect(self):
        # [内存优化] 延迟加载：只有在真正连接时才导入库
        try:
            from clickhouse_driver import Client
        except ImportError:
            raise ImportError("未安装 clickhouse-driver 库")

        cfg = self.get_config()
        if not cfg['host']: raise ValueError("Host 地址为空")

        port = int(cfg['port']) if cfg['port'].isdigit() else 9000
        use_secure = (port == 9440)

        self.client = Client(
            host=cfg['host'],
            port=port,
            user=cfg['user'],
            password=cfg['password'],
            database=cfg['database'],
            secure=use_secure,
            connect_timeout=10,
            send_receive_timeout=10
        )
        return self.client

    def init_table(self):
        client = self.connect()
        # Drafts 表
        sql_drafts = """
        CREATE TABLE IF NOT EXISTS drafts (
            uuid String,
            content String,
            created_at DateTime64,
            last_updated_at DateTime64,
            machine_id String
        ) ENGINE = ReplacingMergeTree()
        ORDER BY (created_at, uuid)
        """
        client.execute(sql_drafts)

        # Folders 表
        sql_folders = """
        CREATE TABLE IF NOT EXISTS folders (
            uuid String,
            name String,
            is_deleted UInt8,
            updated_at DateTime64,
            machine_id String
        ) ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY uuid
        """
        client.execute(sql_folders)

        # Notes 表
        sql_notes = """
        CREATE TABLE IF NOT EXISTS notes (
            uuid String,
            folder_uuid String,
            title String,
            content String,
            is_deleted UInt8,
            updated_at DateTime64,
            machine_id String
        ) ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY uuid
        """
        client.execute(sql_notes)
        return True

    def test_connection(self):
        try:
            if self.init_table():
                return True, "连接成功！表结构已验证 ✅"
            return False, "连接失败：未知原因"
        except ImportError:
            return False, "缺少依赖库：请运行 pip install clickhouse-driver"
        except Exception as e:
            return False, f"连接发生错误:\n{str(e)}"

    def push_log(self, content, created_at_iso, updated_at_iso):
        # [修复 Bug] 移除对全局 CHClient 的检查，改为检查配置
        # 如果未开启同步，直接返回，不触发任何导入
        cfg = self.get_config()
        if not cfg['enabled']: return

        def _do_push():
            try:
                client = self.connect()
                record_uuid = str(uuid.uuid4())
                dt_created = datetime.fromisoformat(created_at_iso)
                dt_updated = datetime.fromisoformat(updated_at_iso)

                # 使用确定性 UUID 逻辑 (可选，防止重复)
                unique_source = f"{created_at_iso}_{content}"
                record_uuid = hashlib.md5(unique_source.encode('utf-8')).hexdigest()

                client.execute(
                    'INSERT INTO drafts (uuid, content, created_at, last_updated_at, machine_id) VALUES',
                    [(record_uuid, content, dt_created, dt_updated, self.machine_id)]
                )
            except Exception as e:
                print(f"[ClickHouse] Push Draft Failed: {e}")

        threading.Thread(target=_do_push, daemon=True).start()

    def push_all_history(self, clear_first=False):
        # [修复 Bug] 推送前确保表存在
        try:
            self.init_table()
        except:
            pass  # 忽略初始化错误，尝试继续

        client = self.connect()

        if clear_first:
            try:
                client.execute('TRUNCATE TABLE drafts')
                print("[ClickHouse] Cloud drafts table cleared.")
            except Exception as e:
                print(f"[ClickHouse] Clear table failed: {e}")

        # --- A. 推送草稿 ---
        with self.local_db.lock:
            self.local_db.cursor.execute('SELECT content, created_at, last_updated_at FROM drafts')
            rows = self.local_db.cursor.fetchall()

        data_drafts = []
        for content, c_at, u_at in rows:
            try:
                unique_source = f"{c_at}_{content}"
                deterministic_uuid = hashlib.md5(unique_source.encode('utf-8')).hexdigest()
                data_drafts.append({
                    'uuid': deterministic_uuid,
                    'content': content,
                    'created_at': datetime.fromisoformat(c_at),
                    'last_updated_at': datetime.fromisoformat(u_at),
                    'machine_id': self.machine_id
                })
            except:
                continue
        if data_drafts:
            client.execute('INSERT INTO drafts (uuid, content, created_at, last_updated_at, machine_id) VALUES',
                           data_drafts)

        # --- B. 推送文件夹 ---
        with self.local_db.lock:
            self.local_db.cursor.execute('SELECT uuid, name, is_deleted, updated_at FROM folders')
            rows_f = self.local_db.cursor.fetchall()

        data_f = []
        for r in rows_f:
            try:
                data_f.append({
                    'uuid': r[0], 'name': r[1],
                    'is_deleted': r[2],
                    'updated_at': datetime.fromisoformat(r[3]),
                    'machine_id': self.machine_id
                })
            except:
                continue
        if data_f:
            client.execute('INSERT INTO folders (uuid, name, is_deleted, updated_at, machine_id) VALUES', data_f)

        # --- C. 推送笔记 ---
        with self.local_db.lock:
            self.local_db.cursor.execute('SELECT uuid, folder_uuid, title, content, is_deleted, updated_at FROM notes')
            rows_n = self.local_db.cursor.fetchall()

        data_n = []
        for r in rows_n:
            try:
                data_n.append({
                    'uuid': r[0], 'folder_uuid': r[1], 'title': r[2], 'content': r[3],
                    'is_deleted': r[4],
                    'updated_at': datetime.fromisoformat(r[5]),
                    'machine_id': self.machine_id
                })
            except:
                continue
        if data_n:
            client.execute(
                'INSERT INTO notes (uuid, folder_uuid, title, content, is_deleted, updated_at, machine_id) VALUES',
                data_n)

        return len(data_drafts) + len(data_f) + len(data_n)

    def pull_and_merge(self):
        # [修复 Bug] 拉取前确保表存在
        try:
            self.init_table()
        except:
            pass

        client = self.connect()

        # 1. 拉取草稿
        rows = client.execute(
            "SELECT content, created_at, last_updated_at FROM drafts ORDER BY last_updated_at DESC LIMIT 1000")
        count_drafts = 0
        with self.local_db.lock:
            for content, dt_created, dt_updated in rows:
                iso_created = dt_created.isoformat()
                iso_updated = dt_updated.isoformat()
                self.local_db.cursor.execute('SELECT id FROM drafts WHERE created_at = ? AND content = ?',
                                             (iso_created, content))
                if not self.local_db.cursor.fetchone():
                    self.local_db.cursor.execute(
                        'INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                        (content, iso_created, iso_updated))
                    count_drafts += 1
            self.local_db.conn.commit()

        # 2. 拉取笔记
        count_notes = self.pull_notebook_data()
        return count_drafts + count_notes

    def push_folder_log(self, folder_uuid, name, is_deleted, updated_at_iso):
        cfg = self.get_config()
        if not cfg['enabled']: return

        def _do():
            try:
                client = self.connect()
                dt = datetime.fromisoformat(updated_at_iso)
                client.execute('INSERT INTO folders (uuid, name, is_deleted, updated_at, machine_id) VALUES',
                               [(folder_uuid, name, 1 if is_deleted else 0, dt, self.machine_id)])
            except Exception as e:
                print(f"[ClickHouse] Push Folder Failed: {e}")

        threading.Thread(target=_do, daemon=True).start()

    def push_note_log(self, note_uuid, folder_uuid, title, content, is_deleted, updated_at_iso):
        cfg = self.get_config()
        if not cfg['enabled']: return

        def _do():
            try:
                client = self.connect()
                dt = datetime.fromisoformat(updated_at_iso)
                client.execute(
                    'INSERT INTO notes (uuid, folder_uuid, title, content, is_deleted, updated_at, machine_id) VALUES',
                    [(note_uuid, folder_uuid, title, content, 1 if is_deleted else 0, dt, self.machine_id)])
            except Exception as e:
                print(f"[ClickHouse] Push Note Failed: {e}")

        threading.Thread(target=_do, daemon=True).start()

    def pull_notebook_data(self):
        client = self.connect()
        # 1. 文件夹
        rows_f = client.execute("SELECT uuid, name, is_deleted, updated_at FROM folders FINAL")
        for f_uuid, name, is_deleted, dt_updated in rows_f:
            iso_updated = dt_updated.isoformat()
            self.local_db.upsert_folder_from_cloud(f_uuid, name, is_deleted, iso_updated)

        # 2. 笔记
        rows_n = client.execute("SELECT uuid, folder_uuid, title, content, is_deleted, updated_at FROM notes FINAL")
        for n_uuid, f_uuid, title, content, is_deleted, dt_updated in rows_n:
            iso_updated = dt_updated.isoformat()
            self.local_db.upsert_note_from_cloud(n_uuid, f_uuid, title, content, is_deleted, iso_updated)

        return len(rows_f) + len(rows_n)


class StorageManager:
    def __init__(self, db_name="safedraft.db"):
        self.base_path = self.get_real_executable_path()
        self.db_path = os.path.join(self.base_path, db_name)

        self.lock = threading.Lock()  # 保持现有的锁机制

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._init_db()

        # [修改] 删除 self.current_session_id = None 这行
        # 我们不再在这里存 ID 了

        self._observers = []
        self.ch_manager = ClickHouseManager(self)
        self.debounce_timer = None
        self.current_draft_cache = None

    def get_real_executable_path(self):
        if getattr(sys, 'frozen', False) or "__compiled__" in globals():
            return os.path.dirname(os.path.abspath(sys.argv[0]))
        else:
            return os.path.dirname(os.path.abspath(__file__))

    def _init_db(self):
        with self.lock:
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT,
                    created_at TIMESTAMP,
                    last_updated_at TIMESTAMP
                )''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS triggers_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_type TEXT, value TEXT, enabled INTEGER DEFAULT 1,
                    UNIQUE(rule_type, value)
                )''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')

            # 笔记系统表
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS folders (
                    uuid TEXT PRIMARY KEY,
                    name TEXT,
                    is_deleted INTEGER DEFAULT 0,
                    updated_at TIMESTAMP
                )''')
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS notes (
                    uuid TEXT PRIMARY KEY,
                    folder_uuid TEXT,
                    title TEXT,
                    content TEXT,
                    is_deleted INTEGER DEFAULT 0,
                    updated_at TIMESTAMP,
                    source_draft_id INTEGER
                )''')

            self.cursor.execute('SELECT count(*) FROM triggers_v2')
            if self.cursor.fetchone()[0] == 0:
                self.cursor.executemany(
                    'INSERT OR IGNORE INTO triggers_v2 (rule_type, value, enabled) VALUES (?, ?, ?)', DEFAULT_TRIGGERS)

            self.cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ("theme", "Deep"))
            self.conn.commit()

    def add_observer(self, callback):
        if callback not in self._observers: self._observers.append(callback)

    def remove_observer(self, callback):
        if callback in self._observers: self._observers.remove(callback)

    def _notify_observers(self):
        # 通知 UI 更新（在锁外执行，防止 UI 回调反过来请求锁导致死锁）
        for cb in self._observers:
            try:
                cb()
            except:
                pass

    # --- 设置 ---
    def get_setting(self, key, default=None):
        with self.lock:
            return self.get_setting_no_lock(key, default)

    def get_setting_no_lock(self, key, default=None):
        """供内部已加锁的方法调用，避免重入死锁"""
        self.cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = self.cursor.fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        with self.lock:
            self.cursor.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
            self.conn.commit()

    # --- Drafts CRUD ---
    def save_content(self, content, draft_id=None):
        if not content.strip(): return None
        now = datetime.now()

        new_draft_id = draft_id

        with self.lock:
            if draft_id is None:
                # 如果没有传入 ID，说明是新草稿，直接插入
                self.cursor.execute('INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                                    (content, now.isoformat(), now.isoformat()))
                new_draft_id = self.cursor.lastrowid
            else:
                # 如果传入了 ID，则更新该条记录
                self.cursor.execute('UPDATE drafts SET content = ?, last_updated_at = ? WHERE id = ?',
                                    (content, now.isoformat(), draft_id))

            self.conn.commit()

        self._notify_observers()
        # 触发防抖同步 (传入 new_draft_id 方便后续扩展，这里暂时保持原样)
        self._trigger_debounce_sync(content, now.isoformat(), now.isoformat())

        return new_draft_id

    def _trigger_debounce_sync(self, content, c_at, u_at):
        if self.debounce_timer: self.debounce_timer.cancel()
        self.current_draft_cache = (content, c_at, u_at)
        self.debounce_timer = threading.Timer(5.0, lambda: self.ch_manager.push_log(*self.current_draft_cache))
        self.debounce_timer.start()

    def save_content_forced(self, content):
        if not content.strip(): return
        now = datetime.now()
        with self.lock:
            # 强制保存总是作为新记录插入 (归档)
            self.cursor.execute('INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                                (content, now.isoformat(), now.isoformat()))
            self.conn.commit()
        self._notify_observers()
        self.ch_manager.push_log(content, now.isoformat(), now.isoformat())

    def save_snapshot(self, content):
        if not content.strip(): return
        now = datetime.now()
        with self.lock:
            self.cursor.execute('INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                                (content, now.isoformat(), now.isoformat()))
            self.conn.commit()
        self._notify_observers()
        self.ch_manager.push_log(content, now.isoformat(), now.isoformat())

    def deduplicate_drafts(self):
        """清理内容重复的草稿，只保留 ID 最大（最新）的一条"""
        with self.lock:
            # 使用 SQL 逻辑：删除那些 ID 不在“每个内容分组的最大ID列表”中的记录
            self.cursor.execute('''
                DELETE FROM drafts
                WHERE id NOT IN (
                    SELECT MAX(id)
                    FROM drafts
                    GROUP BY content
                )
            ''')
            deleted_count = self.cursor.rowcount
            self.conn.commit()

        self._notify_observers()
        return deleted_count

    def get_history(self, keyword=None):
        with self.lock:
            if keyword:
                self.cursor.execute(
                    'SELECT id, content, created_at, last_updated_at FROM drafts WHERE content LIKE ? ORDER BY last_updated_at DESC',
                    (f"%{keyword}%",))
            else:
                self.cursor.execute(
                    'SELECT id, content, created_at, last_updated_at FROM drafts ORDER BY last_updated_at DESC')
            return self.cursor.fetchall()

    # --- Triggers CRUD ---
    def get_all_triggers(self):
        with self.lock:
            self.cursor.execute('SELECT id, rule_type, value, enabled FROM triggers_v2 ORDER BY rule_type, value')
            return self.cursor.fetchall()

    def get_enabled_rules(self):
        # Watcher 线程调用，务必加锁并使用独立 cursor
        with self.lock:
            # 这里为了绝对安全，使用临时 cursor
            cur = self.conn.cursor()
            try:
                cur.execute('SELECT rule_type, value FROM triggers_v2 WHERE enabled = 1')
                data = cur.fetchall()
                rules = {'title': [], 'process': []}
                for r, v in data: rules.setdefault(r, []).append(v.lower())
                return rules
            finally:
                cur.close()

    def add_trigger(self, rtype, val):
        with self.lock:
            self.cursor.execute('INSERT OR IGNORE INTO triggers_v2 (rule_type, value, enabled) VALUES (?, ?, 1)',
                                (rtype, val))
            self.conn.commit()

    def toggle_trigger(self, tid, enabled):
        with self.lock:
            self.cursor.execute('UPDATE triggers_v2 SET enabled = ? WHERE id = ?', (1 if enabled else 0, tid))
            self.conn.commit()

    def delete_trigger(self, tid):
        with self.lock:
            self.cursor.execute('DELETE FROM triggers_v2 WHERE id = ?', (tid,))
            self.conn.commit()

    # ==========================
    # 📒 Notebook API
    # ==========================
    def get_folders(self):
        with self.lock:
            self.cursor.execute('SELECT uuid, name FROM folders WHERE is_deleted = 0 ORDER BY updated_at DESC')
            return self.cursor.fetchall()

    def create_folder(self, name):
        fid = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self.lock:
            self.cursor.execute('INSERT INTO folders (uuid, name, is_deleted, updated_at) VALUES (?, ?, 0, ?)',
                                (fid, name, now))
            self.conn.commit()
        self._notify_observers()
        self.ch_manager.push_folder_log(fid, name, False, now)
        return fid

    def rename_folder(self, fid, new_name):
        now = datetime.now().isoformat()
        with self.lock:
            self.cursor.execute('UPDATE folders SET name = ?, updated_at = ? WHERE uuid = ?', (new_name, now, fid))
            self.conn.commit()
        self._notify_observers()
        self.ch_manager.push_folder_log(fid, new_name, False, now)

    def delete_folder(self, fid, delete_children=False):
        now = datetime.now().isoformat()
        fname = "deleted"

        # 使用锁，并使用独立 cursor 处理复杂逻辑
        with self.lock:
            cur = self.conn.cursor()
            try:
                # 1. 删除文件夹
                cur.execute('UPDATE folders SET is_deleted = 1, updated_at = ? WHERE uuid = ?', (now, fid))

                # 获取名字
                cur.execute('SELECT name FROM folders WHERE uuid = ?', (fid,))
                row = cur.fetchone()
                if row: fname = row[0]

                # 2. 处理子笔记
                if delete_children:
                    cur.execute('SELECT uuid, title, content FROM notes WHERE folder_uuid = ? AND is_deleted = 0',
                                (fid,))
                    notes_to_del = cur.fetchall()

                    cur.execute('UPDATE notes SET is_deleted = 1, updated_at = ? WHERE folder_uuid = ?', (now, fid))

                    # 记录需要推送的日志
                    self.logs_to_push = [(n[0], fid, n[1], n[2], True) for n in notes_to_del]
                else:
                    cur.execute('SELECT uuid, title, content FROM notes WHERE folder_uuid = ? AND is_deleted = 0',
                                (fid,))
                    notes_to_move = cur.fetchall()

                    cur.execute('UPDATE notes SET folder_uuid = "", updated_at = ? WHERE folder_uuid = ?', (now, fid))

                    self.logs_to_push = [(n[0], "", n[1], n[2], False) for n in notes_to_move]

                self.conn.commit()
            except Exception as e:
                print(f"Del folder err: {e}")
            finally:
                cur.close()

        # 锁释放后再推送日志，防止网络卡顿影响数据库锁
        self.ch_manager.push_folder_log(fid, fname, True, now)
        if hasattr(self, 'logs_to_push'):
            for item in self.logs_to_push:
                self.ch_manager.push_note_log(item[0], item[1], item[2], item[3], item[4], now)
            del self.logs_to_push

        self._notify_observers()

    def upsert_folder_from_cloud(self, uuid, name, is_deleted, updated_at):
        with self.lock:
            self.cursor.execute('SELECT updated_at FROM folders WHERE uuid = ?', (uuid,))
            row = self.cursor.fetchone()
            should_update = False
            if not row:
                should_update = True
            elif datetime.fromisoformat(updated_at) > datetime.fromisoformat(row[0]):
                should_update = True

            if should_update:
                self.cursor.execute('REPLACE INTO folders (uuid, name, is_deleted, updated_at) VALUES (?, ?, ?, ?)',
                                    (uuid, name, is_deleted, updated_at))
                self.conn.commit()

    def get_notes(self, folder_uuid=None, keyword=None):
        sql = 'SELECT uuid, title, content, updated_at FROM notes WHERE is_deleted = 0'
        params = []
        if folder_uuid:
            sql += ' AND folder_uuid = ?'
            params.append(folder_uuid)
        if keyword:
            sql += ' AND (title LIKE ? OR content LIKE ?)'
            params.append(f"%{keyword}%")
            params.append(f"%{keyword}%")
        sql += ' ORDER BY updated_at DESC'

        with self.lock:
            self.cursor.execute(sql, tuple(params))
            return self.cursor.fetchall()

    def get_note_detail(self, note_uuid):
        with self.lock:
            self.cursor.execute('SELECT uuid, folder_uuid, title, content, updated_at FROM notes WHERE uuid = ?',
                                (note_uuid,))
            return self.cursor.fetchone()

    def create_note(self, folder_uuid, title, content, source_draft_id=None):
        nid = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self.lock:
            self.cursor.execute('''INSERT INTO notes (uuid, folder_uuid, title, content, is_deleted, updated_at, source_draft_id)
                VALUES (?, ?, ?, ?, 0, ?, ?)''', (nid, folder_uuid, title, content, now, source_draft_id))
            self.conn.commit()
        self._notify_observers()
        self.ch_manager.push_note_log(nid, folder_uuid, title, content, False, now)
        return nid

    def update_note(self, nid, title, content, folder_uuid=None):
        now = datetime.now().isoformat()
        with self.lock:
            if folder_uuid is None:
                self.cursor.execute('SELECT folder_uuid FROM notes WHERE uuid = ?', (nid,))
                row = self.cursor.fetchone()
                folder_uuid = row[0] if row else ""

            self.cursor.execute(
                'UPDATE notes SET title = ?, content = ?, folder_uuid = ?, updated_at = ? WHERE uuid = ?',
                (title, content, folder_uuid, now, nid))
            self.conn.commit()
        self._notify_observers()
        self.ch_manager.push_note_log(nid, folder_uuid, title, content, False, now)

    def delete_note(self, nid):
        now = datetime.now().isoformat()
        row = None
        with self.lock:
            self.cursor.execute('UPDATE notes SET is_deleted = 1, updated_at = ? WHERE uuid = ?', (now, nid))
            self.conn.commit()
            self.cursor.execute('SELECT folder_uuid, title, content FROM notes WHERE uuid = ?', (nid,))
            row = self.cursor.fetchone()

        self._notify_observers()
        if row:
            self.ch_manager.push_note_log(nid, row[0], row[1], row[2], True, now)

    def get_deleted_notes(self):
        with self.lock:
            self.cursor.execute(
                'SELECT uuid, title, content, updated_at FROM notes WHERE is_deleted = 1 ORDER BY updated_at DESC')
            return self.cursor.fetchall()

    def restore_note(self, nid):
        now = datetime.now().isoformat()
        nrow = None
        target_folder = ""

        with self.lock:
            # 检查原文件夹
            self.cursor.execute('SELECT folder_uuid FROM notes WHERE uuid = ?', (nid,))
            row = self.cursor.fetchone()
            if row and row[0]:
                fid = row[0]
                self.cursor.execute('SELECT is_deleted FROM folders WHERE uuid = ?', (fid,))
                frow = self.cursor.fetchone()
                if frow and frow[0] == 0:
                    target_folder = fid

            # 还原
            self.cursor.execute('UPDATE notes SET is_deleted = 0, folder_uuid = ?, updated_at = ? WHERE uuid = ?',
                                (target_folder, now, nid))
            self.conn.commit()

            self.cursor.execute('SELECT title, content FROM notes WHERE uuid = ?', (nid,))
            nrow = self.cursor.fetchone()

        self._notify_observers()
        if nrow:
            self.ch_manager.push_note_log(nid, target_folder, nrow[0], nrow[1], False, now)

    def hard_delete_note(self, nid):
        with self.lock:
            self.cursor.execute('DELETE FROM notes WHERE uuid = ?', (nid,))
            self.conn.commit()
        self._notify_observers()

    def upsert_note_from_cloud(self, uuid, folder_uuid, title, content, is_deleted, updated_at):
        with self.lock:
            self.cursor.execute('SELECT updated_at FROM notes WHERE uuid = ?', (uuid,))
            row = self.cursor.fetchone()
            should_update = False
            if not row:
                should_update = True
            elif datetime.fromisoformat(updated_at) > datetime.fromisoformat(row[0]):
                should_update = True

            if should_update:
                self.cursor.execute('''REPLACE INTO notes (uuid, folder_uuid, title, content, is_deleted, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)''', (uuid, folder_uuid, title, content, is_deleted, updated_at))
                self.conn.commit()

    def close(self):
        if self.debounce_timer: self.debounce_timer.cancel()
        self.conn.close()