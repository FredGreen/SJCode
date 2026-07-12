# SJCode V2 打包说明

## 环境准备

### 1. 安装依赖

```powershell
# 安装打包工具
pip install pyinstaller

# 安装运行依赖
pip install PySide6 openpyxl requests yt-dlp openai-whisper
```

### 2. 验证安装

```powershell
python -c "import PyInstaller; print(PyInstaller.__version__)"
python -c "import PySide6; print('PySide6 OK')"
```

## 打包步骤

### 方法一：使用打包脚本（推荐）

```powershell
cd SJCode
python build_v2.py
```

打包完成后，exe 文件在 `dist/SJCode_V2.exe`

### 方法二：手动打包

```powershell
cd SJCode

pyinstaller ^
    --name="SJCode_V2" ^
    --windowed ^
    --onefile ^
    --clean ^
    --noconfirm ^
    --collect-all PySide6 ^
    --collect-all yt_dlp ^
    --hidden-import=PySide6 ^
    --hidden-import=openpyxl ^
    --hidden-import=requests ^
    --hidden-import=yt_dlp ^
    --hidden-import=whisper ^
    --hidden-import=v2 ^
    --hidden-import=v2.core ^
    --hidden-import=v2.core.downloader ^
    --hidden-import=v2.core.parser ^
    --hidden-import=v2.ui ^
    --hidden-import=v2.ui.main_window ^
    --hidden-import=shared ^
    --hidden-import=shared.utils ^
    --add-data "config;config" ^
    v2/main.py
```

## 打包参数说明

| 参数 | 说明 |
|------|------|
| `--name` | 输出的 exe 文件名 |
| `--windowed` | 不显示控制台窗口 |
| `--onefile` | 打包成单个 exe 文件 |
| `--clean` | 清理临时文件 |
| `--collect-all` | 收集模块的所有文件 |
| `--hidden-import` | 手动添加隐藏导入 |
| `--add-data` | 添加数据文件（Windows 用 `;` 分隔） |

## 常见问题

### 1. 打包后运行闪退

打开控制台查看错误：
```powershell
# 双击 exe 看错误，或右键选择"在终端中打开"
dist/SJCode_V2.exe
```

### 2. 缺少模块错误

在打包命令中添加：
```
--hidden-import=模块名
```

### 3. 文件体积太大

- 正常体积：200-500 MB（包含 PySide6 和 Whisper）
- 可以使用 `--exclude-module` 排除不需要的模块

### 4. 找不到 config/cookies.txt

确保打包时添加了 config 目录：
```
--add-data "config;config"
```

## 分发

打包完成后，将 `dist/SJCode_V2.exe` 发给用户即可。

用户无需安装 Python，直接运行 exe 即可使用。

## 注意事项

1. **首次运行较慢**：单文件模式需要解压到临时目录，首次启动可能需要 10-30 秒
2. **杀毒软件误报**：PyInstaller 打包的 exe 可能被杀毒软件误报，需要添加信任
3. **Whisper 模型**：首次使用时会自动下载 Whisper 模型（约 1.4GB）
4. **Cookies**：用户需要自己上传 B站 cookies 才能下载视频
