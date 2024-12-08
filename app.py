import logging
import os
import sys
import subprocess
import json
import traceback
import re
import yt_dlp
from flask import Flask, request, jsonify, render_template
from flask import send_from_directory, Response

# 尝试导入 flask_cors，如果失败则给出友好提示
try:
    from flask_cors import CORS
except ImportError:
    print("未找到 flask_cors 模块。请运行 'pip install flask-cors' 安装。")
    CORS = None  # 提供一个备选方案

# 设置更详细的日志
logging.basicConfig(
    level=logging.DEBUG,  # 改为 DEBUG 级别
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 输出到控制台
        logging.FileHandler('app.log', encoding='utf-8')  # 同时写入日志文件
    ]
)
logger = logging.getLogger(__name__)

# 设置 aria2c 路径
ARIA2C_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aria2', 'aria2-1.36.0-win-64bit-build1', 'aria2c.exe')

# 设置代理，如果需要的话
PROXY = None

app = Flask(__name__, static_folder='static', static_url_path='/static')
if CORS:
    CORS(app)  # 启用 CORS

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering template: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/video_info', methods=['GET', 'POST'])
def video_info():
    logger.debug(f"收到视频信息请求，方法: {request.method}")
    logger.debug(f"请求参数: {request.args}")
    logger.debug(f"请求表单: {request.form}")

    try:
        if request.method == 'POST':
            url = request.form.get('url')
        else:
            url = request.args.get('url')
        
        logger.debug(f"解析出的 URL: {url}")
            
        if not url:
            logger.error("未提供视频链接")
            return jsonify({'error': '请提供视频链接'}), 400

        logger.info(f"请求视频信息的 URL: {url}")
        try:
            logger.info("开始提取视频 ID...")
            video_id = extract_video_id(url)
            if not video_id:
                logger.error("未能提取视频 ID")
                logger.error(f"视频链接：{url}")
                return jsonify({'error': '无效的视频链接'}), 400
            logger.info(f"成功提取视频 ID: {video_id}")
            logger.info("开始获取视频信息...")
            try:
                # 使用 yt-dlp 获取详细的格式信息
                ydl_opts = {
                    'quiet': False,  # 改为 False 以获取更多信息
                    'no_warnings': False,  # 改为 False 以获取警告信息
                    'no_color': True,
                    'extract_flat': False,  # 改为 False 以获取完整信息
                    'format': 'best'  # 确保获取最佳格式
                }
                
                # 转换 URL 为 Twitter 域名
                twitter_url = url.replace('x.com', 'twitter.com')
                
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        logger.debug(f"开始使用 yt-dlp 提取 {twitter_url} 的信息")
                        info_dict = ydl.extract_info(twitter_url, download=False)
                        
                        logger.debug(f"成功获取视频信息字典: {info_dict.keys()}")
                        
                        # 处理格式信息
                        formats = []
                        if 'formats' in info_dict:
                            for fmt in info_dict['formats']:
                                # 只保留视频格式
                                if fmt.get('vcodec', 'none') != 'none':
                                    format_info = {
                                        'format_id': fmt.get('format_id', ''),
                                        'resolution': f"{fmt.get('width', 0)}x{fmt.get('height', 0)}",
                                        'ext': fmt.get('ext', 'mp4'),
                                        'filesize': fmt.get('filesize', 0) or 0,
                                        'tbr': fmt.get('tbr', 0)  # 总比特率
                                    }
                                    formats.append(format_info)
                        
                        # 按分辨率排序
                        formats.sort(key=lambda x: int(x['resolution'].split('x')[1]) if 'x' in x['resolution'] else 0, reverse=True)
                        
                        video_data = {
                            'title': info_dict.get('title', f'Twitter Video {video_id}'),
                            'formats': formats
                        }
                        
                        logger.info(f"成功获取视频信息: {video_data}")
                        return jsonify(video_data)
                
                except Exception as extract_error:
                    logger.error(f"yt-dlp 提取信息失败: {str(extract_error)}")
                    logger.error(f"错误详情: {traceback.format_exc()}")
                    return jsonify({'error': f'无法获取视频信息: {str(extract_error)}'}), 500
            
            except Exception as e:
                logger.error(f"获取视频信息时发生错误: {str(e)}")
                logger.error(f"错误详情: {traceback.format_exc()}")
                return jsonify({'error': f'获取视频信息失败: {str(e)}'}), 500
        except Exception as e:
            logger.error(f"获取视频信息时发生错误: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            return jsonify({'error': f'获取视频信息失败: {str(e)}'}), 500
    
    except Exception as e:
        logger.error(f"处理视频信息请求时发生错误: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        return jsonify({'error': f'处理请求失败: {str(e)}'}), 500

@app.route('/download', methods=['GET'])
def download_video():
    try:
        url = request.args.get('url')
        
        logger.info(f"下载请求 - URL: {url}")
        
        if not url:
            logger.error("缺少 URL 参数")
            return jsonify({'error': '缺少必要的下载参数'}), 400
        
        # 转换 URL 为 Twitter 域名
        twitter_url = url.replace('x.com', 'twitter.com')
        
        def generate():
            try:
                # 桌面路径
                desktop_path = os.path.expanduser('~/Desktop')
                
                # 极简和高性能的 yt-dlp 配置
                ydl_opts = {
                    'format': 'best[ext=mp4]',  # 选择最佳 MP4 格式
                    'merge_output_format': 'mp4',
                    'outtmpl': os.path.join(desktop_path, '%(title).80s.%(ext)s'),  # 缩短文件名
                    
                    # 性能优化
                    'no_color': True,
                    'quiet': True,  # 最小化日志
                    'no_warnings': True,
                    'nooverwrites': True,
                    
                    # 网络性能极致优化
                    'socket_timeout': 5,  # 缩短超时
                    'retries': 1,  # 减少重试
                    'fragment_retries': 1,
                    'concurrent_fragments': 16,  # 增加并发数
                    'buffer_size': '16M',  # 增大缓冲区
                    
                    # 精简信息提取
                    'extract_flat': True,
                    
                    # 最小化处理开销
                    'no_mtime': True,
                    'no_part': True,
                    'ignoreerrors': True,
                    
                    # 进度钩子
                    'progress_hooks': [
                        lambda d: logger.info(f"下载进度: {d.get('_percent_str', 'N/A')}")
                    ],
                    
                    # 后处理优化
                    'postprocessors': [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mp4',
                    }],
                    'postprocessor_args': ['-vcodec', 'libx264', '-acodec', 'aac', '-threads', '0', '-preset', 'ultrafast']
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    logger.info(f"开始快速下载: {twitter_url}")
                    
                    try:
                        # 单步获取信息并下载
                        info_dict = ydl.extract_info(twitter_url, download=True)
                        
                        # 准备文件路径
                        downloaded_file = ydl.prepare_filename(info_dict)
                        
                        # 快速检查文件
                        if os.path.exists(downloaded_file):
                            file_size = os.path.getsize(downloaded_file)
                            logger.info(f"视频已下载: {downloaded_file} ({file_size} 字节)")
                            
                            # 发送下载完成事件
                            yield f"data: {json.dumps({'percent': 100, 'message': '下载完成', 'file': downloaded_file})}\n\n"
                        else:
                            logger.error(f"文件未找到: {downloaded_file}")
                            yield f"data: {json.dumps({'error': '视频下载失败'})}\n\n"
                    
                    except Exception as e:
                        logger.error(f"下载过程错误: {str(e)}")
                        logger.error(f"错误追踪: {traceback.format_exc()}")
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
            except Exception as e:
                logger.error(f"处理过程未知错误: {str(e)}")
                logger.error(f"错误追踪: {traceback.format_exc()}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return Response(generate(), mimetype='text/event-stream')
    
    except Exception as e:
        logger.error(f"请求处理错误: {str(e)}")
        logger.error(f"错误追踪: {traceback.format_exc()}")
        return jsonify({'error': f'处理下载请求失败: {str(e)}'}), 500

@app.route('/test')
def test():
    return "Hello, this is a test page!"

def extract_video_id(url):
    # 使用正则表达式提取 Twitter/X 视频 ID
    match = re.search(r'/status/(\d+)', url)
    if match:
        return match.group(1)
    return None

def get_video_data(url):
    # 这里是获取视频信息的逻辑
    # 假设我们返回一个模拟的视频数据
    return {
        'title': '示例视频',
        'description': '这是一个示例视频描述',
        'url': url
    }

if __name__ == '__main__':
    print("启动 Flask 应用...")
    print(f"Python 版本: {sys.version}")
    
    try:
        import flask
        print(f"Flask 版本: {flask.__version__}")
        
        # 添加更多的调试信息
        print("尝试配置应用...")
        
        # 确保日志输出到文件
        file_handler = logging.FileHandler('flask_debug.log', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
        
        # 运行应用
        print("开始运行应用...")
        app.run(
            host='0.0.0.0', 
            port=5000, 
            debug=True,
            use_reloader=False  # 禁用重载器以便更好地捕获错误
        )
    except Exception as e:
        print(f"启动失败，错误信息: {e}")
        print(f"详细错误追踪: {traceback.format_exc()}")
        # 将错误写入日志文件
        with open('startup_error.log', 'w', encoding='utf-8') as f:
            f.write(f"启动失败，错误信息: {e}\n")
            f.write(f"详细错误追踪: {traceback.format_exc()}")
