import tkinter as tk
from ctypes import windll
import random

# 你指定的6种颜色
COLORS = [
    "#fff59d",  # 黄色 默认
    "#a8e6a1",  # 浅绿
    "#ff9eb5",  # 粉色
    "#d1a3ff",  # 紫色
    "#9edcff",  # 浅蓝
    "#b0b0b0"   # 灰色
]

class StickyNote(tk.Toplevel):
    def __init__(self):
        super().__init__()
        self.overrideredirect(True)
        self.geometry("360x460+400+100")

        self.current_bg = COLORS[0]
        self.title_bg = self.darken_color(self.current_bg)
        self.border_w = 8

        # 拖动变量
        self._drag_x = 0
        self._drag_y = 0
        self._win_x = 0
        self._win_y = 0

        self.main_container = tk.Frame(self, bg=self.current_bg, bd=0)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        self.create_title_bar()
        self.create_content_area()
        self.bind_resize_events()

        # 显示在任务栏 + Windows 11 样式修复
        self.update_idletasks()
        hwnd = windll.user32.GetParent(self.winfo_id())
        style = windll.user32.GetWindowLongW(hwnd, -20)
        windll.user32.SetWindowLongW(hwnd, -20, style & ~0x00000080)

        self.apply_color(self.current_bg)

    def create_title_bar(self):
        self.title_bar = tk.Frame(self.main_container, bg=self.title_bg, height=42)
        self.title_bar.pack(fill=tk.X, side=tk.TOP, padx=0, pady=0)

        self.title_label = tk.Label(
            self.title_bar, text="便签", bg=self.title_bg, fg="#212121",
            font=("微软雅黑", 10, "bold"), anchor="w", padx=15
        )
        self.title_label.pack(side=tk.LEFT, fill=tk.Y, expand=True)

        self.btn_frame = tk.Frame(self.title_bar, bg=self.title_bg)
        self.btn_frame.pack(side=tk.RIGHT, padx=8)

        self.new_btn = tk.Button(self.btn_frame, text="＋", width=3, bg=self.title_bg, fg="#212121",
                                 bd=0, font=("微软雅黑", 14), relief="flat", command=self.new_note)
        self.new_btn.pack(side=tk.LEFT, padx=3)

        self.color_btn = tk.Button(self.btn_frame, text="🎨", width=3, bg=self.title_bg, fg="#212121",
                                   bd=0, font=("微软雅黑", 12), relief="flat", command=self.show_color_palette)
        self.color_btn.pack(side=tk.LEFT, padx=3)

        self.min_btn = tk.Button(self.btn_frame, text="−", width=3, bg=self.title_bg, fg="#212121",
                                 bd=0, font=("微软雅黑", 14), relief="flat", command=self.minimize_win)
        self.min_btn.pack(side=tk.LEFT, padx=3)

        self.close_btn = tk.Button(self.btn_frame, text="×", width=3, bg=self.title_bg, fg="#212121",
                                   bd=0, font=("微软雅黑", 15, "bold"), relief="flat",
                                   activebackground="#e74c3c", activeforeground="white",
                                   command=self.destroy)
        self.close_btn.pack(side=tk.LEFT, padx=3)

        # ====================== 拖动绑定（关键修复） ======================
        drag_widgets = [
            self.title_bar, self.title_label, self.btn_frame,
            self.new_btn, self.color_btn, self.min_btn, self.close_btn
        ]
        for widget in drag_widgets:
            widget.bind("<ButtonPress-1>", self.start_move)      # 使用 ButtonPress-1 更稳定
            widget.bind("<B1-Motion>", self.do_move)
            widget.bind("<Double-Button-1>", lambda e: self.toggle_maximize())

    def create_content_area(self):
        self.text_area = tk.Text(
            self.main_container, bg=self.current_bg, fg="#212121",
            font=("微软雅黑", 11), wrap=tk.WORD,
            padx=18, pady=15, relief="flat", bd=0, highlightthickness=0
        )
        self.text_area.pack(fill=tk.BOTH, expand=True, padx=self.border_w, pady=(0, self.border_w))
        self.text_area.insert(tk.END, "1.\n2.\n\n在这里输入内容...")

    def apply_color(self, color):
        self.current_bg = color
        self.title_bg = self.darken_color(color)

        self.main_container.config(bg=self.current_bg)
        self.text_area.config(bg=self.current_bg)
        self.title_bar.config(bg=self.title_bg)
        self.btn_frame.config(bg=self.title_bg)
        self.title_label.config(bg=self.title_bg)

        for btn in [self.new_btn, self.color_btn, self.min_btn]:
            btn.config(bg=self.title_bg, activebackground=self.darken_color(color))
        self.close_btn.config(bg=self.title_bg)

    def darken_color(self, hex_color):
        h = hex_color.lstrip('#')
        r = max(25, int(int(h[0:2], 16) * 0.65))
        g = max(25, int(int(h[2:4], 16) * 0.65))
        b = max(25, int(int(h[4:6], 16) * 0.65))
        return f"#{r:02x}{g:02x}{b:02x}"

    def show_color_palette(self):
        pal = tk.Toplevel(self)
        pal.overrideredirect(True)
        pal.geometry(f"280x65+{self.winfo_x()+40}+{self.winfo_y()+50}")

        f = tk.Frame(pal, bg="#f5f5f5", relief="solid", bd=1)
        f.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        for i, c in enumerate(COLORS):
            selected = (c == self.current_bg)
            btn = tk.Button(f, bg=c, width=4, height=2,
                            bd=4 if selected else 1,
                            relief="solid" if selected else "flat",
                            command=lambda col=c, win=pal: self.pick_color(col, win))
            btn.grid(row=0, column=i, padx=6, pady=8)

    def pick_color(self, color, pal):
        self.apply_color(color)
        pal.destroy()

    # ====================== 纯手动拖动（Windows 11 稳定版） ======================
    def start_move(self, event):
        self._drag_x = event.x_root
        self._drag_y = event.y_root
        self._win_x = self.winfo_x()
        self._win_y = self.winfo_y()

    def do_move(self, event):
        dx = event.x_root - self._drag_x
        dy = event.y_root - self._drag_y
        new_x = self._win_x + dx
        new_y = self._win_y + dy
        self.geometry(f"+{new_x}+{new_y}")

    def minimize_win(self):
        hwnd = windll.user32.GetParent(self.winfo_id())
        windll.user32.ShowWindow(hwnd, 6)

    def toggle_maximize(self):
        if getattr(self, 'is_max', False):
            self.geometry(getattr(self, 'normal_geo', self.geometry()))
            self.is_max = False
        else:
            self.normal_geo = self.geometry()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            self.geometry(f"{sw}x{sh-60}+0+0")
            self.is_max = True

    def new_note(self):
        note = StickyNote()
        note.geometry(f"360x460+{random.randint(100, 800)}+{random.randint(80, 400)}")

    # ====================== 边缘缩放（保持不变） ======================
    def bind_resize_events(self):
        self.bind("<Motion>", self.update_cursor)
        self.bind("<Button-1>", self.start_resize, add="+")
        self.bind("<B1-Motion>", self.do_resize)

    def update_cursor(self, event):
        x, y = event.x, event.y
        w, h = self.winfo_width(), self.winfo_height()
        b = self.border_w + 4
        if (x < b and y < b) or (x > w-b and y > h-b):
            self.config(cursor="size_nw_se")
        elif (x < b and y > h-b) or (x > w-b and y < b):
            self.config(cursor="size_ne_sw")
        elif x < b or x > w - b:
            self.config(cursor="size_we")
        elif y < b or y > h - b:
            self.config(cursor="size_ns")
        else:
            self.config(cursor="")

    def start_resize(self, event):
        self.rs_x = event.x_root
        self.rs_y = event.y_root
        self.rs_w = self.winfo_width()
        self.rs_h = self.winfo_height()
        self.rs_winx = self.winfo_x()
        self.rs_winy = self.winfo_y()

    def do_resize(self, event):
        dx = event.x_root - self.rs_x
        dy = event.y_root - self.rs_y
        cur = self.cget("cursor")
        nw = max(260, self.rs_w + dx) if "e" in cur else self.rs_w
        nh = max(220, self.rs_h + dy) if "s" in cur else self.rs_h
        nx = self.rs_winx + dx if "w" in cur else self.rs_winx
        ny = self.rs_winy + dy if "n" in cur else self.rs_winy

        if "w" in cur:
            nw = max(260, self.rs_w - dx)
        if "n" in cur:
            nh = max(220, self.rs_h - dy)

        self.geometry(f"{nw}x{nh}+{nx}+{ny}")


# ====================== 启动 ======================
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    StickyNote().mainloop()