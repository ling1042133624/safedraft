import time
import threading
import win32gui
import win32process
import psutil


class WindowWatcher:
    def __init__(self, db_manager, callback):
        self.db_manager = db_manager
        self.callback = callback
        self.running = False
        self.last_hwnd = None
        self.lock = threading.Lock()

        # 初始加载规则
        self.reload_rules()

    def start(self):
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False

    def reload_rules(self):
        """从数据库重新加载规则"""
        with self.lock:
            rules = self.db_manager.get_enabled_rules()
            self.title_keywords = rules['title']  # List of strings
            self.process_names = rules['process']  # List of strings (e.g., 'winword.exe')
            # print(f"Watcher rules reloaded: {len(self.title_keywords)} titles, {len(self.process_names)} processes")

    def _get_process_name(self, hwnd):
        """通过窗口句柄获取进程名 (如 winword.exe)"""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid > 0:
                proc = psutil.Process(pid)
                return proc.name().lower()
        except Exception:
            return ""
        return ""

    def _loop(self):
        while self.running:
            try:
                hwnd = win32gui.GetForegroundWindow()
                # 只有当窗口句柄变化时才检测
                if hwnd != self.last_hwnd:
                    self.last_hwnd = hwnd

                    # 1. 获取信息
                    window_title = win32gui.GetWindowText(hwnd).lower()
                    process_name = self._get_process_name(hwnd)

                    matched = False

                    with self.lock:
                        # 2. 优先检测：进程名匹配 (精确且高效)
                        if process_name in self.process_names:
                            matched = True
                            # print(f"Triggered by Process: {process_name}")

                        # 3. 其次检测：标题关键词 (用于浏览器网页)
                        if not matched:
                            for kw in self.title_keywords:
                                if kw in window_title:
                                    matched = True
                                    # print(f"Triggered by Title: {kw}")
                                    break

                    if matched:
                        self.callback()

            except Exception as e:
                # print(f"Watcher error: {e}")
                pass

            time.sleep(1)  # 1秒检测一次，省电