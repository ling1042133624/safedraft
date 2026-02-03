import sqlite3
import os
import sys
import threading
import uuid
import time
import shutil
from datetime import datetime, timedelta
import paramiko

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


class StorageManager:
    def __init__(self, db_name="safedraft.db"):
        self.base_path = self.get_real_executable_path()
        self.db_path = os.path.join(self.base_path, db_name)

        self.lock = threading.Lock()

        # 初始化连接
        self.conn = None
        self.cursor = None
        self.connect_db()
        self._init_db()

        self._observers = []

    def get_real_executable_path(self):
        if getattr(sys, 'frozen', False) or "__compiled__" in globals():
            return os.path.dirname(os.path.abspath(sys.argv[0]))
        else:
            return os.path.dirname(os.path.abspath(__file__))

    def connect_db(self):
        """建立数据库连接"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()

    def reload_db(self):
        """重载数据库连接（通常在覆盖数据库文件后调用）"""
        with self.lock:
            if self.conn:
                try:
                    self.conn.close()
                except:
                    pass
            self.connect_db()
        self._notify_observers()

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

    # --- SSH Sync Features ---
    def _get_ssh_client(self, ip_input):
        """辅助方法：创建SSH客户端并连接"""
        if '@' in ip_input:
            username, hostname = ip_input.split('@', 1)
        else:
            username, hostname = None, ip_input

        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # 尝试连接（超时10秒）
        ssh.connect(hostname, username=username, timeout=10)
        return ssh

    def sync_upload(self, server_ip, remote_path):
        """上传当前数据库到服务器"""
        if not server_ip or not remote_path:
            raise ValueError("配置不完整")

        ssh = self._get_ssh_client(server_ip)
        sftp = ssh.open_sftp()
        try:
            remote_file = f"{remote_path.rstrip('/')}/safedraft.db"
            # 刷新本地缓存
            with self.lock:
                self.conn.commit()

            sftp.put(self.db_path, remote_file)
        finally:
            sftp.close()
            ssh.close()

    def sync_download(self, server_ip, remote_path):
        """从服务器下载数据库并覆盖本地"""
        if not server_ip or not remote_path:
            raise ValueError("配置不完整")

        tmp_path = self.db_path + ".tmp"
        bak_path = self.db_path + ".bak"

        ssh = self._get_ssh_client(server_ip)
        sftp = ssh.open_sftp()

        try:
            remote_file = f"{remote_path.rstrip('/')}/safedraft.db"
            sftp.get(remote_file, tmp_path)

            # 覆盖逻辑
            with self.lock:
                if self.conn: self.conn.close()

                if os.path.exists(self.db_path):
                    shutil.move(self.db_path, bak_path)

                shutil.move(tmp_path, self.db_path)

                try:
                    self.connect_db()
                    # 简单自检
                    self.cursor.execute("SELECT count(*) FROM settings")
                except Exception as e:
                    # 回滚
                    if self.conn: self.conn.close()
                    if os.path.exists(bak_path):
                        shutil.move(bak_path, self.db_path)
                    self.connect_db()
                    raise Exception(f"数据库校验失败，已回滚: {e}")

        except Exception as e:
            if self.conn:
                try:
                    self.conn.cursor()
                except:
                    self.connect_db()
            raise e
        finally:
            if os.path.exists(tmp_path): os.remove(tmp_path)
            sftp.close()
            ssh.close()

        self._notify_observers()

    def add_observer(self, callback):
        if callback not in self._observers: self._observers.append(callback)

    def remove_observer(self, callback):
        if callback in self._observers: self._observers.remove(callback)

    def _notify_observers(self):
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
                self.cursor.execute('INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                                    (content, now.isoformat(), now.isoformat()))
                new_draft_id = self.cursor.lastrowid
            else:
                self.cursor.execute('UPDATE drafts SET content = ?, last_updated_at = ? WHERE id = ?',
                                    (content, now.isoformat(), draft_id))

            self.conn.commit()

        self._notify_observers()
        return new_draft_id

    def save_content_forced(self, content):
        if not content.strip(): return
        now = datetime.now()
        with self.lock:
            self.cursor.execute('INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                                (content, now.isoformat(), now.isoformat()))
            self.conn.commit()
        self._notify_observers()

    def save_snapshot(self, content):
        if not content.strip(): return
        now = datetime.now()
        with self.lock:
            self.cursor.execute('INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                                (content, now.isoformat(), now.isoformat()))
            self.conn.commit()
        self._notify_observers()

    def deduplicate_drafts(self):
        with self.lock:
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

    def delete_draft(self, draft_id):
        with self.lock:
            self.cursor.execute('DELETE FROM drafts WHERE id = ?', (draft_id,))
            self.conn.commit()
        self._notify_observers()

    # --- Triggers CRUD ---
    def get_all_triggers(self):
        with self.lock:
            self.cursor.execute('SELECT id, rule_type, value, enabled FROM triggers_v2 ORDER BY rule_type, value')
            return self.cursor.fetchall()

    def get_enabled_rules(self):
        with self.lock:
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
        return fid

    def rename_folder(self, fid, new_name):
        now = datetime.now().isoformat()
        with self.lock:
            self.cursor.execute('UPDATE folders SET name = ?, updated_at = ? WHERE uuid = ?', (new_name, now, fid))
            self.conn.commit()
        self._notify_observers()

    def delete_folder(self, fid, delete_children=False):
        now = datetime.now().isoformat()
        with self.lock:
            cur = self.conn.cursor()
            try:
                cur.execute('UPDATE folders SET is_deleted = 1, updated_at = ? WHERE uuid = ?', (now, fid))
                if delete_children:
                    cur.execute('UPDATE notes SET is_deleted = 1, updated_at = ? WHERE folder_uuid = ?', (now, fid))
                else:
                    cur.execute('UPDATE notes SET folder_uuid = "", updated_at = ? WHERE folder_uuid = ?', (now, fid))
                self.conn.commit()
            except Exception as e:
                print(f"Del folder err: {e}")
            finally:
                cur.close()
        self._notify_observers()

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

    def delete_note(self, nid):
        now = datetime.now().isoformat()
        with self.lock:
            self.cursor.execute('UPDATE notes SET is_deleted = 1, updated_at = ? WHERE uuid = ?', (now, nid))
            self.conn.commit()
        self._notify_observers()

    def get_deleted_notes(self):
        with self.lock:
            self.cursor.execute(
                'SELECT uuid, title, content, updated_at FROM notes WHERE is_deleted = 1 ORDER BY updated_at DESC')
            return self.cursor.fetchall()

    def restore_note(self, nid):
        now = datetime.now().isoformat()
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

            self.cursor.execute('UPDATE notes SET is_deleted = 0, folder_uuid = ?, updated_at = ? WHERE uuid = ?',
                                (target_folder, now, nid))
            self.conn.commit()
        self._notify_observers()

    def hard_delete_note(self, nid):
        with self.lock:
            self.cursor.execute('DELETE FROM notes WHERE uuid = ?', (nid,))
            self.conn.commit()
        self._notify_observers()

    def close(self):
        if self.conn:
            self.conn.close()