import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import datetime
import os
from storage import StorageManager
from watcher import WindowWatcher

# --- 样式配置 ---
THEME_BG = "#1e1e1e"
THEME_FG = "#d4d4d4"
THEME_ACCENT = "#3c3c3c"
THEME_LIST_BG = "#252526"
THEME_LIST_FG = "#e0e0e0"
THEME_BTN_HOVER = "#505050"


class HistoryWindow(tk.Toplevel):
    """独立的时光机弹窗"""

    def __init__(self, parent, db, restore_callback):
        super().__init__(parent)
        self.title("时光机 - 历史归档")
        self.geometry("400x550")  # 稍微加高一点给按钮留空间
        self.configure(bg=THEME_BG)
        self.db = db
        self.restore_callback = restore_callback

        # 顶部说明
        lbl = tk.Label(self, text="双击记录可恢复 | 选中可删除", bg=THEME_BG, fg="#888888", pady=10)
        lbl.pack(side="top", fill="x")

        # 列表区域
        frame = tk.Frame(self, bg=THEME_BG)
        frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        self.scrollbar = ttk.Scrollbar(frame, orient="vertical")
        self.listbox = tk.Listbox(frame, bg=THEME_LIST_BG, fg=THEME_LIST_FG,
                                  relief="flat", highlightthickness=0,
                                  selectbackground="#4a90e2",
                                  yscrollcommand=self.scrollbar.set,
                                  font=("Consolas", 10))

        self.scrollbar.config(command=self.listbox.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True)

        self.listbox.bind("<Double-Button-1>", self.on_double_click)

        # --- 底部按钮区 (新增) ---
        btn_frame = tk.Frame(self, bg=THEME_BG, pady=10)
        btn_frame.pack(side="bottom", fill="x", padx=10)

        # 删除按钮
        tk.Button(btn_frame, text="🗑️ 删除选中", command=self.on_delete,
                  bg=THEME_BG, fg="#ff5555", relief="flat",
                  activebackground="#2d2d2d", activeforeground="#ff5555").pack(side="right")

        # 刷新数据
        self.refresh_data()

    def refresh_data(self):
        self.listbox.delete(0, "end")
        self.history_data = self.db.get_history()

        if not self.history_data:
            self.listbox.insert("end", "暂无历史记录")
            return

        for row in self.history_data:
            # row: (id, content, created_at, last_updated_at)
            try:
                dt_str = row[3]
                dt = datetime.fromisoformat(dt_str)
                if dt.date() == datetime.now().date():
                    time_str = dt.strftime("%H:%M")
                else:
                    time_str = dt.strftime("%m/%d %H:%M")

                content = row[1].strip().replace("\n", " ")
                if len(content) > 20:
                    content = content[:20] + "..."

                self.listbox.insert("end", f"[{time_str}] {content}")
            except Exception:
                pass

    def on_double_click(self, event):
        selection = self.listbox.curselection()
        if not selection: return
        index = selection[0]

        if index >= len(self.history_data): return

        content = self.history_data[index][1]
        self.restore_callback(content)

    def on_delete(self):
        """删除选中项逻辑"""
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一条记录")
            return

        index = selection[0]
        # 防止点击到"暂无记录"
        if index >= len(self.history_data): return

        # 获取数据库 ID (row[0] 是 id)
        draft_id = self.history_data[index][0]

        if messagebox.askyesno("确认删除", "确定要永久删除这条记录吗？"):
            self.db.delete_draft(draft_id)
            self.refresh_data()


class SettingsDialog(tk.Toplevel):
    """监控设置弹窗"""

    def __init__(self, parent, db, watcher):
        super().__init__(parent)
        self.title("监控规则设置")
        self.geometry("450x550")
        self.configure(bg=THEME_BG)
        self.db = db
        self.watcher = watcher

        header = tk.Label(self, text="配置 SafeDraft 自动弹出的触发条件", bg=THEME_BG, fg="#888888", pady=10)
        header.pack()

        btn_frame = tk.Frame(self, bg=THEME_BG, pady=5)
        btn_frame.pack(fill="x", padx=10)

        tk.Button(btn_frame, text="➕ 选择应用 (.exe)", command=self.add_exe,
                  bg="#4a90e2", fg="white", relief="flat", padx=10).pack(side="left", padx=5)

        tk.Button(btn_frame, text="➕ 添加网址/标题", command=self.add_title_keyword,
                  bg=THEME_ACCENT, fg=THEME_FG, relief="flat", padx=10).pack(side="left", padx=5)

        list_frame = tk.Frame(self, bg=THEME_BG)
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(list_frame, bg=THEME_BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=THEME_BG)

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
            row = tk.Frame(self.scrollable_frame, bg=THEME_BG, pady=2)
            row.pack(fill="x")

            var = tk.BooleanVar(value=bool(enabled))
            cb = tk.Checkbutton(row, variable=var, bg=THEME_BG, selectcolor=THEME_ACCENT,
                                activebackground=THEME_BG,
                                command=lambda i=rid, v=var: self.toggle_rule(i, v.get()))
            cb.pack(side="left")

            type_color = "#d35400" if rtype == 'process' else "#2980b9"
            type_text = "[应用]" if rtype == 'process' else "[标题]"
            tk.Label(row, text=type_text, fg=type_color, bg=THEME_BG, width=6, anchor="w").pack(side="left")
            tk.Label(row, text=val, fg=THEME_FG, bg=THEME_BG).pack(side="left")

            del_btn = tk.Label(row, text="×", fg="#ff5555", bg=THEME_BG, cursor="hand2", font=("Arial", 12))
            del_btn.pack(side="right", padx=10)
            del_btn.bind("<Button-1>", lambda e, i=rid: self.delete_rule(i))

    def add_exe(self):
        file_path = filedialog.askopenfilename(title="选择要监控的执行文件", filetypes=[("Executables", "*.exe")])
        if file_path:
            exe_name = os.path.basename(file_path).lower()
            self.db.add_trigger('process', exe_name)
            self.watcher.reload_rules()
            self.load_rules()

    def add_title_keyword(self):
        kw = simpledialog.askstring("添加关键词", "请输入窗口标题包含的关键词\n(例如: GitHub)")
        if kw and kw.strip():
            self.db.add_trigger('title', kw.strip())
            self.watcher.reload_rules()
            self.load_rules()

    def toggle_rule(self, rid, enabled):
        self.db.toggle_trigger(rid, enabled)
        self.watcher.reload_rules()

    def delete_rule(self, rid):
        if messagebox.askyesno("确认", "删除此监控规则？"):
            self.db.delete_trigger(rid)
            self.watcher.reload_rules()
            self.load_rules()


class SafeDraftApp:
    def __init__(self, root):
        self.root = root
        self.db = StorageManager()
        self.watcher = WindowWatcher(self.db, self.on_trigger_detected)
        self.watcher.start()

        self.setup_window()
        self.setup_ui()
        self.setup_events()

        self.is_topmost = False
        self.topmost_timer = None

    def setup_window(self):
        self.root.title("SafeDraft")
        self.root.geometry("500x400+100+100")
        self.root.configure(bg=THEME_BG)
        self.root.attributes("-alpha", 0.95)

    def setup_ui(self):
        # Toolbar
        self.toolbar = tk.Frame(self.root, bg=THEME_BG, height=40)
        self.toolbar.pack(fill="x", padx=5, pady=5)

        self.btn_save = tk.Button(self.toolbar, text="💾 保存并清空", command=self.manual_save,
                                  bg=THEME_ACCENT, fg=THEME_FG, relief="flat", padx=10)
        self.btn_save.pack(side="left", padx=5)

        self.btn_settings = tk.Button(self.toolbar, text="⚙️ 监控规则", command=self.open_settings,
                                      bg=THEME_ACCENT, fg=THEME_FG, relief="flat", padx=10)
        self.btn_settings.pack(side="left", padx=5)

        self.btn_history = tk.Button(self.toolbar, text="🕒 时光机", command=self.open_history,
                                     bg=THEME_ACCENT, fg=THEME_FG, relief="flat", padx=10)
        self.btn_history.pack(side="right", padx=5)

        self.btn_top = tk.Button(self.toolbar, text="📌 临时置顶", command=self.toggle_manual_topmost,
                                 bg=THEME_ACCENT, fg=THEME_FG, relief="flat", padx=10)
        self.btn_top.pack(side="right", padx=5)

        # Text Area
        self.text_frame = tk.Frame(self.root, bg=THEME_BG, padx=5, pady=5)
        self.text_frame.pack(fill="both", expand=True)

        self.text_area = tk.Text(self.text_frame, bg=THEME_BG, fg=THEME_FG, insertbackground="white",
                                 relief="flat", font=("Consolas", 12), undo=True, wrap="word", padx=10, pady=10)
        self.text_area.pack(fill="both", expand=True)

    def setup_events(self):
        self.text_area.bind("<KeyRelease>", self.on_key_release)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

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

        self._flash_btn(self.btn_save, "已归档 ✔", "#4caf50")

    def _flash_btn(self, btn, text, color):
        orig_text = "💾 保存并清空"
        orig_fg = THEME_FG
        btn.config(text=text, fg=color)
        self.root.after(1000, lambda: btn.config(text=orig_text, fg=orig_fg))

    def open_history(self):
        HistoryWindow(self.root, self.db, self.restore_draft_content)

    def restore_draft_content(self, content):
        if messagebox.askyesno("恢复确认", "确定要覆盖当前输入框的内容吗？"):
            self.text_area.delete("1.0", "end")
            self.text_area.insert("1.0", content)
            self.db.current_session_id = None
            self.text_area.focus_set()

    def open_settings(self):
        SettingsDialog(self.root, self.db, self.watcher)

    def on_trigger_detected(self):
        self.root.after(0, self._perform_auto_pop)

    def _perform_auto_pop(self):
        if self.is_topmost and not self.topmost_timer: return
        if self.root.state() == 'iconic': self.root.deiconify()
        if self.root.focus_displayof() is None:
            self.root.geometry("+100+100")
        self._start_auto_topmost()

    def _start_auto_topmost(self):
        self.is_topmost = True
        self.root.attributes('-topmost', True)
        self.btn_top.config(text="📌 锁定(2m)", bg="#d35400", fg="white")
        if self.topmost_timer: self.root.after_cancel(self.topmost_timer)
        self.topmost_timer = self.root.after(120000, self._cancel_topmost)

    def _cancel_topmost(self):
        self.is_topmost = False
        self.topmost_timer = None
        self.root.attributes('-topmost', False)
        self.btn_top.config(text="📌 临时置顶", bg=THEME_ACCENT, fg=THEME_FG)

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

    def on_close(self):
        self.watcher.stop()
        self.db.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = SafeDraftApp(root)
    root.mainloop()