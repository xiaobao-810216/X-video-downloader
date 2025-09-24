import os
import sys
import platform
from pathlib import Path

# ---------------- 版本与特性开关 ----------------
# 统一版本号（打包、日志、诊断接口都可读取）通过 version.py 单一来源
try:
    from version import APP_VERSION  # type: ignore
except Exception:
    APP_VERSION = "0.0.0"  # 回退占位，极端情形下仍可运行

# 元数据写入默认模式：优先显式 META_MODE，其次旧布尔禁用；未设则 sidecar
_env_meta_mode = (os.environ.get('META_MODE') or '').strip().lower()
if not _env_meta_mode:
    if os.environ.get('LUMINA_DISABLE_META','').lower() in ('1','true','yes'):
        _env_meta_mode = 'off'
    else:
        _env_meta_mode = 'sidecar'
if _env_meta_mode not in ('off','sidecar','folder'):
    _env_meta_mode = 'sidecar'
DEFAULT_META_MODE = _env_meta_mode  # 供后端诊断或未来接口返回

# FAST_START 标志（供前端或诊断展示，不直接决定逻辑；核心逻辑仍在 tasks.py）
FAST_START_ENABLED = os.environ.get('LUMINA_FAST_START','').lower() in ('1','true','yes')

# 公开一个简洁汇总函数（可在 /diag 或交互式调试里使用）
def runtime_summary() -> dict:
    return {
        "app_version": APP_VERSION,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "default_meta_mode": DEFAULT_META_MODE,
        "fast_start": FAST_START_ENABLED,
        "download_dir": DOWNLOAD_DIR if 'DOWNLOAD_DIR' in globals() else None,
        "ffmpeg_bundled": FFMPEG_BUNDLED_PATH if 'FFMPEG_BUNDLED_PATH' in globals() else None,
    }

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
        # path_ptr.value 可能为 None（极端情况下 API 未写入），需要防御以避免类型错误
        raw = path_ptr.value
        if not raw:
            return None
        try:
            return Path(raw)
        except Exception:
            return None
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

def resource_path(relative_path: str) -> str:
    """解析资源文件的绝对路径。

    修复: 之前使用 os.path.abspath('.') 作为基准，当用户通过快捷方式或在其它工作目录启动
    已打包的一键目录 (one-folder) 应用时，当前工作目录可能不是 exe 所在目录，导致找不到 ffmpeg/yt-dlp 等资源。

    优先顺序:
      1. PyInstaller one-file 解包目录 (sys._MEIPASS)
      2. 冻结应用 (sys.frozen) 下的可执行文件所在目录 (sys.executable)
      3. 源码运行: 本文件所在目录 (__file__)
    """
    # 1) PyInstaller one-file 临时目录
    if hasattr(sys, '_MEIPASS'):
        base_path = getattr(sys, '_MEIPASS')  # type: ignore[attr-defined]
    # 2) PyInstaller one-folder / 冻结应用
    elif getattr(sys, 'frozen', False):  # type: ignore[attr-defined]
        base_path = os.path.dirname(sys.executable)
    else:
        # 3) 源码模式：以当前文件所在目录为基准 (避免依赖启动时 CWD)
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            # 兜底: 仍退回当前工作目录
            base_path = os.path.abspath('.')
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
