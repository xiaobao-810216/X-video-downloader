# run.py (最终物理隔离版启动器)
import sys
import time
import webbrowser
import threading
import multiprocessing
from app import app # 从我们的“引擎”文件 app.py 中导入 app 实例

if __name__ == '__main__':
    multiprocessing.freeze_support()
    
    def run_server():
        app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
    
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    
    time.sleep(2)
    webbrowser.open_new("http://127.0.0.1:5000")
    
    try:
        while server_thread.is_alive():
            server_thread.join(1)
    except (KeyboardInterrupt, SystemExit):
        pass