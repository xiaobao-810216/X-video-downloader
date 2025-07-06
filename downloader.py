# 这是 downloader.py 的全部内容
import multiprocessing
from yt_dlp import main

if __name__ == '__main__':
    # 这一行是必须的，防止它在某些情况下也产生问题
    multiprocessing.freeze_support()
    # 直接运行 yt-dlp 的主函数
    main()