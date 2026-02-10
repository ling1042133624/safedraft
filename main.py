import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import sys
import os
import psutil
from pynput import keyboard

# 项目内模块
from storage import StorageManager
from watcher import WindowWatcher
from utils import ThemeManager, StartupManager, get_icon_image, DEFAULT_FONT_SIZE
from windows import HistoryWindow, SettingsDialog
from notebook import NotebookWindow


class GlobalHotKeys:
    def __init__(self, app):
        self.app = app
        self.listener = None
        self.start()

    def start(self):
        if self.listener: return
        self.listener = keyboard.GlobalHotKeys({
            '<ctrl>+`': self.on_activate
        })
        self.listener.start()

    def on_activate(self):
        self.app.toggle_main_window()

    def stop(self):
        if self.listener:
            self.listener.stop()
            self.listener = None


class SafeDraftApp:
    # [修复1] 恢复 existing_db 参数，确保多窗口共享同一个数据库连接
    def __init__(self, root, existing_db=None, is_main_window=True):
        self.root = root
        self.is_main_window = is_main_window

        # 数据库初始化逻辑：优先使用传入的实例
        if existing_db:
            self.db = existing_db
        else:
            self.db = StorageManager()

        # 加载配置
        try:
            self.font_size = int(self.db.get_setting("font_size", str(DEFAULT_FONT_SIZE)))
        except:
            self.font_size = DEFAULT_FONT_SIZE

        # 1. 窗口基础设置
        self.root.title("SafeDraft" if is_main_window else "SafeDraft (New)")
        self.root.geometry("600x600")

        # 图标
        self.load_icon()

        # 2. 主题初始化
        self.theme_manager = ThemeManager()
        self.current_theme_name = self.db.get_setting("theme", "Deep")
        self.colors = self.theme_manager.get_theme(self.current_theme_name)
        self.root.configure(bg=self.colors["bg"])

        # 初始化置顶定时器变量
        self.topmost_timer = None

        # 3. UI 构建
        self.setup_ui()

        # 4. 逻辑组件
        if self.is_main_window:
            self.watcher = WindowWatcher(self.db, self.on_trigger)
            self.watcher.start()
            self.hotkeys = GlobalHotKeys(self)

            self.setup_tray()

            alpha = float(self.db.get_setting("window_alpha", "0.95"))
            self.root.attributes("-alpha", alpha)

            self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)
        else:
            self.watcher = None
            # [修复2] 子窗口使用安全的关闭方法，防止定时器崩溃
            self.root.protocol("WM_DELETE_WINDOW", self.on_sub_window_close)

        # 5. 加载初始数据
        self.current_draft_id = None
        self.last_content = ""

        # --- 核心修改点：取消启动时的自动填充 ---
        # 原逻辑：仅主窗口自动加载历史，新建窗口保持空白
        # 修改后：无论是否为主窗口，启动时均不加载最新草稿，保持输入框纯净
        # if self.is_main_window:
        #     self.load_latest_draft()

        # 6. 事件绑定 & 自动保存定时器
        self.auto_save_timer = None
        self.text_area.bind("<Control-s>", self.on_ctrl_s)
        self.text_area.bind("<<Modified>>", self.on_text_change)

        self.db.add_observer(self.on_db_update)

    def load_icon(self):
        try:
            from PIL import ImageTk
            pil_img = get_icon_image()
            self.tk_icon = ImageTk.PhotoImage(pil_img)
            self.root.iconphoto(True, self.tk_icon)
        except Exception as e:
            print(f"Icon load fail: {e}")

    def setup_ui(self):
        self.toolbar = tk.Frame(self.root, height=40)
        self.toolbar.pack(fill="x", padx=5, pady=5)

        # [左侧按钮组]
        self.btn_new = tk.Button(self.toolbar, text="➕ 新建", command=self.open_new_window, relief="flat", padx=5)
        self.btn_new.pack(side="left", padx=2)

        self.btn_save = tk.Button(self.toolbar, text="💾 保存", command=self.manual_save, relief="flat",
                                  padx=5)
        self.btn_save.pack(side="left", padx=2)

        if self.is_main_window:
            self.btn_up = tk.Button(self.toolbar, text="☁️⬆️", command=self.manual_upload, relief="flat", padx=2)
            self.btn_up.pack(side="left", padx=2)
            self.btn_down = tk.Button(self.toolbar, text="☁️⬇️", command=self.manual_download, relief="flat", padx=2)
            self.btn_down.pack(side="left", padx=2)

        if self.is_main_window:
            self.btn_settings = tk.Button(self.toolbar, text="⚙️ 设置", command=self.open_settings, relief="flat",
                                          padx=5)
            self.btn_settings.pack(side="left", padx=2)
        else:
            self.btn_settings = None

        # [右侧按钮组]
        self.btn_top = tk.Button(self.toolbar, text="📌 临时置顶", command=self.toggle_manual_topmost, relief="flat",
                                 padx=5)
        self.btn_top.pack(side="right", padx=2)

        if self.is_main_window:
            self.btn_notebook = tk.Button(self.toolbar, text="📓 笔记", command=self.open_notebook, relief="flat",
                                          padx=5)
            self.btn_notebook.pack(side="right", padx=2)
        else:
            self.btn_notebook = None

        self.btn_history = tk.Button(self.toolbar, text="🕒 历史归档", command=self.open_history, relief="flat",
                                     padx=5)
        self.btn_history.pack(side="right", padx=2)

        self.text_frame = tk.Frame(self.root, padx=5, pady=5)
        self.text_frame.pack(fill="both", expand=True)

        self.text_area = tk.Text(self.text_frame, relief="flat",
                                 font=("Consolas", self.font_size),
                                 undo=True, wrap="word", padx=10, pady=10)
        self.text_area.pack(fill="both", expand=True)

        self.apply_theme_colors()

    # --- 同步逻辑 ---
    def manual_upload(self):
        if self.db.get_setting("ssh_enabled", "0") != "1":
            messagebox.showinfo("提示", "请先在设置中开启并配置服务器同步功能。")
            return
        ip = self.db.get_setting("ssh_ip", "")
        path = self.db.get_setting("ssh_path", "")
        if not ip or not path:
            messagebox.showerror("配置缺失", "请先在设置中填写服务器 IP 和路径。")
            return
        if messagebox.askyesno("确认", "确定要上传当前数据覆盖服务器端吗？"):
            self._run_async_sync(self.db.sync_upload, ip, path, "上传成功")

    def manual_download(self):
        if self.db.get_setting("ssh_enabled", "0") != "1":
            messagebox.showinfo("提示", "请先在设置中开启并配置服务器同步功能。")
            return
        ip = self.db.get_setting("ssh_ip", "")
        path = self.db.get_setting("ssh_path", "")
        if messagebox.askyesno("确认", "下载将覆盖本地所有数据（不可撤销）。\n确定继续吗？"):
            self._run_async_sync(self.db.sync_download, ip, path, "下载成功，数据已重载")

    def _run_async_sync(self, func, ip, path, success_msg):
        def _worker():
            try:
                func(ip, path)
                self.root.after(0, lambda: messagebox.showinfo("成功", success_msg))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: messagebox.showerror("同步失败", f"错误详情:\n{err}"))

        threading.Thread(target=_worker, daemon=True).start()

    def setup_tray(self):
        import pystray
        from PIL import Image

        def quit_app(icon, item):
            icon.stop()
            self.root.after(0, self.exit_app)

        def show_app(icon, item):
            self.root.after(0, self.show_main_window)

        image = get_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("显示", show_app, default=True),
            pystray.MenuItem("退出", quit_app)
        )
        self.tray_icon = pystray.Icon("SafeDraft", image, "SafeDraft", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def on_close_window(self):
        action = self.db.get_setting("exit_action", "ask")
        if action == "quit":
            self.exit_app()
        elif action == "tray":
            self.hide_main_window()
        else:
            ans = messagebox.askyesnocancel("退出", "是=最小化到托盘\n否=完全退出程序")
            if ans is None: return
            if ans:
                self.hide_main_window()
            else:
                self.exit_app()

    # [修复2] 子窗口关闭逻辑：取消定时器，防止崩溃
    def on_sub_window_close(self):
        if self.auto_save_timer:
            self.root.after_cancel(self.auto_save_timer)
            # 可选：关闭前立即执行一次保存
            self.perform_auto_save()
        self.root.destroy()

    def show_main_window(self):
        self.root.deiconify()
        self.root.lift()
        # 修复：确保唤醒时遵循当前的置顶逻辑
        is_top = self.root.attributes("-topmost")
        self.root.attributes("-topmost", True)  # 强制刷一次置顶
        if not is_top:
            # 如果原本不是置顶状态，刷完后再恢复，以确保窗口能跳到最前面
            self.root.after(10, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def hide_main_window(self):
        self.root.withdraw()

    def toggle_main_window(self):
        if self.root.state() == 'normal':
            if self.root.winfo_viewable():
                self.hide_main_window()
            else:
                self.show_main_window()
        else:
            self.show_main_window()

    def exit_app(self):
        if self.watcher: self.watcher.stop()
        if self.hotkeys: self.hotkeys.stop()
        if hasattr(self, 'tray_icon'): self.tray_icon.stop()
        self.db.close()
        self.root.quit()
        sys.exit()

    def on_trigger(self, rule_type, val):
        master_on = self.db.get_setting("master_monitor", "1")
        if master_on == "1":
            self.root.after(0, self._perform_auto_pop)

    def _perform_auto_pop(self):
        self.show_main_window()
        self._start_auto_topmost()

    def _start_auto_topmost(self):
        self.root.attributes('-topmost', True)
        self.btn_top.config(text="📌 锁定(2m)", bg="#4a90e2", fg="white")

        if self.topmost_timer: self.root.after_cancel(self.topmost_timer)
        self.topmost_timer = self.root.after(120000, self._cancel_topmost)

    def _cancel_topmost(self):
        self.topmost_timer = None
        self.root.attributes('-topmost', False)
        bg_color = self.colors.get("bg_btn_default", "#f0f0f0")
        self.btn_top.config(text="📌 临时置顶", bg=bg_color, fg=self.colors["fg"])

    def toggle_manual_topmost(self):
        is_currently_top = self.root.attributes("-topmost")

        # 清理现有的定时器，防止冲突
        if self.topmost_timer:
            self.root.after_cancel(self.topmost_timer)
            self.topmost_timer = None

        if is_currently_top:
            self.root.attributes("-topmost", False)
            # 修复：增加显式的颜色回退逻辑
            bg_color = self.colors.get("bg_btn_default", "#f0f0f0")
            self.btn_top.config(text="📌 临时置顶", bg=bg_color, fg=self.colors.get("fg", "black"))
        else:
            self.root.attributes("-topmost", True)
            # 修复：确保使用高亮色
            active_bg = self.colors.get("btn_top_active", "#4a90e2")
            self.btn_top.config(text="📌 已强制锁定", bg=active_bg, fg="white")

        # 强制更新 idle 任务以刷新 UI
        self.root.update_idletasks()

    def on_text_change(self, event):
        if self.text_area.edit_modified():
            content = self.text_area.get("1.0", "end-1c")
            if content != self.last_content:
                self.last_content = content
                if self.auto_save_timer:
                    self.root.after_cancel(self.auto_save_timer)
                self.auto_save_timer = self.root.after(1000, self.perform_auto_save)
            self.text_area.edit_modified(False)

    def on_ctrl_s(self, event):
        content = self.text_area.get("1.0", "end-1c")
        if content.strip():
            self.db.save_snapshot(content)
            success_color = self.colors.get("btn_save_success", "#4caf50")
            self.flash_button(self.btn_save, "✅ 已快照", "💾 保存", success_color)
        return "break"

    def perform_auto_save(self):
        # 增加安全检查，防止窗口销毁后调用报错
        try:
            if not self.root.winfo_exists(): return
            content = self.text_area.get("1.0", "end-1c")
            if not content.strip(): return
            new_id = self.db.save_content(content, self.current_draft_id)
            if new_id:
                self.current_draft_id = new_id
        except:
            pass
        finally:
            self.auto_save_timer = None

    def manual_save(self):
        content = self.text_area.get("1.0", "end-1c")
        if content.strip():
            self.db.save_snapshot(content)
            self.text_area.delete("1.0", "end")
            self.current_draft_id = None
            self.last_content = ""
            success_color = self.colors.get("btn_save_success", "#4caf50")
            self.flash_button(self.btn_save, "✅ 已归档", "💾 保存", success_color)

    def load_latest_draft(self):
        history = self.db.get_history()
        if history:
            latest = history[0]
            self.current_draft_id = latest[0]
            self.text_area.delete("1.0", "end")
            self.text_area.insert("1.0", latest[1])
            self.last_content = latest[1]

    def on_db_update(self):
        pass

    def restore_draft(self, content):
        self.text_area.delete("1.0", "end")
        self.text_area.insert("1.0", content)
        self.current_draft_id = None
        self.perform_auto_save()
        self.show_main_window()

    def open_new_window(self):
        new_root = tk.Toplevel(self.root)
        # [修复1] 传递 existing_db=self.db，确保新窗口复用连接
        app = SafeDraftApp(new_root, existing_db=self.db, is_main_window=False)
        new_root.app = app

    def open_history(self):
        win = HistoryWindow(self.root, self.db, self.restore_draft, self.colors)

    def open_notebook(self):
        win = NotebookWindow(self.root, self.db, self.colors)

    def open_settings(self):
        win = SettingsDialog(self.root, self.db, self.watcher, self)

    def apply_theme_colors(self):
        c = self.colors
        self.root.configure(bg=c["bg"])
        self.toolbar.configure(bg=c["bg"])
        self.text_frame.configure(bg=c["bg"])
        self.text_area.configure(bg=c["text_bg"], fg=c["text_fg"], insertbackground=c["text_fg"])

        # 按钮样式通用
        for widget in self.toolbar.winfo_children():
            if isinstance(widget, tk.Button):
                if widget == getattr(self, 'btn_top', None):
                    is_top = self.root.attributes("-topmost")
                    if is_top:
                        widget.config(bg="#4a90e2", fg="white")
                    else:
                        widget.config(bg=c.get("bg_btn_default", "#f0f0f0"), fg=c["fg"])
                else:
                    widget.config(bg=c.get("bg_btn_default", "#f0f0f0"), fg=c["fg"], activebackground=c["accent"])

        self.text_area.configure(font=("Consolas", self.font_size))

    def switch_theme(self, theme_name):
        self.colors = self.theme_manager.get_theme(theme_name)
        self.apply_theme_colors()

    def set_window_alpha(self, alpha):
        self.root.attributes("-alpha", float(alpha))

    def set_font_size(self, size):
        self.font_size = int(size)
        self.text_area.configure(font=("Consolas", self.font_size))

    def flash_button(self, btn, text, restore_text, text_color=None):
        orig_fg = self.colors["fg"]
        if text_color:
            btn.config(text=text, fg=text_color)
        else:
            btn.config(text=text)
        self.root.after(1500, lambda: btn.config(text=restore_text, fg=orig_fg))


if __name__ == "__main__":
    root = tk.Tk()
    app = SafeDraftApp(root)
    root.mainloop()