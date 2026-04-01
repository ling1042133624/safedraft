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

            # 便签系统表
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS stickynotes (
                    uuid TEXT PRIMARY KEY,
                    title TEXT DEFAULT '便签',
                    content TEXT,
                    color TEXT DEFAULT '#fff9c4',
                    is_topmost INTEGER DEFAULT 0,
                    position_x INTEGER,
                    position_y INTEGER,
                    width INTEGER DEFAULT 250,
                    height INTEGER DEFAULT 200,
                    is_deleted INTEGER DEFAULT 0,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
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

    # --- Smart Merge Sync ---
    def merge_database(self, other_db_path):
        """
        将另一个数据库的内容合并到当前数据库
        - folders: 按 uuid 合并，保留 updated_at 最新
        - notes: 按 uuid 合并，保留 updated_at 最新，处理软删除
        - drafts: 按内容去重，保留 last_updated_at 最新
        - triggers_v2: 按 (rule_type, value) 去重
        """
        if not os.path.exists(other_db_path):
            return

        # 连接临时数据库
        other_conn = sqlite3.connect(other_db_path, check_same_thread=False)
        other_cur = other_conn.cursor()

        with self.lock:
            try:
                # 1. 合并 folders (按 uuid)
                other_cur.execute('SELECT uuid, name, is_deleted, updated_at FROM folders')
                for row in other_cur.fetchall():
                    uuid_val, name, is_deleted, updated_at = row
                    # 检查本地是否存在
                    self.cursor.execute('SELECT updated_at, is_deleted FROM folders WHERE uuid = ?', (uuid_val,))
                    local_row = self.cursor.fetchone()
                    if local_row:
                        # 比较 updated_at，保留较新的
                        local_updated = local_row[0] or ""
                        local_is_deleted = local_row[1]
                        if updated_at > local_updated:
                            # 远程更新，覆盖本地
                            self.cursor.execute(
                                'UPDATE folders SET name = ?, is_deleted = ?, updated_at = ? WHERE uuid = ?',
                                (name, is_deleted, updated_at, uuid_val))
                    else:
                        # 本地不存在，直接插入
                        self.cursor.execute(
                            'INSERT OR IGNORE INTO folders (uuid, name, is_deleted, updated_at) VALUES (?, ?, ?, ?)',
                            (uuid_val, name, is_deleted, updated_at))

                # 2. 合并 notes (按 uuid)
                other_cur.execute('SELECT uuid, folder_uuid, title, content, is_deleted, updated_at, source_draft_id FROM notes')
                for row in other_cur.fetchall():
                    uuid_val, folder_uuid, title, content, is_deleted, updated_at, source_draft_id = row
                    self.cursor.execute('SELECT updated_at, is_deleted FROM notes WHERE uuid = ?', (uuid_val,))
                    local_row = self.cursor.fetchone()
                    if local_row:
                        local_updated = local_row[0] or ""
                        if updated_at > local_updated:
                            self.cursor.execute('''UPDATE notes SET folder_uuid = ?, title = ?, content = ?,
                                                   is_deleted = ?, updated_at = ?, source_draft_id = ? WHERE uuid = ?''',
                                                (folder_uuid, title, content, is_deleted, updated_at, source_draft_id, uuid_val))
                    else:
                        self.cursor.execute('''INSERT OR IGNORE INTO notes (uuid, folder_uuid, title, content, is_deleted, updated_at, source_draft_id)
                                               VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                            (uuid_val, folder_uuid, title, content, is_deleted, updated_at, source_draft_id))

                # 3. 合并 drafts (按内容去重，保留 last_updated_at 最新)
                other_cur.execute('SELECT content, created_at, last_updated_at FROM drafts')
                for row in other_cur.fetchall():
                    content, created_at, last_updated_at = row
                    if not content or not content.strip():
                        continue
                    # 检查是否存在相同内容
                    self.cursor.execute('SELECT id, last_updated_at FROM drafts WHERE content = ?', (content,))
                    local_row = self.cursor.fetchone()
                    if local_row:
                        local_id, local_updated = local_row
                        if last_updated_at > (local_updated or ""):
                            # 远程更新，更新本地时间戳
                            self.cursor.execute('UPDATE drafts SET last_updated_at = ? WHERE id = ?',
                                                (last_updated_at, local_id))
                    else:
                        # 本地不存在该内容，插入
                        self.cursor.execute('INSERT INTO drafts (content, created_at, last_updated_at) VALUES (?, ?, ?)',
                                            (content, created_at, last_updated_at))

                # 4. 合并 triggers_v2 (按 rule_type + value 去重)
                other_cur.execute('SELECT rule_type, value, enabled FROM triggers_v2')
                for row in other_cur.fetchall():
                    rule_type, value, enabled = row
                    self.cursor.execute('INSERT OR IGNORE INTO triggers_v2 (rule_type, value, enabled) VALUES (?, ?, ?)',
                                        (rule_type, value, enabled))

                # 5. 合并 stickynotes (按 uuid 合并，保留 updated_at 最新；再按 content 去重)
                other_cur.execute('''SELECT uuid, title, content, color, is_topmost, position_x, position_y,
                                    width, height, is_deleted, created_at, updated_at FROM stickynotes''')
                for row in other_cur.fetchall():
                    (uuid_val, title, content, color, is_topmost, pos_x, pos_y, width, height,
                     is_deleted, created_at, updated_at) = row
                    # 检查本地是否存在相同 uuid
                    self.cursor.execute('SELECT updated_at, is_deleted FROM stickynotes WHERE uuid = ?', (uuid_val,))
                    local_row = self.cursor.fetchone()
                    if local_row:
                        local_updated = local_row[0] or ""
                        if updated_at > local_updated:
                            # 远程更新较新，覆盖本地
                            self.cursor.execute('''UPDATE stickynotes SET title = ?, content = ?, color = ?,
                                                  is_topmost = ?, position_x = ?, position_y = ?,
                                                  width = ?, height = ?, is_deleted = ?, updated_at = ?
                                                  WHERE uuid = ?''',
                                                (title, content, color, is_topmost, pos_x, pos_y,
                                                 width, height, is_deleted, updated_at, uuid_val))
                    else:
                        # 本地不存在该 uuid，检查是否有相同 content 的便签
                        if content:
                            self.cursor.execute('SELECT uuid, updated_at FROM stickynotes WHERE content = ?', (content,))
                            dup_row = self.cursor.fetchone()
                            if dup_row:
                                # 存在相同 content，保留 updated_at 最新的
                                dup_uuid, dup_updated = dup_row
                                if updated_at > (dup_updated or ""):
                                    # 远程较新，删除本地重复的，插入远程的
                                    self.cursor.execute('DELETE FROM stickynotes WHERE uuid = ?', (dup_uuid,))
                                    self.cursor.execute('''INSERT INTO stickynotes (uuid, title, content, color, is_topmost,
                                                          position_x, position_y, width, height, is_deleted, created_at, updated_at)
                                                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                                        (uuid_val, title, content, color, is_topmost, pos_x, pos_y,
                                                         width, height, is_deleted, created_at, updated_at))
                                # 否则什么都不做，保留本地的
                            else:
                                # 没有重复，插入
                                self.cursor.execute('''INSERT INTO stickynotes (uuid, title, content, color, is_topmost,
                                                      position_x, position_y, width, height, is_deleted, created_at, updated_at)
                                                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                                    (uuid_val, title, content, color, is_topmost, pos_x, pos_y,
                                                     width, height, is_deleted, created_at, updated_at))

                self.conn.commit()

            finally:
                other_conn.close()

        # 最终去重
        self.deduplicate_drafts()
        self._notify_observers()

    def sync_upload_merge(self, server_ip, remote_path):
        """
        智能上传：先下载服务器数据，合并后再上传
        1. 下载服务器数据库到临时文件
        2. 将服务器数据合并到本地
        3. 推送合并后的本地数据库到服务器
        """
        if not server_ip or not remote_path:
            raise ValueError("配置不完整")

        tmp_path = self.db_path + ".remote_tmp"

        ssh = self._get_ssh_client(server_ip)
        sftp = ssh.open_sftp()

        try:
            remote_file = f"{remote_path.rstrip('/')}/safedraft.db"

            # 1. 尝试下载服务器数据库
            try:
                sftp.get(remote_file, tmp_path)
                server_has_data = True
            except FileNotFoundError:
                # 服务器上没有数据，跳过合并
                server_has_data = False
            except Exception as e:
                # 其他错误（如文件不存在但不是 FileNotFoundError）
                server_has_data = os.path.exists(tmp_path)

            # 2. 如果服务器有数据，合并到本地
            if server_has_data and os.path.exists(tmp_path):
                self.merge_database(tmp_path)
                os.remove(tmp_path)

            # 3. 上传合并后的本地数据库
            with self.lock:
                self.conn.commit()
            sftp.put(self.db_path, remote_file)

        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass
            sftp.close()
            ssh.close()

    def sync_download_merge(self, server_ip, remote_path):
        """
        智能下载：下载服务器数据，与本地合并
        1. 下载服务器数据库到临时文件
        2. 将服务器数据合并到本地
        3. 通知观察者刷新 UI
        """
        if not server_ip or not remote_path:
            raise ValueError("配置不完整")

        tmp_path = self.db_path + ".remote_tmp"

        ssh = self._get_ssh_client(server_ip)
        sftp = ssh.open_sftp()

        try:
            remote_file = f"{remote_path.rstrip('/')}/safedraft.db"
            sftp.get(remote_file, tmp_path)

            # 合并服务器数据到本地
            if os.path.exists(tmp_path):
                self.merge_database(tmp_path)
                os.remove(tmp_path)

        except FileNotFoundError:
            raise Exception("服务器上暂无同步数据")
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass
            sftp.close()
            ssh.close()

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
        """按内容去重，保留 last_updated_at 最新的记录"""
        with self.lock:
            # 按 content 分组，保留每组中 last_updated_at 最大的记录
            self.cursor.execute('''
                DELETE FROM drafts
                WHERE id NOT IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (PARTITION BY content ORDER BY last_updated_at DESC) as rn
                        FROM drafts
                    ) WHERE rn = 1
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

    # ==========================
    # 📝 Sticky Notes API
    # ==========================
    def create_sticky(self, title="便签", color="#fff9c4"):
        sid = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self.lock:
            self.cursor.execute('''INSERT INTO stickynotes
                (uuid, title, content, color, is_topmost, position_x, position_y, width, height, is_deleted, created_at, updated_at)
                VALUES (?, ?, '', ?, 0, NULL, NULL, 250, 200, 0, ?, ?)''',
                (sid, title, color, now, now))
            self.conn.commit()
        self._notify_observers()
        return sid

    def get_all_stickies(self):
        with self.lock:
            self.cursor.execute('''SELECT uuid, title, content, color, is_topmost, position_x, position_y, width, height, created_at, updated_at
                FROM stickynotes WHERE is_deleted = 0 ORDER BY updated_at DESC''')
            return self.cursor.fetchall()

    def get_sticky(self, uuid_val):
        with self.lock:
            self.cursor.execute('''SELECT uuid, title, content, color, is_topmost, position_x, position_y, width, height, created_at, updated_at
                FROM stickynotes WHERE uuid = ? AND is_deleted = 0''', (uuid_val,))
            return self.cursor.fetchone()

    def update_sticky(self, uuid_val, title=None, content=None, color=None, is_topmost=None,
                      position_x=None, position_y=None, width=None, height=None):
        now = datetime.now().isoformat()
        with self.lock:
            updates = []
            params = []
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if content is not None:
                updates.append("content = ?")
                params.append(content)
            if color is not None:
                updates.append("color = ?")
                params.append(color)
            if is_topmost is not None:
                updates.append("is_topmost = ?")
                params.append(1 if is_topmost else 0)
            if position_x is not None:
                updates.append("position_x = ?")
                params.append(position_x)
            if position_y is not None:
                updates.append("position_y = ?")
                params.append(position_y)
            if width is not None:
                updates.append("width = ?")
                params.append(width)
            if height is not None:
                updates.append("height = ?")
                params.append(height)

            if updates:
                updates.append("updated_at = ?")
                params.append(now)
                params.append(uuid_val)
                sql = f"UPDATE stickynotes SET {', '.join(updates)} WHERE uuid = ?"
                self.cursor.execute(sql, tuple(params))
                self.conn.commit()
        self._notify_observers()

    def delete_sticky(self, uuid_val):
        now = datetime.now().isoformat()
        with self.lock:
            self.cursor.execute('UPDATE stickynotes SET is_deleted = 1, updated_at = ? WHERE uuid = ?',
                                (now, uuid_val))
            self.conn.commit()
        self._notify_observers()

    def close(self):
        if self.conn:
            self.conn.close()