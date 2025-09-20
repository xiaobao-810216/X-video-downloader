import os
import sys
import platform
from pathlib import Path

# -------------------------------------------------------------
# 桌面/下载目录路径解析改进
# 目标：避免出现两个“流光视频下载”目录（如 Desktop 与 本地化“桌面” 或 OneDrive 重定向并存）
# 优先级：环境变量显式指定 > Windows 官方 KnownFolder Desktop > 传统 ~/Desktop > 传统 ~/桌面 > 最后回退到项目根 ./downloads
# 可通过设置环境变量 LUMINA_DOWNLOAD_DIR 来覆盖。
# -------------------------------------------------------------

def _win_known_folder_desktop() -> Path | None:
    """尝试使用 Windows API 获取真实桌面路径，避免语言/重定向差异。
    返回 Path 或 None (非 Windows / 失败)。"""
    if platform.system().lower() != 'windows':
        return None
    try:
        import ctypes
        from ctypes import wintypes
        # FOLDERID_Desktop = {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
        _REFID = ctypes.c_char * 16
        CLSID_Desktop = _REFID.from_buffer_copy(bytes.fromhex('B4BFCC3ADB2C424CB0297FE99A87C641'))
        SHGetKnownFolderPath = ctypes.windll.shell32.SHGetKnownFolderPath
        SHGetKnownFolderPath.argtypes = [ctypes.POINTER(_REFID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
        path_ptr = ctypes.c_wchar_p()
        # Flags=0 (默认), hToken=None
        res = SHGetKnownFolderPath(ctypes.byref(CLSID_Desktop), 0, None, ctypes.byref(path_ptr))
        if res != 0:
            return None
        return Path(path_ptr.value)
    except Exception:
        return None

def _candidate_desktop_paths() -> list[Path]:
    home = Path.home()
    candidates = []
    # Known Folder 优先
    kf = _win_known_folder_desktop()
    if kf:
        candidates.append(kf)
    # 常规英文 Desktop
    candidates.append(home / 'Desktop')
    # 常见中文 本地化（有时显示名是“桌面”但真实仍是 Desktop，保守添加）
    candidates.append(home / '桌面')
    # OneDrive 重定向场景（通常真实桌面已是 OneDrive\Desktop，这里兜底再追加一次）
    onedrive = os.environ.get('OneDrive') or os.environ.get('OneDriveConsumer') or os.environ.get('OneDriveCommercial')
    if onedrive:
        candidates.append(Path(onedrive) / 'Desktop')
    # 去重 & 仅保留存在的
    seen = set()
    existing = []
    for p in candidates:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if rp in seen:
            continue
        seen.add(rp)
        if rp.exists():
            existing.append(rp)
    # 如果没有存在的候选，仍返回原始顺序（之后由上层决定创建哪一个）
    return existing or candidates

def resolve_download_root(folder_name: str = '流光视频下载') -> Path:
    # 1. 显式环境变量覆盖
    env_dir = os.environ.get('LUMINA_DOWNLOAD_DIR')
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    # 2. 逐个候选桌面路径（优先已有的）
    for desk in _candidate_desktop_paths():
        target = desk / folder_name
        # 若目标已存在直接用
        if target.exists():
            return target
    # 3. 若没有任何已存在的，选第一个可写候选并创建
    first = _candidate_desktop_paths()[0]
    target = first / folder_name
    return target

def detect_legacy_duplicates(chosen: Path, folder_name: str = '流光视频下载') -> list[Path]:
    """搜寻可能的历史重复目录（不同桌面路径导致）。不做自动迁移，只返回列表。"""
    legacy = []
    search_bases = set(_candidate_desktop_paths())
    for base in search_bases:
        candidate = base / folder_name
        try:
            if candidate.exists() and candidate.resolve() != chosen.resolve():
                legacy.append(candidate)
        except Exception:
            continue
    return legacy

def resource_path(relative_path):
    """获取资源的绝对路径，无论是从源代码运行还是从打包后的可执行文件运行。"""
    try:
        # PyInstaller 创建一个临时文件夹，并将路径存储在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        # 不在 PyInstaller 打包环境中，使用常规路径
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- 核心依赖路径 ---
# 注意：这些路径都基于 resource_path，以确保在打包后也能正确定位文件。

# Cookies 文件
COOKIES_FILE = resource_path("cookies.txt")

# yt-dlp 可执行文件
YTDLP_PATH = resource_path("yt-dlp.exe")

# Aria2c 可执行文件
ARIA2C_PATH = resource_path(os.path.join("aria2", "aria2-1.36.0-win-64bit-build1", "aria2c.exe"))

# FFmpeg 可执行文件 (打包版本和系统版本)
FFMPEG_BUNDLED_PATH = resource_path(os.path.join("ffmpeg", "bin", "ffmpeg.exe"))
FFMPEG_SYSTEM_PATH = "ffmpeg.exe"  # 假设在系统 PATH 中

# --- 下载与日志目录 ---

# 解析下载目录（改进版）
_DOWNLOAD_PATH = resolve_download_root('流光视频下载')
DOWNLOAD_DIR = str(_DOWNLOAD_PATH)

# 日志目录
LOG_DIR = str(_DOWNLOAD_PATH / '流光下载器日志')

# 检测潜在重复（仅记录，不自动迁移，以免误操作）
_legacy = detect_legacy_duplicates(_DOWNLOAD_PATH)
if _legacy:
    try:
        # 仅打印一次警告；生产环境可在未来版本添加迁移指引或自动合并策略
        sys.stderr.write(("[WARN] 发现可能的历史重复下载目录: " + ", ".join(str(p) for p in _legacy) +
                          f"\n[WARN] 当前使用: {DOWNLOAD_DIR}\n[WARN] 如需合并，请手动检查后迁移文件并删除多余目录。\n"))
    except Exception:
        pass

# --- 网络与服务器设置 ---

# Flask 服务器监听的端口
SERVER_PORT = 5001

# --- 初始化目录 ---
# 确保下载和日志目录在程序启动时存在（惰性创建，避免不可写失败直接崩溃）
try:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
except Exception as _e:
    # 如果失败，降级到当前工作目录的 downloads 目录
    fallback = Path('./downloads').resolve()
    sys.stderr.write(f"[WARN] 创建下载目录失败: {DOWNLOAD_DIR} -> 使用回退目录 {fallback} ({_e})\n")
    DOWNLOAD_DIR = str(fallback)
    LOG_DIR = str(fallback / 'logs')
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
