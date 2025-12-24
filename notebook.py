import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import datetime
from PIL import ImageTk
import threading

# 导入工具
from utils import get_icon_image, DEFAULT_FONT_SIZE


class NotebookWindow(tk.Toplevel):
    def __init__(self, parent, db, theme):
        super().__init__(parent)
        self.title("SafeDraft 笔记")
        self.geometry("1000x700")
        self.db = db
        self.colors = theme

        # 状态变量
        self.current_folder_uuid = None  # None 表示"所有笔记"
        self.current_note_uuid = None
        self.is_dirty = False  # 内容是否有变更未保存
        self.save_timer = None

        try:
            self.font_size = int(self.db.get_setting("font_size", str(DEFAULT_FONT_SIZE)))
        except:
            self.font_size = DEFAULT_FONT_SIZE

        self.configure(bg=self.colors["bg"])
        self.load_icon()
        self.setup_ui()
        self.load_folders()
        self.load_notes_list()

        # 绑定事件
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def load_icon(self):
        try:
            pil_img = get_icon_image()
            self.tk_icon = ImageTk.PhotoImage(pil_img)
            self.iconphoto(True, self.tk_icon)
        except:
            pass

    def setup_ui(self):
        # 使用 PanedWindow 实现可拖动的三栏布局
        self.paned = tk.PanedWindow(self, orient="horizontal", bg=self.colors["bg"], sashwidth=4, sashrelief="flat")
        self.paned.pack(fill="both", expand=True)

        # ==========================================
        # 1. 左栏：文件夹
        # ==========================================
        self.frame_left = tk.Frame(self.paned, bg=self.colors["list_bg"], width=200)
        self.paned.add(self.frame_left, minsize=150)

        # 左栏顶部标题
        lbl_folders = tk.Label(self.frame_left, text="📂 文件夹", bg=self.colors["list_bg"],
                               fg="#888888", font=("Arial", 10, "bold"), pady=10)
        lbl_folders.pack(side="top", anchor="w", padx=10)

        # 文件夹列表 (Treeview)
        style = ttk.Style()
        style.theme_use('clam')
        # 配置 Treeview 颜色以适应深色/浅色主题
        style.configure("Treeview",
                        background=self.colors["list_bg"],
                        fieldbackground=self.colors["list_bg"],
                        foreground=self.colors["list_fg"],
                        borderwidth=0)
        style.map("Treeview",
                  background=[('selected', self.colors["accent"])],
                  foreground=[('selected', self.colors["fg"])])

        self.tree_folders = ttk.Treeview(self.frame_left, show="tree", selectmode="browse")
        self.tree_folders.pack(fill="both", expand=True, padx=5)
        self.tree_folders.bind("<<TreeviewSelect>>", self.on_folder_select)

        # 左栏底部操作按钮 (新建/重命名/删除文件夹)
        btn_frame_left = tk.Frame(self.frame_left, bg=self.colors["list_bg"], pady=5)
        btn_frame_left.pack(side="bottom", fill="x")

        tk.Button(btn_frame_left, text="➕", command=self.add_folder, relief="flat",
                  bg=self.colors["list_bg"], fg=self.colors["fg"]).pack(side="left", fill="x", expand=True)
        tk.Button(btn_frame_left, text="✏️", command=self.rename_folder, relief="flat",
                  bg=self.colors["list_bg"], fg=self.colors["fg"]).pack(side="left", fill="x", expand=True)
        tk.Button(btn_frame_left, text="🗑️", command=self.delete_folder, relief="flat",
                  bg=self.colors["list_bg"], fg="#ff5555").pack(side="left", fill="x", expand=True)

        # ==========================================
        # 2. 中栏：笔记列表
        # ==========================================
        self.frame_mid = tk.Frame(self.paned, bg=self.colors["bg"], width=250)
        self.paned.add(self.frame_mid, minsize=200)

        # 搜索框
        search_frame = tk.Frame(self.frame_mid, bg=self.colors["bg"], pady=5, padx=5)
        search_frame.pack(side="top", fill="x")
        self.entry_search = tk.Entry(search_frame, bg=self.colors["list_bg"], fg=self.colors["list_fg"],
                                     relief="flat", insertbackground=self.colors["list_fg"])
        self.entry_search.pack(fill="x", ipady=3)
        self.entry_search.bind("<KeyRelease>", self.on_search)

        # 笔记列表 (Listbox)
        self.list_notes = tk.Listbox(self.frame_mid, bg=self.colors["list_bg"], fg=self.colors["list_fg"],
                                     relief="flat", highlightthickness=0, selectbackground=self.colors["accent"],
                                     font=("Arial", 10))
        self.list_notes.pack(fill="both", expand=True, padx=5, pady=5)
        self.list_notes.bind("<<ListboxSelect>>", self.on_note_select)

        # 新建笔记按钮
        self.btn_add_note = tk.Button(self.frame_mid, text="➕ 新建笔记", command=self.add_note,
                                      bg=self.colors["accent"], fg=self.colors["fg"], relief="flat", pady=5)
        self.btn_add_note.pack(side="bottom", fill="x", padx=5, pady=5)

        # ==========================================
        # 3. 右栏：编辑器
        # ==========================================
        self.frame_right = tk.Frame(self.paned, bg=self.colors["bg"], width=500)
        self.paned.add(self.frame_right, minsize=300)

        # 标题栏
        self.entry_title = tk.Entry(self.frame_right, font=("Arial", 14, "bold"),
                                    bg=self.colors["bg"], fg=self.colors["fg"],
                                    relief="flat", insertbackground=self.colors["fg"])
        self.entry_title.pack(side="top", fill="x", padx=15, pady=(15, 5))
        self.entry_title.bind("<KeyRelease>", self.on_content_change)

        # 分割线
        ttk.Separator(self.frame_right, orient="horizontal").pack(fill="x", padx=15, pady=5)

        # 正文编辑区
        self.text_content = tk.Text(self.frame_right, font=("Consolas", self.font_size),
                                    bg=self.colors["bg"], fg=self.colors["fg"], relief="flat",
                                    wrap="word", undo=True, padx=15, pady=10,
                                    insertbackground=self.colors["fg"])
        self.text_content.pack(fill="both", expand=True)
        self.text_content.bind("<KeyRelease>", self.on_content_change)
        self.text_content.bind("<Control-s>", self.manual_save)

        # --- 底部栏 (状态 + 动态按钮组) ---
        self.bottom_bar = tk.Frame(self.frame_right, bg=self.colors["bg"])
        self.bottom_bar.pack(side="bottom", fill="x", padx=15, pady=10)

        # 状态标签 (左侧)
        self.lbl_status = tk.Label(self.bottom_bar, text="就绪", bg=self.colors["bg"],
                                   fg="#888888", anchor="w", font=("Arial", 8))
        self.lbl_status.pack(side="left", fill="x", expand=True)

        # 按钮组 (右侧) - 初始全部创建，但由 toggle_editor 控制显示谁

        # 1. 正常删除按钮 (放入回收站)
        self.btn_del_note = tk.Button(self.bottom_bar, text="🗑️ 删除", command=self.delete_current_note,
                                      bg=self.colors["bg"], fg="#ff5555", relief="flat", font=("Arial", 9),
                                      activebackground=self.colors["bg"], activeforeground="#d35400", cursor="hand2")

        # 2. 回收站专用：还原按钮
        self.btn_restore = tk.Button(self.bottom_bar, text="♻️ 还原笔记", command=self.restore_current_note,
                                     bg="#27ae60", fg="white", relief="flat", font=("Arial", 9), padx=10)

        # 3. 回收站专用：彻底删除按钮
        self.btn_hard_del = tk.Button(self.bottom_bar, text="❌ 彻底删除", command=self.hard_delete_current_note,
                                      bg=self.colors["bg"], fg="#888888", relief="flat", font=("Arial", 9), padx=10)

        # 初始状态：禁用编辑器和按钮
        self.toggle_editor(False)

    # --- 逻辑控制 ---

    def toggle_editor(self, enable):
        state = "normal" if enable else "disabled"
        bg = self.colors["bg"] if enable else self.colors["list_bg"]

        # 如果在回收站，强制只读
        is_trash = (self.current_folder_uuid == "TRASH_BIN")
        if is_trash and enable:
            state = "disabled"  # 文本框不可编辑
            bg = self.colors["list_bg"]  # 灰色背景
            # 允许复制，所以不用完全 disabled，而是 state='disabled' 但能选中
            # Tkinter Text disabled 无法选中，暂且这样，或者设为 normal 但绑定键盘事件 return break

        self.entry_title.config(state=state, bg=bg)
        self.text_content.config(state=state, bg=bg)

        # --- 按钮切换逻辑 ---
        # 先隐藏所有
        self.btn_del_note.pack_forget()
        self.btn_restore.pack_forget()
        self.btn_hard_del.pack_forget()

        if enable or is_trash:  # 选中了笔记才显示按钮
            if is_trash:
                self.btn_hard_del.pack(side="right", padx=5)
                self.btn_restore.pack(side="right", padx=5)
            else:
                self.btn_del_note.pack(side="right")
        # ------------------

        if not enable and not is_trash:
            self.entry_title.delete(0, "end")
            self.text_content.delete("1.0", "end")
            self.current_note_uuid = None
            self.lbl_status.config(text="")

    def load_folders(self):
        # 清空
        for item in self.tree_folders.get_children():
            self.tree_folders.delete(item)

        # 添加"全部笔记"
        self.tree_folders.insert("", "end", iid="ALL_NOTES", text="📂 所有笔记", open=True)

        # 加载用户文件夹
        folders = self.db.get_folders()
        for uuid, name in folders:
            self.tree_folders.insert("", "end", iid=uuid, text=f"📁 {name}")

        # --- 新增：回收站节点 ---
        self.tree_folders.insert("", "end", iid="TRASH_BIN", text="🗑️ 回收站")

    # [新增/替换以下方法]
    def on_folder_select(self, event):
        selected = self.tree_folders.selection()
        if not selected: return
        folder_uuid = selected[0]

        self.current_folder_uuid = folder_uuid

        # 如果选了回收站，禁用新建按钮
        if folder_uuid == "TRASH_BIN":
            self.btn_add_note.config(state="disabled", text="回收站 (只读)")
        elif folder_uuid == "ALL_NOTES":
            self.btn_add_note.config(state="disabled", text="请先选择文件夹")
        else:
            self.btn_add_note.config(state="normal", text="➕ 新建笔记")

        self.load_notes_list()

    def delete_current_note(self):
        if not self.current_note_uuid: return

        # 1. 检查配置：是否需要确认
        need_confirm = self.db.get_setting("confirm_note_delete", "1") == "1"

        should_delete = True
        if need_confirm:
            should_delete = self.show_delete_confirm_dialog()

        if should_delete:
            self.db.delete_note(self.current_note_uuid)
            self.load_notes_list()  # 刷新后会自动清空右侧
            self.lbl_status.config(text="已移入回收站")

    def show_delete_confirm_dialog(self):
        """自定义删除确认弹窗 (带'不再提示')"""
        dlg = tk.Toplevel(self)
        dlg.title("删除确认")
        dlg.geometry("350x160")
        dlg.resizable(False, False)
        dlg.configure(bg=self.colors["bg"])

        # 居中
        self.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - 350) // 2
        y = self.winfo_rooty() + (self.winfo_height() - 160) // 2
        dlg.geometry(f"+{x}+{y}")

        # 结果容器
        result = {"delete": False}

        # 内容
        tk.Label(dlg, text="确定要将这条笔记移入回收站吗？\n(可以在回收站中还原)",
                 bg=self.colors["bg"], fg=self.colors["fg"], pady=20).pack()

        # 底部
        frame_bottom = tk.Frame(dlg, bg=self.colors["list_bg"], padx=15, pady=10)
        frame_bottom.pack(side="bottom", fill="x")

        var_skip = tk.BooleanVar(value=False)
        tk.Checkbutton(frame_bottom, text="下次不再提示", variable=var_skip,
                       bg=self.colors["list_bg"], fg=self.colors["fg"],
                       selectcolor=self.colors["accent"], activebackground=self.colors["list_bg"]).pack(side="left")

        def on_yes():
            if var_skip.get():
                self.db.set_setting("confirm_note_delete", "0")
            result["delete"] = True
            dlg.destroy()

        def on_no():
            dlg.destroy()

        tk.Button(frame_bottom, text="取消", command=on_no, bg=self.colors["bg"], fg=self.colors["fg"],
                  relief="flat", width=8).pack(side="right", padx=5)
        tk.Button(frame_bottom, text="删除", command=on_yes, bg="#ff5555", fg="white", relief="flat", width=8).pack(
            side="right")

        dlg.transient(self)
        dlg.grab_set()
        self.wait_window(dlg)
        return result["delete"]

    def restore_current_note(self):
        if not self.current_note_uuid: return
        self.db.restore_note(self.current_note_uuid)
        messagebox.showinfo("成功", "笔记已还原！")
        self.load_notes_list()

    def hard_delete_current_note(self):
        if not self.current_note_uuid: return
        if messagebox.askyesno("彻底删除", "确定要【永久删除】这条笔记吗？\n此操作无法撤销！"):
            self.db.hard_delete_note(self.current_note_uuid)
            self.load_notes_list()

    def add_folder(self):
        name = simpledialog.askstring("新建文件夹", "请输入文件夹名称:")
        if name and name.strip():
            self.db.create_folder(name.strip())
            self.load_folders()

    def rename_folder(self):
        selected = self.tree_folders.selection()
        if not selected or selected[0] == "ALL_NOTES": return
        old_name = self.tree_folders.item(selected[0])['text'].replace("📁 ", "")
        new_name = simpledialog.askstring("重命名", "请输入新名称:", initialvalue=old_name)
        if new_name and new_name.strip():
            self.db.rename_folder(selected[0], new_name.strip())
            self.load_folders()

    def delete_folder(self):
        selected = self.tree_folders.selection()
        if not selected or selected[0] == "ALL_NOTES": return
        fid = selected[0]

        # 1. 确认删除动作
        if not messagebox.askyesno("删除确认", "确定要删除该文件夹吗？"):
            return

        # 2. 询问子内容处理 (Yes/No/Cancel)
        # askyesnocancel: Yes=True, No=False, Cancel=None
        choice = messagebox.askyesnocancel("子项处理",
                                           "检测到该文件夹可能包含笔记。\n\n"
                                           "您希望如何处理这些笔记？\n"
                                           "-----------------------------------\n"
                                           "【是 (Yes)】 ： 删除文件夹，并同时删除里面的所有笔记\n"
                                           "【否 (No)】  ： 仅删除文件夹，笔记保留在'所有笔记'中\n"
                                           "【取消 (Cancel)】 ： 我点错了，取消操作")

        if choice is None:  # 用户点了取消
            return

        delete_children = choice  # True or False

        self.db.delete_folder(fid, delete_children=delete_children)

        # 刷新 UI
        self.load_folders()
        # 如果当前正选着这个文件夹，重置视图到“所有笔记”或空
        if self.current_folder_uuid == fid:
            self.current_folder_uuid = None
            self.load_notes_list()

    def delete_current_note(self):
        if not self.current_note_uuid: return

        if messagebox.askyesno("删除确认", "确定要将这条笔记移入回收站吗？"):
            # 数据库删除
            self.db.delete_note(self.current_note_uuid)

            # 刷新列表 (会自动触发 toggle_editor(False) 清空右侧)
            self.load_notes_list()
            messagebox.showinfo("提示", "笔记已删除")
    # --- 笔记列表逻辑 ---

    def load_notes_list(self):
        self.list_notes.delete(0, "end")
        self.note_uuid_map = []

        keyword = self.entry_search.get().strip()

        # --- 分支逻辑：是否是回收站 ---
        if self.current_folder_uuid == "TRASH_BIN":
            notes = self.db.get_deleted_notes()
            # 如果有搜索词，简单过滤一下
            if keyword:
                notes = [n for n in notes if keyword.lower() in (n[1] + n[2]).lower()]
        else:
            notes = self.db.get_notes(self.current_folder_uuid, keyword)
        # ---------------------------

        for uuid, title, content, updated_at in notes:
            display_title = title if title else "无标题"
            try:
                dt = datetime.fromisoformat(updated_at)
                time_str = dt.strftime("%m-%d")
            except:
                time_str = ""

            # 回收站里的笔记加个标记
            prefix = "♻️ " if self.current_folder_uuid == "TRASH_BIN" else ""
            self.list_notes.insert("end", f"{prefix}{display_title}  ({time_str})")
            self.note_uuid_map.append(uuid)

        self.toggle_editor(False)

    def on_search(self, event):
        self.load_notes_list()

    def add_note(self):
        if not self.current_folder_uuid:
            messagebox.showwarning("提示", "请先在左侧选择一个文件夹")
            return

        new_uuid = self.db.create_note(self.current_folder_uuid, "新笔记", "")
        self.load_notes_list()

        # 自动选中新建的笔记
        try:
            idx = self.note_uuid_map.index(new_uuid)
            self.list_notes.selection_clear(0, "end")
            self.list_notes.selection_set(idx)
            self.list_notes.see(idx)
            self.on_note_select(None)
            self.entry_title.focus_set()
            self.entry_title.select_range(0, 'end')
        except:
            pass

    def on_note_select(self, event):
        # 如果有未保存的更改，先保存上一条
        self.flush_save()

        selection = self.list_notes.curselection()
        if not selection: return

        idx = selection[0]
        if idx >= len(self.note_uuid_map): return

        note_uuid = self.note_uuid_map[idx]
        self.current_note_uuid = note_uuid

        # 加载详情
        data = self.db.get_note_detail(note_uuid)
        if data:
            self.toggle_editor(True)
            self.entry_title.delete(0, "end")
            self.entry_title.insert(0, data[2] if data[2] else "")

            self.text_content.delete("1.0", "end")
            self.text_content.insert("1.0", data[3] if data[3] else "")
            self.is_dirty = False
            self.lbl_status.config(text="已同步")

    # --- 编辑与保存逻辑 ---

    def on_content_change(self, event):
        if not self.current_note_uuid: return
        # 忽略控制键
        if event.keysym in ("Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R"): return

        self.is_dirty = True
        self.lbl_status.config(text="未保存...", fg="#e67e22")

        # 防抖保存 (2秒)
        if self.save_timer:
            self.save_timer.cancel()
        self.save_timer = threading.Timer(2.0, self.save_current_note)
        self.save_timer.start()

    def manual_save(self, event=None):
        self.flush_save()
        return "break"  # 阻止默认行为

    def flush_save(self):
        """立即执行保存"""
        if self.save_timer:
            self.save_timer.cancel()
            self.save_timer = None
        if self.is_dirty and self.current_note_uuid:
            self.save_current_note()

    def save_current_note(self):
        if not self.current_note_uuid: return

        title = self.entry_title.get().strip()
        content = self.text_content.get("1.0", "end-1c")

        # 更新数据库
        self.db.update_note(self.current_note_uuid, title, content)

        # UI 更新
        self.is_dirty = False

        def _update_ui():
            if self.winfo_exists():
                self.lbl_status.config(text="已保存 ✔", fg=self.colors["fg"])
                # 可选：刷新列表标题，如果标题变了
                # self.load_notes_list() # 这会导致焦点丢失，暂不刷新列表，除非必要

        self.after(0, _update_ui)

    def on_close(self):
        self.flush_save()
        self.destroy()