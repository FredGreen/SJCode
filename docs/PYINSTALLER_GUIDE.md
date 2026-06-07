# PyCharm 打包 SJCode 为 EXE 指南

本文档详细说明如何在 PyCharm 中将 SJCode 桌面应用打包为独立的 Windows 可执行文件（.exe）。

## 环境要求

- Windows 10/11 操作系统
- Python 3.10+ （建议使用与开发环境相同的版本）
- PyCharm 2023+ （Community 或 Professional 均可）

## 第一步：安装打包依赖

在 PyCharm 的 Terminal 中安装 PyInstaller：

```bash
pip install pyinstaller
```

或使用 requirements 文件：

```bash
pip install -r requirements_ui.txt
pip install pyinstaller
```

## 第二步：完整依赖列表

确保以下依赖已安装：

```bash
# UI 相关
pip install PySide6 openpyxl

# 视频下载相关
pip install requests yt-dlp

# ASR/LLM 相关（如果需要语音转文字功能）
pip install dashscope

# 打包工具
pip install pyinstaller
```

## 第三步：准备资源文件

### 1. 下载 ffmpeg

推荐使用 `bin/` 目录管理 ffmpeg，与项目一起打包：

1. 访问 https://ffmpeg.org/download.html
2. 下载 Windows 版本（推荐 `ffmpeg-release-essentials.zip`）
3. 解压到项目根目录的 `bin/` 文件夹下：

```
SJCode/
├── bin/
│   └── ffmpeg.exe          ← 从 ffmpeg/bin/ 复制
├── config/
├── core/
├── parser/
├── ui/
└── ...
```

### 2. 配置文件

确保以下文件存在：

```
config/
├── settings.py
└── cookies.txt
```

> **注意**: `cookies.txt` 是 B站下载必需的登录凭证，从浏览器插件导出。

## 第四步：PyCharm 打包步骤

### 方法一：使用 PyCharm 界面

1. **打开项目**：在 PyCharm 中打开 SJCode 项目

2. **安装 PyInstaller 插件**（可选）：
   - File → Settings → Plugins
   - 搜索 "PyInstaller"
   - 安装后重启 PyCharm

3. **运行打包**：
   - 右键点击 `ui/main_window.py`
   - 选择 "Show in" → "Explorer"
   - 在文件管理器中打开目录
   - 按住 Shift + 右键 → "在此处打开 PowerShell"

4. **执行打包命令**：

```powershell
# 进入项目目录
cd D:\path\to\SJCode

# 执行打包（无控制台窗口）
pyinstaller --name SJCode `
           --windowed `
           --onedir `
           --add-data "config;config" `
           --add-data "bin;bin" `
           --add-data "parser;parser" `
           --hidden-import PySide6 `
           --hidden-import PySide6.QtCore `
           --hidden-import PySide6.QtGui `
           --hidden-import PySide6.QtWidgets `
           --hidden-import openpyxl `
           --hidden-import requests `
           --hidden-import yt_dlp `
           ui/main_window.py
```

### 方法二：使用 .spec 文件（推荐）

1. 项目中已包含 `SJCode.spec` 文件

2. 修改 .spec 文件中的路径为绝对路径

3. 在 Terminal 中执行：

```bash
pyinstaller SJCode.spec
```

## 第五步：验证打包结果

打包完成后，在 `dist/SJCode/` 目录下会生成：

```
dist/
└── SJCode/
    ├── SJCode.exe              ← 主程序
    ├── config/                 ← 配置文件目录
    ├── bin/                    ← ffmpeg 等工具
    ├── parser/                 ← 解析器模块
    ├── PySide6/                ← Qt 库
    └── ...（其他依赖）
```

### 测试运行

1. 双击 `SJCode.exe` 运行
2. 检查是否正常显示界面
3. 测试上传 Excel、下载视频等功能

## 常见问题解决

### 1. 打包后运行时缺少 DLL

**错误**: `RuntimeError: Unable to import ...`

**解决**: 添加更多 hidden-import：

```bash
pyinstaller --hidden-import=shiboken6 ...
```

### 2. ffmpeg 找不到

**解决**: 确保 `bin/ffmpeg.exe` 存在，或将 ffmpeg 添加到系统 PATH

### 3. PySide6 样式问题

**解决**: 打包时添加 Qt 插件目录：

```bash
--additional-hooks-dir "C:\path\to\PySide6\bindings"
```

### 4. 中文路径/文件名乱码

**解决**: 在代码开头添加：

```python
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
```

### 5. 打包体积过大

**解决**: 使用虚拟环境隔离依赖，仅打包必要的包：

```bash
# 创建虚拟环境
python -m venv venv打包
.\venv打包\Scripts\activate
pip install PySide6 openpyxl requests yt-dlp pyinstaller
```

## 高级配置

### 添加应用图标

1. 准备 256x256 像素的 ICO 文件（如 `icon.ico`）
2. 修改打包命令：

```bash
pyinstaller --icon=icon.ico ...
```

### 单文件打包

如果希望生成单个 EXE 文件（体积更大但更方便分发）：

```bash
pyinstaller --name SJCode --windowed --onefile --add-data "config;config" --add-data "bin;bin" ui/main_window.py
```

### 清理构建缓存

```bash
pyinstaller --clean
del /s /q __pycache__
del /s /q *.pyc
```

## 自动化脚本

在项目中创建 `build.bat`：

```batch
@echo off
echo Building SJCode...

:: 清理旧构建
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build

:: 执行打包
pyinstaller SJCode.spec

echo Build complete!
pause
```

双击运行即可自动打包。

## 分发说明

打包完成后，可以将整个 `dist/SJCode/` 文件夹分发给用户：

```
分发给用户的文件/
├── SJCode.exe          ← 主程序
├── config/             ← 用户需要配置 cookies.txt
├── bin/                ← ffmpeg 等工具
└── ...
```

**用户需要**：
1. 将 `cookies.txt` 放入 `config/` 目录
2. 双击 `SJCode.exe` 即可运行

## 技术支持

如遇到打包问题，请检查：
1. Python 版本是否一致
2. 所有依赖是否正确安装
3. 路径是否正确（中文路径可能出现兼容性问题）
4. 系统是否安装了必要的 Visual C++ 运行库
