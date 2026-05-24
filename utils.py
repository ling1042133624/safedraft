import sys
import os
import winreg
import base64
import io
import tkinter as tk
from PIL import Image

try:
    from icon_data import ICON_BASE64
except ImportError:
    ICON_BASE64 = None

# --- 新增：默认字体大小 ---
DEFAULT_FONT_SIZE = 12

# --- 便签预设颜色 ---
STICKY_COLORS = ['#fff9c4', '#ffccbc', '#c8e6c9', '#bbdefb', '#e1bee7', '#ffffff']

# --- 便签默认字体大小 ---
DEFAULT_STICKY_TITLE_SIZE = 9
DEFAULT_STICKY_CONTENT_SIZE = 9

# --- 主题定义 ---
THEMES = {
    "Deep": {
        "bg": "#1e1e1e", "fg": "#d4d4d4", "accent": "#3c3c3c",
        "bg_btn_default": "#1e1e1e", "fg_btn_default": "#d4d4d4", # 补充默认按钮色
        "list_bg": "#252526", "list_fg": "#e0e0e0",
        "text_bg": "#1e1e1e", "text_fg": "#d4d4d4", "insert_bg": "white",
        "btn_top_active": "#d35400", "btn_save_success": "#4caf50",
    },
    "Light": {
        "bg": "#f0f0f0", "fg": "#333333", "accent": "#e0e0e0",
        "bg_btn_default": "#f0f0f0", "fg_btn_default": "#333333", # 补充默认按钮色
        "list_bg": "#ffffff", "list_fg": "#000000",
        "text_bg": "#ffffff", "text_fg": "#000000", "insert_bg": "black",
        "btn_top_active": "#e67e22", "btn_save_success": "#27ae60",
    }
}

class ThemeManager:
    def get_theme(self, theme_name):
        # 如果找不到指定主题，默认返回 Deep
        return THEMES.get(theme_name, THEMES["Deep"])

def get_icon_image():
    """将 Base64 转换为 PIL Image"""
    if ICON_BASE64:
        try:
            image_data = base64.b64decode(ICON_BASE64)
            return Image.open(io.BytesIO(image_data))
        except: pass
    return Image.new('RGB', (64, 64), color=(74, 144, 226))

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
                    exe_path = os.path.abspath(sys.argv[0])
                    winreg.SetValueEx(key, StartupManager.APP_NAME, 0, winreg.REG_SZ, exe_path)
                else:
                    try:
                        winreg.DeleteValue(key, StartupManager.APP_NAME)
                    except FileNotFoundError:
                        pass
                key.Close()
            except Exception as e:
                raise e
        elif sys.platform == "darwin":
            pass


class TextSearchBar:
    """可复用的文本搜索组件，支持 Ctrl+F 搜索、高亮、上下翻页"""

    def __init__(self, parent_frame, text_widget, colors, read_only=False, pack_before=None):
        """
        parent_frame: 搜索栏要插入的父容器 (tk.Frame)
        text_widget: 要搜索的 tk.Text 组件
        colors: 主题颜色字典
        read_only: 文本框是否为只读
        pack_before: pack 在哪个控件之前（可选）
        """
        self.text_widget = text_widget
        self.colors = colors
        self.read_only = read_only
        self._matches = []
        self._match_index = -1
        self._trace_cbname = None
        self._pack_before = pack_before

        # 创建搜索栏 Frame (默认隐藏)
        self.frame = tk.Frame(parent_frame, bg=colors["bg"])

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(self.frame, textvariable=self.search_var,
                                     bg=colors.get("list_bg", "#252526"),
                                     fg=colors.get("list_fg", "#e0e0e0"),
                                     insertbackground=colors.get("list_fg", "#e0e0e0"),
                                     relief="flat", width=20)
        self.search_entry.pack(side="left", padx=2)
        self.search_entry.bind("<Return>", self.search_next)
        self.search_entry.bind("<Shift-Return>", self.search_prev)
        self.search_entry.bind("<Escape>", self.close)

        self.count_label = tk.Label(self.frame, text="", bg=colors["bg"],
                                    fg="#888888", font=("Arial", 9))
        self.count_label.pack(side="left", padx=5)

        tk.Button(self.frame, text="▲", command=self.search_prev, relief="flat", padx=4,
                  bg=colors["bg"], fg=colors.get("fg", "#d4d4d4"), font=("Arial", 8)).pack(side="left")
        tk.Button(self.frame, text="▼", command=self.search_next, relief="flat", padx=4,
                  bg=colors["bg"], fg=colors.get("fg", "#d4d4d4"), font=("Arial", 8)).pack(side="left")
        tk.Button(self.frame, text="×", command=self.close, relief="flat", padx=4,
                  bg=colors["bg"], fg="#ff5555", font=("Arial", 10)).pack(side="left")

        # Tag 配置
        text_widget.tag_configure("search_highlight", background="#f39c12", foreground="white")
        text_widget.tag_configure("search_current", background="#e74c3c", foreground="white")

    def _set_state(self, state):
        if self.read_only:
            self.text_widget.config(state=state)

    def open(self, event=None):
        if self._pack_before:
            self.frame.pack(fill="x", pady=(2, 0), before=self._pack_before)
        else:
            self.frame.pack(fill="x", pady=(2, 0))
        self.search_entry.delete(0, "end")
        self.search_entry.focus_set()
        self.count_label.config(text="")
        self._matches = []
        self._match_index = -1
        self._set_state("normal")
        self.text_widget.tag_remove("search_highlight", "1.0", "end")
        self.text_widget.tag_remove("search_current", "1.0", "end")
        self._set_state("disabled")
        if self._trace_cbname:
            try:
                self.search_var.trace_remove("write", self._trace_cbname)
            except:
                pass
        self._trace_cbname = self.search_var.trace_add("write", self._on_input)
        return "break"

    def close(self, event=None):
        if self._trace_cbname:
            try:
                self.search_var.trace_remove("write", self._trace_cbname)
            except:
                pass
            self._trace_cbname = None
        self.frame.pack_forget()
        self._set_state("normal")
        self.text_widget.tag_remove("search_highlight", "1.0", "end")
        self.text_widget.tag_remove("search_current", "1.0", "end")
        self._set_state("disabled")
        self._matches = []
        self._match_index = -1
        return "break"

    def _on_input(self, *args):
        self._do_search()
        if self._matches:
            self._match_index = 0
            self._highlight_current()

    def _do_search(self):
        keyword = self.search_var.get()
        self._set_state("normal")
        self.text_widget.tag_remove("search_highlight", "1.0", "end")
        self.text_widget.tag_remove("search_current", "1.0", "end")
        self._set_state("disabled")
        self._matches = []
        self._match_index = -1

        if not keyword:
            self.count_label.config(text="")
            return

        content = self.text_widget.get("1.0", "end-1c")
        start = 0
        while True:
            idx = content.find(keyword, start)
            if idx == -1:
                break
            self._matches.append(idx)
            start = idx + 1

        self._set_state("normal")
        for pos in self._matches:
            start_idx = f"1.0+{pos}c"
            end_idx = f"1.0+{pos + len(keyword)}c"
            self.text_widget.tag_add("search_highlight", start_idx, end_idx)
        self._set_state("disabled")

        count = len(self._matches)
        self.count_label.config(text=f"{count} 个结果" if count > 0 else "无结果")

    def search_next(self, event=None):
        if not self._matches:
            if self.search_var.get():
                self._do_search()
            return "break"
        self._match_index = (self._match_index + 1) % len(self._matches)
        self._highlight_current()
        return "break"

    def search_prev(self, event=None):
        if not self._matches:
            if self.search_var.get():
                self._do_search()
            return "break"
        self._match_index = (self._match_index - 1) % len(self._matches)
        self._highlight_current()
        return "break"

    def _highlight_current(self):
        if self._match_index < 0 or self._match_index >= len(self._matches):
            return
        keyword = self.search_var.get()
        if not keyword:
            return

        self._set_state("normal")
        self.text_widget.tag_remove("search_current", "1.0", "end")
        pos = self._matches[self._match_index]
        start_idx = f"1.0+{pos}c"
        end_idx = f"1.0+{pos + len(keyword)}c"
        self.text_widget.tag_add("search_current", start_idx, end_idx)
        self.text_widget.see(start_idx)
        self._set_state("disabled")

        self.count_label.config(text=f"{self._match_index + 1}/{len(self._matches)}")