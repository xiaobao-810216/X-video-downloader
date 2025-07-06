#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流光下载器打包脚本
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def run_command(cmd, description):
    """运行命令并显示结果"""
    print(f"\n正在{description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True, encoding='utf-8')
        print(f"+ {description}成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"- {description}失败:")
        print(f"错误: {e.stderr}")
        return False

def check_dependencies():
    """检查必要的依赖"""
    print("检查依赖项...")
    
    # 检查 PyInstaller
    try:
        import PyInstaller
        print("+ PyInstaller 已安装")
    except ImportError:
        print("- PyInstaller 未安装，正在安装...")
        if not run_command("pip install PyInstaller", "安装 PyInstaller"):
            return False
    
    # 检查必要文件
    required_files = [
        "app.py",
        "yt-dlp.exe",
        "templates",
        "static",
        "ffmpeg",
        "aria2"
    ]
    
    missing_files = []
    for file in required_files:
        if not Path(file).exists():
            missing_files.append(file)
    
    if missing_files:
        print("- 缺少必要文件:")
        for file in missing_files:
            print(f"  - {file}")
        return False
    
    print("+ 所有必要文件已就绪")
    return True

def clean_build():
    """清理构建目录"""
    print("\n清理旧的构建文件...")
    dirs_to_clean = ["build", "dist", "__pycache__"]
    
    for dir_name in dirs_to_clean:
        if Path(dir_name).exists():
            shutil.rmtree(dir_name)
            print(f"+ 已删除 {dir_name}")

def build_app():
    """构建应用"""
    print("\n开始打包应用...")
    
    if not run_command("pyinstaller build_app.spec", "打包应用"):
        return False
    
    # 检查输出文件
    exe_path = Path("dist/流光下载器/流光下载器.exe")
    if exe_path.exists():
        print(f"\n+ 打包成功！")
        print(f"  输出位置: {exe_path.absolute()}")
        print(f"  文件大小: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
        return True
    else:
        print("- 打包失败：找不到输出文件")
        return False

def main():
    """主函数"""
    print("=" * 50)
    print("流光下载器打包工具")
    print("=" * 50)
    
    # 检查依赖
    if not check_dependencies():
        print("\n- 依赖检查失败，请解决问题后重试")
        input("按回车键退出...")
        return 1
    
    # 清理构建目录
    clean_build()
    
    # 开始构建
    if build_app():
        print("\n+ 构建完成！")
        
        # 询问是否打开文件夹
        try:
            choice = input("\n是否打开输出文件夹? (y/n): ").lower()
            if choice == 'y':
                if sys.platform == "win32":
                    os.startfile("dist\\流光下载器")
                elif sys.platform == "darwin":
                    subprocess.run(["open", "dist/流光下载器"])
                else:
                    subprocess.run(["xdg-open", "dist/流光下载器"])
        except KeyboardInterrupt:
            pass
        
        return 0
    else:
        print("\n- 构建失败！")
        input("按回车键退出...")
        return 1

if __name__ == "__main__":
    # 设置标准输出编码为 UTF-8
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())