import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import datetime
import os
import sys
import winreg
import threading
import keyboard
import pystray  # --- 新增依赖: 系统托盘 ---
from PIL import Image  # --- 新增依赖: 图片处理 ---
from storage import StorageManager
from watcher import WindowWatcher

# --- 主题定义 ---
THEMES = {
    "Deep": {
        "bg": "#1e1e1e",
        "fg": "#d4d4d4",
        "accent": "#3c3c3c",
        "list_bg": "#252526",
        "list_fg": "#e0e0e0",
        "text_bg": "#1e1e1e",
        "text_fg": "#d4d4d4",
        "insert_bg": "white",
        "btn_top_active": "#d35400",
        "btn_save_success": "#4caf50",
    },
    "Light": {
        "bg": "#f0f0f0",
        "fg": "#333333",
        "accent": "#e0e0e0",
        "list_bg": "#ffffff",
        "list_fg": "#000000",
        "text_bg": "#ffffff",
        "text_fg": "#000000",
        "insert_bg": "black",
        "btn_top_active": "#e67e22",
        "btn_save_success": "#27ae60",
    }
}


class StartupManager:
    KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "SafeDraft"

    @staticmethod
    def is_autostart_enabled():
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.KEY_PATH, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, StartupManager.APP_NAME)
            key.Close()
            return True
        except FileNotFoundError:
            return False

    @staticmethod
    def set_autostart(enable):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.KEY_PATH, 0, winreg.KEY_ALL_ACCESS)
            if enable:
                exe_path = sys.executable
                winreg.SetValueEx(key, StartupManager.APP_NAME, 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, StartupManager.APP_NAME)
                except FileNotFoundError:
                    pass
            key.Close()
        except Exception as e:
            messagebox.showerror("错误", f"修改注册表失败: {e}")


class HistoryWindow(tk.Toplevel):
    def __init__(self, parent, db, restore_callback, theme):
        super().__init__(parent)
        self.title("时光机 - 历史归档")
        self.geometry("400x550")
        self.db = db
        self.restore_callback = restore_callback
        self.colors = theme

        self.configure(bg=self.colors["bg"])
        self.setup_ui()
        self.refresh_data()
        self.load_icon()

    def load_icon(self):
        try:
            if os.path.exists("icon.ico"):
                self.iconbitmap("icon.ico")
            elif os.path.exists("icon.png"):
                img = tk.PhotoImage(file="icon.png")
                self.iconphoto(True, img)
        except:
            pass

    def setup_ui(self):
        lbl = tk.Label(self, text="双击记录可恢复 | 选中可删除", bg=self.colors["bg"], fg="#888888", pady=10)
        lbl.pack(side="top", fill="x")

        frame = tk.Frame(self, bg=self.colors["bg"])
        frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        self.scrollbar = ttk.Scrollbar(frame, orient="vertical")
        self.listbox = tk.Listbox(frame, bg=self.colors["list_bg"], fg=self.colors["list_fg"],
                                  relief="flat", highlightthickness=0,
                                  selectbackground="#4a90e2",
                                  yscrollcommand=self.scrollbar.set,
                                  font=("Consolas", 10))

        self.scrollbar.config(command=self.listbox.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", self.on_double_click)

        btn_frame = tk.Frame(self, bg=self.colors["bg"], pady=10)
        btn_frame.pack(side="bottom", fill="x", padx=10)

        tk.Button(btn_frame, text="🗑️ 删除选中", command=self.on_delete,
                  bg=self.colors["bg"], fg="#ff5555", relief="flat",
                  activebackground=self.colors["accent"], activeforeground="#ff5555").pack(side="right")

    def refresh_data(self):
        self.listbox.delete(0, "end")
        self.history_data = self.db.get_history()
        if not self.history_data:
            self.listbox.insert("end", "暂无历史记录")
            return
        for row in self.history_data:
            try:
                dt = datetime.fromisoformat(row[3])
                time_str = dt.strftime("%H:%M") if dt.date() == datetime.now().date() else dt.strftime("%m/%d %H:%M")
                content = row[1].strip().replace("\n", " ")
                if len(content) > 20: content = content[:20] + "..."
                self.listbox.insert("end", f"[{time_str}] {content}")
            except:
                pass

    def on_double_click(self, event):
        selection = self.listbox.curselection()
        if not selection: return
        index = selection[0]
        if index >= len(self.history_data): return
        self.restore_callback(self.history_data[index][1])

    def on_delete(self):
        selection = self.listbox.curselection()
        if not selection: return
        index = selection[0]
        if index >= len(self.history_data): return
        if messagebox.askyesno("确认删除", "确定要永久删除这条记录吗？"):
            self.db.delete_draft(self.history_data[index][0])
            self.refresh_data()


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, db, watcher, app):
        super().__init__(parent)
        self.title("设置")
        self.geometry("480x600")
        self.db = db
        self.watcher = watcher
        self.app = app
        self.colors = app.colors

        self.configure(bg=self.colors["bg"])
        self.load_icon()

        style = ttk.Style()
        style.configure("TNotebook", background=self.colors["bg"])
        style.configure("TNotebook.Tab", background=self.colors["accent"], foreground="black")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.page_rules = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(self.page_rules, text=" 监控规则 ")
        self.setup_rules_ui()

        self.page_general = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(self.page_general, text=" 常规设置 ")
        self.setup_general_ui()

    def load_icon(self):
        try:
            if os.path.exists("icon.ico"):
                self.iconbitmap("icon.ico")
            elif os.path.exists("icon.png"):
                img = tk.PhotoImage(file="icon.png")
                self.iconphoto(True, img)
        except:
            pass

    def setup_general_ui(self):
        # Hotkey Hint
        frame_hotkey = tk.Frame(self.page_general, bg=self.colors["bg"], pady=10)
        frame_hotkey.pack(fill="x", padx=20)
        tk.Label(frame_hotkey, text="全局快捷键: Ctrl + Alt + S (快速呼出)",
                 bg=self.colors["bg"], fg="#4a90e2", font=("Arial", 10, "bold")).pack(anchor="w")

        # Boot
        frame_boot = tk.Frame(self.page_general, bg=self.colors["bg"], pady=10)
        frame_boot.pack(fill="x", padx=20)
        self.var_boot = tk.BooleanVar(value=StartupManager.is_autostart_enabled())
        chk_boot = tk.Checkbutton(frame_boot, text="开机自动启动 SafeDraft", variable=self.var_boot,
                                  bg=self.colors["bg"], fg=self.colors["fg"], selectcolor=self.colors["accent"],
                                  activebackground=self.colors["bg"], activeforeground=self.colors["fg"],
                                  command=self.toggle_boot)
        chk_boot.pack(anchor="w")
        tk.Label(frame_boot, text="注意：受安全软件影响，可能需要允许注册表修改。",
                 bg=self.colors["bg"], fg="#888888", font=("Arial", 9)).pack(anchor="w", padx=20)

        # Theme
        frame_theme = tk.Frame(self.page_general, bg=self.colors["bg"], pady=20)
        frame_theme.pack(fill="x", padx=20)
        tk.Label(frame_theme, text="界面主题:", bg=self.colors["bg"], fg=self.colors["fg"]).pack(side="left")
        current_theme = self.db.get_setting("theme", "Deep")
        self.combo_theme = ttk.Combobox(frame_theme, values=["Deep", "Light"], state="readonly", width=10)
        self.combo_theme.set(current_theme)
        self.combo_theme.pack(side="left", padx=10)
        self.combo_theme.bind("<<ComboboxSelected>>", self.change_theme)

    def toggle_boot(self):
        StartupManager.set_autostart(self.var_boot.get())

    def change_theme(self, event):
        theme_name = self.combo_theme.get()
        self.db.set_setting("theme", theme_name)
        self.app.switch_theme(theme_name)
        self.colors = self.app.colors
        self.configure(bg=self.colors["bg"])

    def setup_rules_ui(self):
        btn_frame = tk.Frame(self.page_rules, bg=self.colors["bg"], pady=5)
        btn_frame.pack(fill="x", padx=0)

        tk.Button(btn_frame, text="➕ 选择应用 (.exe)", command=self.add_exe,
                  bg="#4a90e2", fg="white", relief="flat", padx=10).pack(side="left", padx=5)

        tk.Button(btn_frame, text="➕ 添加网址/标题", command=self.add_title_keyword,
                  bg=self.colors["accent"], fg=self.colors["fg"], relief="flat", padx=10).pack(side="left", padx=5)

        list_frame = tk.Frame(self.page_rules, bg=self.colors["bg"])
        list_frame.pack(fill="both", expand=True, padx=0, pady=10)

        self.canvas = tk.Canvas(list_frame, bg=self.colors["bg"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=self.colors["bg"])

        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.load_rules()

    def load_rules(self):
        for w in self.scrollable_frame.winfo_children(): w.destroy()
        rules = self.db.get_all_triggers()
        for rid, rtype, val, enabled in rules:
            row = tk.Frame(self.scrollable_frame, bg=self.colors["bg"], pady=2)
            row.pack(fill="x")
            var = tk.BooleanVar(value=bool(enabled))
            cb = tk.Checkbutton(row, variable=var, bg=self.colors["bg"], selectcolor=self.colors["accent"],
                                activebackground=self.colors["bg"],
                                command=lambda i=rid, v=var: self.toggle_rule(i, v.get()))
            cb.pack(side="left")
            type_color = "#d35400" if rtype == 'process' else "#2980b9"
            type_text = "[应用]" if rtype == 'process' else "[标题]"
            tk.Label(row, text=type_text, fg=type_color, bg=self.colors["bg"], width=6, anchor="w").pack(side="left")
            tk.Label(row, text=val, fg=self.colors["fg"], bg=self.colors["bg"]).pack(side="left")
            del_btn = tk.Label(row, text="×", fg="#ff5555", bg=self.colors["bg"], cursor="hand2", font=("Arial", 12))
            del_btn.pack(side="right", padx=10)
            del_btn.bind("<Button-1>", lambda e, i=rid: self.delete_rule(i))

    def add_exe(self):
        file_path = filedialog.askopenfilename(title="选择执行文件", filetypes=[("Executables", "*.exe")])
        if file_path:
            self.db.add_trigger('process', os.path.basename(file_path).lower())
            self.watcher.reload_rules()
            self.load_rules()

    def add_title_keyword(self):
        kw = simpledialog.askstring("添加关键词", "请输入标题关键词")
        if kw and kw.strip():
            self.db.add_trigger('title', kw.strip())
            self.watcher.reload_rules()
            self.load_rules()

    def toggle_rule(self, rid, enabled):
        self.db.toggle_trigger(rid, enabled)
        self.watcher.reload_rules()

    def delete_rule(self, rid):
        if messagebox.askyesno("确认", "删除此规则？"):
            self.db.delete_trigger(rid)
            self.watcher.reload_rules()
            self.load_rules()


class SafeDraftApp:
    def __init__(self, root):
        self.root = root

        self.is_topmost = False
        self.topmost_timer = None
        self.tray_icon = None  # 托盘图标对象

        self.db = StorageManager()
        self.watcher = WindowWatcher(self.db, self.on_trigger_detected)
        self.watcher.start()

        try:
            keyboard.add_hotkey('ctrl+alt+s', self.on_global_hotkey)
        except Exception as e:
            print(f"Hotkey register failed: {e}")

        theme_name = self.db.get_setting("theme", "Deep")
        self.colors = THEMES.get(theme_name, THEMES["Deep"])

        self.setup_window()
        self.setup_ui()
        self.setup_events()
        self.apply_theme()

    def setup_window(self):
        self.root.title("SafeDraft")
        self.root.geometry("500x400+100+100")
        self.root.attributes("-alpha", 0.95)

        try:
            if os.path.exists("icon.ico"):
                self.root.iconbitmap("icon.ico")
            elif os.path.exists("icon.png"):
                img = tk.PhotoImage(file="icon.png")
                self.root.iconphoto(True, img)
        except Exception as e:
            print(f"Icon load failed: {e}")

    def setup_ui(self):
        self.toolbar = tk.Frame(self.root, height=40)
        self.toolbar.pack(fill="x", padx=5, pady=5)

        self.btn_save = tk.Button(self.toolbar, text="💾 保存并清空", command=self.manual_save, relief="flat", padx=10)
        self.btn_save.pack(side="left", padx=5)

        self.btn_settings = tk.Button(self.toolbar, text="⚙️ 设置", command=self.open_settings, relief="flat", padx=10)
        self.btn_settings.pack(side="left", padx=5)

        self.btn_history = tk.Button(self.toolbar, text="🕒 时光机", command=self.open_history, relief="flat", padx=10)
        self.btn_history.pack(side="right", padx=5)

        self.btn_top = tk.Button(self.toolbar, text="📌 临时置顶", command=self.toggle_manual_topmost, relief="flat",
                                 padx=10)
        self.btn_top.pack(side="right", padx=5)

        self.text_frame = tk.Frame(self.root, padx=5, pady=5)
        self.text_frame.pack(fill="both", expand=True)

        self.text_area = tk.Text(self.text_frame, relief="flat", font=("Consolas", 12), undo=True, wrap="word", padx=10,
                                 pady=10)
        self.text_area.pack(fill="both", expand=True)

    def apply_theme(self):
        c = self.colors
        self.root.configure(bg=c["bg"])
        self.toolbar.configure(bg=c["bg"])
        self.text_frame.configure(bg=c["bg"])

        def config_btn(btn, bg=c["accent"], fg=c["fg"]):
            btn.configure(bg=bg, fg=fg, activebackground=c["bg"], activeforeground=fg)

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

    def setup_events(self):
        self.text_area.bind("<KeyRelease>", self.on_key_release)
        # 拦截关闭窗口事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- 核心：托盘与退出逻辑 ---
    def on_close(self):
        """用户点击关闭时的确认逻辑"""
        # askyesnocancel 返回值: True(是), False(否), None(取消)
        res = messagebox.askyesnocancel(
            "退出确认",
            "是否要保持后台运行？\n\n【是】最小化到系统托盘 (推荐)\n【否】彻底退出程序\n【取消】手滑了"
        )

        if res is True:
            self.minimize_to_tray()
        elif res is False:
            self.quit_app()
        # None: 什么都不做

    def minimize_to_tray(self):
        """最小化到系统托盘"""
        self.root.withdraw()  # 隐藏主窗口

        # 加载托盘图标 (pystray 需要 PIL Image 对象)
        try:
            if os.path.exists("icon.png"):
                image = Image.open("icon.png")
            elif os.path.exists("icon.ico"):
                image = Image.open("icon.ico")
            else:
                # 如果没有图标，生成一个简单的色块
                image = Image.new('RGB', (64, 64), color=(74, 144, 226))
        except Exception:
            image = Image.new('RGB', (64, 64), color=(74, 144, 226))

        # 定义托盘菜单
        def on_tray_quit(icon, item):
            icon.stop()
            self.root.after(0, self.quit_app)

        def on_tray_show(icon, item):
            icon.stop()
            self.root.after(0, self.restore_from_tray)

        menu = (
            pystray.MenuItem('显示主界面', on_tray_show, default=True),
            pystray.MenuItem('彻底退出', on_tray_quit)
        )

        self.tray_icon = pystray.Icon("SafeDraft", image, "SafeDraft", menu)

        # 在独立线程运行托盘，防止阻塞 Tkinter 主循环
        # 注意：Tkinter 隐藏后，mainloop 仍在运行处理其他事件(如 keyboard)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def restore_from_tray(self):
        """从托盘恢复"""
        if self.tray_icon:
            # 停止托盘图标线程（图标会消失）
            self.tray_icon.stop()
            self.tray_icon = None

        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit_app(self):
        """彻底退出"""
        if self.tray_icon:
            self.tray_icon.stop()
        self.watcher.stop()
        self.db.close()
        self.root.destroy()
        os._exit(0)

    # --- 其他功能 ---
    def on_key_release(self, event):
        content = self.text_area.get("1.0", "end-1c")
        self.db.save_content(content)

    def manual_save(self):
        content = self.text_area.get("1.0", "end-1c")
        if not content.strip():
            self._flash_btn(self.btn_save, "空内容!", "#ff5555")
            return
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
            self.db.current_session_id = None
            self.text_area.focus_set()

    def open_settings(self):
        SettingsDialog(self.root, self.db, self.watcher, self)

    def on_global_hotkey(self):
        self.root.after(0, self._perform_auto_pop_force)

    def _perform_auto_pop_force(self):
        # 强制恢复（如果最小化到了托盘，也要恢复）
        self.restore_from_tray()
        self._start_auto_topmost()

    def on_trigger_detected(self):
        self.root.after(0, self._perform_auto_pop)

    def _perform_auto_pop(self):
        if self.is_topmost and not self.topmost_timer: return

        # 如果在托盘里，恢复它
        if self.root.state() == 'withdrawn':
            self.restore_from_tray()
        elif self.root.state() == 'iconic':
            self.root.deiconify()

        if self.root.focus_displayof() is None:
            self.root.geometry("+100+100")
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
    root = tk.Tk()
    app = SafeDraftApp(root)
    root.mainloop()