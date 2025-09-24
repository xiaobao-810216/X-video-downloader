#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流光下载器打包脚本
"""

import os
import sys
import shutil
import subprocess
import time
import stat
from pathlib import Path
import importlib.util
import ctypes
try:
    from version import APP_VERSION
except Exception:
    APP_VERSION = "0.0.0"

# -------------------------------------------------------------
# 环境自检：避免用意外的解释器 (例如 conda env) 打包导致 _ctypes 缺失
# -------------------------------------------------------------
def environment_self_check():
    print("\n[环境自检] Python 可执行: ", sys.executable)
    print("[环境自检] sys.prefix    : ", sys.prefix)
    print("[环境自检] sys.base_prefix: ", sys.base_prefix)
    # 检查 _ctypes
    try:
        import _ctypes  # noqa: F401
        print("+ _ctypes 模块可导入")
        ctypes_file = getattr(_ctypes, '__file__', None)
        if ctypes_file:
            print(f"  _ctypes 路径: {ctypes_file}")
    except Exception as e:
        print(f"- 警告：无法导入 _ctypes ({e})，可能导致最终 exe 启动失败。")
    # 检查 libffi (仅在 Windows 下意义较大)
    if sys.platform.startswith('win'):
        dll_dir = Path(sys.base_prefix) / 'DLLs'
        candidates = ['libffi-8.dll','libffi-7.dll','libffi.dll','ffi.dll']
        found = False
        for name in candidates:
            if (dll_dir / name).exists():
                print(f"+ 检测到 libffi 相关: {(dll_dir / name)}")
                found = True
                break
        if not found:
            print("- 未找到 libffi DLL，若执行期出现 _ctypes 加载失败，可手动把对应 DLL 加入 spec binaries")
    # 给出系统 Python vs conda 提示
    if 'conda' in sys.executable.lower() or 'envs' in sys.executable.lower():
        print("[提示] 当前使用的是 Conda/虚拟环境，若目标是在普通 Windows 上运行，建议改用系统安装的 Python 重打包。")
    print("[环境自检] 完成\n")

def run_command(cmd, description):
    """运行命令并显示结果 (宽容解码)"""
    print(f"\n正在{description}...")
    try:
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out_b, err_b = proc.communicate()
        rc = proc.returncode
        def _decode(data: bytes) -> str:
            if data is None:
                return ''
            for enc in ('utf-8','gbk','cp936','latin-1'):
                try:
                    return data.decode(enc)
                except Exception:
                    continue
            return data.decode('utf-8','ignore')
        out = _decode(out_b)
        err = _decode(err_b)
        if rc == 0:
            print(f"+ {description}成功")
            if out.strip():
                print(out.strip()[:800])
            return True
        else:
            print(f"- {description}失败 (returncode={rc})")
            if err.strip():
                print(err.strip()[:800])
            else:
                print(out.strip()[:800])
            return False
    except Exception as e:
        print(f"- {description}异常: {e}")
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

    def _onerror(func, path, exc_info):
        # 尝试去掉只读属性再重试一次
        try:
            if not os.access(path, os.W_OK):
                os.chmod(path, stat.S_IWUSR)
        except Exception:
            pass
        try:
            func(path)
        except PermissionError:
            raise
        except Exception:
            pass

    def _robust_rmtree(p: Path):
        if not p.exists():
            return True
        # 若是 Windows 且目录下包含当前仍在运行的 exe，提示用户先关闭
        if sys.platform.startswith('win') and 'dist' in p.as_posix():
            exe = p / '流光下载器.exe'
            if exe.exists():
                try:
                    # 尝试独占打开
                    with open(exe, 'rb'):
                        pass
                except PermissionError:
                    print(f"- 检测到 {exe} 可能仍在运行或被占用，请先关闭该程序再重试 (或 任务管理器 结束进程)。")
                    return False
        for attempt in range(3):
            try:
                shutil.rmtree(p, onerror=_onerror)
                print(f"+ 已删除 {p}")
                return True
            except PermissionError as e:
                print(f"! 第 {attempt+1} 次删除 {p} 失败: {e}")
                # 等待杀毒/文件句柄释放
                time.sleep(0.8)
        # 仍失败：尝试重命名为 .stale 以便继续后续流程
        try:
            stale = p.with_name(p.name + f".stale_{int(time.time())}")
            os.rename(p, stale)
            print(f"! 无法直接删除 {p}，已重命名为 {stale}，可稍后手动删除。")
            return True
        except Exception as e:
            print(f"- 最终仍无法处理 {p}: {e}")
            return False

    all_ok = True
    for dir_name in dirs_to_clean:
        p = Path(dir_name)
        if p.exists():
            ok = _robust_rmtree(p)
            all_ok = all_ok and ok
    if not all_ok:
        print("[WARN] 部分旧目录未能完全删除，继续尝试打包 (如果打包失败请先手动清理后重试)。")

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
        # ---------------------------------------------------------
        # 资源完整性二次校验（某些环境下 PyInstaller datas 丢失兜底）
        # ---------------------------------------------------------
        dist_root = exe_path.parent
        required_dirs = [
            ('templates', 'templates'),
            ('static', 'static'),
            ('ffmpeg', 'ffmpeg'),
            ('aria2', 'aria2'),
        ]
        required_files = [
            ('yt-dlp.exe', 'yt-dlp.exe'),
        ]
        fixed_any = False
        for src, rel in required_dirs:
            target = dist_root / rel
            if not target.exists():
                if Path(src).exists():
                    try:
                        print(f"[资源校验] 缺失目录 {rel} -> 正在补拷贝...")
                        if target.parent.exists():
                            from shutil import copytree
                            copytree(src, target)
                            fixed_any = True
                        else:
                            print(f"[资源校验][WARN] 目标父目录不存在: {target.parent}")
                    except Exception as ce:
                        print(f"[资源校验][ERROR] 复制 {src} 失败: {ce}")
                else:
                    print(f"[资源校验][WARN] 源目录缺失: {src} (未补拷贝)")
        for src, rel in required_files:
            target = dist_root / rel
            if not target.exists():
                if Path(src).exists():
                    try:
                        print(f"[资源校验] 缺失文件 {rel} -> 正在补拷贝...")
                        from shutil import copy2
                        copy2(src, target)
                        fixed_any = True
                    except Exception as fe:
                        print(f"[资源校验][ERROR] 复制 {src} 失败: {fe}")
                else:
                    print(f"[资源校验][WARN] 源文件缺失: {src} (未补拷贝)")
        if fixed_any:
            # 再次确认关键模板文件存在
            probe_tpl = dist_root / 'templates' / 'index.html'
            print(f"[资源校验] templates/index.html 存在: {probe_tpl.exists()}")
        else:
            print("[资源校验] 所有声明资源在首次打包输出中已存在。")

        # ---------------------------------------------------------
        # libffi 兜底: _ctypes 早期加载需要找到 ffi / libffi-7.dll
        # 逻辑: 若 dist 根目录没有 *ffi*.dll，则从 sys.base_prefix/DLLs 复制
        # 并创建一个 ffi.dll 的别名 (Windows 某些调用路径直接寻找 ffi.dll)
        # ---------------------------------------------------------
        try:
            dll_dir = Path(sys.base_prefix) / 'DLLs'
            candidates_order = ['libffi-8.dll','libffi-7.dll','libffi.dll','ffi.dll']
            dist_has = any(list(dist_root.glob('*ffi*.dll')))
            if not dist_has:
                picked = None
                for name in candidates_order:
                    src = dll_dir / name
                    if src.exists():
                        picked = src
                        break
                if picked:
                    target_primary = dist_root / picked.name
                    shutil.copy2(picked, target_primary)
                    print(f"[libffi] 已复制 {picked.name} -> dist 根目录")
                    # 若没有 ffi.dll 且 picked 不是 ffi.dll，再复制一个别名
                    alias = dist_root / 'ffi.dll'
                    if not alias.exists():
                        try:
                            shutil.copy2(picked, alias)
                            print("[libffi] 已创建别名 ffi.dll")
                        except Exception as ce:
                            print(f"[libffi][WARN] 创建 ffi.dll 失败: {ce}")
                else:
                    print("[libffi][WARN] 未在当前 Python DLLs 目录找到任何 libffi*.dll")
            else:
                # 确保 ffi.dll 别名存在 (避免只存在 libffi-7.dll 的情况)
                alias = dist_root / 'ffi.dll'
                if not alias.exists():
                    # 找已有的 libffi* 复制一个
                    existing = list(dist_root.glob('libffi-*.dll')) + list(dist_root.glob('libffi.dll'))
                    if existing:
                        try:
                            shutil.copy2(existing[0], alias)
                            print("[libffi] 已补充别名 ffi.dll")
                        except Exception as ce:
                            print(f"[libffi][WARN] 补充别名失败: {ce}")
                print("[libffi] dist 根目录已存在 ffi 相关 DLL")
        except Exception as e:
            print(f"[libffi][ERROR] 处理 libffi 兜底时出错: {e}")

        # 写入构建元数据 (无 git 时容错)
        meta = {
            'build_time': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'python': sys.version.split()[0],
            'version': APP_VERSION
        }
        # 获取 git 提交哈希
        try:
            proc = subprocess.run('git rev-parse --short HEAD', shell=True, capture_output=True)
            if proc.returncode == 0:
                meta['commit'] = proc.stdout.decode('utf-8','ignore').strip()
        except Exception:
            pass
        try:
            with open('dist/流光下载器/build_meta.json','w',encoding='utf-8') as mf:
                import json as _json
                _json.dump(meta, mf, ensure_ascii=False, indent=2)
            print(f"+ 已写入 build_meta.json: {meta}")
        except Exception as me:
            print(f"- 写入 build_meta.json 失败: {me}")
        return True
    else:
        print("- 打包失败：找不到输出文件")
        return False

def main():
    """主函数"""
    print("=" * 50)
    print(f"流光下载器打包工具 (版本 {APP_VERSION})")
    print("=" * 50)
    
    # 环境自检 (优先)
    environment_self_check()

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
    if getattr(sys.stdout, 'encoding', None) != 'utf-8':
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
            except Exception:
                pass
    if getattr(sys.stderr, 'encoding', None) != 'utf-8':
        if hasattr(sys.stderr, 'reconfigure'):
            try:
                sys.stderr.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
            except Exception:
                pass
    sys.exit(main())