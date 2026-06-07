## 项目概述
SJCode 是一个视频内容处理与商机检索工具集，包含视频转 Markdown、商机搜索、B站视频下载和桌面 UI 功能。

## 技术栈
- Python 3.10+
- PySide6（桌面 UI）
- 阿里云百炼 ASR（paraformer-v2）
- LLM 文本处理（清洗、结构化）
- AnySearch API（商机检索）
- yt-dlp（视频下载）
- PyInstaller（打包）
- requests、openpyxl

## 目录结构
```
SJCode/
├── bin/                    # 外部工具（ffmpeg 等）
│   └── ffmpeg.exe          # 视频处理工具
├── config/                 # 配置模块
│   ├── settings.py        # 路径和输出配置
│   └── cookies.txt        # B站 cookies（需用户配置）
├── core/                   # 核心功能
│   ├── anysearch/         # 商机检索模块
│   ├── bilibili_search_download-v2.py   # B站下载（命令行版）
│   └── bilibili_search_download_v2_ui.py # B站下载（UI集成版）
├── parser/                 # 视频转 Markdown
│   ├── asr_client.py       # 阿里云 ASR 语音识别
│   ├── llm_processor.py    # LLM 清洗和结构化
│   ├── md_generator.py     # Markdown 生成
│   ├── summary.py          # 商机提炼总结
│   └── main.py             # 主入口
├── ui/                     # 桌面 UI（PySide6）
│   ├── __init__.py
│   └── main_window.py      # 主窗口
├── docs/                   # 文档
│   └── PYINSTALLER_GUIDE.md # PyInstaller 打包指南
├── output/                 # 输出目录
│   ├── docs/               # Parser 生成的 Markdown 文档
│   ├── asr_cache/          # ASR 缓存
│   ├── video/              # 下载的视频
│   ├── tasks/              # 上传的 Excel 任务
│   ├── summary/            # 商机提炼总结
│   └── history/            # 关键词历史记录
├── .coze                   # 项目配置
├── requirements_ui.txt     # UI 依赖
├── SJCode.spec             # PyInstaller 配置
└── AGENTS.md               # 本文件
```

## 关键入口 / 核心模块

### 1. 桌面 UI（主要入口）
```bash
# 安装 UI 依赖
pip install -r requirements_ui.txt

# 运行桌面应用
python -m ui.main_window
# 或
python ui/main_window.py
```

### 2. 视频转 Markdown（命令行）
```bash
python -m parser.main <视频文件> [--source 来源] [--author 作者] [--date 日期]
```

### 3. B站视频下载（命令行）
```bash
# 单关键词
python -m core.bilibili_search_download_v2 "Python教程"

# Excel 批量模式
python -m core.bilibili_search_download_v2 --excel tasks.xlsx
```

### 4. 商机检索
```bash
python -m core.anysearch.search
```

### 5. 商机提炼总结
```bash
# 单文件处理
python -m parser.summary <Markdown文件>

# 批量处理目录
python -m parser.summary <目录> --pattern "*.md"

# 指定输出目录
python -m parser.summary <文件> -o output/summary
```
输出目录：`output/summary/`

## UI 功能说明

### 主要功能
1. **Excel 任务上传**：上传包含关键词的 Excel 文件，支持预览
2. **B站视频下载**：下载指定关键词的视频
3. **视频列表管理**：显示已下载视频，支持勾选加入 ASR 队列
4. **语音转文字**：将选中视频转换为 Markdown
5. **关键词历史**：记录已处理的关键词，避免重复处理
6. **任务进度**：实时显示下载和处理进度

### Excel 模板格式
参考 `output/tasks/商机检索-关键词.xlsx`：

| 关键词 | 排序方式 | 数量 |
|--------|----------|------|
| Python教程 | totalrank | 5 |
| AI入门 | pubdate | 3 |

排序方式可选值：
- `totalrank`：综合排序
- `click`：播放量
- `pubdate`：最新发布
- `dm`：弹幕数
- `stow`：收藏数

## 打包为 EXE

详见 `docs/PYINSTALLER_GUIDE.md`

### 快速打包
```bash
# 安装依赖
pip install pyinstaller PySide6 openpyxl

# 执行打包
pyinstaller SJCode.spec
```

### 输出位置
```
dist/SJCode/
├── SJCode.exe       # 主程序
├── config/          # 需用户配置 cookies.txt
└── bin/             # ffmpeg 等工具
```

## ffmpeg 管理方案

采用 `bin/` 目录管理 ffmpeg：
- 优势：版本统一、随项目分发、避免系统依赖
- 劣势：略微增加项目体积

下载 ffmpeg：
1. 访问 https://ffmpeg.org/download.html
2. 下载 Windows 版本
3. 解压到 `bin/` 目录

## 用户偏好与长期约束
- 使用 PySide6 开发桌面 UI
- 复用现有核心模块（下载、ASR）
- 统一输出到 `output/` 目录
- API 密钥硬编码在代码中（需注意安全）
- PyInstaller 打包，支持一键生成 EXE

## 常见问题和预防
1. **B站下载需要 cookies**：配置 `config/cookies.txt`
2. **ASR 需要阿里云 access_key**：配置 `parser/config.py`
3. **LLM 调用需要配置**：配置 `parser/config.py`
4. **ffmpeg 缺失**：放入 `bin/` 目录或安装到系统 PATH
5. **中文路径问题**：避免在项目路径中使用中文

## 版本信息
- 项目版本：参考 core/bilibili_search_download-v2.py
- UI 版本：1.0.0
