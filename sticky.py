import tkinter as tk
from tkinter import colorchooser
from utils import STICKY_COLORS


class StickyNoteWindow(tk.Toplevel):
    """单个便签窗口 - 无边框自定义样式，工具栏同色隐藏式"""

    def __init__(self, parent, db, uuid_val, title="便签", content="", color="#fff9c4",
                 is_topmost=False, position_x=None, position_y=None, width=250, height=200,
                 on_close_callback=None, create_new_callback=None):
        super().__init__(parent)
        self.db = db
        self.uuid = uuid_val
        self.on_close_callback = on_close_callback
        self.create_new_callback = create_new_callback
        self._save_timer = None

        # 无边框窗口
        self.overrideredirect(True)
        self.attributes('-topmost', is_topmost)
        self.is_topmost = is_topmost

        # 窗口设置
        self.geometry(f"{width}x{height}")
        if position_x is not None and position_y is not None:
            self.geometry(f"+{position_x}+{position_y}")

        self.sticky_color = color
        self.configure(bg=color)

        # 拖动相关
        self._drag_start_x = 0
        self._drag_start_y = 0

        # 读取字体设置
        try:
            self.title_font_size = int(self.db.get_setting("sticky_title_size", "9"))
            self.content_font_size = int(self.db.get_setting("sticky_content_size", "9"))
        except:
            self.title_font_size = 9
            self.content_font_size = 9

        self.setup_ui(title, content)
        self.apply_color(color)

        # 绑定事件
        self.bind("<Configure>", self._on_configure)

    def setup_ui(self, title, content):
        # 顶部栏（与便签同色）
        self.header = tk.Frame(self, bg=self.sticky_color, height=30)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)

        # 让顶部栏可拖动
        self.header.bind("<Button-1>", self._start_drag)
        self.header.bind("<B1-Motion>", self._do_drag)

        # 标题（可双击编辑）
        self.title_var = tk.StringVar(value=title)
        self.title_label = tk.Label(self.header, textvariable=self.title_var, bg=self.sticky_color,
                                    fg="#333", font=("Microsoft YaHei UI", self.title_font_size, "bold"),
                                    cursor="hand2")
        self.title_label.pack(side="left", padx=5, pady=2)
        self.title_label.bind("<Double-Button-1>", self._edit_title)

        # 按钮容器
        btn_frame = tk.Frame(self.header, bg=self.sticky_color)
        btn_frame.pack(side="right")

        # 按钮背景与便签同色
        # 颜色按钮
        self.btn_color = tk.Button(btn_frame, text="🎨", relief="flat", bg=self.sticky_color,
                                   fg="#333", font=("Segoe UI Emoji", 10), padx=4, pady=2,
                                   command=self._choose_color, cursor="hand2", bd=0, highlightthickness=0)
        self.btn_color.pack(side="left", padx=1)

        # 置顶按钮
        self.btn_topmost = tk.Button(btn_frame, text="📌", relief="flat", bg=self.sticky_color,
                                     fg="#333" if not self.is_topmost else "#e74c3c",
                                     font=("Segoe UI Emoji", 10), padx=4, pady=2,
                                     command=self._toggle_topmost, cursor="hand2", bd=0, highlightthickness=0)
        self.btn_topmost.pack(side="left", padx=1)

        # 新增按钮
        self.btn_new = tk.Button(btn_frame, text="+", relief="flat", bg=self.sticky_color,
                                 fg="#333", font=("Arial", 12, "bold"), padx=4, pady=2,
                                 command=self._create_new, cursor="hand2", bd=0, highlightthickness=0)
        self.btn_new.pack(side="left", padx=1)

        # 关闭按钮
        self.btn_close = tk.Button(btn_frame, text="×", relief="flat", bg=self.sticky_color,
                                   fg="#666", font=("Arial", 12), padx=4, pady=2,
                                   command=self._on_close, cursor="hand2", bd=0, highlightthickness=0)
        self.btn_close.pack(side="left", padx=1)

        # 内容区域
        self.text_frame = tk.Frame(self, bg=self.sticky_color)
        self.text_frame.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        self.text_area = tk.Text(self.text_frame, wrap="word", relief="flat",
                                 bg=self.sticky_color, fg="#333", font=("Microsoft YaHei UI", self.content_font_size),
                                 padx=5, pady=5)
        self.text_area.pack(fill="both", expand=True)
        self.text_area.insert("1.0", content)
        self.text_area.bind("<KeyRelease>", self._on_text_change)

        # 边框区域（用于调整大小）- 四条边
        self.resize_borders = []
        border_width = 5
        cursor_map = {'n': 'sb_v_double_arrow', 's': 'sb_v_double_arrow',
                      'e': 'sb_h_double_arrow', 'w': 'sb_h_double_arrow'}
        for side in ['n', 's', 'e', 'w']:
            border = tk.Frame(self, bg=self.sticky_color, cursor=cursor_map[side])
            if side == 'n':
                border.place(relx=0, rely=0, relwidth=1.0, relheight=0.02, anchor="nw")
            elif side == 's':
                border.place(relx=0, rely=1.0, relwidth=1.0, relheight=0.02, anchor="sw")
            elif side == 'e':
                border.place(relx=1.0, rely=0, relwidth=0.02, relheight=1.0, anchor="ne")
            elif side == 'w':
                border.place(relx=0, rely=0, relwidth=0.02, relheight=1.0, anchor="nw")

            border.bind("<Button-1>", lambda e, s=side: self._start_resize(e, s))
            border.bind("<B1-Motion>", lambda e, s=side: self._do_resize(e, s))
            self.resize_borders.append(border)

        # 右下角调整大小手柄
        self.resize_handle = tk.Label(self, text="◢", bg=self.sticky_color, fg="#999",
                                      font=("Arial", 8), cursor="fleur")
        self.resize_handle.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-2)
        self.resize_handle.bind("<Button-1>", self._start_resize_corner)
        self.resize_handle.bind("<B1-Motion>", self._do_resize_corner)

    def apply_color(self, color):
        self.sticky_color = color
        self.configure(bg=color)
        self.header.configure(bg=color)
        self.btn_color.configure(bg=color, fg="#333")
        self.btn_topmost.configure(bg=color, fg="#333" if not self.is_topmost else "#e74c3c")
        self.btn_new.configure(bg=color, fg="#333")
        self.btn_close.configure(bg=color, fg="#666")
        self.title_label.configure(bg=color)
        self.text_frame.configure(bg=color)
        self.text_area.configure(bg=color)
        self.resize_handle.configure(bg=color)
        for border in self.resize_borders:
            border.configure(bg=color)

    def _start_drag(self, event):
        self._drag_start_x = event.x_root - self.winfo_x()
        self._drag_start_y = event.y_root - self.winfo_y()

    def _do_drag(self, event):
        x = event.x_root - self._drag_start_x
        y = event.y_root - self._drag_start_y
        self.geometry(f"+{x}+{y}")

    def _start_resize(self, event, side):
        self._resize_start_x = event.x_root
        self._resize_start_y = event.y_root
        self._start_width = self.winfo_width()
        self._start_height = self.winfo_height()
        self._resize_side = side
        self._start_geom = self.geometry()

    def _do_resize(self, event, side):
        dx = event.x_root - self._resize_start_x
        dy = event.y_root - self._resize_start_y

        new_width = self._start_width
        new_height = self._start_height
        new_x = self.winfo_x()
        new_y = self.winfo_y()

        if side == 'e':
            new_width = max(150, self._start_width + dx)
        elif side == 'w':
            new_width = max(150, self._start_width - dx)
            new_x = self._start_width - new_width + self.winfo_x()
        elif side == 's':
            new_height = max(100, self._start_height + dy)
        elif side == 'n':
            new_height = max(100, self._start_height - dy)
            new_y = self._start_height - new_height + self.winfo_y()

        self.geometry(f"{new_width}x{new_height}+{new_x}+{new_y}")

    def _start_resize_corner(self, event):
        self._resize_start_x = event.x_root
        self._resize_start_y = event.y_root
        self._start_width = self.winfo_width()
        self._start_height = self.winfo_height()

    def _do_resize_corner(self, event):
        dx = event.x_root - self._resize_start_x
        dy = event.y_root - self._resize_start_y
        new_width = max(150, self._start_width + dx)
        new_height = max(100, self._start_height + dy)
        self.geometry(f"{new_width}x{new_height}")

    def _edit_title(self, event):
        # 创建编辑框
        entry = tk.Entry(self.header, textvariable=self.title_var, bg="white",
                         fg="#333", font=("Microsoft YaHei UI", self.title_font_size, "bold"),
                         relief="solid", bd=1)
        entry.pack(side="left", padx=5, pady=2)
        entry.select_range(0, tk.END)
        entry.focus()

        def save_title(e=None):
            entry.destroy()
            self.title_label.pack(side="left", padx=5, pady=2)
            self._save_data()

        entry.bind("<Return>", save_title)
        entry.bind("<Escape>", lambda e: (entry.destroy(), self.title_label.pack(side="left", padx=5, pady=2)))
        entry.bind("<FocusOut>", save_title)

    def _choose_color(self):
        # 先显示预设颜色选择菜单
        menu = tk.Menu(self, tearoff=0)
        for c in STICKY_COLORS:
            menu.add_command(label="■", foreground=c, font=("Arial", 14),
                           command=lambda color=c: self._set_color(color))
        menu.add_separator()
        menu.add_command(label="自定义...", command=self._open_color_picker)
        menu.tk_popup(self.winfo_rootx() + 20, self.winfo_rooty() + 30)

    def _set_color(self, color):
        self.apply_color(color)
        self._save_data()

    def _open_color_picker(self):
        color = colorchooser.askcolor(initialcolor=self.sticky_color, title="选择便签颜色")[1]
        if color:
            self._set_color(color)

    def _toggle_topmost(self):
        self.is_topmost = not self.is_topmost
        self.attributes('-topmost', self.is_topmost)
        self.btn_topmost.configure(fg="#e74c3c" if self.is_topmost else "#333")
        self._save_data()

    def _create_new(self):
        if self.create_new_callback:
            self.create_new_callback()

    def _on_text_change(self, event=None):
        if self._save_timer:
            self.after_cancel(self._save_timer)
        self._save_timer = self.after(1000, self._save_data)

    def _save_data(self):
        content = self.text_area.get("1.0", tk.END).strip()
        title = self.title_var.get().strip() or "便签"
        self.db.update_sticky(
            self.uuid,
            title=title,
            content=content,
            color=self.sticky_color,
            is_topmost=self.is_topmost
        )

    def _on_configure(self, event):
        # 保存位置和大小
        if event.widget == self:
            if self._save_timer:
                self.after_cancel(self._save_timer)
            self._save_timer = self.after(500, self._save_position)

    def _save_position(self):
        self.db.update_sticky(
            self.uuid,
            position_x=self.winfo_x(),
            position_y=self.winfo_y(),
            width=self.winfo_width(),
            height=self.winfo_height()
        )

    def _on_close(self):
        self._save_data()
        self._save_position()
        if self.on_close_callback:
            self.on_close_callback(self.uuid)
        self.destroy()


class StickyManagerWindow(tk.Toplevel):
    """便签管理窗口"""

    def __init__(self, parent, db, theme):
        super().__init__(parent)
        self.db = db
        self.colors = theme
        self.sticky_windows = {}

        self.title("便签管理")
        self.geometry("750x500")
        self.configure(bg=self.colors["bg"])

        self.setup_ui()
        self.load_stickies()

        self.db.add_observer(self._on_db_change)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        toolbar = tk.Frame(self, bg=self.colors["bg"], height=40)
        toolbar.pack(fill="x", padx=5, pady=5)

        tk.Label(toolbar, text="单击预览 | 双击打开便签", bg=self.colors["bg"], fg="#888888",
                 font=("Microsoft YaHei UI", 10)).pack(side="left", padx=5)

        btn_new = tk.Button(toolbar, text="+", relief="flat", bg=self.colors.get("accent", "#3c3c3c"),
                            fg=self.colors["fg"], font=("Arial", 14, "bold"), padx=10,
                            command=self.create_sticky)
        btn_new.pack(side="right", padx=5)

        # 主内容区（使用 PanedWindow 实现可拖动调整）
        paned = tk.PanedWindow(self, orient="horizontal", bg=self.colors["bg"],
                               sashwidth=6, sashrelief="raised", sashpad=2)
        paned.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        # 左侧：便签列表
        left_frame = tk.Frame(paned, bg=self.colors["bg"])

        scrollbar = tk.Scrollbar(left_frame)
        scrollbar.pack(side="right", fill="y")

        self.listbox = tk.Listbox(left_frame, bg=self.colors.get("list_bg", "#252526"),
                                   fg=self.colors.get("list_fg", "#e0e0e0"),
                                   selectbackground=self.colors.get("accent", "#3c3c3c"),
                                   font=("Microsoft YaHei UI", 10),
                                   yscrollcommand=scrollbar.set)
        self.listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)

        # 单击预览
        self.listbox.bind("<<ListboxSelect>>", self._on_select_preview)
        # 双击打开
        self.listbox.bind("<Double-Button-1>", self._on_double_click)
        # 右键菜单
        self.listbox.bind("<Button-3>", self._show_context_menu)

        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="打开", command=self._open_selected)
        self.context_menu.add_command(label="删除", command=self._delete_selected)

        # 右侧：预览区
        right_frame = tk.Frame(paned, bg=self.colors["bg"])

        preview_title = tk.Label(right_frame, text="📄 内容预览", bg=self.colors["bg"],
                                 fg="#888888", font=("Arial", 10, "bold"), anchor="w")
        preview_title.pack(fill="x", pady=(0, 5))

        self.preview_text = tk.Text(right_frame, bg=self.colors.get("text_bg", "#1e1e1e"),
                                    fg=self.colors.get("text_fg", "#e0e0e0"),
                                    relief="flat", wrap="word", font=("Microsoft YaHei UI", 10),
                                    padx=10, pady=10)
        self.preview_text.pack(fill="both", expand=True)
        self.preview_text.config(state="disabled")

        # 添加到 PanedWindow
        paned.add(left_frame, width=280, minsize=200)
        paned.add(right_frame, minsize=250)

        # 底部按钮区
        btn_frame = tk.Frame(self, bg=self.colors["bg"], pady=5)
        btn_frame.pack(side="bottom", fill="x", padx=5)

        tk.Button(btn_frame, text="🗑️ 删除", command=self._delete_selected,
                  bg=self.colors["bg"], fg="#ff5555", relief="flat", padx=8).pack(side="right", padx=2)
        tk.Button(btn_frame, text="📂 打开便签", command=self._open_selected,
                  bg=self.colors.get("accent", "#3c3c3c"), fg=self.colors["fg"], relief="flat", padx=8).pack(side="right", padx=2)

    def _on_select_preview(self, event):
        """单击时在右侧预览区显示内容"""
        selection = self.listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self.sticky_data):
            return
        row = self.sticky_data[idx]
        uuid_val, title, content, color, is_topmost, pos_x, pos_y, w, h, created, updated = row
        self.show_preview(title, content)

    def show_preview(self, title, content):
        """在预览区显示内容"""
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", "end")
        display = f"【{title}】\n\n{content or '(空)'}"
        self.preview_text.insert("1.0", display)
        self.preview_text.config(state="disabled")

    def load_stickies(self):
        self.listbox.delete(0, tk.END)
        self.sticky_data = self.db.get_all_stickies()
        for row in self.sticky_data:
            uuid_val, title, content, color, is_topmost, pos_x, pos_y, w, h, created, updated = row
            preview = content[:30].replace('\n', ' ') if content else "(空)"
            display = f"{title} - {preview}"
            self.listbox.insert(tk.END, display)

    def create_sticky(self):
        uuid_val = self.db.create_sticky()
        self._open_sticky_window(uuid_val)

    def _open_sticky_window(self, uuid_val):
        if uuid_val in self.sticky_windows:
            win = self.sticky_windows[uuid_val]
            try:
                win.lift()
                win.focus_force()
                return
            except tk.TclError:
                del self.sticky_windows[uuid_val]

        data = self.db.get_sticky(uuid_val)
        if not data:
            return

        uuid_val, title, content, color, is_topmost, pos_x, pos_y, w, h, created, updated = data

        win = StickyNoteWindow(
            self, self.db, uuid_val,
            title=title, content=content or "", color=color,
            is_topmost=bool(is_topmost), position_x=pos_x, position_y=pos_y,
            width=w or 250, height=h or 200,
            on_close_callback=self._on_sticky_close,
            create_new_callback=self.create_sticky
        )
        self.sticky_windows[uuid_val] = win

    def _on_sticky_close(self, uuid_val):
        if uuid_val in self.sticky_windows:
            del self.sticky_windows[uuid_val]

    def _on_double_click(self, event):
        self._open_selected()

    def _open_selected(self):
        selection = self.listbox.curselection()
        if selection:
            idx = selection[0]
            if idx < len(self.sticky_data):
                uuid_val = self.sticky_data[idx][0]
                self._open_sticky_window(uuid_val)

    def _show_context_menu(self, event):
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(self.listbox.nearest(event.y))
        self.context_menu.tk_popup(event.x_root, event.y_root)

    def _delete_selected(self):
        selection = self.listbox.curselection()
        if selection:
            idx = selection[0]
            if idx < len(self.sticky_data):
                uuid_val = self.sticky_data[idx][0]
                self.db.delete_sticky(uuid_val)
                if uuid_val in self.sticky_windows:
                    try:
                        self.sticky_windows[uuid_val].destroy()
                    except:
                        pass
                    del self.sticky_windows[uuid_val]

    def _on_db_change(self):
        self.load_stickies()

    def on_close(self):
        self.db.remove_observer(self._on_db_change)
        self.destroy()
