import sqlite3
from datetime import datetime, timedelta

DEFAULT_TRIGGERS = [
    ("title", "ChatGPT", 1),
    ("title", "Claude", 1),
    ("title", "DeepSeek", 1),
    ("process", "winword.exe", 1),
    ("process", "wps.exe", 1),
    ("process", "notepad.exe", 1),
    ("process", "feishu.exe", 1),
]


class StorageManager:
    def __init__(self, db_name="safedraft.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._init_db()
        self.current_session_id = None

    def _init_db(self):
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

        self.cursor.execute('SELECT count(*) FROM triggers_v2')
        if self.cursor.fetchone()[0] == 0:
            self.cursor.executemany('INSERT OR IGNORE INTO triggers_v2 (rule_type, value, enabled) VALUES (?, ?, ?)',
                                    DEFAULT_TRIGGERS)

        self.conn.commit()

    def save_content(self, content):
        if not content.strip(): return
        now = datetime.now()
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
            if row and (now - datetime.fromisoformat(row[0])) > timedelta(minutes=10):
                should_create_new = True

        if should_create_new:
            self.cursor.execute('INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                                (content, now.isoformat(), now.isoformat()))
            self.current_session_id = self.cursor.lastrowid
        else:
            self.cursor.execute('UPDATE drafts SET content = ?, last_updated_at = ? WHERE id = ?',
                                (content, now.isoformat(), self.current_session_id))
        self.conn.commit()

    def save_content_forced(self, content):
        if not content.strip(): return
        now = datetime.now()
        self.cursor.execute('INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                            (content, now.isoformat(), now.isoformat()))
        self.conn.commit()

    def get_history(self):
        self.cursor.execute('SELECT id, content, created_at, last_updated_at FROM drafts ORDER BY last_updated_at DESC')
        rows = self.cursor.fetchall()
        return rows

    # --- 新增：删除功能 ---
    def delete_draft(self, draft_id):
        self.cursor.execute('DELETE FROM drafts WHERE id = ?', (draft_id,))
        self.conn.commit()

    # --- 触发器管理 ---
    def get_all_triggers(self):
        self.cursor.execute('SELECT id, rule_type, value, enabled FROM triggers_v2 ORDER BY rule_type, value')
        return self.cursor.fetchall()

    def get_enabled_rules(self):
        self.cursor.execute('SELECT rule_type, value FROM triggers_v2 WHERE enabled = 1')
        data = self.cursor.fetchall()
        rules = {'title': [], 'process': []}
        for r_type, val in data:
            if r_type in rules:
                rules[r_type].append(val.lower())
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
        self.conn.close()