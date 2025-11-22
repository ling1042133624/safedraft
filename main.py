import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import datetime
import os
import sys
import threading
import keyboard
import pystray
from PIL import Image, ImageTk
from storage import StorageManager
from watcher import WindowWatcher

if sys.platform == "win32":
    import winreg


# ---------------------------------------------------------
# 1. 终极路径获取逻辑 (穷举法)
# ---------------------------------------------------------
def get_asset_path(filename):
    """
    尝试在所有可能的目录下寻找文件。
    返回找到的第一个存在的绝对路径，如果都没找到，返回当前目录下的路径。
    """
    search_dirs = []

    # 1. 当前工作目录 (双击 exe 时通常就是这里)
    search_dirs.append(os.getcwd())

    # 2. EXE 所在的物理目录 (sys.argv[0])
    if getattr(sys, 'frozen', False):
        search_dirs.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    else:
        search_dirs.append(os.path.dirname(os.path.abspath(__file__)))

    # 3. Nuitka/PyInstaller 的临时解压目录 (sys.executable)
    if getattr(sys, 'frozen', False):
        search_dirs.append(os.path.dirname(sys.executable))

    # 开始寻找
    for directory in search_dirs:
        full_path = os.path.join(directory, filename)
        if os.path.exists(full_path):
            return full_path

    # 如果都没找到，默认返回当前目录 (虽然不存在)
    return os.path.join(os.getcwd(), filename)


# ---------------------------------------------------------
# 2. 调试日志 (强制写在当前目录下)
# ---------------------------------------------------------
def log_debug(message):
    try:
        # 强制写在当前工作目录，确保你能看到
        log_path = os.path.join(os.getcwd(), "_safedraft_debug.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] {message}\n")
    except:
        pass


# --- 主题定义 ---
THEMES = {
    "Deep": {
        "bg": "#1e1e1e", "fg": "#d4d4d4", "accent": "#3c3c3c",
        "list_bg": "#252526", "list_fg": "#e0e0e0",
        "text_bg": "#1e1e1e", "text_fg": "#d4d4d4", "insert_bg": "white",
        "btn_top_active": "#d35400", "btn_save_success": "#4caf50",
    },
    "Light": {
        "bg": "#f0f0f0", "fg": "#333333", "accent": "#e0e0e0",
        "list_bg": "#ffffff", "list_fg": "#000000",
        "text_bg": "#ffffff", "text_fg": "#000000", "insert_bg": "black",
        "btn_top_active": "#e67e22", "btn_save_success": "#27ae60",
    }
}


class StartupManager:
    WIN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "SafeDraft"
    MAC_PLIST_NAME = "com.safedraft.autostart.plist"

    @staticmethod
    def _get_mac_plist_path():
        return os.path.expanduser(f"~/Library/LaunchAgents/{StartupManager.MAC_PLIST_NAME}")

    @staticmethod
    def is_autostart_enabled():
        if sys.platform == "win32":
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.WIN_KEY_PATH, 0, winreg.KEY_READ)
                winreg.QueryValueEx(key, StartupManager.APP_NAME)
                key.Close()
                return True
            except FileNotFoundError:
                return False
        elif sys.platform == "darwin":
            return os.path.exists(StartupManager._get_mac_plist_path())
        return False

    @staticmethod
    def set_autostart(enable):
        if sys.platform == "win32":
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, StartupManager.WIN_KEY_PATH, 0, winreg.KEY_ALL_ACCESS)
                if enable:
                    # 修复：开机自启也使用 sys.argv[0] 锁定物理 exe
                    exe_path = os.path.abspath(sys.argv[0])
                    winreg.SetValueEx(key, StartupManager.APP_NAME, 0, winreg.REG_SZ, exe_path)
                else:
                    try:
                        winreg.DeleteValue(key, StartupManager.APP_NAME)
                    except:
                        pass
                key.Close()
            except Exception as e:
                messagebox.showerror("错误", f"修改注册表失败: {e}")
        elif sys.platform == "darwin":
            pass


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
        ico_path = get_asset_path("icon.ico")
        png_path = get_asset_path("icon.png")
        try:
            if sys.platform == "win32" and os.path.exists(ico_path):
                self.iconbitmap(ico_path)
            elif os.path.exists(png_path):
                img = Image.open(png_path)
                self.icon_img = ImageTk.PhotoImage(img)
                self.iconphoto(True, self.icon_img)
        except:
            pass

    def setup_ui(self):
        lbl = tk.Label(self, text="双击记录可恢复 | 选中可删除", bg=self.colors["bg"], fg="#888888", pady=10)
        lbl.pack(side="top", fill="x")
        frame = tk.Frame(self, bg=self.colors["bg"])
        frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        self.scrollbar = ttk.Scrollbar(frame, orient="vertical")
        self.listbox = tk.Listbox(frame, bg=self.colors["list_bg"], fg=self.colors["list_fg"],
                                  relief="flat", highlightthickness=0, selectbackground="#4a90e2",
                                  yscrollcommand=self.scrollbar.set, font=("Consolas", 10))
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
        ico_path = get_asset_path("icon.ico")
        png_path = get_asset_path("icon.png")
        try:
            if sys.platform == "win32" and os.path.exists(ico_path):
                self.iconbitmap(ico_path)
            elif os.path.exists(png_path):
                img = Image.open(png_path)
                self.icon_img = ImageTk.PhotoImage(img)
                self.iconphoto(True, self.icon_img)
        except:
            pass

    def setup_general_ui(self):
        frame_hotkey = tk.Frame(self.page_general, bg=self.colors["bg"], pady=10)
        frame_hotkey.pack(fill="x", padx=20)
        tk.Label(frame_hotkey, text="全局快捷键: Ctrl + ~ (Backtick)",
                 bg=self.colors["bg"], fg="#4a90e2", font=("Arial", 10, "bold")).pack(anchor="w")
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
        frame_theme = tk.Frame(self.page_general, bg=self.colors["bg"], pady=20)
        frame_theme.pack(fill="x", padx=20)
        tk.Label(frame_theme, text="界面主题:", bg=self.colors["bg"], fg=self.colors["fg"]).pack(side="left")
        current_theme = self.db.get_setting("theme", "Deep")
        self.combo_theme = ttk.Combobox(frame_theme, values=["Deep", "Light"], state="readonly", width=10)
        self.combo_theme.set(current_theme)
        self.combo_theme.pack(side="left", padx=10)
        self.combo_theme.bind("<<ComboboxSelected>>", self.change_theme)
        frame_alpha = tk.Frame(self.page_general, bg=self.colors["bg"], pady=10)
        frame_alpha.pack(fill="x", padx=20)
        tk.Label(frame_alpha, text="窗口透明度:", bg=self.colors["bg"], fg=self.colors["fg"]).pack(side="left")
        current_alpha = float(self.db.get_setting("window_alpha", "0.95"))
        self.scale_alpha = tk.Scale(frame_alpha, from_=0.2, to=1.0, resolution=0.05, orient="horizontal",
                                    bg=self.colors["bg"], fg=self.colors["fg"], highlightthickness=0,
                                    activebackground=self.colors["accent"], bd=0, length=200,
                                    command=self.on_alpha_change)
        self.scale_alpha.set(current_alpha)
        self.scale_alpha.pack(side="left", padx=10)
        frame_exit = tk.Frame(self.page_general, bg=self.colors["bg"], pady=20)
        frame_exit.pack(fill="x", padx=20)
        tk.Label(frame_exit, text="关闭主窗口时:", bg=self.colors["bg"], fg=self.colors["fg"]).pack(side="left")
        current_exit = self.db.get_setting("exit_action", "ask")
        self.combo_exit = ttk.Combobox(frame_exit, values=["ask", "tray", "quit"], state="readonly", width=10)
        self.exit_map = {"ask": "每次询问", "tray": "最小化到托盘", "quit": "退出程序"}
        self.exit_map_rev = {v: k for k, v in self.exit_map.items()}
        self.combo_exit.set(self.exit_map.get(current_exit, "每次询问"))
        self.combo_exit.pack(side="left", padx=10)
        self.combo_exit.bind("<<ComboboxSelected>>", self.change_exit_pref)

    def toggle_boot(self):
        StartupManager.set_autostart(self.var_boot.get())

    def change_theme(self, event):
        theme_name = self.combo_theme.get()
        self.db.set_setting("theme", theme_name)
        self.app.switch_theme(theme_name)
        self.colors = self.app.colors
        self.configure(bg=self.colors["bg"])

    def on_alpha_change(self, value):
        self.db.set_setting("window_alpha", value)
        self.app.set_window_alpha(value)

    def change_exit_pref(self, event):
        display_val = self.combo_exit.get()
        db_val = self.exit_map_rev.get(display_val, "ask")
        self.db.set_setting("exit_action", db_val)

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
        self.tray_icon = None
        self.db = StorageManager()
        self.watcher = WindowWatcher(self.db, self.on_trigger_detected)
        self.watcher.start()
        try:
            keyboard.add_hotkey('ctrl+`', self.on_global_hotkey)
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
        alpha = float(self.db.get_setting("window_alpha", "0.95"))
        self.root.attributes("-alpha", alpha)

        # --- 终极加载逻辑 + 调试日志 ---
        log_debug("Starting Icon Load...")
        ico_path = get_asset_path("icon.ico")
        png_path = get_asset_path("icon.png")
        log_debug(f"Calculated ICO path: {ico_path}")
        log_debug(f"Calculated PNG path: {png_path}")

        try:
            if sys.platform == "win32" and os.path.exists(ico_path):
                log_debug("Found ICO, loading via iconbitmap")
                self.root.iconbitmap(ico_path)
            elif os.path.exists(png_path):
                log_debug("Found PNG, loading via Pillow")
                img = Image.open(png_path)
                self.icon_img = ImageTk.PhotoImage(img)
                self.root.iconphoto(True, self.icon_img)
            else:
                log_debug("ERROR: No icon file found at calculated paths.")
                # 尝试最后一种可能：当前目录直接加载
                if os.path.exists("icon.png"):
                    log_debug("Fallback: Loading icon.png from CWD")
                    img = Image.open("icon.png")
                    self.icon_img = ImageTk.PhotoImage(img)
                    self.root.iconphoto(True, self.icon_img)
        except Exception as e:
            log_debug(f"EXCEPTION during icon load: {e}")

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

    def set_window_alpha(self, value):
        try:
            self.root.attributes("-alpha", float(value))
        except:
            pass

    def setup_events(self):
        self.text_area.bind("<KeyRelease>", self.on_key_release)
        self.text_area.bind("<Control-s>", self.on_ctrl_s)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        exit_action = self.db.get_setting("exit_action", "ask")
        if exit_action == "tray":
            self.minimize_to_tray()
        elif exit_action == "quit":
            self.quit_app()
        else:
            res = messagebox.askyesnocancel("退出确认",
                                            "是否要保持后台运行？\n\n【是】最小化到系统托盘 (推荐)\n【否】彻底退出程序\n【取消】手滑了")
            if res is True:
                self.db.set_setting("exit_action", "tray")
                self.minimize_to_tray()
            elif res is False:
                self.db.set_setting("exit_action", "quit")
                self.quit_app()

    def minimize_to_tray(self):
        self.root.withdraw()
        ico_path = get_asset_path("icon.ico")
        png_path = get_asset_path("icon.png")
        try:
            if os.path.exists(png_path):
                image = Image.open(png_path)
            elif os.path.exists(ico_path):
                image = Image.open(ico_path)
            else:
                # Fallback
                if os.path.exists("icon.png"):
                    image = Image.open("icon.png")
                else:
                    image = Image.new('RGB', (64, 64), color=(74, 144, 226))
        except Exception:
            image = Image.new('RGB', (64, 64), color=(74, 144, 226))

        def on_tray_quit(icon, item):
            icon.stop()
            self.root.after(0, self.quit_app)

        def on_tray_show(icon, item):
            icon.stop()
            self.root.after(0, self.restore_from_tray)

        menu = (pystray.MenuItem('显示主界面', on_tray_show, default=True), pystray.MenuItem('彻底退出', on_tray_quit))
        self.tray_icon = pystray.Icon("SafeDraft", image, "SafeDraft", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def restore_from_tray(self):
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit_app(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.watcher.stop()
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
        self.restore_from_tray()
        self._start_auto_topmost()

    def on_trigger_detected(self):
        self.root.after(0, self._perform_auto_pop)

    def _perform_auto_pop(self):
        if self.is_topmost and not self.topmost_timer: return
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