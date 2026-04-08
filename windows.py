import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import datetime
from PIL import ImageTk
import os
import threading
import json

# 导入工具模块
from utils import get_icon_image, StartupManager, DEFAULT_FONT_SIZE, DEFAULT_STICKY_TITLE_SIZE, DEFAULT_STICKY_CONTENT_SIZE


class HistoryWindow(tk.Toplevel):
    def __init__(self, parent, db, restore_callback, theme):
        super().__init__(parent)
        self.title("历史归档")

        # 窗口大小 - 加宽以容纳预览区
        self.geometry("900x700")

        self.db = db
        self.restore_callback = restore_callback
        self.colors = theme
        self.history_data = []  # 缓存历史数据

        val = self.db.get_setting("quick_restore", "0")
        self.quick_restore_var = tk.BooleanVar(value=(val == "1"))

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
        # 1. 顶部栏
        top_bar = tk.Frame(self, bg=self.colors["bg"], pady=5)
        top_bar.pack(side="top", fill="x", padx=10)

        lbl = tk.Label(top_bar, text="单击预览 | 双击恢复到主窗口", bg=self.colors["bg"], fg="#888888")
        lbl.pack(side="left")

        # 2. 搜索栏
        search_frame = tk.Frame(self, bg=self.colors["bg"], pady=5, padx=10)
        search_frame.pack(side="top", fill="x")
        tk.Label(search_frame, text="🔍", bg=self.colors["bg"], fg="#888888").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self.on_search_change)
        self.entry_search = tk.Entry(search_frame, textvariable=self.search_var,
                                     bg=self.colors["list_bg"], fg=self.colors["list_fg"],
                                     relief="flat", insertbackground=self.colors["list_fg"])
        self.entry_search.pack(side="left", fill="x", expand=True, padx=5)

        # 3. 主内容区（使用 PanedWindow 实现可拖动调整）
        paned = tk.PanedWindow(self, orient="horizontal", bg=self.colors["bg"],
                               sashwidth=8, sashrelief="raised", sashpad=2)
        paned.pack(fill="both", expand=True, padx=10, pady=(5, 5))

        # 左侧：列表区
        left_frame = tk.Frame(paned, bg=self.colors["bg"])
        left_frame.pack_propagate(False)

        self.scrollbar = ttk.Scrollbar(left_frame, orient="vertical")
        list_font = ("Consolas", max(9, self.font_size - 2))
        self.listbox = tk.Listbox(left_frame, bg=self.colors["list_bg"], fg=self.colors["list_fg"],
                                  relief="flat", highlightthickness=0, selectbackground="#4a90e2",
                                  yscrollcommand=self.scrollbar.set, font=list_font, width=35)
        self.scrollbar.config(command=self.listbox.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True)

        # 单击预览
        self.listbox.bind("<<ListboxSelect>>", self.on_select_preview)
        # 双击恢复
        self.listbox.bind("<Double-Button-1>", self.on_double_click)

        # 右侧：预览区
        right_frame = tk.Frame(paned, bg=self.colors["bg"])

        # 预览区标题
        preview_title = tk.Label(right_frame, text="📄 内容预览", bg=self.colors["bg"],
                                 fg="#888888", font=("Arial", 10, "bold"), anchor="w")
        preview_title.pack(fill="x", pady=(0, 5))

        # 预览文本框
        self.preview_text = tk.Text(right_frame, bg=self.colors["text_bg"], fg=self.colors["text_fg"],
                                    relief="flat", wrap="word", font=("Consolas", self.font_size),
                                    padx=10, pady=10)
        self.preview_text.pack(fill="both", expand=True)
        self.preview_text.config(state="disabled")  # 只读

        # 添加到 PanedWindow
        paned.add(left_frame, width=350, minsize=200)
        paned.add(right_frame, minsize=300)

        # 4. 底部功能按钮区
        btn_frame = tk.Frame(self, bg=self.colors["bg"], pady=10)
        btn_frame.pack(side="bottom", fill="x", padx=10)

        chk_quick = tk.Checkbutton(btn_frame, text="双击直接恢复", variable=self.quick_restore_var,
                                   bg=self.colors["bg"], fg="#888888", selectcolor=self.colors["accent"],
                                   activebackground=self.colors["bg"], activeforeground="#888888",
                                   command=self.on_toggle_quick_restore)
        chk_quick.pack(side="left")

        # 恢复按钮
        tk.Button(btn_frame, text="📥 恢复到主窗口", command=self.on_restore_clicked,
                  bg="#4a90e2", fg="white", relief="flat", padx=8).pack(side="right", padx=2)

        # 按钮 A: 删除 (最右)
        tk.Button(btn_frame, text="🗑️ 删除", command=self.on_delete,
                  bg=self.colors["bg"], fg="#ff5555", relief="flat", padx=8,
                  activebackground=self.colors["accent"], activeforeground="#ff5555").pack(side="right", padx=2)

        # 按钮 B: 清理重复
        tk.Button(btn_frame, text="🧹 去重", command=self.on_deduplicate,
                  bg=self.colors["bg"], fg=self.colors["fg"], relief="flat", padx=8,
                  activebackground=self.colors["accent"], activeforeground=self.colors["fg"]).pack(side="right", padx=2)

        # 按钮 C: 存为笔记
        tk.Button(btn_frame, text="⭐ 存笔记", command=self.on_save_to_note,
                  bg="#f1c40f", fg="white", relief="flat", padx=8).pack(side="right", padx=2)

    def on_select_preview(self, event):
        """单击时在右侧预览区显示内容"""
        selection = self.listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self.history_data):
            return
        content = self.history_data[index][1]
        self.show_preview(content)

    def show_preview(self, content):
        """在预览区显示内容"""
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", content)
        self.preview_text.config(state="disabled")

    def on_restore_clicked(self):
        """点击恢复按钮"""
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        index = selection[0]
        if index >= len(self.history_data):
            return
        content = self.history_data[index][1]
        if self.quick_restore_var.get():
            self.restore_callback(content)
        else:
            if messagebox.askyesno("恢复确认", "确定要恢复到主窗口吗？"):
                self.restore_callback(content)

    def on_deduplicate(self):
        if messagebox.askyesno("清理确认", "确定要扫描并删除所有内容重复的记录吗？\n\n仅保留最新的一条记录。"):
            try:
                count = self.db.deduplicate_drafts()
                if count > 0:
                    messagebox.showinfo("完成", f"清理成功！\n共删除了 {count} 条重复记录。")
                else:
                    messagebox.showinfo("完成", "没有发现重复记录，列表很干净。")
                self.refresh_data()
            except Exception as e:
                messagebox.showerror("错误", f"清理失败: {str(e)}")

    def on_save_to_note(self):
        selection = self.listbox.curselection()
        if not selection: return
        index = selection[0]
        if index >= len(self.history_data): return

        draft_id, content, created_at, _ = self.history_data[index]

        # 1. 获取文件夹列表
        folders = self.db.get_folders()
        if not folders:
            if messagebox.askyesno("提示", "还没有笔记文件夹，是否立即创建一个？"):
                name = simpledialog.askstring("新建文件夹", "名称:")
                if name:
                    fid = self.db.create_folder(name)
                    folders = [(fid, name)]
                else:
                    return
            else:
                return

        # 2. 选择文件夹弹窗
        select_win = tk.Toplevel(self)
        select_win.title("选择目标文件夹")
        select_win.geometry("300x400")
        select_win.configure(bg=self.colors["bg"])

        # 居中显示
        self.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - 300) // 2
        y = self.winfo_rooty() + (self.winfo_height() - 400) // 2
        select_win.geometry(f"+{x}+{y}")

        tk.Label(select_win, text="请选择要保存到的文件夹:", bg=self.colors["bg"], fg=self.colors["fg"],
                 pady=10).pack()

        lb = tk.Listbox(select_win, bg=self.colors["list_bg"], fg=self.colors["list_fg"], relief="flat")
        lb.pack(fill="both", expand=True, padx=10, pady=5)

        folder_map = []
        for fid, fname in folders:
            lb.insert("end", f"📁 {fname}")
            folder_map.append(fid)

        def _confirm():
            sel = lb.curselection()
            if not sel: return
            target_fid = folder_map[sel[0]]

            # 生成标题
            title = content.strip().split('\n')[0][:20]
            if len(content) > 20: title += "..."

            # 执行保存
            self.db.create_note(target_fid, title, content, source_draft_id=draft_id)
            select_win.destroy()

            # 检查配置，决定是否弹窗
            if self.db.get_setting("show_note_success_msg", "1") == "1":
                self.show_success_dialog(title)

        tk.Button(select_win, text="确定", command=_confirm, bg=self.colors["accent"], fg=self.colors["fg"]).pack(
            pady=10)

    def show_success_dialog(self, title):
        dlg = tk.Toplevel(self)
        dlg.title("成功")
        dlg.geometry("380x160")
        dlg.resizable(False, False)
        dlg.configure(bg=self.colors["bg"])

        # 相对于父窗口居中
        self.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - 380) // 2
        y = self.winfo_rooty() + (self.winfo_height() - 160) // 2
        dlg.geometry(f"+{x}+{y}")

        # 内容区域
        frame_content = tk.Frame(dlg, bg=self.colors["bg"], padx=20, pady=20)
        frame_content.pack(fill="both", expand=True)

        # 图标 (用 Label 模拟)
        lbl_icon = tk.Label(frame_content, text="ℹ️", font=("Arial", 24),
                            bg=self.colors["bg"], fg="#4a90e2")
        lbl_icon.pack(side="left", anchor="n", padx=(0, 15))

        # 消息文本
        msg = f"已保存到笔记！\n标题: {title}"
        lbl_msg = tk.Label(frame_content, text=msg, justify="left", wraplength=260,
                           bg=self.colors["bg"], fg=self.colors["fg"], font=("Arial", 10))
        lbl_msg.pack(side="left", fill="both", expand=True)

        # 底部按钮区域
        frame_bottom = tk.Frame(dlg, bg=self.colors["list_bg"], padx=15, pady=10)
        frame_bottom.pack(side="bottom", fill="x")

        # 复选框：不再提示
        var_skip = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(frame_bottom, text="下次不再提示", variable=var_skip,
                             bg=self.colors["list_bg"], fg=self.colors["fg"],
                             selectcolor=self.colors["accent"],
                             activebackground=self.colors["list_bg"],
                             activeforeground=self.colors["fg"])
        chk.pack(side="left")

        # 确定按钮
        def on_ok():
            if var_skip.get():
                self.db.set_setting("show_note_success_msg", "0")
            dlg.destroy()

        btn_ok = tk.Button(frame_bottom, text="确定", command=on_ok,
                           bg=self.colors["accent"], fg=self.colors["fg"], relief="flat", width=8)
        btn_ok.pack(side="right")

        dlg.transient(self)
        dlg.grab_set()
        self.wait_window(dlg)

    def on_toggle_quick_restore(self):
        val = "1" if self.quick_restore_var.get() else "0"
        self.db.set_setting("quick_restore", val)

    def on_search_change(self, *args):
        self.refresh_data()

    def refresh_data(self):
        self.after(0, self._do_refresh)

    def _do_refresh(self):
        if not self.winfo_exists(): return
        keyword = self.search_var.get().strip()
        self.listbox.delete(0, "end")
        self.history_data = self.db.get_history(keyword)
        if not self.history_data:
            display_text = "未找到相关记录" if keyword else "暂无历史记录"
            self.listbox.insert("end", display_text)
            return
        for row in self.history_data:
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
        if index >= len(self.history_data): return
        content = self.history_data[index][1]
        if self.quick_restore_var.get():
            self.restore_callback(content)
        else:
            if messagebox.askyesno("恢复确认", "确定要覆盖当前输入框的内容吗？"):
                self.restore_callback(content)

    def on_delete(self):
        selection = self.listbox.curselection()
        if not selection: return
        index = selection[0]
        if index >= len(self.history_data): return
        if messagebox.askyesno("确认删除", "确定要永久删除这条记录吗？"):
            self.db.delete_draft(self.history_data[index][0])


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, db, watcher, app):
        super().__init__(parent)
        self.title("设置")
        self.geometry("480x650")
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

        # 新增：服务器同步
        self.page_sync = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(self.page_sync, text=" 服务器同步 ")
        self.setup_sync_ui()

        self.page_general = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(self.page_general, text=" 常规设置 ")
        self.setup_general_ui()

        # 便签设置
        self.page_sticky = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.notebook.add(self.page_sticky, text=" 便签设置 ")
        self.setup_sticky_ui()

    def load_icon(self):
        try:
            pil_img = get_icon_image()
            self.tk_icon = ImageTk.PhotoImage(pil_img)
            self.iconphoto(True, self.tk_icon)
        except:
            pass

    def setup_sync_ui(self):
        f = tk.Frame(self.page_sync, bg=self.colors["bg"], padx=20, pady=20)
        f.pack(fill="both", expand=True)

        tk.Label(f, text="服务器同步设置 (SSH/SCP)",
                 bg=self.colors["bg"], fg="#4a90e2", font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 10))

        # 开关
        is_enabled = self.db.get_setting("ssh_enabled", "0") == "1"
        self.var_ssh_enabled = tk.BooleanVar(value=is_enabled)
        chk = tk.Checkbutton(f, text="启用服务器同步功能", variable=self.var_ssh_enabled,
                             bg=self.colors["bg"], fg=self.colors["fg"], selectcolor=self.colors["accent"],
                             activebackground=self.colors["bg"], activeforeground=self.colors["fg"],
                             command=self.toggle_ssh_enabled)
        chk.pack(anchor="w", pady=(0, 15))

        # Grid布局
        grid_frame = tk.Frame(f, bg=self.colors["bg"])
        grid_frame.pack(fill="x")

        # 1. IP
        tk.Label(grid_frame, text="服务器 IP (user@ip):", bg=self.colors["bg"], fg=self.colors["fg"]).grid(row=0, column=0, sticky="w", pady=5)
        self.entry_ssh_ip = tk.Entry(grid_frame, bg=self.colors["list_bg"], fg=self.colors["list_fg"], insertbackground=self.colors["fg"])
        self.entry_ssh_ip.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        self.entry_ssh_ip.insert(0, self.db.get_setting("ssh_ip", ""))
        # 绑定保存
        self.entry_ssh_ip.bind("<FocusOut>", lambda e: self.db.set_setting("ssh_ip", self.entry_ssh_ip.get().strip()))

        # 2. Path
        tk.Label(grid_frame, text="远程目录路径:", bg=self.colors["bg"], fg=self.colors["fg"]).grid(row=1, column=0, sticky="w", pady=5)
        self.entry_ssh_path = tk.Entry(grid_frame, bg=self.colors["list_bg"], fg=self.colors["list_fg"], insertbackground=self.colors["fg"])
        self.entry_ssh_path.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        self.entry_ssh_path.insert(0, self.db.get_setting("ssh_path", "/tmp"))
        # 绑定保存
        self.entry_ssh_path.bind("<FocusOut>", lambda e: self.db.set_setting("ssh_path", self.entry_ssh_path.get().strip()))

        grid_frame.columnconfigure(1, weight=1)

        tk.Label(f, text="* 请确保本地已配置 SSH 公钥免密登录到服务器。\n* 启用后，主界面将显示上传/下载按钮。",
                 bg=self.colors["bg"], fg="#888888", justify="left").pack(anchor="w", pady=20)

        # --- 自动同步设置 ---
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=15)

        tk.Label(f, text="自动同步设置",
                 bg=self.colors["bg"], fg="#4a90e2", font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 10))

        config = self._load_sync_config()

        # 启用自动同步
        self.var_auto_sync = tk.BooleanVar(value=config.get("auto_sync_enabled", False))
        chk_auto = tk.Checkbutton(f, text="启用自动同步",
                                  variable=self.var_auto_sync,
                                  bg=self.colors["bg"], fg=self.colors["fg"],
                                  selectcolor=self.colors["accent"],
                                  activebackground=self.colors["bg"],
                                  activeforeground=self.colors["fg"])
        chk_auto.pack(anchor="w", pady=(0, 10))

        # 时间段
        time_frame = tk.Frame(f, bg=self.colors["bg"])
        time_frame.pack(fill="x", pady=5)

        tk.Label(time_frame, text="活跃时间段:", bg=self.colors["bg"],
                 fg=self.colors["fg"]).grid(row=0, column=0, sticky="w", pady=5)

        tk.Label(time_frame, text="开始:", bg=self.colors["bg"],
                 fg=self.colors["fg"]).grid(row=0, column=1, padx=(10, 2))
        self.entry_sync_start = tk.Entry(time_frame, width=6,
                                        bg=self.colors["list_bg"], fg=self.colors["list_fg"],
                                        insertbackground=self.colors["fg"])
        self.entry_sync_start.insert(0, config.get("active_time_start", "09:00"))
        self.entry_sync_start.grid(row=0, column=2, pady=5)

        tk.Label(time_frame, text="结束:", bg=self.colors["bg"],
                 fg=self.colors["fg"]).grid(row=0, column=3, padx=(10, 2))
        self.entry_sync_end = tk.Entry(time_frame, width=6,
                                       bg=self.colors["list_bg"], fg=self.colors["list_fg"],
                                       insertbackground=self.colors["fg"])
        self.entry_sync_end.insert(0, config.get("active_time_end", "22:00"))
        self.entry_sync_end.grid(row=0, column=4, pady=5)

        # 间隔
        interval_frame = tk.Frame(f, bg=self.colors["bg"])
        interval_frame.pack(fill="x", pady=5)

        tk.Label(interval_frame, text="检查间隔(分钟):", bg=self.colors["bg"],
                 fg=self.colors["fg"]).pack(side="left")
        self.spin_interval = tk.Spinbox(interval_frame, from_=5, to=60, increment=5, width=5,
                                        bg=self.colors["list_bg"], fg=self.colors["list_fg"])
        self.spin_interval.delete(0, "end")
        self.spin_interval.insert(0, str(config.get("sync_interval_minutes", 10)))
        self.spin_interval.pack(side="left", padx=10)

        # 保存按钮
        tk.Button(f, text="保存自动同步配置", command=self._save_sync_config,
                  bg="#4a90e2", fg="white", relief="flat", padx=10).pack(anchor="w", pady=15)

        tk.Label(f, text="* 自动同步需要先启用SSH同步并正确配置服务器信息。\n"
                         "* 活跃时间段格式: HH:MM (24小时制)，留空表示全天候。",
                 bg=self.colors["bg"], fg="#888888", justify="left").pack(anchor="w")

    def _load_sync_config(self):
        """读取 sync_config.json"""
        config_path = os.path.join(self.db.base_path, "sync_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "auto_sync_enabled": False,
            "sync_interval_minutes": 10,
            "active_time_start": "09:00",
            "active_time_end": "22:00"
        }

    def _save_sync_config(self):
        """保存自动同步配置到 JSON 文件"""
        # 验证时间格式
        start_str = self.entry_sync_start.get().strip()
        end_str = self.entry_sync_end.get().strip()
        for val, name in [(start_str, "开始时间"), (end_str, "结束时间")]:
            if val:
                try:
                    parts = val.split(":")
                    if len(parts) != 2:
                        raise ValueError
                    h, m = int(parts[0]), int(parts[1])
                    if not (0 <= h <= 23 and 0 <= m <= 59):
                        raise ValueError
                except (ValueError, IndexError):
                    messagebox.showerror("格式错误", f"{name}格式应为 HH:MM（如 09:00）")
                    return

        # 验证间隔
        try:
            interval = int(self.spin_interval.get())
            if not (1 <= interval <= 120):
                raise ValueError
        except ValueError:
            messagebox.showerror("格式错误", "检查间隔应为 1-120 之间的整数")
            return

        config = {
            "auto_sync_enabled": self.var_auto_sync.get(),
            "sync_interval_minutes": interval,
            "active_time_start": start_str,
            "active_time_end": end_str
        }

        config_path = os.path.join(self.db.base_path, "sync_config.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("成功", "自动同步配置已保存")

    def toggle_ssh_enabled(self):
        val = "1" if self.var_ssh_enabled.get() else "0"
        self.db.set_setting("ssh_enabled", val)

    def setup_general_ui(self):
        # 快捷键
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

        # 字体大小
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
        theme_name = self.combo_theme.get();
        self.db.set_setting("theme", theme_name)
        self.app.switch_theme(theme_name)
        self.colors = self.app.colors;
        self.configure(bg=self.colors["bg"])

    def on_alpha_change(self, value):
        self.db.set_setting("window_alpha", value);
        self.app.set_window_alpha(value)

    def on_font_change(self, value):
        self.db.set_setting("font_size", value);
        self.app.set_font_size(value)

    def change_exit_pref(self, event):
        display_val = self.combo_exit.get();
        db_val = self.exit_map_rev.get(display_val, "ask")
        self.db.set_setting("exit_action", db_val)

    def setup_rules_ui(self):
        # 1. 全局开关
        frame_master = tk.Frame(self.page_rules, bg=self.colors["bg"], pady=10)
        frame_master.pack(fill="x", padx=10)
        current_master = self.db.get_setting("master_monitor", "1")
        self.var_master = tk.BooleanVar(value=(current_master == "1"))
        cb_master = tk.Checkbutton(frame_master, text="启用智能感知 (自动弹出)", variable=self.var_master,
                                   bg=self.colors["bg"], fg=self.colors["fg"], selectcolor=self.colors["accent"],
                                   activebackground=self.colors["bg"], activeforeground=self.colors["fg"],
                                   font=("Arial", 10, "bold"), command=self.toggle_master_monitor)
        cb_master.pack(anchor="w")
        tk.Label(frame_master, text="关闭后，软件将不会自动弹出，但快捷键依然可用。",
                 bg=self.colors["bg"], fg="#888888", font=("Arial", 9)).pack(anchor="w", padx=24)
        ttk.Separator(self.page_rules, orient="horizontal").pack(fill="x", padx=10, pady=5)

        # 2. 按钮
        btn_frame = tk.Frame(self.page_rules, bg=self.colors["bg"], pady=5)
        btn_frame.pack(fill="x", padx=0)
        tk.Button(btn_frame, text="➕ 选择应用 (.exe)", command=self.add_exe, bg="#4a90e2", fg="white", relief="flat",
                  padx=10).pack(side="left", padx=5)
        tk.Button(btn_frame, text="➕ 添加网址/标题", command=self.add_title_keyword, bg=self.colors["accent"],
                  fg=self.colors["fg"], relief="flat", padx=10).pack(side="left", padx=5)

        # 3. 列表
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

    def toggle_master_monitor(self):
        val = "1" if self.var_master.get() else "0"
        self.db.set_setting("master_monitor", val)

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
        self.db.toggle_trigger(rid, enabled);
        self.watcher.reload_rules()

    def delete_rule(self, rid):
        if messagebox.askyesno("确认", "删除此规则？"): self.db.delete_trigger(
            rid); self.watcher.reload_rules(); self.load_rules()

    def setup_sticky_ui(self):
        f = tk.Frame(self.page_sticky, bg=self.colors["bg"], padx=20, pady=20)
        f.pack(fill="both", expand=True)

        tk.Label(f, text="便签字体设置",
                 bg=self.colors["bg"], fg="#4a90e2", font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 15))

        # 标题字体大小
        frame_title = tk.Frame(f, bg=self.colors["bg"])
        frame_title.pack(fill="x", pady=5)
        tk.Label(frame_title, text="标题字体大小:", bg=self.colors["bg"], fg=self.colors["fg"]).pack(side="left")
        try:
            current_title_size = int(self.db.get_setting("sticky_title_size", str(DEFAULT_STICKY_TITLE_SIZE)))
        except:
            current_title_size = DEFAULT_STICKY_TITLE_SIZE
        self.scale_sticky_title = tk.Scale(frame_title, from_=8, to=20, resolution=1, orient="horizontal",
                                            bg=self.colors["bg"], fg=self.colors["fg"], highlightthickness=0,
                                            activebackground=self.colors["accent"], bd=0, length=150,
                                            command=self.on_sticky_title_change)
        self.scale_sticky_title.set(current_title_size)
        self.scale_sticky_title.pack(side="left", padx=10)

        # 内容字体大小
        frame_content = tk.Frame(f, bg=self.colors["bg"])
        frame_content.pack(fill="x", pady=5)
        tk.Label(frame_content, text="内容字体大小:", bg=self.colors["bg"], fg=self.colors["fg"]).pack(side="left")
        try:
            current_content_size = int(self.db.get_setting("sticky_content_size", str(DEFAULT_STICKY_CONTENT_SIZE)))
        except:
            current_content_size = DEFAULT_STICKY_CONTENT_SIZE
        self.scale_sticky_content = tk.Scale(frame_content, from_=8, to=24, resolution=1, orient="horizontal",
                                              bg=self.colors["bg"], fg=self.colors["fg"], highlightthickness=0,
                                              activebackground=self.colors["accent"], bd=0, length=150,
                                              command=self.on_sticky_content_change)
        self.scale_sticky_content.set(current_content_size)
        self.scale_sticky_content.pack(side="left", padx=10)

    def on_sticky_title_change(self, value):
        self.db.set_setting("sticky_title_size", value)

    def on_sticky_content_change(self, value):
        self.db.set_setting("sticky_content_size", value)