import tkinter as tk
from tkinter import messagebox
import sys
import os
import threading
# import pystray
from PIL import ImageTk
from pynput import keyboard as pk

# 导入自定义模块
from storage import StorageManager
from watcher import WindowWatcher
from utils import THEMES, get_icon_image, DEFAULT_FONT_SIZE
from windows import HistoryWindow, SettingsDialog
# 在原有导入下添加：
from notebook import NotebookWindow

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

    # [请替换 SafeDraftApp 类中的这三个方法]
    def setup_window(self):
        title = "SafeDraft" if self.is_main_window else "SafeDraft (New)"
        self.root.title(title)
        # --- 修改 1: 宽度调整为 620，高度 600 ---
        self.root.geometry("620x600+100+100")
        # -------------------------------------
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

        # --- 修改 2: 紧凑布局 (padx 减小) ---

        # [左侧按钮组]
        self.btn_new = tk.Button(self.toolbar, text="➕ 新建", command=self.open_new_window, relief="flat", padx=5)
        self.btn_new.pack(side="left", padx=2)

        self.btn_save = tk.Button(self.toolbar, text="💾 保存并清空", command=self.manual_save, relief="flat",
                                  padx=5)
        self.btn_save.pack(side="left", padx=2)

        self.btn_sync = tk.Button(self.toolbar, text="☁️ 同步", command=self.manual_sync, relief="flat", padx=5)
        self.btn_sync.pack(side="left", padx=2)

        if self.is_main_window:
            self.btn_settings = tk.Button(self.toolbar, text="⚙️ 设置", command=self.open_settings, relief="flat",
                                          padx=5)
            self.btn_settings.pack(side="left", padx=2)
        else:
            self.btn_settings = None

        # [右侧按钮组] (注意：pack side='right' 是从右向左堆叠的)

        # 1. 最右边：临时置顶
        self.btn_top = tk.Button(self.toolbar, text="📌 临时置顶", command=self.toggle_manual_topmost, relief="flat",
                                 padx=5)
        self.btn_top.pack(side="right", padx=2)

        # 2. 中间：笔记 (在置顶的左边)
        if self.is_main_window:
            self.btn_notebook = tk.Button(self.toolbar, text="📓 笔记", command=self.open_notebook, relief="flat",
                                          padx=5)
            self.btn_notebook.pack(side="right", padx=2)
        else:
            self.btn_notebook = None

        # 3. 左边：时光机 (在笔记的左边)
        self.btn_history = tk.Button(self.toolbar, text="🕒 历史归档", command=self.open_history, relief="flat",
                                     padx=5)
        self.btn_history.pack(side="right", padx=2)
        # -------------------------------------

        self.text_frame = tk.Frame(self.root, padx=5, pady=5)
        self.text_frame.pack(fill="both", expand=True)

        self.text_area = tk.Text(self.text_frame, relief="flat",
                                 font=("Consolas", self.font_size),
                                 undo=True, wrap="word", padx=10, pady=10)
        self.text_area.pack(fill="both", expand=True)

    def apply_theme(self):
        c = self.colors
        self.root.configure(bg=c["bg"])
        self.toolbar.configure(bg=c["bg"])
        self.text_frame.configure(bg=c["bg"])

        # 辅助函数：统一配置按钮样式
        def config_btn(btn, bg=c["accent"], fg=c["fg"]):
            if btn:
                # [核心修复] 必须设置 bg，flat 样式的按钮才会显示背景色块
                btn.configure(bg=bg, fg=fg, activebackground=c["bg"], activeforeground=fg)

        # 逐个配置所有按钮
        config_btn(self.btn_new)
        config_btn(self.btn_save)
        config_btn(self.btn_sync)
        config_btn(self.btn_settings)

        # --- 👇 必须加上这一行，笔记按钮才会有样式 👇 ---
        config_btn(self.btn_notebook)
        # ---------------------------------------------

        config_btn(self.btn_history)

        # 临时置顶按钮的特殊颜色处理
        if self.is_topmost:
            top_color = "#4a90e2" if "强制" in self.btn_top.cget("text") else c["btn_top_active"]
            config_btn(self.btn_top, bg=top_color, fg="white")
        else:
            config_btn(self.btn_top)

        self.text_area.configure(bg=c["text_bg"], fg=c["text_fg"], insertbackground=c["insert_bg"])

    # --- 新增方法 ---
    def open_notebook(self):
        NotebookWindow(self.root, self.db, self.colors)


    def open_new_window(self):
        new_root = tk.Toplevel(self.root)
        new_app = SafeDraftApp(new_root, existing_db=self.db, is_main_window=False)
        new_root.app = new_app


    def switch_theme(self, theme_name):
        self.colors = THEMES.get(theme_name, THEMES["Deep"])
        self.apply_theme()

    def set_window_alpha(self, value):
        try:
            self.root.attributes("-alpha", float(value))
        except:
            pass

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

        # --- 修改：延迟加载 pystray ---
        import pystray
        # ----------------------------

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

    # --- 新增：主动同步逻辑 ---
    def manual_sync(self):
        # 1. 检查是否开启
        if self.db.get_setting("ch_enabled", "0") != "1":
            messagebox.showinfo("提示", "云同步未开启。\n请前往【设置 -> 云端同步】进行配置。")
            return

        # 2. UI 变为加载状态
        orig_text = "☁️ 同步"
        self.btn_sync.config(text="⏳...", state="disabled")

        # 3. 异步执行
        def _run():
            try:
                # 执行同步
                count = self.db.ch_manager.pull_and_merge()

                # 成功回调
                self.root.after(0, lambda: self._on_sync_done(count, orig_text))
            except Exception as e:
                # --- [关键修复] ---
                # 必须先将异常转为字符串存入局部变量，否则 lambda 执行时 e 已被销毁
                err_msg = str(e)
                self.root.after(0, lambda: self._on_sync_fail(err_msg, orig_text))

        threading.Thread(target=_run, daemon=True).start()

    def _on_sync_done(self, count, orig_text):
        self.btn_sync.config(text=orig_text, state="normal")
        if count > 0:
            messagebox.showinfo("同步完成", f"成功从云端拉取了 {count} 条新记录！\n请在“时光机”中查看。")
        else:
            messagebox.showinfo("同步完成", "本地已是最新状态。")

    def _on_sync_fail(self, err_msg, orig_text):
        self.btn_sync.config(text=orig_text, state="normal")
        messagebox.showerror("同步失败", f"无法连接到云端：\n{err_msg}")
    # -----------------------

    def _flash_btn(self, btn, text, color):
        orig_text = "💾 保存并清空"
        orig_fg = self.colors["fg"]
        orig_bg = self.colors["accent"]
        btn.config(text=text, fg=color)
        self.root.after(1000, lambda: btn.config(text=orig_text, fg=orig_fg, bg=orig_bg))

    def open_history(self):
        HistoryWindow(self.root, self.db, self.restore_draft_content, self.colors)

    def restore_draft_content(self, content):
        # 移除了这里的确认弹窗，改为直接执行
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
        """Watcher 发现目标后的回调"""
        # --- 新增：检查总开关 ---
        master_switch = self.db.get_setting("master_monitor", "1")
        if master_switch == "0":
            return  # 总开关关闭，忽略自动弹出
        # ----------------------

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