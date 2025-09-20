import threading, queue, time, uuid, os, re, subprocess, json, logging, traceback, shutil
from urllib.parse import urlparse
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from errors import classify_error

logger = logging.getLogger(__name__)

# 在 Windows 下隐藏所有子进程控制台窗口，避免打包后的 exe 弹出黑色命令窗
CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

@dataclass
class Task:
    id: str
    url: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: str = 'queued'   # queued|downloading|merging|finished|error|canceled
    stage: Optional[str] = None
    progress: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: Optional[int] = None
    speed: Optional[float] = None
    video_format: Optional[str] = None
    audio_format: Optional[str] = None
    merge: bool = True
    subtitles: List[str] = field(default_factory=list)
    auto_subtitles: bool = False
    prefer_container: str = 'mp4'
    filename_template: str = '%(title)s'
    retry: int = 3
    attempts: int = 0
    geo_bypass: bool = False
    file_path: Optional[str] = None
    title: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    log: List[str] = field(default_factory=list)
    canceled: bool = False
    # 新增：模式/质量/字幕专用
    mode: str = 'merged'  # merged | video_only | audio_only
    quality: str = 'best'  # auto|best8k|best4k|best|fast
    subtitles_only: bool = False
    # 新增：媒体元信息（用于前端展示）
    width: Optional[int] = None
    height: Optional[int] = None
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    filesize: Optional[int] = None
    partial_success: bool = False
    warning_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # 截断日志避免过大
        if len(d['log']) > 200:
            d['log'] = d['log'][-200:]
        return d

class TaskManager:
    def __init__(self, ytdlp_path: str, ffmpeg_locator, download_dir: str, cookies_file: str):
        self.ytdlp_path = ytdlp_path
        self.ffmpeg_locator = ffmpeg_locator
        self.download_dir = download_dir
        self.cookies_file = cookies_file
        self.tasks: Dict[str, Task] = {}
        self.tasks_lock = threading.Lock()
        self.queue = queue.Queue()
        self.max_workers = 2
        self.workers: List[threading.Thread] = []
        self.procs: Dict[str, Any] = {}
        self.aria2c_path: Optional[str] = self._detect_aria2c()
        self._stop = False
        self._start_workers()

    def _start_workers(self):
        for i in range(self.max_workers):
            t = threading.Thread(target=self._worker_loop, name=f'dl-worker-{i}', daemon=True)
            t.start()
            self.workers.append(t)
        logger.info(f"TaskManager: 启动 {self.max_workers} 个下载线程")

    def _detect_aria2c(self) -> Optional[str]:
        # 允许通过环境变量显式禁用，避免在某些环境弹出额外窗口
        if os.environ.get('LUMINA_DISABLE_ARIA2C','').lower() in ('1','true','yes'):
            return None
        # 优先使用环境变量指定路径
        p = os.environ.get('ARIA2C_PATH')
        if p and os.path.exists(p):
            return p
        # 尝试常见的打包路径
        bundled = os.path.join(os.getcwd(), 'aria2', 'aria2-1.36.0-win-64bit-build1', 'aria2c.exe')
        if os.path.exists(bundled):
            return bundled
        # 尝试 PATH 中的可执行文件
        w = shutil.which('aria2c') or shutil.which('aria2c.exe')
        if w:
            return w
        return None

    def _should_use_aria2c(self, url: str) -> bool:
        if self.aria2c_path is None:
            return False
        # 若显式设置禁用环境变量，直接 False
        if os.environ.get('LUMINA_DISABLE_ARIA2C','').lower() in ('1','true','yes'):
            return False
        try:
            host = urlparse(url).hostname or ''
            host = host.lower()
            # 对常见流媒体站点关闭 aria2c，交给 yt-dlp 原生处理
            blocked = (
                'youtube.com', 'youtu.be', 'googlevideo.com',
            )
            return self.aria2c_path is not None and not any(h in host for h in blocked)
        except Exception:
            return self.aria2c_path is not None

    def add_task(self, **kwargs) -> Task:
        task_id = str(uuid.uuid4())
        task = Task(id=task_id, **kwargs)
        
        # DEBUG: 记录任务创建时的参数
        mode = kwargs.get('mode', 'merged')
        quality = kwargs.get('quality', 'best')
        subtitles_only = kwargs.get('subtitles_only', False)
        logger.info(f"[TASK_ADD] 任务 {task_id} 创建 - Mode: {mode}, Quality: '{quality}', Subtitles_only: {subtitles_only}")
        
        with self.tasks_lock:
            self.tasks[task_id] = task
        self.queue.put(task_id)
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        with self.tasks_lock:
            return self.tasks.get(task_id)

    def list_tasks(self) -> List[Dict[str, Any]]:
        with self.tasks_lock:
            return [t.to_dict() for t in self.tasks.values()]

    def cleanup_finished_tasks(self) -> int:
        """移除所有已完成、错误或已取消的任务，并返回移除的数量。"""
        removed_count = 0
        with self.tasks_lock:
            finished_task_ids = [
                task_id for task_id, task in self.tasks.items()
                if task.status in ['finished', 'error', 'canceled']
            ]
            for task_id in finished_task_ids:
                del self.tasks[task_id]
                removed_count += 1
        logger.info(f"清除了 {removed_count} 个已完成/错误的任务")
        return removed_count

    # --------------- Worker Logic ---------------
    def _worker_loop(self):
        while not self._stop:
            try:
                task_id = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            task = self.get_task(task_id)
            if not task:
                self.queue.task_done()
                continue
            if task.status == 'canceled' or task.canceled:
                self.queue.task_done()
                continue
            try:
                self._execute_download(task)
            except Exception as e:
                code, msg = classify_error(str(e))
                self._update_task(task, status='error', error_code=code, error_message=msg)
                logger.error(f"Task {task.id} 失败: {msg}\n{traceback.format_exc()}")
            finally:
                self.queue.task_done()

    def _update_task(self, task: Task, **fields):
        with self.tasks_lock:
            for k,v in fields.items():
                setattr(task, k, v)
            task.updated_at = time.time()

    # --------------- Core Download ---------------
    def _execute_download(self, task: Task):
        task.attempts += 1
        self._update_task(task, status='downloading', stage='fetch_info')

        info = self._probe_info(task)
        title = info.get('title') or 'video'
        safe_title = self._safe_filename(title)
        base_template = task.filename_template.replace('%(title)s', safe_title)
        self._update_task(task, title=title)

        # 字幕专用流程（只下载字幕，不下载媒体）
        if getattr(task, 'subtitles_only', False):
            out_base = os.path.join(self.download_dir, f"{base_template}")
            args = [self.ytdlp_path, '--no-warnings', '--no-check-certificate', '--newline', '--ignore-errors',
                    '--skip-download', '--convert-subs', 'srt', '-o', out_base]
            # 字幕语言
            if task.subtitles:
                args += ['--write-subs', '--sub-langs', ','.join(task.subtitles)]
            if task.auto_subtitles:
                args += ['--write-auto-subs']
            if task.geo_bypass:
                args.append('--geo-bypass')
            # 对字幕-only：默认不再自动尝试浏览器提取，除非设置 LUMINA_FORCE_BROWSER_COOKIES=1
            if os.path.exists(self.cookies_file):
                args += ['--cookies', self.cookies_file]
                logger.info(f"[SUBTITLE] 使用cookies.txt文件: {self.cookies_file}")
            elif os.environ.get('LUMINA_FORCE_BROWSER_COOKIES','').lower() in ('1','true','yes'):
                try:
                    args += ['--cookies-from-browser', 'chrome']
                    logger.info("[SUBTITLE] FORCE 开启，尝试浏览器自动提取 cookies")
                except Exception:
                    logger.warning("[SUBTITLE] 浏览器 cookies 提取失败，将继续无 cookies")
            ffmpeg_path = self.ffmpeg_locator()
            if ffmpeg_path:
                args += ['--ffmpeg-location', ffmpeg_path]
            args.append(task.url)

            logger.info(f"Task {task.id} 字幕下载: {' '.join(args)}")
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='ignore', creationflags=CREATE_NO_WINDOW)
            self.procs[task.id] = proc
            for line in iter(proc.stdout.readline, ''):
                if task.canceled:
                    try: proc.kill()
                    except Exception: pass
                    self._update_task(task, status='canceled', stage=None); task.log.append('[canceled] 用户已取消任务');
                    break
                line = line.rstrip('\n');
                if line: task.log.append(line)
            proc.wait()
            try:
                self.procs.pop(task.id, None)
            except Exception:
                pass
            if proc.returncode != 0:
                raise RuntimeError(f"字幕下载失败 (exit={proc.returncode})\n最后输出: {task.log[-3:]} ")
            # 选择生成的 srt 文件（以 base_template 前缀匹配）
            chosen = None
            for fname in os.listdir(self.download_dir):
                if fname.startswith(os.path.basename(base_template)) and fname.endswith('.srt'):
                    chosen = os.path.join(self.download_dir, fname)
                    break
            if not chosen:
                raise RuntimeError('找不到生成的字幕文件')
            task.file_path = chosen
            # 合并每段为单行（就地修改）
            try:
                self._update_task(task, stage='merging', progress=85.0)
                normalize_srt_inplace(chosen)
                task.log.append('[subtitle] 已将每段字幕合并为单行')
            except Exception as ne:
                task.log.append(f'[subtitle] 合并单行失败: {ne}')
            self._update_task(task, status='finished', progress=100.0, stage=None)
            logger.info(f"Task {task.id} 字幕完成: {chosen}")
            return

        # -------- 媒体下载路径与格式选择 (重构部分) --------
        q = getattr(task, 'quality', 'auto')
        mode = getattr(task, 'mode', 'merged')

        height_cap: Optional[int] = None
        try:
            # 确保 q 是字符串类型
            q_str = str(q) if q is not None else ''
            if q_str:  # 只有当q_str非空时才尝试正则表达式
                m = re.search(r"height<=(\d+)", q_str)
                if m:
                    height_cap = int(m.group(1))
        except Exception:
            height_cap = None
        
        # 容器/输出策略重构：不提前写死扩展名，使用 yt-dlp 自判 ext；仅在明确 audio_only 时指定 m4a
        if mode == 'audio_only':
            forced_container = 'm4a'
        else:
            forced_container = None  # 让 yt-dlp 自选 (可能是 webm/mp4/mkv)

        out_path_template = os.path.join(self.download_dir, f"{base_template}.%(ext)s")
        # 任务初始 file_path 先记录模板（完成后再由实际文件填充或由前端展示）
        task.file_path = out_path_template

        # 格式选择器逻辑 (修复: 使用yt-dlp推荐的YouTube格式选择语法)
        q = getattr(task, 'quality', 'best')
        mode = getattr(task, 'mode', 'merged')
        
        logger.info(f"[FORMAT_SEL] 任务 {task.id} - Raw Quality: '{q}', Mode: {mode}")
        
        # 如果前端直接传入标准格式表达式（含 '[' 和 ']'）则尊重原始字符串
        if isinstance(q, str) and '[' in q and ']' in q:
            format_selector = q
            logger.info(f"[FORMAT_SEL] 使用前端直接传递的选择器: '{format_selector}'")
        else:
            if mode == 'audio_only':
                format_selector = 'bestaudio/best'
                logger.info(f"[FORMAT_SEL] 音频模式，选择器: '{format_selector}'")
            elif mode == 'video_only':
                # 视频仅下载（不需要音频）
                if q == 'best8k':
                    format_selector = 'bestvideo[height<=?4320]/bestvideo'
                elif q == 'best4k':
                    format_selector = 'bestvideo[height<=?2160]/bestvideo'
                elif q in ('best','auto'):
                    format_selector = 'bestvideo[height<=?1080]/bestvideo'
                elif q == '640p':
                    format_selector = 'bestvideo[height<=?640]/bestvideo'
                else:
                    format_selector = 'bestvideo[height<=?720]/bestvideo'
                logger.info(f"[FORMAT_SEL] 视频模式，选择器: '{format_selector}'")
            else:
                # merged 模式：组合优先，再回退单路 best。使用简洁别名 bv (bestvideo) / ba (bestaudio) / b (best)
                # 使用 "<=?" 让 yt-dlp 自动在没有该高度时向下兼容，bv* 代表首选最佳视频轨（含所有编解码可能）
                if q == 'best8k':
                    format_selector = 'bv[height<=?4320]+ba/best[height<=?4320]/b'
                elif q == 'best4k':
                    format_selector = 'bv[height<=?2160]+ba/best[height<=?2160]/b'
                elif q in ('best','auto'):
                    format_selector = 'bv[height<=?1080]+ba/best[height<=?1080]/b'
                elif q == 'fast':
                    # fast: 限制到 720p 以内，优先较低码率（让 YouTube 返回的更小）
                    format_selector = 'bv[height<=?720]+ba/best[height<=?720]/b'
                elif q == '640p':
                    format_selector = 'bv[height<=?640]+ba/best[height<=?640]/b'
                else:
                    # 尝试解析自定义 height<=X 的写法
                    try:
                        q_str = str(q)
                        m = re.search(r"height<=(\d+)", q_str)
                        if m:
                            custom_h = int(m.group(1))
                            # 自定义：使用 <=?custom_h 作为上限，向下兼容
                            format_selector = f'bv[height<=?{custom_h}]+ba/best[height<=?{custom_h}]/b'
                            logger.info(f"[FORMAT_SEL] 自定义高度上限 {custom_h}p 组合优先")
                        else:
                            format_selector = 'bv+ba/b'
                            logger.info("[FORMAT_SEL] 未识别质量参数，使用通用 bv+ba/b")
                    except Exception as e:
                        format_selector = 'bv+ba/b'
                        logger.warning(f"[FORMAT_SEL] 解析质量字符串失败: {e}，使用通用 bv+ba/b")
                logger.info(f"[FORMAT_SEL] 合并模式最终选择器: '{format_selector}'")

        # ---------- 构建与执行下载（更稳的默认 + 自动降级 + aria2c 兜底） ----------
        def build_args(conc: int, chunk: str, use_aria: bool=False) -> List[str]:
            # 确保所有参数都是字符串类型
            format_selector_str = str(format_selector) if format_selector is not None else 'best'
            a = [str(self.ytdlp_path), '-f', format_selector_str,
                 '--no-warnings', '--no-check-certificate', '--newline', '--ignore-errors',
                 '--socket-timeout', '15', '--retries', '20', '--fragment-retries', '50', '--retry-sleep', '2',
                 '--force-ipv4', '--concurrent-fragments', str(conc), '--http-chunk-size', chunk,
                 '--hls-prefer-native', '-o', out_path_template]
            # 如果用户是 audio_only 且我们想固定 m4a，则提供 merge-output-format；否则保持自适应
            if forced_container and mode == 'audio_only':
                a += ['--merge-output-format', forced_container]
            if task.geo_bypass:
                a.append('--geo-bypass')
            # Cookie 策略：默认只用 cookies.txt；仅在 FORCE 且未 DISABLE 且非 subtitles_only 时尝试浏览器
            force_browser = os.environ.get('LUMINA_FORCE_BROWSER_COOKIES','').lower() in ('1','true','yes')
            disable_browser = os.environ.get('LUMINA_DISABLE_BROWSER_COOKIES','').lower() in ('1','true','yes')
            if os.path.exists(str(self.cookies_file)):
                a += ['--cookies', str(self.cookies_file)]
                logger.info(f"[COOKIES] 使用cookies.txt文件: {self.cookies_file}")
            elif force_browser and not disable_browser and not getattr(task,'subtitles_only', False):
                try:
                    a += ['--cookies-from-browser', 'chrome']
                    logger.info("[COOKIES] FORCE 开启，尝试浏览器 cookies")
                except Exception:
                    logger.warning("[COOKIES] 浏览器 cookies 初始化失败，继续无 cookies")
            ffmpeg_path = self.ffmpeg_locator()
            if ffmpeg_path:
                a += ['--ffmpeg-location', ffmpeg_path]
            if use_aria:
                a += ['--downloader', 'http:aria2c', '--downloader', 'https:aria2c',
                      '--downloader-args', 'aria2c:-x16 -s16 -k1M -m16 --retry-wait=2 --summary-interval=1']
            a.append(task.url)
            
            # 添加格式选择调试信息
            logger.info(f"[YT_DLP_CMD] 任务 {task.id} - Format: '{format_selector_str}', OutputTemplate: {out_path_template}, Aria2c: {use_aria}, Full cmd length: {len(a)} args")
            # 记录实际使用的格式选择器供调试
            task.log.append(f"[DEBUG] 使用格式选择器: {format_selector_str}")
            return a

        def run_once(args: List[str], label: str) -> tuple[int, list[str]]:
            env = None
            if self.aria2c_path:
                env = os.environ.copy()
                aria_dir = os.path.dirname(self.aria2c_path)
                if aria_dir and aria_dir not in env.get('PATH', ''):
                    env['PATH'] = aria_dir + os.pathsep + env['PATH']
            logger.info(f"Task {task.id} 媒体下载[{label}]: {' '.join(args)}")
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding='utf-8', errors='ignore', env=env,
                                    creationflags=CREATE_NO_WINDOW)
            self.procs[task.id] = proc
            task.log.append(label)
            recent: list[str] = []
            try:
                for raw in iter(proc.stdout.readline, ''):
                    if task.canceled:
                        try: proc.kill()
                        except Exception: pass
                        self._update_task(task, status='canceled', stage=None)
                        task.log.append('[canceled] 用户已取消任务')
                        return 130, recent
                    line = (raw or '').rstrip('\n')
                    if not line:
                        continue
                    task.log.append(line)
                    recent.append(line)
                    if len(recent) > 400:
                        recent = recent[-400:]
                    try:
                        # 确保line是字符串类型
                        line_str = str(line) if line is not None else ''
                        m = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%", line_str) or re.search(r"\((\d{1,3})%\)", line_str)
                        if m:
                            pct = float(m.group(1))
                            self._update_task(task, progress=pct, stage='downloading')
                        elif 'Merging formats' in line_str or 'Merger' in line_str:
                            self._update_task(task, stage='merging')
                    except Exception:
                        pass
            finally:
                proc.wait()
                try: self.procs.pop(task.id, None)
                except Exception: pass
            return proc.returncode, recent

        # 尝试 1：稳健默认（并发=4, 分块=4M, IPv4, 重试更高）
        rc, recent = run_once(build_args(4, '4M', use_aria=False), '[speed] 使用内置下载器 (并发分片=4, 块=4M, IPv4)')

        def has_ssl_eof(lines: list[str]) -> bool:
            text = '\n'.join(lines).lower()
            return ('eof occurred in violation of protocol' in text) or ('ssleof' in text) or ('tlsv1' in text) or ('10054' in text) or ('connection reset' in text)

        if rc != 0 and has_ssl_eof(recent):
            task.log.append('[net] 检测到 SSLEOF/连接被对端提前关闭，降低并发与增大分块后重试…')
            rc, recent = run_once(build_args(2, '8M', use_aria=False), '[speed] 内置下载器降级重试 (并发=2, 块=8M, IPv4)')

        if rc != 0 and has_ssl_eof(recent):
            if self.aria2c_path:
                task.log.append('[net] 仍失败，切换 aria2c 兜底重试…')
                rc, recent = run_once(build_args(2, '8M', use_aria=True), '[speed] 使用 aria2c 兜底 (-x16 -s16 -k1M)')

        if rc != 0:
            raise RuntimeError(f"媒体下载失败 (exit={rc})\n最后输出: {recent[-3:]} ")

        # 下载成功后：根据模板解析真实文件（优先选择已经合并的文件；若不存在则识别组件文件）
        try:
            base_name = os.path.basename(base_template)
            merged_candidate = None
            component_files: List[str] = []
            comp_re = re.compile(rf"^{re.escape(base_name)}\.f(\d+)\.")
            for fname in os.listdir(self.download_dir):
                if not fname.startswith(base_name + '.') or '%(ext)' in fname:
                    continue
                fullp = os.path.join(self.download_dir, fname)
                if comp_re.search(fname):
                    component_files.append(fullp)
                else:
                    # 非 fXXX 形式，视为已合并输出
                    merged_candidate = fullp
            if merged_candidate and os.path.exists(merged_candidate):
                task.file_path = merged_candidate
                task.log.append(f"[detect] 发现已合并文件: {os.path.basename(merged_candidate)}")
            elif component_files:
                # 选择最新的视频组件作为当前 file_path（后续尝试组件合并）
                try:
                    component_files.sort(key=lambda p: os.stat(p).st_mtime, reverse=True)
                except Exception:
                    pass
                task.file_path = component_files[0]
                task.log.append(f"[detect] 未发现合并文件，组件文件数: {len(component_files)}，暂用: {os.path.basename(task.file_path)}")
                task.log.append("[component-scan] 组件文件: " + ', '.join(os.path.basename(p) for p in component_files))
        except Exception as resolve_err:
            task.log.append(f"[warn] 输出文件解析失败: {resolve_err}")

        # 先填充一次元数据（用于检测是否已有音频轨）
        try:
            self._fill_media_metadata(task)
        except Exception as meta_err:
            task.log.append(f"[warn] 初次元数据填充失败: {meta_err}")

        # 如果存在分离的组件文件且当前文件无音频，尝试直接组件合并（优先于重新下载 bestaudio）
        component_merged = False
        try:
            if mode == 'merged' and task.file_path and not getattr(task, 'acodec', None):
                # 重新扫描组件
                base_name = os.path.basename(base_template)
                comp_re = re.compile(rf"^{re.escape(base_name)}\.f(\d+)\.")
                components = []
                for fname in os.listdir(self.download_dir):
                    if fname.startswith(base_name + '.') and comp_re.search(fname):
                        components.append(os.path.join(self.download_dir, fname))
                if components:
                    # 分类视频/音频
                    video_parts = []
                    audio_parts = []
                    for fp in components:
                        kind = self._classify_media_file(fp)
                        if kind == 'video':
                            video_parts.append(fp)
                        elif kind == 'audio':
                            audio_parts.append(fp)
                    if video_parts and audio_parts:
                        # 取最新的视频、最新的音频
                        try:
                            video_parts.sort(key=lambda p: os.stat(p).st_mtime, reverse=True)
                            audio_parts.sort(key=lambda p: os.stat(p).st_mtime, reverse=True)
                        except Exception:
                            pass
                        vfile = video_parts[0]
                        afile = audio_parts[0]
                        ffmpeg_loc = self.ffmpeg_locator()
                        ffmpeg_bin = None
                        if ffmpeg_loc:
                            if os.path.isdir(ffmpeg_loc):
                                cand = os.path.join(ffmpeg_loc, 'ffmpeg.exe')
                                if os.path.exists(cand):
                                    ffmpeg_bin = cand
                                else:
                                    cand2 = os.path.join(ffmpeg_loc, 'ffmpeg')
                                    if os.path.exists(cand2):
                                        ffmpeg_bin = cand2
                            else:
                                ffmpeg_bin = ffmpeg_loc
                        if ffmpeg_bin:
                            merged_out = os.path.join(self.download_dir, f"{base_template}.mkv")
                            merge_cmd = [ffmpeg_bin, '-y', '-i', vfile, '-i', afile, '-c:v', 'copy', '-c:a', 'copy', '-map', '0:v:0', '-map', '1:a:0?', merged_out]
                            task.log.append('[component-merge] 检测到独立视频+音频组件，尝试直接合并')
                            task.log.append('[component-merge] ffmpeg 命令: ' + ' '.join(merge_cmd))
                            logger.info(f"Task {task.id} 组件合并: {' '.join(merge_cmd)}")
                            pm = subprocess.run(merge_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', creationflags=CREATE_NO_WINDOW)
                            if pm.returncode == 0 and os.path.exists(merged_out):
                                task.file_path = merged_out
                                component_merged = True
                                task.log.append('[component-merge] 合并成功 -> ' + os.path.basename(merged_out))
                                try:
                                    self._fill_media_metadata(task)
                                except Exception:
                                    pass
                            else:
                                task.log.append(f"[component-merge] 合并失败(exit={pm.returncode}) {pm.stderr[-160:]}" )
                        else:
                            task.log.append('[component-merge] 未找到 ffmpeg，无法组件合并')
        except Exception as ce:
            task.log.append(f'[component-merge] 处理异常: {ce}')

        # 如果期望合并(merged)且没有检测到音频轨，尝试补救：单独抓取 bestaudio 并用 ffmpeg 合并
        try:
            if mode == 'merged' and not task.canceled and not component_merged:
                no_audio = not getattr(task, 'acodec', None)
                if no_audio:
                    task.log.append('[audio-fallback] 未检测到音频轨，尝试下载音频并合并…')
                    ffmpeg_loc = self.ffmpeg_locator()
                    # 解析 ffmpeg 可执行文件路径
                    ffmpeg_bin = None
                    if ffmpeg_loc:
                        if os.path.isdir(ffmpeg_loc):
                            cand = os.path.join(ffmpeg_loc, 'ffmpeg.exe')
                            if os.path.exists(cand): ffmpeg_bin = cand
                            else:
                                cand2 = os.path.join(ffmpeg_loc, 'ffmpeg')
                                if os.path.exists(cand2): ffmpeg_bin = cand2
                        else:
                            ffmpeg_bin = ffmpeg_loc
                    if not ffmpeg_bin:
                        task.log.append('[audio-fallback] 找不到 ffmpeg，放弃补救')
                    else:
                        # 构建音频下载
                        audio_template = os.path.join(self.download_dir, f"{base_template}.audio.%(ext)s")
                        audio_args = [self.ytdlp_path, '-f', 'bestaudio/best', '--no-warnings', '--no-check-certificate', '--newline', '--ignore-errors', '-o', audio_template]
                        if os.path.exists(str(self.cookies_file)):
                            audio_args += ['--cookies', str(self.cookies_file)]
                        else:
                            try:
                                audio_args += ['--cookies-from-browser', 'chrome']
                            except Exception:
                                pass
                        if ffmpeg_loc:
                            audio_args += ['--ffmpeg-location', ffmpeg_loc]
                        audio_args.append(task.url)
                        task.log.append('[audio-fallback] 执行音频补抓: ' + ' '.join(audio_args))
                        logger.info(f"Task {task.id} 补抓音频: {' '.join(audio_args)}")
                        proc_a = subprocess.Popen(audio_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='ignore', creationflags=CREATE_NO_WINDOW)
                        for l in iter(proc_a.stdout.readline, ''):
                            if not l: continue
                            task.log.append('[A] ' + l.rstrip())
                        proc_a.wait()
                        if proc_a.returncode != 0:
                            task.log.append(f'[audio-fallback] 音频下载失败(exit={proc_a.returncode})')
                        else:
                            # 寻找音频文件
                            audio_file = None
                            base_name = os.path.basename(base_template)
                            for fname in os.listdir(self.download_dir):
                                if fname.startswith(base_name + '.audio.'):
                                    audio_file = os.path.join(self.download_dir, fname)
                                    break
                            if not audio_file:
                                task.log.append('[audio-fallback] 未找到音频文件，放弃补救')
                            else:
                                # 重新确认视频文件
                                video_file = task.file_path
                                if not video_file or not os.path.exists(video_file):
                                    task.log.append('[audio-fallback] 视频文件丢失，放弃合并')
                                else:
                                    # 生成合并输出：使用 mkv 容器以避免编解码兼容问题
                                    merged_out = os.path.join(self.download_dir, f"{base_template}.mkv")
                                    if os.path.abspath(merged_out) == os.path.abspath(video_file):
                                        merged_out = video_file + '.mkv'
                                    merge_cmd = [ffmpeg_bin, '-y', '-i', video_file, '-i', audio_file, '-c:v', 'copy', '-c:a', 'copy', '-map', '0:v:0', '-map', '1:a:0?', merged_out]
                                    task.log.append('[audio-fallback] ffmpeg 合并命令: ' + ' '.join(merge_cmd))
                                    logger.info(f"Task {task.id} 音频补救合并: {' '.join(merge_cmd)}")
                                    p_merge = subprocess.run(merge_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', creationflags=CREATE_NO_WINDOW)
                                    if p_merge.returncode != 0:
                                        task.log.append(f'[audio-fallback] 合并失败(exit={p_merge.returncode}) {p_merge.stderr[-200:]}')
                                    else:
                                        # 更新文件指向合并后的文件
                                        task.file_path = merged_out
                                        task.log.append('[audio-fallback] 合并成功，更新文件路径为 MKV')
                                        # 再次填充元数据
                                        try:
                                            self._fill_media_metadata(task)
                                        except Exception:
                                            pass
        except Exception as fallback_err:
            task.log.append(f'[audio-fallback] 处理异常: {fallback_err}')

        # 最终标记完成
        self._update_task(task, status='finished', progress=100.0, stage=None)
        logger.info(f"Task {task.id} 完成: {task.file_path}")

    def _fill_media_metadata(self, task: Task):
        """使用 ffprobe 填充 width/height/vcodec/acodec/filesize"""
        try:
            fp = task.file_path
            if not fp or not os.path.exists(fp):
                return
            ffmpeg_path = self.ffmpeg_locator()
            probe_bin = None
            if ffmpeg_path:
                if os.path.isdir(ffmpeg_path):
                    cand = os.path.join(ffmpeg_path, 'ffprobe.exe')
                    if os.path.exists(cand): probe_bin = cand
                else:
                    pdir = os.path.dirname(ffmpeg_path)
                    cand = os.path.join(pdir, 'ffprobe.exe')
                    if os.path.exists(cand): probe_bin = cand
            # 尝试 PATH 上的 ffprobe
            if not probe_bin:
                probe_bin = 'ffprobe'
            width = height = vcodec = acodec = None
            # 视频
            try:
                vc_cmd = [probe_bin, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,codec_name', '-of', 'default=noprint_wrappers=1:nokey=1', fp]
                p = subprocess.run(vc_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=10, creationflags=CREATE_NO_WINDOW)
                vals = [v.strip() for v in (p.stdout or '').strip().split('\n') if v.strip()]
                if len(vals) >= 3:
                    width, height, vcodec = vals[0], vals[1], vals[2]
            except Exception:
                pass
            # 音频
            try:
                ac_cmd = [probe_bin, '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1', fp]
                pa = subprocess.run(ac_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=6, creationflags=CREATE_NO_WINDOW)
                if pa.returncode == 0 and pa.stdout.strip():
                    acodec = pa.stdout.strip().split('\n')[0]
            except Exception:
                pass
            fsize = None
            try:
                fsize = os.path.getsize(fp)
            except Exception:
                pass
            fields = {}
            if width and str(width).isdigit(): fields['width'] = int(width)
            if height and str(height).isdigit(): fields['height'] = int(height)
            if vcodec: fields['vcodec'] = vcodec
            if acodec: fields['acodec'] = acodec
            if fsize is not None: fields['filesize'] = fsize
            if fields:
                self._update_task(task, **fields)
        except Exception as e:
            logger.debug(f"_fill_media_metadata failed: {e}")

    def _classify_media_file(self, fp: str) -> str:
        """简单区分文件包含视频还是音频流 (返回 video|audio|unknown)"""
        try:
            ffmpeg_path = self.ffmpeg_locator()
            probe_bin = None
            if ffmpeg_path:
                if os.path.isdir(ffmpeg_path):
                    cand = os.path.join(ffmpeg_path, 'ffprobe.exe')
                    if os.path.exists(cand):
                        probe_bin = cand
                else:
                    pdir = os.path.dirname(ffmpeg_path)
                    cand = os.path.join(pdir, 'ffprobe.exe')
                    if os.path.exists(cand):
                        probe_bin = cand
            if not probe_bin:
                probe_bin = 'ffprobe'
            cmd_v = [probe_bin, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name', '-of', 'csv=p=0', fp]
            pv = subprocess.run(cmd_v, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=6, creationflags=CREATE_NO_WINDOW)
            if pv.returncode == 0 and pv.stdout.strip():
                return 'video'
            cmd_a = [probe_bin, '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_name', '-of', 'csv=p=0', fp]
            pa = subprocess.run(cmd_a, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=6, creationflags=CREATE_NO_WINDOW)
            if pa.returncode == 0 and pa.stdout.strip():
                return 'audio'
            return 'unknown'
        except Exception:
            return 'unknown'


    def _probe_info(self, task: Task) -> Dict[str, Any]:
        cmd = [self.ytdlp_path, '--skip-download', '--dump-single-json', '--no-warnings', '--no-check-certificate']
        if task.geo_bypass:
            cmd.append('--geo-bypass')
        cmd.append(task.url)
        # Cookie 策略：有 cookies.txt 用文件；否则仅在未 subtitle-only 且未禁用时尝试浏览器自动提取
        # 新策略：默认不尝试浏览器提取，除非显式 LUMINA_FORCE_BROWSER_COOKIES=1
        try_browser = (
            os.environ.get('LUMINA_FORCE_BROWSER_COOKIES','').lower() in ('1','true','yes') and
            os.environ.get('LUMINA_DISABLE_BROWSER_COOKIES','').lower() not in ('1','true','yes') and
            not getattr(task, 'subtitles_only', False)
        )
        if os.path.exists(self.cookies_file):
            cmd += ['--cookies', self.cookies_file]
            logger.info(f"[PROBE] 使用cookies.txt文件: {self.cookies_file}")
        elif try_browser:
            try:
                cmd += ['--cookies-from-browser', 'chrome']
                logger.info("[PROBE] FORCE=1 且无 cookies.txt -> 尝试浏览器自动提取 (chrome)")
            except Exception:
                logger.warning("[PROBE] 浏览器 cookies 提取初始化失败，继续无 cookies")
        else:
            # 仅在既没有文件也没有 FORCE 时记录一次，避免用户误解默认会自动提取
            if os.environ.get('LUMINA_DISABLE_BROWSER_COOKIES','').lower() in ('1','true','yes'):
                logger.info("[PROBE] 未使用 cookies (已显式禁用浏览器提取, 无 cookies.txt)")
            else:
                logger.info("[PROBE] 未使用 cookies (无 cookies.txt 且未设置 FORCE)")
        
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=40, creationflags=CREATE_NO_WINDOW)
            if r.returncode != 0:
                err_text = (r.stderr or r.stdout)
                # 针对 Chrome cookie 数据库复制失败的特殊回退：去掉 '--cookies-from-browser' 重试一次
                if 'Could not copy Chrome cookie database' in err_text and '--cookies-from-browser' in ' '.join(cmd):
                    logger.warning('[PROBE] 浏览器 cookie 复制失败，回退为无 cookies 再试一次')
                    cmd_no_cookie = [c for c in cmd if c not in ('--cookies-from-browser','chrome')]
                    r2 = subprocess.run(cmd_no_cookie, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=40, creationflags=CREATE_NO_WINDOW)
                    if r2.returncode != 0:
                        raise RuntimeError(r2.stderr or r2.stdout or err_text)
                    result = json.loads(r2.stdout)
                else:
                    raise RuntimeError(err_text)
            else:
                result = json.loads(r.stdout)
            if result is None:
                raise RuntimeError("yt-dlp 返回 null，无法获取视频信息")
            return result
        except Exception as e:
            raise e

    def _safe_filename(self, name: str) -> str:
        name = re.sub(r'[\\/:*?"<>|]', '_', name)
        name = name.strip().strip('.')
        if len(name) > 150:
            name = name[:150]
        return name or 'video'


# ---------------- Subtitle Utilities: merge multi-line cue to single line ----------------
_cjk_ranges = (
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0x3400, 0x4DBF),  # CJK Extension A
    (0x3040, 0x30FF),  # Hiragana + Katakana
    (0xAC00, 0xD7AF),  # Hangul Syllables
)

def _is_cjk_char(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    for a,b in _cjk_ranges:
        if a <= cp <= b:
            return True
    return False

def _merge_lines_to_single(lines: List[str]) -> str:
    # 清理 HTML 标签并去首尾空白
    clean = [re.sub(r"<[^>]+>", "", (ln or "")).strip() for ln in lines]
    clean = [ln for ln in clean if ln]
    if not clean:
        return ""
    # 对话检测：以 - / – / — 开头
    has_dialog = any(re.match(r"^\s*[-–—]\s+", ln) for ln in clean)
    if has_dialog:
        parts = [re.sub(r"^\s*[-–—]\s*", "", ln) for ln in clean]
        out = " — ".join([p for p in parts if p])
        return re.sub(r"\s+", " ", out).strip()
    # 语言判定：按 CJK 字符占比
    sample = "".join(clean)
    if sample:
        nonspace = [ch for ch in sample if not ch.isspace()]
    else:
        nonspace = []
    cjk_cnt = sum(1 for ch in nonspace if _is_cjk_char(ch))
    ratio = (cjk_cnt / max(1, len(nonspace)))
    sep = "" if ratio >= 0.5 else " "
    out = sep.join(clean)
    if sep == " ":
        out = re.sub(r"\s+", " ", out)
    # 去掉标点前的多余空格
    out = re.sub(r"\s+([,\.!?;:])", r"\1", out)
    return out.strip()

def normalize_srt_inplace(path: str) -> None:
    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            content = f.read()
    except Exception:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    blocks = re.split(r"\r?\n\r?\n+", content.strip())
    ts_re = re.compile(r"\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}")
    out_blocks: List[str] = []
    for blk in blocks:
        lines = blk.splitlines()
        if len(lines) >= 3 and lines[0].strip().isdigit() and ts_re.match(lines[1].strip()):
            num = lines[0].strip()
            ts = lines[1].strip()
            text = _merge_lines_to_single(lines[2:])
            out_blocks.append(f"{num}\n{ts}\n{text}")
        else:
            out_blocks.append(blk.strip())
    new_content = "\n\n".join(out_blocks).rstrip() + "\n"
    with open(path, "w", encoding="utf-8", errors="ignore", newline="\n") as f:
        f.write(new_content)

task_manager: TaskManager | None = None

def init_task_manager(ytdlp_path, ffmpeg_locator, download_dir, cookies_file):
    global task_manager
    if task_manager is None:
        task_manager = TaskManager(ytdlp_path, ffmpeg_locator, download_dir, cookies_file)
    return task_manager

def cancel_task(task_id: str) -> bool:
    if not task_manager:
        return False
    t = task_manager.get_task(task_id)
    if not t:
        return False
    # 终止正在运行的进程（如果有）
    try:
        p = getattr(task_manager, 'procs', {}).get(task_id)
        if p and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass
    except Exception:
        pass
    # 标记取消
    if t.status not in ('finished','error','canceled'):
        t.canceled = True
        t.status = 'canceled'
        t.stage = None
        t.log.append('[canceled] 标记取消')
    # 清理进程表
    try:
        task_manager.procs.pop(task_id, None)
    except Exception:
        pass
    return True

__all__ = ['Task', 'TaskManager', 'init_task_manager', 'task_manager', 'cancel_task']
