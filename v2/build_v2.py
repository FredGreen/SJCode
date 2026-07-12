#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SJCode V2 打包脚本
使用 PyInstaller 打包成 exe
"""

import os
import sys
import subprocess
import shutil


def clean_build():
    """清理旧的构建文件"""
    dirs_to_remove = ['build', 'dist', '__pycache__']
    files_to_remove = ['SJCode_V2.spec']
    
    for d in dirs_to_remove:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"已删除: {d}")
    
    for f in files_to_remove:
        if os.path.exists(f):
            os.remove(f)
            print(f"已删除: {f}")


def check_dependencies():
    """检查必要的依赖"""
    try:
        import PyInstaller
        print(f"PyInstaller 版本: {PyInstaller.__version__}")
    except ImportError:
        print("错误: 未安装 PyInstaller")
        print("请运行: pip install pyinstaller")
        sys.exit(1)
    
    try:
        import PySide6
        print(f"PySide6 已安装")
    except ImportError:
        print("错误: 未安装 PySide6")
        print("请运行: pip install PySide6")
        sys.exit(1)


def build_exe():
    """构建 exe"""
    # v2 目录
    v2_dir = os.path.dirname(os.path.abspath(__file__))
    # 项目根目录
    root_dir = os.path.dirname(v2_dir)
    os.chdir(root_dir)
    
    # 入口文件
    entry_point = "v2/main.py"
    
    # 应用名称
    app_name = "SJCode_V2"
    
    # 图标文件（如果有的话）
    icon_file = "v2/ui/icon.ico"
    icon_option = f"--icon={icon_file}" if os.path.exists(icon_file) else ""
    
    # 数据文件
    # 格式: (源路径, 目标路径)
    data_files = []
    
    # 添加 config 目录（如果存在）
    if os.path.exists("config"):
        data_files.append(("config", "config"))
    
    # 添加 v2/config 目录（如果存在）
    if os.path.exists("v2/config"):
        data_files.append(("v2/config", "v2/config"))
    
    # 添加 whisper 资源文件
    try:
        import whisper
        whisper_path = os.path.dirname(whisper.__file__)
        assets_path = os.path.join(whisper_path, "assets")
        if os.path.exists(assets_path):
            data_files.append((assets_path, "whisper/assets"))
            print(f"✓ 添加 whisper 资源: {assets_path}")
    except Exception as e:
        print(f"⚠ 无法添加 whisper 资源: {e}")
    
    # 构建数据文件参数
    add_data = ""
    for src, dst in data_files:
        if os.path.exists(src):
            add_data += f' --add-data "{src}{os.pathsep}{dst}"'
    
    # 隐藏导入
    hidden_imports = [
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "openpyxl",
        "requests",
        "yt_dlp",
        "whisper",
        "v2",
        "v2.core",
        "v2.core.downloader",
        "v2.core.parser",
        "v2.ui",
        "v2.ui.main_window",
        "shared",
        "shared.utils",
    ]
    
    hidden_import_str = " ".join([f"--hidden-import={m}" for m in hidden_imports])
    
    # 排除的模块（减小体积）
    excludes = [
        "tkinter",
        "matplotlib",
        "numpy.distutils",
        "scipy",
        "pandas",
    ]
    exclude_str = " ".join([f"--exclude-module={m}" for m in excludes])
    
    # PyInstaller 命令（简化配置，避免兼容性问题）
    cmd = f'''pyinstaller
        --name="{app_name}"
        --windowed
        --onefile
        --clean
        --noconfirm
        {hidden_import_str}
        {exclude_str}
        {add_data}
        {icon_option}
        {entry_point}
    '''.replace('\n', ' ').replace('  ', ' ')
    
    print("=" * 60)
    print("开始打包 SJCode V2")
    print("=" * 60)
    print(f"入口文件: {entry_point}")
    print(f"输出名称: {app_name}")
    print(f"数据文件: {data_files}")
    print(f"命令: {cmd}")
    print("=" * 60)
    
    # 执行打包
    result = subprocess.run(cmd, shell=True)
    
    if result.returncode == 0:
        print("=" * 60)
        print("打包成功!")
        print(f"输出文件: dist/{app_name}.exe")
        print("=" * 60)
        
        # 显示文件大小
        exe_path = f"dist/{app_name}.exe"
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"文件大小: {size_mb:.2f} MB")
    else:
        print("=" * 60)
        print("打包失败!")
        print("=" * 60)
        sys.exit(1)


def main():
    """主函数"""
    print("SJCode V2 打包工具")
    print("=" * 60)
    
    # 清理旧文件
    print("\n[1/3] 清理旧构建文件...")
    clean_build()
    
    # 检查依赖
    print("\n[2/3] 检查依赖...")
    check_dependencies()
    
    # 构建
    print("\n[3/3] 开始构建...")
    build_exe()


if __name__ == "__main__":
    main()
