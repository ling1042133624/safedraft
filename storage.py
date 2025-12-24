import sqlite3
import os
import sys
import threading
import uuid
import time
from datetime import datetime, timedelta

# --- 新增：尝试导入 clickhouse_driver，防止未安装报错 ---
try:
    from clickhouse_driver import Client as CHClient
except ImportError:
    CHClient = None

# 默认触发器配置 (保持不变)
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


# --- 新增：ClickHouse 管理器类 ---
# ... (保留头部的引用)

class ClickHouseManager:
    def __init__(self, db_manager):
        self.local_db = db_manager
        self.client = None
        self.machine_id = str(uuid.uuid1())

    def get_config(self):
        return {
            'host': self.local_db.get_setting("ch_host", ""),
            'port': self.local_db.get_setting("ch_port", "9000"),
            'user': self.local_db.get_setting("ch_user", "default"),
            'password': self.local_db.get_setting("ch_password", ""),
            'database': self.local_db.get_setting("ch_database", "default"),
            'enabled': self.local_db.get_setting("ch_enabled", "0") == "1"
        }

    def connect(self):
        """建立连接（不吞异常，供外部捕获）"""
        if not CHClient:
            raise ImportError("未安装 clickhouse-driver 库")

        cfg = self.get_config()
        if not cfg['host']:
            raise ValueError("Host 地址为空")

        port = int(cfg['port']) if cfg['port'].isdigit() else 9000

        # --- 核心修复：智能判断 SSL ---
        # 9440 是 ClickHouse 默认的安全原生端口，必须开启 secure=True
        use_secure = (port == 9440)
        # ---------------------------

        # 每次都实例化一个新的 Client，确保配置即时生效且无状态残留
        self.client = CHClient(
            host=cfg['host'],
            port=port,
            user=cfg['user'],
            password=cfg['password'],
            database=cfg['database'],
            secure=use_secure,  # <--- 关键参数
            connect_timeout=10,  # <--- 延长超时
            send_receive_timeout=10
        )
        return self.client

    def init_table(self):
        """确保云端表结构存在"""
        # 这里不捕获异常，让异常冒泡给 test_connection
        client = self.connect()

        # 使用 ReplacingMergeTree 自动去重（基于创建时间和内容）
        sql = """
        CREATE TABLE IF NOT EXISTS drafts (
            uuid String,
            content String,
            created_at DateTime64,
            last_updated_at DateTime64,
            machine_id String
        ) ENGINE = ReplacingMergeTree()
        ORDER BY (created_at, uuid)
        """
        client.execute(sql)
        return True

    def test_connection(self):
        """测试连接并初始化表（捕获异常并返回具体的错误信息）"""
        try:
            if self.init_table():
                return True, "连接成功！表结构已验证 ✅"
            return False, "连接失败：未知原因"
        except ImportError:
            return False, "缺少依赖库：请运行 pip install clickhouse-driver"
        except Exception as e:
            # --- 核心修复：返回具体错误字符串 ---
            error_msg = str(e)
            if "Connection refused" in error_msg:
                return False, f"连接被拒绝 (Connection Refused)。\n请检查：\n1. 端口是否正确？(原生端口通常是 9000 或 9440，不是 8123)\n2. 防火墙设置。\n\n详细: {error_msg}"
            return False, f"连接发生错误:\n{error_msg}"

    def push_log(self, content, created_at_iso, updated_at_iso):
        """异步推送一条记录（Append Only）"""
        if not CHClient: return
        cfg = self.get_config()
        if not cfg['enabled']: return

        def _do_push():
            try:
                client = self.connect()  # 这里可能会抛异常，需要捕获
                record_uuid = str(uuid.uuid4())
                dt_created = datetime.fromisoformat(created_at_iso)
                dt_updated = datetime.fromisoformat(updated_at_iso)

                client.execute(
                    'INSERT INTO drafts (uuid, content, created_at, last_updated_at, machine_id) VALUES',
                    [(record_uuid, content, dt_created, dt_updated, self.machine_id)]
                )
                print(f"[ClickHouse] Pushed success.")
            except Exception as e:
                print(f"[ClickHouse] Push Failed: {e}")

        threading.Thread(target=_do_push, daemon=True).start()

    def pull_and_merge(self):
        """拉取云端所有数据并合并到本地"""
        # 不捕获异常，直接抛出给 UI 层显示
        client = self.connect()

        rows = client.execute(
            "SELECT content, created_at, last_updated_at FROM drafts ORDER BY last_updated_at DESC LIMIT 1000")

        count_new = 0
        for content, dt_created, dt_updated in rows:
            iso_created = dt_created.isoformat()
            iso_updated = dt_updated.isoformat()

            self.local_db.cursor.execute(
                'SELECT id FROM drafts WHERE created_at = ? AND content = ?',
                (iso_created, content)
            )
            if not self.local_db.cursor.fetchone():
                self.local_db.cursor.execute(
                    'INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                    (content, iso_created, iso_updated)
                )
                count_new += 1

        self.local_db.conn.commit()
        return count_new

    # 在 ClickHouseManager 类内部添加此方法
    def push_all_history(self):
        """将本地所有 SQLite 历史记录批量推送到 ClickHouse (用于迁移)"""
        client = self.connect()
        if not client: raise Exception("无法连接到 ClickHouse")

        # 1. 从本地 SQLite 读取所有数据
        self.local_db.cursor.execute('SELECT content, created_at, last_updated_at FROM drafts')
        rows = self.local_db.cursor.fetchall()

        if not rows:
            return 0

        # 2. 构造批量数据
        data_to_insert = []
        for content, c_at, u_at in rows:
            try:
                # 转换时间格式字符串 -> datetime 对象
                dt_c = datetime.fromisoformat(c_at)
                dt_u = datetime.fromisoformat(u_at)

                # 为每条历史记录生成一个新的 UUID
                # 注意：如果你多次点击推送，ClickHouse 会产生重复数据
                # (依靠 ReplacingMergeTree 后台去重，或者这里可以做更复杂的排重检查)
                record_uuid = str(uuid.uuid4())

                data_to_insert.append({
                    'uuid': record_uuid,
                    'content': content,
                    'created_at': dt_c,
                    'last_updated_at': dt_u,
                    'machine_id': self.machine_id
                })
            except Exception as e:
                print(f"Skipping bad record: {e}")
                continue

        # 3. 执行批量插入 (Batch Insert)
        if data_to_insert:
            client.execute(
                'INSERT INTO drafts (uuid, content, created_at, last_updated_at, machine_id) VALUES',
                data_to_insert
            )

        return len(data_to_insert)

class StorageManager:
    def __init__(self, db_name="safedraft.db"):
        self.base_path = self.get_real_executable_path()
        self.db_path = os.path.join(self.base_path, db_name)

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._init_db()
        self.current_session_id = None
        self._observers = []

        # --- 新增：ClickHouse 管理器实例 ---
        self.ch_manager = ClickHouseManager(self)

        # --- 新增：防抖定时器 ---
        self.debounce_timer = None
        self.current_draft_cache = None  # 暂存当前草稿信息

    def get_real_executable_path(self):
        if getattr(sys, 'frozen', False) or "__compiled__" in globals():
            candidate = os.path.abspath(sys.argv[0])
            return os.path.dirname(candidate)
        else:
            return os.path.dirname(os.path.abspath(__file__))

    def _init_db(self):
        # (保持原有的建表逻辑不变)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT,
                created_at TIMESTAMP,
                last_updated_at TIMESTAMP
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS triggers_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_type TEXT, 
                value TEXT,
                enabled INTEGER DEFAULT 1,
                UNIQUE(rule_type, value)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        self.cursor.execute('SELECT count(*) FROM triggers_v2')
        count = self.cursor.fetchone()[0]

        if count == 0:
            self.cursor.executemany('''
                INSERT OR IGNORE INTO triggers_v2 (rule_type, value, enabled) 
                VALUES (?, ?, ?)
            ''', DEFAULT_TRIGGERS)

        self.cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', ("theme", "Deep"))
        self.conn.commit()

    # --- 信号槽 (保持不变) ---
    def add_observer(self, callback):
        if callback not in self._observers: self._observers.append(callback)

    def remove_observer(self, callback):
        if callback in self._observers: self._observers.remove(callback)

    def _notify_observers(self):
        for callback in self._observers:
            try:
                callback()
            except:
                pass

    # --- 设置 (保持不变) ---
    def get_setting(self, key, default=None):
        self.cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = self.cursor.fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        self.cursor.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        self.conn.commit()

    # --- 草稿保存 (修改：增加防抖同步) ---
    def save_content(self, content):
        if not content.strip(): return
        now = datetime.now()

        # 1. 本地逻辑 (保持不变)
        should_create_new = False
        if self.current_session_id is None:
            self.cursor.execute('SELECT id, last_updated_at FROM drafts ORDER BY id DESC LIMIT 1')
            row = self.cursor.fetchone()
            if row:
                last_time = datetime.fromisoformat(row[1])
                if (now - last_time) > timedelta(minutes=10):
                    should_create_new = True
                else:
                    self.current_session_id = row[0]
            else:
                should_create_new = True

        if not should_create_new:
            self.cursor.execute('SELECT last_updated_at FROM drafts WHERE id = ?', (self.current_session_id,))
            row = self.cursor.fetchone()
            if row and (now - datetime.fromisoformat(row[0])) > timedelta(minutes=10): should_create_new = True

        created_at_str = now.isoformat()  # 默认值

        if should_create_new:
            self.cursor.execute('INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                                (content, now.isoformat(), now.isoformat()))
            self.current_session_id = self.cursor.lastrowid
            created_at_str = now.isoformat()
        else:
            # 获取该 session 的创建时间，保持一致性
            self.cursor.execute('SELECT created_at FROM drafts WHERE id = ?', (self.current_session_id,))
            row = self.cursor.fetchone()
            if row: created_at_str = row[0]

            self.cursor.execute('UPDATE drafts SET content = ?, last_updated_at = ? WHERE id = ?',
                                (content, now.isoformat(), self.current_session_id))

        self.conn.commit()
        self._notify_observers()

        # 2. 云端同步 (新增防抖逻辑)
        self._trigger_debounce_sync(content, created_at_str, now.isoformat())

    def _trigger_debounce_sync(self, content, created_at, updated_at):
        """5秒防抖，避免频繁请求 ClickHouse"""
        if self.debounce_timer:
            self.debounce_timer.cancel()

        # 封装参数
        self.current_draft_cache = (content, created_at, updated_at)

        # 开启新定时器
        self.debounce_timer = threading.Timer(5.0, self._perform_sync)
        self.debounce_timer.start()

    def _perform_sync(self):
        """定时器触发的实际同步动作"""
        if self.current_draft_cache:
            content, c_at, u_at = self.current_draft_cache
            self.ch_manager.push_log(content, c_at, u_at)

    def save_content_forced(self, content):
        # (保持不变)
        if not content.strip(): return
        now = datetime.now()
        self.cursor.execute('INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                            (content, now.isoformat(), now.isoformat()))
        self.current_session_id = self.cursor.lastrowid
        self.conn.commit()
        self._notify_observers()
        # 强制保存也触发一次同步
        self.ch_manager.push_log(content, now.isoformat(), now.isoformat())

    def save_snapshot(self, content):
        # (保持不变)
        if not content.strip(): return
        now = datetime.now()
        self.cursor.execute('INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                            (content, now.isoformat(), now.isoformat()))
        self.conn.commit()
        self._notify_observers()
        # 快照也同步
        self.ch_manager.push_log(content, now.isoformat(), now.isoformat())

    def delete_draft(self, draft_id):
        # (保持不变)
        self.cursor.execute('DELETE FROM drafts WHERE id = ?', (draft_id,))
        self.conn.commit()
        self._notify_observers()

    def get_history(self, keyword=None):
        # (保持不变)
        if keyword:
            search_term = f"%{keyword}%"
            self.cursor.execute(
                'SELECT id, content, created_at, last_updated_at FROM drafts WHERE content LIKE ? ORDER BY last_updated_at DESC',
                (search_term,))
        else:
            self.cursor.execute(
                'SELECT id, content, created_at, last_updated_at FROM drafts ORDER BY last_updated_at DESC')
        return self.cursor.fetchall()

    # --- 触发器 (保持不变) ---
    def get_all_triggers(self):
        self.cursor.execute('SELECT id, rule_type, value, enabled FROM triggers_v2 ORDER BY rule_type, value')
        return self.cursor.fetchall()

    def get_enabled_rules(self):
        self.cursor.execute('SELECT rule_type, value FROM triggers_v2 WHERE enabled = 1')
        data = self.cursor.fetchall()
        rules = {'title': [], 'process': []}
        for r_type, val in data:
            if r_type in rules: rules[r_type].append(val.lower())
        return rules

    def add_trigger(self, rule_type, value):
        self.cursor.execute('INSERT OR IGNORE INTO triggers_v2 (rule_type, value, enabled) VALUES (?, ?, 1)',
                            (rule_type, value))
        self.conn.commit()

    def toggle_trigger(self, trigger_id, enabled):
        self.cursor.execute('UPDATE triggers_v2 SET enabled = ? WHERE id = ?', (1 if enabled else 0, trigger_id))
        self.conn.commit()

    def delete_trigger(self, trigger_id):
        self.cursor.execute('DELETE FROM triggers_v2 WHERE id = ?', (trigger_id,))
        self.conn.commit()

    def close(self):
        if self.debounce_timer: self.debounce_timer.cancel()
        self.conn.close()