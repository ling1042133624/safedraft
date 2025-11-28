import tkinter as tk
from tkinter import messagebox
import sys
import os
import threading
import pystray
from PIL import ImageTk
from pynput import keyboard as pk

# 导入自定义模块
from storage import StorageManager
from watcher import WindowWatcher
# 引入 DEFAULT_FONT_SIZE
from utils import THEMES, get_icon_image, DEFAULT_FONT_SIZE
from windows import HistoryWindow, SettingsDialog


class SafeDraftApp:
    def __init__(self, root, existing_db=None, is_main_window=True):
        self.root = root
        self.is_main_window = is_main_window

        self.is_topmost = False
        self.topmost_timer = None
        self.tray_icon = None
        self.hotkey_listener = None

        if existing_db:
            self.db = existing_db
        else:
            self.db = StorageManager()

        # 初始化读取字体大小
        try:
            self.font_size = int(self.db.get_setting("font_size", str(DEFAULT_FONT_SIZE)))
        except:
            self.font_size = DEFAULT_FONT_SIZE

        if self.is_main_window:
            self.watcher = WindowWatcher(self.db, self.on_trigger_detected)
            self.watcher.start()
            self.start_global_hotkey()
        else:
            self.watcher = None

        theme_name = self.db.get_setting("theme", "Deep")
        self.colors = THEMES.get(theme_name, THEMES["Deep"])

        self.setup_window()
        self.setup_ui()
        self.setup_events()
        self.apply_theme()

    def start_global_hotkey(self):
        try:
            self.hotkey_listener = pk.GlobalHotKeys({
                '<ctrl>+`': self.on_global_hotkey
            })
            self.hotkey_listener.start()
        except Exception as e:
            print(f"Hotkey register failed: {e}")

    def setup_window(self):
        title = "SafeDraft" if self.is_main_window else "SafeDraft (New)"
        self.root.title(title)
        self.root.geometry("550x600+100+100")
        try:
            alpha = float(self.db.get_setting("window_alpha", "0.95"))
            self.root.attributes("-alpha", alpha)
        except:
            pass

        try:
            pil_img = get_icon_image()
            self.app_icon = ImageTk.PhotoImage(pil_img)
            self.root.iconphoto(True, self.app_icon)
        except Exception as e:
            print(f"Icon set failed: {e}")

    def setup_ui(self):
        self.toolbar = tk.Frame(self.root, height=40)
        self.toolbar.pack(fill="x", padx=5, pady=5)

        self.btn_new = tk.Button(self.toolbar, text="➕ 新建", command=self.open_new_window, relief="flat", padx=10)
        self.btn_new.pack(side="left", padx=5)

        self.btn_save = tk.Button(self.toolbar, text="💾 保存并清空", command=self.manual_save, relief="flat", padx=10)
        self.btn_save.pack(side="left", padx=5)

        if self.is_main_window:
            self.btn_settings = tk.Button(self.toolbar, text="⚙️ 设置", command=self.open_settings, relief="flat",
                                          padx=10)
            self.btn_settings.pack(side="left", padx=5)
        else:
            self.btn_settings = None

        self.btn_history = tk.Button(self.toolbar, text="🕒 时光机", command=self.open_history, relief="flat", padx=10)
        self.btn_history.pack(side="right", padx=5)

        self.btn_top = tk.Button(self.toolbar, text="📌 临时置顶", command=self.toggle_manual_topmost, relief="flat",
                                 padx=10)
        self.btn_top.pack(side="right", padx=5)

        self.text_frame = tk.Frame(self.root, padx=5, pady=5)
        self.text_frame.pack(fill="both", expand=True)

        # 应用字体大小
        self.text_area = tk.Text(self.text_frame, relief="flat",
                                 font=("Consolas", self.font_size),
                                 undo=True, wrap="word", padx=10, pady=10)
        self.text_area.pack(fill="both", expand=True)

    def open_new_window(self):
        new_root = tk.Toplevel(self.root)
        new_app = SafeDraftApp(new_root, existing_db=self.db, is_main_window=False)
        new_root.app = new_app

    def apply_theme(self):
        c = self.colors
        self.root.configure(bg=c["bg"])
        self.toolbar.configure(bg=c["bg"])
        self.text_frame.configure(bg=c["bg"])

        def config_btn(btn, bg=c["accent"], fg=c["fg"]):
            if btn: btn.configure(bg=bg, fg=fg, activebackground=c["bg"], activeforeground=fg)

        config_btn(self.btn_new)
        config_btn(self.btn_save)
        config_btn(self.btn_settings)
        config_btn(self.btn_history)

        if self.is_topmost:
            top_color = "#4a90e2" if "强制" in self.btn_top.cget("text") else c["btn_top_active"]
            config_btn(self.btn_top, bg=top_color, fg="white")
        else:
            config_btn(self.btn_top)
        self.text_area.configure(bg=c["text_bg"], fg=c["text_fg"], insertbackground=c["insert_bg"])

    def switch_theme(self, theme_name):
        self.colors = THEMES.get(theme_name, THEMES["Deep"])
        self.apply_theme()

    def set_window_alpha(self, value):
        try:
            self.root.attributes("-alpha", float(value))
        except:
            pass

    # --- 新增：实时调整字体 ---
    def set_font_size(self, size):
        try:
            new_size = int(size)
            self.text_area.configure(font=("Consolas", new_size))
            self.font_size = new_size
        except:
            pass

    def setup_events(self):
        self.text_area.bind("<KeyRelease>", self.on_key_release)
        self.text_area.bind("<Control-s>", self.on_ctrl_s)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        if not self.is_main_window:
            self.root.destroy()
            return

        exit_action = self.db.get_setting("exit_action", "ask")
        if exit_action == "tray":
            self.minimize_to_tray()
        elif exit_action == "quit":
            self.quit_app()
        else:
            res = messagebox.askyesnocancel("退出确认",
                                            "是否要保持后台运行？\n\n【是】最小化到系统托盘 (推荐)\n【否】彻底退出程序\n【取消】手滑了")
            if res is True:
                self.db.set_setting("exit_action", "tray"); self.minimize_to_tray()
            elif res is False:
                self.db.set_setting("exit_action", "quit"); self.quit_app()

    def minimize_to_tray(self):
        self.root.withdraw()
        pil_img = get_icon_image()

        def on_tray_quit(icon, item): icon.stop(); self.root.after(0, self.quit_app)

        def on_tray_show(icon, item): icon.stop(); self.root.after(0, self.restore_from_tray)

        menu = (pystray.MenuItem('显示主界面', on_tray_show, default=True), pystray.MenuItem('彻底退出', on_tray_quit))
        self.tray_icon = pystray.Icon("SafeDraft", pil_img, "SafeDraft", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def restore_from_tray(self):
        if self.tray_icon: self.tray_icon.stop(); self.tray_icon = None
        self.root.deiconify();
        self.root.lift();
        self.root.focus_force()

    def quit_app(self):
        if self.tray_icon: self.tray_icon.stop()
        if self.watcher: self.watcher.stop()
        if self.hotkey_listener: self.hotkey_listener.stop()
        self.db.close()
        self.root.destroy()
        os._exit(0)

    def on_key_release(self, event):
        content = self.text_area.get("1.0", "end-1c")
        self.db.save_content(content)

    def on_ctrl_s(self, event):
        content = self.text_area.get("1.0", "end-1c")
        if content.strip():
            self.db.save_snapshot(content)
            self._flash_btn(self.btn_save, "快照已存 ✔", self.colors["btn_save_success"])
        return "break"

    def manual_save(self):
        content = self.text_area.get("1.0", "end-1c")
        if not content.strip(): self._flash_btn(self.btn_save, "空内容!", "#ff5555"); return
        self.db.save_content_forced(content)
        self.text_area.delete("1.0", "end")
        self.db.current_session_id = None
        self._flash_btn(self.btn_save, "已归档 ✔", self.colors["btn_save_success"])

    def _flash_btn(self, btn, text, color):
        orig_text = "💾 保存并清空"
        orig_fg = self.colors["fg"]
        orig_bg = self.colors["accent"]
        btn.config(text=text, fg=color)
        self.root.after(1000, lambda: btn.config(text=orig_text, fg=orig_fg, bg=orig_bg))

    def open_history(self):
        HistoryWindow(self.root, self.db, self.restore_draft_content, self.colors)

    def restore_draft_content(self, content):
        if messagebox.askyesno("恢复确认", "确定要覆盖当前输入框的内容吗？"):
            self.text_area.delete("1.0", "end")
            self.text_area.insert("1.0", content)
            self.text_area.focus_set()

    def open_settings(self):
        if self.watcher:
            SettingsDialog(self.root, self.db, self.watcher, self)

    def on_global_hotkey(self):
        self.root.after(0, self._perform_auto_pop_force)

    def _perform_auto_pop_force(self):
        self.restore_from_tray(); self._start_auto_topmost()

    def on_trigger_detected(self):
        self.root.after(0, self._perform_auto_pop)

    def _perform_auto_pop(self):
        if self.is_topmost and not self.topmost_timer: return
        if self.root.state() == 'withdrawn':
            self.restore_from_tray()
        elif self.root.state() == 'iconic':
            self.root.deiconify()
        if self.root.focus_displayof() is None: self.root.geometry("+100+100")
        self._start_auto_topmost()

    def _start_auto_topmost(self):
        self.is_topmost = True
        self.root.attributes('-topmost', True)
        self.btn_top.config(text="📌 锁定(2m)", bg=self.colors["btn_top_active"], fg="white")
        if self.topmost_timer: self.root.after_cancel(self.topmost_timer)
        self.topmost_timer = self.root.after(120000, self._cancel_topmost)

    def _cancel_topmost(self):
        self.is_topmost = False
        self.topmost_timer = None
        self.root.attributes('-topmost', False)
        self.btn_top.config(text="📌 临时置顶", bg=self.colors["accent"], fg=self.colors["fg"])

    def toggle_manual_topmost(self):
        if self.is_topmost:
            if self.topmost_timer: self.root.after_cancel(self.topmost_timer)
            self._cancel_topmost()
        else:
            self.is_topmost = True
            self.root.attributes('-topmost', True)
            self.btn_top.config(text="📌 已强制锁定", bg="#4a90e2", fg="white")
            if self.topmost_timer: self.root.after_cancel(self.topmost_timer)
            self.topmost_timer = None


if __name__ == "__main__":
    if sys.platform == "win32":
        import ctypes

        myappid = 'SafeDraft.App.Version.1.0'
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except:
            pass

    root = tk.Tk()
    app = SafeDraftApp(root)
    root.mainloop()