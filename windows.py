import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime
from PIL import ImageTk

# 引入 DEFAULT_FONT_SIZE
from utils import get_icon_image, StartupManager, DEFAULT_FONT_SIZE


class HistoryWindow(tk.Toplevel):
    def __init__(self, parent, db, restore_callback, theme):
        super().__init__(parent)
        self.title("时光机 - 历史归档")
        self.geometry("400x600")
        self.db = db
        self.restore_callback = restore_callback
        self.colors = theme

        # 读取当前字体大小配置，用于列表显示
        try:
            self.font_size = int(self.db.get_setting("font_size", str(DEFAULT_FONT_SIZE)))
        except:
            self.font_size = DEFAULT_FONT_SIZE

        self.configure(bg=self.colors["bg"])
        self.setup_ui()
        self.refresh_data()
        self.load_icon()

        self.db.add_observer(self.refresh_data)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.db.remove_observer(self.refresh_data)
        self.destroy()

    def load_icon(self):
        try:
            pil_img = get_icon_image()
            self.tk_icon = ImageTk.PhotoImage(pil_img)
            self.iconphoto(True, self.tk_icon)
        except:
            pass

    def setup_ui(self):
        lbl = tk.Label(self, text="双击记录可恢复 | 选中可删除", bg=self.colors["bg"], fg="#888888", pady=5)
        lbl.pack(side="top", fill="x")

        search_frame = tk.Frame(self, bg=self.colors["bg"], pady=5, padx=10)
        search_frame.pack(side="top", fill="x")
        tk.Label(search_frame, text="🔍", bg=self.colors["bg"], fg="#888888").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self.on_search_change)
        self.entry_search = tk.Entry(search_frame, textvariable=self.search_var,
                                     bg=self.colors["list_bg"], fg=self.colors["list_fg"],
                                     relief="flat", insertbackground=self.colors["list_fg"])
        self.entry_search.pack(side="left", fill="x", expand=True, padx=5)

        frame = tk.Frame(self, bg=self.colors["bg"])
        frame.pack(fill="both", expand=True, padx=10, pady=(5, 5))
        self.scrollbar = ttk.Scrollbar(frame, orient="vertical")

        # 应用字体大小 (稍微比主输入框小一点点，或者保持一致)
        list_font = ("Consolas", max(9, self.font_size - 2))

        self.listbox = tk.Listbox(frame, bg=self.colors["list_bg"], fg=self.colors["list_fg"],
                                  relief="flat", highlightthickness=0, selectbackground="#4a90e2",
                                  yscrollcommand=self.scrollbar.set, font=list_font)
        self.scrollbar.config(command=self.listbox.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", self.on_double_click)

        btn_frame = tk.Frame(self, bg=self.colors["bg"], pady=10)
        btn_frame.pack(side="bottom", fill="x", padx=10)
        tk.Button(btn_frame, text="🗑️ 删除选中", command=self.on_delete,
                  bg=self.colors["bg"], fg="#ff5555", relief="flat",
                  activebackground=self.colors["accent"], activeforeground="#ff5555").pack(side="right")

    def on_search_change(self, *args):
        self.refresh_data()

    def refresh_data(self):
        self.after(0, self._do_refresh)

    def _do_refresh(self):
        if not self.winfo_exists(): return
        keyword = self.search_var.get().strip()
        self.listbox.delete(0, "end")
        history_data = self.db.get_history(keyword)
        if not history_data:
            display_text = "未找到相关记录" if keyword else "暂无历史记录"
            self.listbox.insert("end", display_text)
            return
        for row in history_data:
            try:
                dt = datetime.fromisoformat(row[3])
                time_str = dt.strftime("%H:%M") if dt.date() == datetime.now().date() else dt.strftime("%m/%d %H:%M")
                content = row[1].strip().replace("\n", " ")
                if len(content) > 30: content = content[:30] + "..."
                self.listbox.insert("end", f"[{time_str}] {content}")
            except:
                pass

    def on_double_click(self, event):
        selection = self.listbox.curselection()
        if not selection: return
        index = selection[0]
        keyword = self.search_var.get().strip()
        history = self.db.get_history(keyword)
        if index >= len(history): return
        self.restore_callback(history[index][1])

    def on_delete(self):
        selection = self.listbox.curselection()
        if not selection: return
        index = selection[0]
        keyword = self.search_var.get().strip()
        history = self.db.get_history(keyword)
        if index >= len(history): return
        if messagebox.askyesno("确认删除", "确定要永久删除这条记录吗？"):
            self.db.delete_draft(history[index][0])


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, db, watcher, app):
        super().__init__(parent)
        self.title("设置")
        self.geometry("480x650")  # 稍微调高一点
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
            pil_img = get_icon_image()
            self.tk_icon = ImageTk.PhotoImage(pil_img)
            self.iconphoto(True, self.tk_icon)
        except:
            pass

    def setup_general_ui(self):
        # 快捷键提示
        frame_hotkey = tk.Frame(self.page_general, bg=self.colors["bg"], pady=10)
        frame_hotkey.pack(fill="x", padx=20)
        tk.Label(frame_hotkey, text="全局快捷键: Ctrl + ~ (Backtick)",
                 bg=self.colors["bg"], fg="#4a90e2", font=("Arial", 10, "bold")).pack(anchor="w")

        # 开机启动
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

        # 主题
        frame_theme = tk.Frame(self.page_general, bg=self.colors["bg"], pady=20)
        frame_theme.pack(fill="x", padx=20)
        tk.Label(frame_theme, text="界面主题:", bg=self.colors["bg"], fg=self.colors["fg"]).pack(side="left")
        current_theme = self.db.get_setting("theme", "Deep")
        self.combo_theme = ttk.Combobox(frame_theme, values=["Deep", "Light"], state="readonly", width=10)
        self.combo_theme.set(current_theme)
        self.combo_theme.pack(side="left", padx=10)
        self.combo_theme.bind("<<ComboboxSelected>>", self.change_theme)

        # 透明度
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

        # --- 新增：字体大小 ---
        frame_font = tk.Frame(self.page_general, bg=self.colors["bg"], pady=10)
        frame_font.pack(fill="x", padx=20)
        tk.Label(frame_font, text="字体大小:", bg=self.colors["bg"], fg=self.colors["fg"]).pack(side="left")

        try:
            current_font_size = int(self.db.get_setting("font_size", str(DEFAULT_FONT_SIZE)))
        except:
            current_font_size = DEFAULT_FONT_SIZE

        self.scale_font = tk.Scale(frame_font, from_=8, to=30, resolution=1, orient="horizontal",
                                   bg=self.colors["bg"], fg=self.colors["fg"], highlightthickness=0,
                                   activebackground=self.colors["accent"], bd=0, length=200,
                                   command=self.on_font_change)
        self.scale_font.set(current_font_size)
        self.scale_font.pack(side="left", padx=10)

        # 退出习惯
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
        try:
            StartupManager.set_autostart(self.var_boot.get())
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def change_theme(self, event):
        theme_name = self.combo_theme.get()
        self.db.set_setting("theme", theme_name)
        self.app.switch_theme(theme_name)
        self.colors = self.app.colors
        self.configure(bg=self.colors["bg"])

    def on_alpha_change(self, value):
        self.db.set_setting("window_alpha", value)
        self.app.set_window_alpha(value)

    def on_font_change(self, value):
        """实时修改字体大小"""
        self.db.set_setting("font_size", value)
        self.app.set_font_size(value)

    def change_exit_pref(self, event):
        display_val = self.combo_exit.get()
        db_val = self.exit_map_rev.get(display_val, "ask")
        self.db.set_setting("exit_action", db_val)

    # 监控规则相关方法保持不变
    def setup_rules_ui(self):
        btn_frame = tk.Frame(self.page_rules, bg=self.colors["bg"], pady=5)
        btn_frame.pack(fill="x", padx=0)
        tk.Button(btn_frame, text="➕ 选择应用 (.exe)", command=self.add_exe, bg="#4a90e2", fg="white", relief="flat",
                  padx=10).pack(side="left", padx=5)
        tk.Button(btn_frame, text="➕ 添加网址/标题", command=self.add_title_keyword, bg=self.colors["accent"],
                  fg=self.colors["fg"], relief="flat", padx=10).pack(side="left", padx=5)
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
        if file_path: self.db.add_trigger('process', os.path.basename(
            file_path).lower()); self.watcher.reload_rules(); self.load_rules()

    def add_title_keyword(self):
        kw = simpledialog.askstring("添加关键词", "请输入标题关键词")
        if kw and kw.strip(): self.db.add_trigger('title', kw.strip()); self.watcher.reload_rules(); self.load_rules()

    def toggle_rule(self, rid, enabled):
        self.db.toggle_trigger(rid, enabled); self.watcher.reload_rules()

    def delete_rule(self, rid):
        if messagebox.askyesno("确认", "删除此规则？"): self.db.delete_trigger(
            rid); self.watcher.reload_rules(); self.load_rules()