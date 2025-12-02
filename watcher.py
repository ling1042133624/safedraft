import time
import threading
import sys
import os
import psutil

# 根据平台导入特定库
if sys.platform == "win32":
    import win32gui
    import win32process
elif sys.platform == "darwin":
    from Cocoa import NSWorkspace


class WindowWatcher:
    def __init__(self, db_manager, callback):
        self.db_manager = db_manager
        self.callback = callback
        self.running = False

        # 记录上一次触发的规则 key
        self.last_triggered_key = None

        # 获取自身进程 ID，用于过滤自己
        self.my_pid = os.getpid()

        self.lock = threading.Lock()
        self.reload_rules()

    def start(self):
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False

    def reload_rules(self):
        with self.lock:
            rules = self.db_manager.get_enabled_rules()
            self.title_keywords = rules['title']
            self.process_names = rules['process']

    def _get_active_window_info_win(self):
        """Windows 获取前台窗口信息"""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd).lower()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)

            # --- 核心修复：如果是自己，返回特殊标记 ---
            if pid == self.my_pid:
                return None, None, True  # is_self = True

            proc_name = psutil.Process(pid).name().lower() if pid > 0 else ""
            return title, proc_name, False
        except:
            return "", "", False

    def _get_active_window_info_mac(self):
        """Mac 获取前台窗口信息"""
        try:
            active_app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if not active_app: return "", "", False

            pid = active_app.processIdentifier()
            if pid == self.my_pid:
                return None, None, True

            proc_name = active_app.localizedName().lower()
            title = proc_name
            return title, proc_name + ".app", False
        except:
            return "", "", False

    def _loop(self):
        while self.running:
            try:
                is_self = False
                if sys.platform == "win32":
                    title, proc_name, is_self = self._get_active_window_info_win()
                elif sys.platform == "darwin":
                    title, proc_name, is_self = self._get_active_window_info_mac()
                else:
                    time.sleep(1)
                    continue

                # -----------------------------------------------------------
                # 核心修复逻辑：
                # 如果当前活动窗口是 SafeDraft 自己（比如用户正在点取消置顶，或在打字），
                # 我们【绝对不要】重置 last_triggered_key。
                # 我们假装什么都没发生，保持“在这个应用之前”的状态。
                # 这样当用户切回原来的应用时，系统会认为他“从未离开过”。
                # -----------------------------------------------------------
                if is_self:
                    time.sleep(1)
                    continue

                current_match_key = None

                with self.lock:
                    # 1. 检查进程名
                    for p_rule in self.process_names:
                        clean_rule = p_rule.replace(".exe", "")
                        if clean_rule in proc_name:
                            current_match_key = f"proc:{clean_rule}"
                            break

                    # 2. 检查标题
                    if not current_match_key:
                        for t_rule in self.title_keywords:
                            if t_rule in title:
                                current_match_key = f"title:{t_rule}"
                                break

                # --- 状态机 ---
                if current_match_key:
                    # 检测到监控目标
                    if current_match_key != self.last_triggered_key:
                        # 是一个新的目标（或者从无关应用切回来的）-> 触发！
                        self.callback()
                        self.last_triggered_key = current_match_key
                    else:
                        # 和上次一样 -> 保持安静，不打扰
                        pass
                else:
                    # 检测到无关应用（比如桌面、网易云）
                    # 只有这时才重置锁
                    self.last_triggered_key = None

            except Exception as e:
                pass

            time.sleep(1)