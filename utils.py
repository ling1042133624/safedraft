import sys
import os
import winreg
import base64
import io
from PIL import Image

try:
    from icon_data import ICON_BASE64
except ImportError:
    ICON_BASE64 = None

# --- 新增：默认字体大小 ---
DEFAULT_FONT_SIZE = 12

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