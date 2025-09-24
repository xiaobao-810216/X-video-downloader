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

    now = datetime.datetime.now()
    date_tag = now.strftime("%Y%m%d")
    timestamp_tag = now.strftime("%Y%m%d_%H%M%S")
    version = APP_VERSION
    # 旧命名: 带日期 (保留兼容)
    release_name = f"流光下载器_v{version}_{date_tag}"
    release_path = release_dir / release_name
    dated_zip_name = f"{release_name}.zip"
    dated_zip_path = release_dir / dated_zip_name
    # 新增稳定/时间戳命名
    stable_zip_name = f"流光下载器_v{version}_Windows.zip"  # 稳定文件名，方便脚本/用户总是获取最新版
    ts_zip_name = f"流光下载器_v{version}_Windows_{timestamp_tag}.zip"  # 精确时间戳版本
    stable_zip_path = release_dir / stable_zip_name
    ts_zip_path = release_dir / ts_zip_name

    # --- 2. 检查源文件是否存在 ---
    if not source_dir.exists():
        print(f"错误：未找到源文件夹 {source_dir}")
        print("请先运行 build.py 进行构建。")
        return

    print(f"源文件: {source_dir}")
    print(f"目标版本: {version} (日期标签 {date_tag})")

    # --- 3. 创建发布根目录 (不再整体删除，保留历史版本) ---
    if not release_dir.exists():
        release_dir.mkdir(parents=True)
        print(f"创建发布根目录: {release_dir}")
    # 若已有同名日期目录，先删除再重建，避免残留旧文件
    if release_path.exists():
        print(f"移除同名旧目录: {release_path}")
        shutil.rmtree(release_path)
    print(f"创建发布目录: {release_path}")
    release_path.mkdir(parents=True, exist_ok=True)

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
    created = []
    def _make_zip(src_dir: Path, target_zip: Path, label: str):
        try:
            if target_zip.exists():
                target_zip.unlink()
            zip_dir(src_dir, target_zip)
            size_mb = target_zip.stat().st_size / (1024 * 1024)
            print(f"  + {label} -> {target_zip.name} ({size_mb:.2f} MB)")
            created.append(target_zip.name)
        except Exception as e:
            print(f"  - {label} 失败: {e}")

    print("\n创建压缩包:")
    _make_zip(release_path, dated_zip_path, "日期版")
    _make_zip(release_path, ts_zip_path, "时间戳版")
    _make_zip(release_path, stable_zip_path, "稳定版 (覆盖)")

    print("\n" + "=" * 50)
    print("发布包创建完成！")
    print("生成文件:")
    for name in created:
        print(f"  - {name}")
    print(f"\n稳定版下载直链文件名 (总是最新版本覆盖): {stable_zip_name}")
    print("=" * 50)

if __name__ == "__main__":
    main()
