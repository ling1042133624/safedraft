import time
import threading
import sys
import psutil

# 根据平台导入特定库
if sys.platform == "win32":
    import win32gui
    import win32process
elif sys.platform == "darwin":
    from Cocoa import NSWorkspace
    from Quartz import (
        CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
    )


class WindowWatcher:
    def __init__(self, db_manager, callback):
        self.db_manager = db_manager
        self.callback = callback
        self.running = False
        self.last_active_window_name = None
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
            proc_name = psutil.Process(pid).name().lower() if pid > 0 else ""
            return title, proc_name
        except:
            return "", ""

    def _get_active_window_info_mac(self):
        """Mac 获取前台窗口信息"""
        try:
            # 1. 获取前台 App 名称 (Process Name)
            active_app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if not active_app: return "", ""

            proc_name = active_app.localizedName().lower()

            # 2. 获取窗口标题 (需要屏幕录制权限，否则可能获取不到或只能获取应用名)
            # 这里做一个简单的近似，只监控 App 名字，更深度的窗口标题需要 Accessibility API 比较复杂
            # 简单实现：Mac下主要依靠 App 名称监控
            title = proc_name  # 默认标题等于应用名

            # 尝试通过 Quartz 获取所有窗口信息找到前台应用的窗口 (可选，性能开销较大)
            # options = kCGWindowListOptionOnScreenOnly
            # window_list = CGWindowListCopyWindowInfo(options, kCGNullWindowID)
            # for window in window_list:
            #     if window['kCGWindowOwnerPID'] == active_app.processIdentifier():
            #         title = window.get('kCGWindowName', '').lower()
            #         break

            return title, proc_name + ".app"  # 模拟 .exe 格式方便统一处理
        except:
            return "", ""

    def _loop(self):
        while self.running:
            try:
                if sys.platform == "win32":
                    title, proc_name = self._get_active_window_info_win()
                elif sys.platform == "darwin":
                    title, proc_name = self._get_active_window_info_mac()
                else:
                    time.sleep(1)
                    continue

                # 简单的去重逻辑，防止同一窗口重复触发
                current_id = f"{proc_name}|{title}"
                if current_id != self.last_active_window_name:
                    self.last_active_window_name = current_id

                    matched = False
                    with self.lock:
                        # 1. 检查进程名 (Mac下如 "Code.app", "Google Chrome.app")
                        # 这里的对比需要注意，Mac的应用名通常没有 .exe，我们在上面强行加了 .app 或者你可以只匹配名字
                        for p_rule in self.process_names:
                            # 模糊匹配，例如规则是 "word"，实际是 "microsoft word.app"
                            if p_rule.replace(".exe", "") in proc_name:
                                matched = True
                                break

                        # 2. 检查标题
                        if not matched:
                            for t_rule in self.title_keywords:
                                if t_rule in title:
                                    matched = True
                                    break

                    if matched:
                        self.callback()

            except Exception as e:
                print(f"Watcher error: {e}")

            time.sleep(1)