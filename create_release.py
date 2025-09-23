# -*- coding: utf-8 -*-
import os
import shutil
import datetime
import zipfile
from pathlib import Path
try:
    from version import APP_VERSION
except Exception:
    APP_VERSION = "0.0.0"

def zip_dir(dir_path, zip_path):
    """将文件夹压缩成 zip 文件"""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, os.path.dirname(dir_path))
                zipf.write(file_path, arcname)

def main():
    """主函数"""
    print("=" * 50)
    print("Python Release Packager")
    print("=" * 50)

    # --- 1. 定义路径和版本号 ---
    project_root = Path(__file__).parent
    source_dir = project_root / "dist" / "流光下载器"
    release_dir = project_root / "release"
    
    date_tag = datetime.datetime.now().strftime("%Y%m%d")
    version = APP_VERSION
    release_name = f"流光下载器_v{version}_{date_tag}"
    release_path = release_dir / release_name
    zip_name = f"{release_name}.zip"
    zip_path = release_dir / zip_name

    # --- 2. 检查源文件是否存在 ---
    if not source_dir.exists():
        print(f"错误：未找到源文件夹 {source_dir}")
        print("请先运行 build.py 进行构建。")
        return

    print(f"源文件: {source_dir}")
    print(f"目标版本: {version} (日期标签 {date_tag})")

    # --- 3. 清理并创建发布目录 ---
    if release_dir.exists():
        print(f"清理旧的发布文件夹: {release_dir}")
        shutil.rmtree(release_dir)
    
    print(f"创建发布文件夹: {release_path}")
    release_path.mkdir(parents=True)

    # --- 4. 复制应用文件 ---
    print(f"正在复制应用文件到 {release_path}...")
    shutil.copytree(source_dir, release_path, dirs_exist_ok=True)

    # --- 5. 复制文档和二维码 ---
    print("正在复制附加文件...")
    files_to_copy = {
        "分发指南.md": "使用说明.md",
        "README.md": "README.md",
        "donate_qr.png": "打赏二维码.png"
    }
    for src, dest in files_to_copy.items():
        src_path = project_root / src
        if src_path.exists():
            shutil.copy(src_path, release_path / dest)
            print(f"  + 已复制: {dest}")
        else:
            print(f"  - 未找到: {src}")

    # --- 6. 创建压缩包 ---
    print(f"\n正在创建压缩包: {zip_name}...")
    try:
        zip_dir(release_path, zip_path)
        print(f"压缩包创建成功: {zip_path}")
        
        # 计算大��
        zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"压缩包大小: {zip_size_mb:.2f} MB")

    except Exception as e:
        print(f"创建压缩包失败: {e}")
        return

    print("\n" + "=" * 50)
    print("发布包创建完成！")
    print(f"请在 'release' 文件夹中查看: {zip_name}")
    print("=" * 50)

if __name__ == "__main__":
    main()
