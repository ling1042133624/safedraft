"""
AutoSyncManager - 定时检查并自动同步 SafeDraft 数据库
"""

import os
import threading
import time
import json


class AutoSyncManager:
    def __init__(self, db, on_sync_complete=None):
        self.db = db
        self.base_path = db.base_path
        self.running = False
        self._thread = None
        self._on_sync_complete = on_sync_complete  # 成功回调(success_msg)

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    # --- 配置读写 ---

    def _load_config(self):
        """读取 sync_config.json，返回字典，文件不存在则返回默认值"""
        config_path = os.path.join(self.base_path, "sync_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "auto_sync_enabled": False,
            "sync_interval_minutes": 10,
            "active_time_start": "09:00",
            "active_time_end": "22:00"
        }

    # --- 时间段判断 ---

    def _is_within_active_time(self, config):
        """判断当前时间是否在活跃时间段内，支持跨午夜（如 22:00-06:00）"""
        start_str = config.get("active_time_start", "")
        end_str = config.get("active_time_end", "")
        if not start_str or not end_str:
            return True  # 未设置时间则全天候

        try:
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
        except (ValueError, IndexError):
            return True  # 格式错误时默认放行

        now = time.localtime()
        now_minutes = now.tm_hour * 60 + now.tm_min
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m

        if start_minutes <= end_minutes:
            # 同一天，如 09:00-22:00
            return start_minutes <= now_minutes <= end_minutes
        else:
            # 跨午夜，如 22:00-06:00
            return now_minutes >= start_minutes or now_minutes <= end_minutes

    # --- 远端 MD5 获取（通过 readdir） ---

    def _get_remote_md5(self, server_ip, remote_path):
        """SSH 连接远端目录，查找 safedraft_*.md5 文件名提取 hash，无则返回空字符串"""
        try:
            ssh = self.db._get_ssh_client(server_ip)
            sftp = ssh.open_sftp()
            try:
                base = remote_path.rstrip('/')
                for fname in sftp.listdir(base):
                    if fname.startswith("safedraft_") and fname.endswith(".md5"):
                        ssh.close()
                        return fname[len("safedraft_"):-len(".md5")]
            finally:
                sftp.close()
                ssh.close()
        except:
            pass
        return ""

    # --- 核心同步检查 ---

    def _check_and_sync(self):
        """对比本地与远端 MD5，不一致则执行上传合并"""
        try:
            # 1. 获取配置
            config = self._load_config()
            if not config.get("auto_sync_enabled", False):
                return

            # 2. 检查 ssh_enabled
            if self.db.get_setting("ssh_enabled", "0") != "1":
                return

            server_ip = self.db.get_setting("ssh_ip", "")
            remote_path = self.db.get_setting("ssh_path", "")
            if not server_ip or not remote_path:
                return

            # 3. 计算当前本地 DB 的 MD5（实时计算）
            current_md5 = self.db.calculate_db_md5()

            # 4. 获取本地状态文件中记录的 hash（上次成功同步后的值）
            local_recorded_md5 = self.db.get_local_md5()

            # 5. 从远端目录 readdir 取 hash
            remote_md5 = self._get_remote_md5(server_ip, remote_path)

            # 6. 判断是否需要同步：
            #    只有本地有未同步的更新时才上传（current_md5 != local_recorded_md5）
            if current_md5 == local_recorded_md5:
                # 本地没有未同步的更新，远端有新数据时由 sync_upload_merge 处理
                return

            # 远端没有数据或远端数据与本地相同，无需上传
            if not remote_md5 or remote_md5 == current_md5:
                return

            # 7. 需要上传合并
            self.db.sync_upload_merge(server_ip, remote_path)
            # 同步成功后触发回调
            if self._on_sync_complete:
                self._on_sync_complete("自动同步完成")

        except Exception:
            # 后台任务，异常静默
            pass

    # --- 主循环 ---

    def _loop(self):
        while self.running:
            config = self._load_config()

            # 检查自动同步开关
            if not config.get("auto_sync_enabled", False):
                time.sleep(60)
                continue

            # 检查 ssh_enabled
            if self.db.get_setting("ssh_enabled", "0") != "1":
                time.sleep(60)
                continue

            # 检查时间范围
            if not self._is_within_active_time(config):
                time.sleep(60)
                continue

            # 执行检查和同步
            self._check_and_sync()

            # 按配置的间隔休眠
            interval = config.get("sync_interval_minutes", 10)
            time.sleep(interval * 60)
