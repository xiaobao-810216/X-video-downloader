import logging, os, sys, subprocess, json, traceback, re, datetime, shutil, uuid, queue, threading, time
from flask import Flask, request, Response, render_template, jsonify
import webbrowser
from threading import Timer

# --- 主应用代码 ---
try:
    from flask_cors import CORS
except ImportError:
    CORS = None

# 定义一个全局的、只在Windows上生效的创建标志，用于隐藏子进程窗口
CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- 基本配置和日志 ---
COOKIES_FILE = resource_path("cookies.txt")
YTDLP_PATH = resource_path("yt-dlp.exe")
ARIA2C_PATH = resource_path(os.path.join("aria2", "aria2-1.36.0-win-64bit-build1", "aria2c.exe"))
FFMPEG_BUNDLED_PATH = resource_path(os.path.join("ffmpeg", "bin", "ffmpeg.exe"))
FFMPEG_SYSTEM_PATH = "ffmpeg.exe"
DOWNLOAD_DIR = os.path.join(os.path.expanduser('~'), 'Desktop')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- 任务队列和状态管�� ---
download_queue = queue.Queue()
tasks = {}
tasks_lock = threading.Lock()

# --- 缓存 ---
_ffmpeg_path_cache = None
video_info_cache = {}

def get_ffmpeg_path():
    global _ffmpeg_path_cache
    if _ffmpeg_path_cache is not None: return _ffmpeg_path_cache
    if os.path.exists(FFMPEG_BUNDLED_PATH):
        try:
            subprocess.run([FFMPEG_BUNDLED_PATH, '-version'], capture_output=True, check=True, creationflags=CREATE_NO_WINDOW, timeout=5)
            logger.info("使用打包的 FFmpeg")
            _ffmpeg_path_cache = FFMPEG_BUNDLED_PATH
            return _ffmpeg_path_cache
        except: logger.warning("打包的 FFmpeg 不可用")
    try:
        subprocess.run([FFMPEG_SYSTEM_PATH, '-version'], capture_output=True, check=True, creationflags=CREATE_NO_WINDOW, timeout=5)
        logger.info("使用系统 FFmpeg")
        _ffmpeg_path_cache = FFMPEG_SYSTEM_PATH
        return _ffmpeg_path_cache
    except: logger.warning("系统 FFmpeg 不可用")
    _ffmpeg_path_cache = False
    return None

LANGUAGE_CODES = {'en': '英语', 'zh-CN': '简体中文', 'zh-Hant': '繁体中文', 'ja': '日语', 'ko': '韩语', 'de': '德语', 'fr': '法语', 'es': '西班牙语', 'ru': '俄语'}

def setup_logging():
    log_dir = os.path.join(DOWNLOAD_DIR, "流光下载器日志")
    os.makedirs(log_dir, exist_ok=True)
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    root_logger = logging.getLogger()
    if root_logger.hasHandlers(): root_logger.handlers.clear()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    file_handler = logging.FileHandler(os.path.join(log_dir, f'app_{datetime.datetime.now().strftime("%Y%m%d")}.log'), encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    return logging.getLogger(__name__)

logger = setup_logging()
app = Flask(__name__, template_folder=resource_path('templates'), static_folder=resource_path('static'))
if CORS: CORS(app)

def get_video_info(url, is_playlist=False):
    """获取视频信息，添加超时和缓存机制。为播放列表单独处理。"""
    # 对播放列表禁用缓存，因为内容可能经常变化
    if not is_playlist:
        cache_key = url
        if cache_key in video_info_cache:
            logger.info("使用缓存的视频信息")
            return video_info_cache[cache_key]

    # 基础命令
    cmd = [YTDLP_PATH, '--no-warnings', '--dump-json', '--no-check-certificate',
           '--socket-timeout', '15', '--extractor-retries', '3']

    # 为播放列表使用 --flat-playlist 提高效率
    if is_playlist:
        cmd.extend(['--flat-playlist'])
    else:
        # 单个视频不处理播放列表，加快速度
        cmd.extend(['--no-playlist'])

    cmd.append(url)

    # 添加 Cookies
    if os.path.exists(COOKIES_FILE):
        cmd.extend(['--cookies', COOKIES_FILE])
    else:
        try:
            cmd.extend(['--cookies-from-browser', 'chrome'])
        except Exception:
            logger.warning("无法从浏览器自动提取 cookies")

    try:
        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                               errors='ignore', creationflags=CREATE_NO_WINDOW, timeout=30)

        if process.returncode != 0:
            raise Exception(f"获取视频信息失败: {process.stderr}")

        lines = process.stdout.strip().split('\n')
        
        # 检查是否是播放列表的响应
        first_line_data = json.loads(lines[0])
        is_playlist_response = first_line_data.get('_type') == 'playlist' or 'playlist' in first_line_data

        if is_playlist_response:
            # 如果是播放列表，我们已经用了 --flat-playlist，直接处理
            info = [json.loads(line) for line in lines]
            playlist_title = info[0].get('playlist_title') or info[0].get('title', '未知播放列表')
            for entry in info:
                entry['is_playlist'] = True
                entry['playlist_title'] = playlist_title
            return info
        else:
            # 单个视频
            info = json.loads(lines[0])
            if not is_playlist:
                if len(video_info_cache) >= 20:
                    video_info_cache.pop(next(iter(video_info_cache)))
                video_info_cache[url] = info
            return info

    except subprocess.TimeoutExpired:
        raise Exception("获取视频信息超时")
    except json.JSONDecodeError:
        raise Exception("视频信息解析失败")

def download_worker():
    """后台下载工作线程，现在能处理视频和字幕"""
    while True:
        task_id = download_queue.get()
        if task_id is None: break

        with tasks_lock:
            tasks[task_id]['status'] = 'downloading'
            task = tasks[task_id]
        
        try:
            if task['type'] == 'video':
                execute_video_download(task_id, task)
            elif task['type'] == 'subtitle':
                execute_subtitle_download(task_id, task)
            else:
                raise ValueError(f"未知的任务类型: {task['type']}")

        except Exception as e:
            logger.error(f"任务 {task_id} 失败: {traceback.format_exc()}")
            with tasks_lock:
                if task_id in tasks:
                    tasks[task_id]['status'] = 'error'
                    tasks[task_id]['error_message'] = str(e)
        
        download_queue.task_done()

def execute_video_download(task_id, task):
    """执行视频下载"""
    url = task['url']
    if not url: raise ValueError("任务URL为空")

    title = re.sub(r'[\/*?:"><>|]', '_', task.get('title', 'video_file'))
    output_path = os.path.join(DOWNLOAD_DIR, f"{title[:150]}.mp4")
    
    format_string = 'bestvideo[height<=1080]+bestaudio[ext=m4a]/best' if task['quality'] == 'best' else 'best[height<=720]/best'
    
    dl_cmd = [YTDLP_PATH, '--no-warnings', '--force-overwrites', '--no-check-certificate', 
             '--socket-timeout', '12', '--retries', '3', '--fragment-retries', '5',
             '--no-part', '--concurrent-fragments', '4', '--no-playlist',
             '-f', format_string, '--merge-output-format', 'mp4', '-o', output_path]

    if os.path.exists(COOKIES_FILE): dl_cmd.extend(['--cookies', COOKIES_FILE])
    else: dl_cmd.extend(['--cookies-from-browser', 'chrome'])
    
    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path: dl_cmd.extend(['--ffmpeg-location', ffmpeg_path])
    if os.path.exists(ARIA2C_PATH):
        dl_cmd.extend(['--downloader', 'aria2c', '--downloader-args', "max-connection-per-server=16,min-split-size=1M"])
    
    dl_cmd.append(url)
    
    process = subprocess.Popen(dl_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                             text=True, encoding='utf-8', errors='ignore', bufsize=1, 
                             creationflags=CREATE_NO_WINDOW)

    for line in iter(process.stdout.readline, ''):
        percent = -1
        match_aria = re.search(r'\((\d{1,3})%\)', line)
        if match_aria: percent = int(match_aria.group(1))
        else:
            match_ydl = re.search(r'\[download\]\s+([\d\.]+)\s*%', line)
            if match_ydl: percent = float(match_ydl.group(1))
        
        with tasks_lock:
            if task_id in tasks:
                if percent >= 0: tasks[task_id]['progress'] = percent
                if '[Merger]' in line: tasks[task_id]['status'] = 'merging'

    process.wait()
    if process.returncode == 0 and os.path.exists(output_path):
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['status'] = 'finished'
                tasks[task_id]['progress'] = 100
    else:
        error_output = process.stderr.read() if process.stderr else "未知错误"
        raise RuntimeError(f"下载失败: {error_output}")

def execute_subtitle_download(task_id, task):
    """执行字幕下载和处理"""
    url = task['url']
    lang = task['sub_lang']
    if not url or not lang: raise ValueError("URL或字幕语言为空")

    title = re.sub(r'[\/*?:"><>|]', '_', task.get('title', 'video_file').replace('[字幕] ', ''))
    output_base = os.path.join(DOWNLOAD_DIR, f"{title[:150]}")
    
    with tasks_lock:
        tasks[task_id]['progress'] = 20

    subtitle_extensions = ('.srt', '.vtt', '.ass')
    files_before = {f for f in os.listdir(DOWNLOAD_DIR) if f.endswith(subtitle_extensions)}

    dl_cmd = [YTDLP_PATH, '--no-warnings', '--force-overwrites', '--no-check-certificate',
             '--write-subs', '--sub-langs', lang, '--skip-download',
             '--convert-subs', 'srt', '-o', output_base]
    
    if os.path.exists(COOKIES_FILE): dl_cmd.extend(['--cookies', COOKIES_FILE])
    else: dl_cmd.extend(['--cookies-from-browser', 'chrome'])

    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path: dl_cmd.extend(['--ffmpeg-location', ffmpeg_path])

    dl_cmd.append(url)
    
    process = subprocess.run(dl_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', creationflags=CREATE_NO_WINDOW)
    
    if process.returncode != 0:
        raise RuntimeError(f"yt-dlp下载字幕失败: {process.stderr}")

    with tasks_lock:
        tasks[task_id]['progress'] = 70
        tasks[task_id]['status'] = 'merging' # 用merging表示正在后处理

    files_after = {f for f in os.listdir(DOWNLOAD_DIR) if f.endswith(subtitle_extensions)}
    new_files = files_after - files_before
    
    if not new_files:
        raise RuntimeError("找不到下载的字幕文件，请检查yt-dlp的输出")

    # 优先选择SRT
    srt_files = [f for f in new_files if f.endswith('.srt')]
    subtitle_file_name = srt_files[0] if srt_files else new_files.pop()
    subtitle_file_path = os.path.join(DOWNLOAD_DIR, subtitle_file_name)

    # --- 恢复的核心：SRT文件处理 ---
    try:
        with open(subtitle_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        blocks = content.strip().split('\n\n')
        cleaned_blocks = []
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 2:
                index_line = lines[0]
                time_line = lines[1]
                text_lines = [line.strip() for line in lines[2:] if line.strip()]
                
                if text_lines:
                    merged_text = ' '.join(text_lines)
                    cleaned_block = f"{index_line}\n{time_line}\n{merged_text}"
                    cleaned_blocks.append(cleaned_block)
        
        final_content = '\n\n'.join(cleaned_blocks)
        with open(subtitle_file_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
        logger.info(f"字幕文件 {subtitle_file_name} 已成功处理。")
    except Exception as e:
        logger.error(f"处理SRT文件时出错: {e}")
        raise RuntimeError("字幕文件后处理失败")

    with tasks_lock:
        if task_id in tasks:
            tasks[task_id]['status'] = 'finished'
            tasks[task_id]['progress'] = 100


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/info')
def video_info_route():
    url = request.args.get('url')
    if not url: return jsonify({'error': '缺少URL参数'}), 400
    
    try:
        # 终极修复 V2：逻辑更清晰
        # 1. 优先判断是否为播放列表
        is_playlist = 'list=' in url
        
        # 2. 如果是播放列表，强制使用 --flat-playlist
        if is_playlist:
            info = get_video_info(url, is_playlist=True)
            
            if not isinstance(info, list): # yt-dlp 可能只返回一个 playlist ���型的 json
                info = info.get('entries', [])

            playlist_title = "未知播放列表"
            # 尝试从第一个有效的视频条目中获取列表标题
            if info and info[0] and info[0].get('playlist_title'):
                playlist_title = info[0].get('playlist_title')
            
            videos = [{'id': entry.get('id'), 'url': entry.get('webpage_url', entry.get('url')), 'title': entry.get('title', '未知标题')} for entry in info if entry]
            return jsonify({'type': 'playlist', 'title': playlist_title, 'videos': videos, 'playlist_url': url})

        # 3. 如果不是播放列表，则作为单个视频处理
        else:
            info = get_video_info(url, is_playlist=False)
            if isinstance(info, list): info = info[0] # 防御性编程

            title = info.get('title', '未知标题')
            sub_options = []
            found_langs = set()
            
            manual_subs = info.get('subtitles', {})
            auto_captions = info.get('automatic_captions', {})
            
            for lang_code in sorted(manual_subs.keys()):
                if lang_code not in found_langs:
                    display_name = LANGUAGE_CODES.get(lang_code, lang_code)
                    sub_options.append({'value': lang_code, 'text': f'{display_name} (官方)'})
                    found_langs.add(lang_code)

            for lang_code in sorted(auto_captions.keys()):
                simple_lang_code = lang_code.split('-')[0]
                if simple_lang_code not in found_langs:
                    display_name = LANGUAGE_CODES.get(simple_lang_code, simple_lang_code)
                    sub_options.append({'value': lang_code, 'text': f'{display_name} (自动)'})
                    found_langs.add(simple_lang_code)
            
            return jsonify({
                'type': 'video', 
                'title': title, 
                'id': info.get('id'), 
                'url': info.get('webpage_url', url),
                'sub_options': sub_options
            })
            
    except Exception as e:
        logger.error(f"获取信息失败: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/add_to_queue', methods=['POST'])
def add_to_queue():
    data = request.json
    videos = data.get('videos', [])
    quality = data.get('quality', 'best')
    task_type = data.get('task_type', 'video') # 'video' or 'subtitle'
    sub_lang = data.get('sub_lang')

    if not videos:
        return jsonify({'error': '没有要添加的项目'}), 400

    added_count = 0
    with tasks_lock:
        for video in videos:
            if not video or not video.get('url'):
                logger.warning(f"跳过无效任务（缺少URL）：{video.get('title', '未知标题')}")
                continue

            task_id = str(uuid.uuid4())
            
            title = video['title']
            if task_type == 'subtitle':
                title = f"[字幕] {title}"

            tasks[task_id] = {
                'id': task_id,
                'url': video['url'],
                'title': title,
                'status': 'queued',
                'progress': 0,
                'type': task_type,
                # 特定于类型的数据
                'quality': quality if task_type == 'video' else None,
                'sub_lang': sub_lang if task_type == 'subtitle' else None,
            }
            download_queue.put(task_id)
            logger.info(f"任务 {task_id} ({title}) 已添加到队列")
            added_count += 1

    if added_count > 0:
        return jsonify({'message': f'{added_count} 个任务已添加到队列'})
    else:
        return jsonify({'error': '未能添加任何有效任务'}), 400

@app.route('/queue_status')
def queue_status():
    with tasks_lock:
        tasks_copy = list(tasks.values())
    
    status_order = {'downloading': 0, 'merging': 1, 'queued': 2, 'finished': 3, 'error': 4}
    sorted_tasks = sorted(tasks_copy, key=lambda x: status_order.get(x['status'], 99))
    
    return jsonify(sorted_tasks)

@app.route('/clear_finished', methods=['POST'])
def clear_finished():
    with tasks_lock:
        finished_task_ids = [task_id for task_id, task in tasks.items() if task['status'] in ['finished', 'error']]
        for task_id in finished_task_ids:
            del tasks[task_id]
    logger.info(f"清除了 {len(finished_task_ids)} 个已完成/错误的任务")
    return jsonify({'message': '已清除已完成的任务'})


def open_browser():
    webbrowser.open_new("http://127.0.0.1:5001")

if __name__ == '__main__':
    logger.info("🚀 正在初始化流光下载器...")
    get_ffmpeg_path()
    
    worker_thread = threading.Thread(target=download_worker, daemon=True)
    worker_thread.start()
    logger.info("✅ 后台下载线程已启动")

    if not os.path.exists(COOKIES_FILE):
        logger.warning("="*50)
        logger.warning("未找到 cookies.txt 文件！请注意需要登录的网站可能下载失败。")
        logger.warning("="*50)
    
    logger.info("服务器即将启动在 http://127.0.0.1:5001")
    Timer(1, open_browser).start()
    
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['JSON_AS_ASCII'] = False
    
    @app.after_request
    def after_request(response):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    logger.info("🎬 流光下载器启动成功！")
    app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False, threaded=True)
