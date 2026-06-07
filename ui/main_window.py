# -*- coding: utf-8 -*-
"""
SJCode 视频内容处理工作台 - 主窗口

功能：
  - Excel 任务上传和管理
  - B站视频下载
  - 视频列表展示和 ASR 队列管理
  - 视频转 Markdown（ASR + LLM）
  - 商机提炼总结
  - 多页面导航布局
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QCheckBox,
    QFileDialog, QMessageBox, QGroupBox, QHeaderView, QAbstractItemView,
    QStatusBar, QListWidget, QStackedWidget, QComboBox, QProgressBar,
    QLineEdit
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import (
    OUTPUT_DIR, VIDEO, TASKS, HISTORY,
    DOCS, SUMMARY, ASR_CACHE
)


# ===================== 配置路径 =====================

BASE_DIR = Path(__file__).resolve().parent.parent
HISTORY_FILE = HISTORY / "keywords_history.json"


# ===================== 关键词历史管理 =====================

class KeywordHistory:
    """关键词历史记录管理"""

    def __init__(self, history_file: Path):
        self.history_file = history_file
        self.keywords: dict[str, dict] = {}
        self._load()

    def _load(self):
        """加载历史记录"""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.keywords = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.keywords = {}

    def _save(self):
        """保存历史记录"""
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.keywords, f, ensure_ascii=False, indent=2)

    def add(self, keyword: str):
        """添加关键词"""
        today = datetime.now().strftime("%Y-%m-%d")
        if keyword in self.keywords:
            self.keywords[keyword]["count"] += 1
            self.keywords[keyword]["date"] = today
            self.keywords[keyword]["status"] = "completed"
        else:
            self.keywords[keyword] = {
                "date": today,
                "count": 1,
                "status": "completed"
            }
        self._save()

    def is_processed(self, keyword: str) -> bool:
        """检查关键词是否已处理过"""
        return keyword in self.keywords

    def get_all(self) -> dict[str, dict]:
        """获取所有历史记录"""
        return self.keywords


# ===================== 下载线程 =====================

class DownloadWorker(QThread):
    """视频下载工作线程"""
    progress = Signal(str)
    finished = Signal(bool, str)
    video_added = Signal(dict)
    progress_value = Signal(int, int)  # current, total

    def __init__(self, tasks: list[dict], parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self._running = True

    def run(self):
        print(f"[DEBUG DownloadWorker] 线程启动，共 {len(self.tasks)} 个任务")
        try:
            for i, task in enumerate(self.tasks):
                if not self._running:
                    print("[DEBUG DownloadWorker] 任务被停止")
                    break

                keyword = task["keyword"]
                order = task.get("order", "totalrank")
                limit = task.get("limit", 5)
                
                print(f"[DEBUG DownloadWorker] 开始任务 [{i+1}/{len(self.tasks)}]: keyword={keyword}, order={order}, limit={limit}")

                self.progress.emit(f"[{i+1}/{len(self.tasks)}] 开始下载: {keyword}")
                self.progress_value.emit(i + 1, len(self.tasks))

                print(f"[DEBUG DownloadWorker] 导入 download_keyword_videos...")
                from core.bilibili_search_download_v2_ui import download_keyword_videos
                print(f"[DEBUG DownloadWorker] 调用 download_keyword_videos...")
                
                videos = download_keyword_videos(
                    keyword, order=order, limit=limit,
                    progress_callback=lambda msg: self.progress.emit(f"  {msg}")
                )
                
                print(f"[DEBUG DownloadWorker] 下载完成，找到 {len(videos)} 个视频")

                for video in videos:
                    self.video_added.emit(video)

                self.progress.emit(f"  完成: {keyword} ({len(videos)} 个视频)")

            print("[DEBUG DownloadWorker] 所有任务完成")
            self.finished.emit(True, "所有任务已完成")

        except Exception as e:
            print(f"[DEBUG DownloadWorker] 异常: {str(e)}")
            import traceback
            traceback.print_exc()
            self.finished.emit(False, f"下载失败: {str(e)}")

    def stop(self):
        self._running = False


# ===================== ASR 处理线程 =====================

class ASRWorker(QThread):
    """ASR 处理线程"""
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self.video_path = video_path

    def run(self):
        try:
            self.progress.emit(f"正在处理: {Path(self.video_path).name}")
            result = subprocess.run(
                [sys.executable, "-m", "parser.main", self.video_path],
                capture_output=True, text=True,
                encoding='utf-8', errors='ignore',
                cwd=str(BASE_DIR),
                timeout=600
            )
            if result.returncode == 0:
                self.finished.emit(True, "ASR 处理完成")
            else:
                self.finished.emit(False, f"处理失败: {result.stderr[:100]}")
        except Exception as e:
            self.finished.emit(False, f"错误: {str(e)}")


# ===================== 提炼总结线程 =====================

class SummaryWorker(QThread):
    """提炼总结线程"""
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, input_file: str, parent=None):
        super().__init__(parent)
        self.input_file = input_file

    def run(self):
        try:
            self.progress.emit(f"正在提炼: {Path(self.input_file).name}")
            from parser.summary import summarize_file
            result = summarize_file(self.input_file)
            self.finished.emit(True, f"提炼完成: {result}")
        except Exception as e:
            self.finished.emit(False, f"错误: {str(e)}")


# ===================== 主窗口 =====================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.keyword_history = KeywordHistory(HISTORY_FILE)
        self.download_worker: Optional[DownloadWorker] = None
        self.asr_worker: Optional[ASRWorker] = None
        self.summary_worker: Optional[SummaryWorker] = None

        self.current_tasks: list[dict] = []
        self.preview_data: list[dict] = []
        self.video_list: list[dict] = []
        self.asr_queue: list[dict] = []

        self.channel_options = ["B站", "抖音", "YouTube"]

        self.setWindowTitle("SJCode 视频内容处理工作台")
        self.setMinimumSize(1300, 900)

        self.setup_ui()
        self.apply_styles()
        self.refresh_all_tables()

        self.statusBar().showMessage("就绪 | 流程: 配置任务 → 抓取视频 → ASR转文字 → AI提炼总结")

    def setup_ui(self):
        """初始化 UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧导航菜单
        self.sidebar = QListWidget()
        self.sidebar.setMaximumWidth(180)
        self.sidebar.setMinimumWidth(150)
        for item in ["📋 任务配置", "🎬 视频库", "📝 转文字任务", "✨ 提炼总结"]:
            self.sidebar.addItem(item)
        self.sidebar.currentRowChanged.connect(self.switch_page)
        main_layout.addWidget(self.sidebar)

        # 右侧堆叠区域
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget, 1)

        # 创建各页面
        self.page_task_config = self.create_task_config_page()
        self.page_video_library = self.create_video_library_page()
        self.page_transcribe = self.create_transcribe_page()
        self.page_summary = self.create_summary_page()

        self.stacked_widget.addWidget(self.page_task_config)
        self.stacked_widget.addWidget(self.page_video_library)
        self.stacked_widget.addWidget(self.page_transcribe)
        self.stacked_widget.addWidget(self.page_summary)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def apply_styles(self):
        """应用样式表"""
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f7fa; }
            QGroupBox { font-weight: bold; border: 1px solid #d0d7de; border-radius: 6px; margin-top: 10px; padding-top: 10px; background-color: white; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px 0 5px; color: #24292f; }
            QPushButton { background-color: #2c974b; color: white; border: none; border-radius: 6px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #2c6e3f; }
            QPushButton:pressed { background-color: #1b4d2a; }
            QPushButton#secondaryBtn { background-color: #6c757d; }
            QPushButton#secondaryBtn:hover { background-color: #5a6268; }
            QPushButton#dangerBtn { background-color: #d73a49; }
            QPushButton#dangerBtn:hover { background-color: #b31d28; }
            QPushButton:disabled { background-color: #cccccc; color: #888888; }
            QTableWidget { border: 1px solid #e1e4e8; border-radius: 4px; alternate-background-color: #f8f9fa; gridline-color: #e1e4e8; }
            QHeaderView::section { background-color: #f6f8fa; padding: 4px; border: none; border-right: 1px solid #e1e4e8; border-bottom: 1px solid #e1e4e8; font-weight: bold; }
            QComboBox, QLineEdit { padding: 4px; border: 1px solid #d0d7de; border-radius: 4px; }
            QListWidget { background-color: white; border: none; border-right: 1px solid #e1e4e8; outline: none; }
            QListWidget::item { padding: 12px 8px; border-bottom: 1px solid #e1e4e8; }
            QListWidget::item:selected { background-color: #e2e6ea; color: #24292f; }
            QListWidget::item:hover { background-color: #f0f2f4; }
            QProgressBar { border: 1px solid #d0d7de; border-radius: 4px; text-align: center; }
            QProgressBar::chunk { background-color: #2c974b; border-radius: 3px; }
            QLabel { color: #24292f; }
        """)

    def switch_page(self, index):
        """切换页面"""
        self.stacked_widget.setCurrentIndex(index)

    # ==================== 页面1: 任务配置 ====================

    def create_task_config_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        # 上传区域
        upload_group = QGroupBox("📂 上传Excel文件 (列：检索关键词, 排序, TOP-N)")
        upload_layout = QHBoxLayout(upload_group)
        self.upload_btn = QPushButton("选择文件")
        self.upload_btn.clicked.connect(self.upload_excel)
        self.file_label = QLabel("未选择文件")
        upload_layout.addWidget(self.upload_btn)
        upload_layout.addWidget(self.file_label)
        upload_layout.addStretch()
        layout.addWidget(upload_group)

        # 预览表格
        preview_group = QGroupBox("📄 Excel数据预览 (勾选行，选择渠道后加入任务)")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(5)
        self.preview_table.setHorizontalHeaderLabels(["选择", "检索关键词", "排序", "TOP-N", "渠道"])
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        preview_layout.addWidget(self.preview_table)

        btn_layout = QHBoxLayout()
        self.add_selected_btn = QPushButton("✅ 将选中行加入待执行任务")
        self.add_selected_btn.clicked.connect(self.add_selected_to_tasks)
        self.add_all_btn = QPushButton("📌 全部加入待执行任务")
        self.add_all_btn.clicked.connect(self.add_all_to_tasks)
        btn_layout.addWidget(self.add_selected_btn)
        btn_layout.addWidget(self.add_all_btn)
        btn_layout.addStretch()
        preview_layout.addLayout(btn_layout)
        layout.addWidget(preview_group)

        # 待执行任务表格
        task_group = QGroupBox("⏳ 待执行任务列表")
        task_layout = QVBoxLayout(task_group)
        self.task_table = QTableWidget()
        self.task_table.setColumnCount(6)
        self.task_table.setHorizontalHeaderLabels(["关键词", "排序方式", "数量", "渠道", "状态", "操作"])
        self.task_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.task_table.setAlternatingRowColors(True)
        task_layout.addWidget(self.task_table)

        action_layout = QHBoxLayout()
        self.clear_pending_btn = QPushButton("🗑️ 清空未执行任务")
        self.clear_pending_btn.setObjectName("dangerBtn")
        self.clear_pending_btn.clicked.connect(self.clear_pending_tasks)
        self.start_crawl_btn = QPushButton("🚀 开启抓取视频任务")
        self.start_crawl_btn.clicked.connect(self.start_crawling)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(20)
        action_layout.addWidget(self.clear_pending_btn)
        action_layout.addWidget(self.progress_bar)
        action_layout.addStretch()
        action_layout.addWidget(self.start_crawl_btn)
        task_layout.addLayout(action_layout)
        layout.addWidget(task_group)

        return page

    # ==================== 页面2: 视频库 ====================

    def create_video_library_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        video_group = QGroupBox("🎬 历史下载视频库")
        video_layout = QVBoxLayout(video_group)
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(9)
        self.history_table.setHorizontalHeaderLabels(
            ["选择", "视频名称", "关键词", "大小(MB)", "时长", "收藏数", "播放量", "状态", "操作"]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        video_layout.addWidget(self.history_table)

        btn_layout = QHBoxLayout()
        self.refresh_videos_btn = QPushButton("🔄 刷新列表")
        self.refresh_videos_btn.setObjectName("secondaryBtn")
        self.refresh_videos_btn.clicked.connect(self.refresh_videos)
        self.add_to_asr_btn = QPushButton("🎤 将选中视频加入转文字任务(ASR)")
        self.add_to_asr_btn.clicked.connect(self.add_selected_videos_to_asr)
        btn_layout.addWidget(self.refresh_videos_btn)
        btn_layout.addWidget(self.add_to_asr_btn)
        btn_layout.addStretch()
        video_layout.addLayout(btn_layout)
        layout.addWidget(video_group)
        return page

    # ==================== 页面3: 转文字任务 ====================

    def create_transcribe_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        asr_group = QGroupBox("🎙️ 视频转文字任务列表 (ASR队列)")
        asr_layout = QVBoxLayout(asr_group)
        self.asr_table = QTableWidget()
        self.asr_table.setColumnCount(4)
        self.asr_table.setHorizontalHeaderLabels(["视频名称", "关键词", "状态", "操作"])
        self.asr_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.asr_table.setAlternatingRowColors(True)
        asr_layout.addWidget(self.asr_table)
        self.start_transcribe_btn = QPushButton("🔄 开启视频转文章任务")
        self.start_transcribe_btn.clicked.connect(self.start_transcription)
        asr_layout.addWidget(self.start_transcribe_btn)
        layout.addWidget(asr_group)

        trans_group = QGroupBox("📄 已生成的转文字文件列表")
        trans_layout = QVBoxLayout(trans_group)
        self.transcription_table = QTableWidget()
        self.transcription_table.setColumnCount(4)
        self.transcription_table.setHorizontalHeaderLabels(["文件名", "来源视频", "创建时间", "操作"])
        self.transcription_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        trans_layout.addWidget(self.transcription_table)
        self.refresh_trans_btn = QPushButton("🔄 刷新文件列表")
        self.refresh_trans_btn.setObjectName("secondaryBtn")
        self.refresh_trans_btn.clicked.connect(self.refresh_transcription_files)
        trans_layout.addWidget(self.refresh_trans_btn)
        layout.addWidget(trans_group)
        return page

    # ==================== 页面4: 提炼总结 ====================

    def create_summary_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        summary_group = QGroupBox("✨ AI提炼总结文件列表")
        summary_layout = QVBoxLayout(summary_group)
        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(4)
        self.summary_table.setHorizontalHeaderLabels(["总结文件名", "源文件", "创建时间", "操作"])
        self.summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.summary_table.setAlternatingRowColors(True)
        summary_layout.addWidget(self.summary_table)
        btn_layout = QHBoxLayout()
        self.generate_summary_btn = QPushButton("🧠 开启提炼总结 (基于转文字文件)")
        self.generate_summary_btn.clicked.connect(self.generate_summary_from_trans)
        self.refresh_summary_btn = QPushButton("🔄 刷新文件列表")
        self.refresh_summary_btn.setObjectName("secondaryBtn")
        self.refresh_summary_btn.clicked.connect(self.refresh_summary_files)
        btn_layout.addWidget(self.generate_summary_btn)
        btn_layout.addWidget(self.refresh_summary_btn)
        btn_layout.addStretch()
        summary_layout.addLayout(btn_layout)
        layout.addWidget(summary_group)
        return page

    # ==================== 功能方法 ====================

    def refresh_all_tables(self):
        """刷新所有表格"""
        self.refresh_task_table()
        self.refresh_videos()
        self.refresh_asr_table()
        self.refresh_transcription_files()
        self.refresh_summary_files()

    # --- Excel 处理 ---

    def upload_excel(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择Excel文件", "", "Excel Files (*.xlsx *.xls)"
        )
        if file_path:
            self.file_label.setText(file_path)
            self.load_excel_preview(file_path)

    def load_excel_preview(self, file_path):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path)
            sheet = wb.active
            rows = list(sheet.iter_rows(values_only=True))
            if len(rows) < 2:
                QMessageBox.warning(self, "警告", "Excel至少需要标题行和数据行")
                return

            headers = rows[0]
            col_indices = {}
            for i, h in enumerate(headers):
                if h and str(h) in ["检索关键词", "排序", "TOP-N"]:
                    col_indices[str(h)] = i

            # 兼容：如果列名不一致，默认按顺序取前三列
            if len(col_indices) < 3:
                QMessageBox.information(self, "提示", "将按顺序读取前三列：关键词、排序、数量")
                col_indices = {"检索关键词": 0, "排序": 1, "TOP-N": 2}

            self.preview_data = []
            for row in rows[1:]:
                if len(row) > max(col_indices.values()):
                    keyword = row[col_indices["检索关键词"]]
                    sort_type = row[col_indices["排序"]] if col_indices.get("排序", 1) < len(row) else ""
                    topn = row[col_indices["TOP-N"]] if col_indices.get("TOP-N", 2) < len(row) else 5
                    if keyword:
                        self.preview_data.append({
                            "keyword": str(keyword),
                            "sort": str(sort_type) if sort_type else "totalrank",
                            "count": str(topn) if topn else "5"
                        })

            self.preview_table.setRowCount(len(self.preview_data))
            for idx, data in enumerate(self.preview_data):
                chk = QCheckBox()
                self.preview_table.setCellWidget(idx, 0, chk)
                self.preview_table.setItem(idx, 1, QTableWidgetItem(data["keyword"]))
                self.preview_table.setItem(idx, 2, QTableWidgetItem(data["sort"]))
                self.preview_table.setItem(idx, 3, QTableWidgetItem(data["count"]))
                channel_combo = QComboBox()
                channel_combo.addItems(self.channel_options)
                channel_combo.setCurrentText("B站")
                self.preview_table.setCellWidget(idx, 4, channel_combo)

            self.status_bar.showMessage(f"已加载 {len(self.preview_data)} 行数据，请勾选并选择渠道后加入任务")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"读取Excel失败: {str(e)}")

    def add_selected_to_tasks(self):
        selected_rows = []
        for row in range(self.preview_table.rowCount()):
            chk_widget = self.preview_table.cellWidget(row, 0)
            if chk_widget and chk_widget.isChecked():
                selected_rows.append(row)

        if not selected_rows:
            QMessageBox.information(self, "提示", "请先在预览表格中勾选要加入的任务")
            return

        added = 0
        for row in selected_rows:
            keyword = self.preview_table.item(row, 1).text()
            sort_type = self.preview_table.item(row, 2).text()
            count_str = self.preview_table.item(row, 3).text()
            channel_combo = self.preview_table.cellWidget(row, 4)
            channel = channel_combo.currentText()
            self._add_task(keyword, sort_type, count_str, channel)
            added += 1

        self.status_bar.showMessage(f"添加了 {added} 个任务")
        self.refresh_task_table()

    def add_all_to_tasks(self):
        self.preview_table.selectAll()
        for row in range(self.preview_table.rowCount()):
            chk_widget = self.preview_table.cellWidget(row, 0)
            if chk_widget:
                chk_widget.setChecked(True)
        self.add_selected_to_tasks()

    def _add_task(self, keyword: str, sort_type: str, count_str: str, channel: str):
        """添加任务"""
        # 检查是否重复
        for task in self.current_tasks:
            if task["keyword"] == keyword and task.get("status") != "completed":
                return

        try:
            count = int(count_str) if count_str else 5
        except ValueError:
            count = 5

        self.current_tasks.append({
            "keyword": keyword,
            "order": sort_type or "totalrank",
            "limit": count,
            "channel": channel,
            "status": "pending"
        })

    def refresh_task_table(self):
        """刷新任务表格"""
        self.task_table.setRowCount(0)
        for task in self.current_tasks:
            row = self.task_table.rowCount()
            self.task_table.insertRow(row)

            self.task_table.setItem(row, 0, QTableWidgetItem(task["keyword"]))
            self.task_table.setItem(row, 1, QTableWidgetItem(task.get("order", "totalrank")))
            self.task_table.setItem(row, 2, QTableWidgetItem(str(task.get("limit", 5))))
            self.task_table.setItem(row, 3, QTableWidgetItem(task.get("channel", "B站")))
            self.task_table.setItem(row, 4, QTableWidgetItem(task.get("status", "pending")))

            # 删除按钮
            del_btn = QPushButton("删除")
            del_btn.setObjectName("dangerBtn")
            del_btn.clicked.connect(lambda _, r=row: self.delete_task(r))
            self.task_table.setCellWidget(row, 5, del_btn)

    def delete_task(self, row: int):
        """删除任务"""
        if 0 <= row < len(self.current_tasks):
            self.current_tasks.pop(row)
            self.refresh_task_table()

    def clear_pending_tasks(self):
        """清空未执行任务"""
        self.current_tasks = [t for t in self.current_tasks if t.get("status") == "completed"]
        self.refresh_task_table()
        self.status_bar.showMessage("已清空未执行任务")

    def start_crawling(self):
        """开始下载任务"""
        print("[DEBUG] start_crawling() 被调用")
        
        if not self.current_tasks:
            print("[DEBUG] 没有任务 - self.current_tasks 为空")
            QMessageBox.warning(self, "提示", "没有待执行的任务")
            return

        # 只下载未完成的任务
        pending_tasks = [t for t in self.current_tasks if t.get("status") != "completed"]
        print(f"[DEBUG] 待执行任务数量: {len(pending_tasks)}")
        
        if not pending_tasks:
            QMessageBox.warning(self, "提示", "所有任务已完成")
            return

        self.start_crawl_btn.setEnabled(False)
        self.progress_bar.setMaximum(len(pending_tasks))
        self.progress_bar.setValue(0)
        
        print(f"[DEBUG] 开始创建 DownloadWorker，任务: {pending_tasks}")

        self.download_worker = DownloadWorker(pending_tasks)
        self.download_worker.progress.connect(self.on_download_progress)
        self.download_worker.progress_value.connect(self.on_download_progress_value)
        self.download_worker.finished.connect(self.on_download_finished)
        self.download_worker.video_added.connect(self.on_video_added)
        self.download_worker.start()
        
        print("[DEBUG] DownloadWorker 已启动")

        self.status_bar.showMessage("下载中...")

    def on_download_progress(self, message: str):
        self.status_bar.showMessage(message)

    def on_download_progress_value(self, current: int, total: int):
        self.progress_bar.setValue(current)

    def on_download_finished(self, success: bool, message: str):
        self.start_crawl_btn.setEnabled(True)
        for task in self.current_tasks:
            if task.get("status") != "completed":
                task["status"] = "completed"
                self.keyword_history.add(task["keyword"])
        self.refresh_task_table()
        self.refresh_videos()
        self.status_bar.showMessage(message)
        QMessageBox.information(self, "完成", message)

    def on_video_added(self, video: dict):
        self.video_list.append(video)

    # --- 视频库 ---

    def refresh_videos(self):
        """刷新视频列表"""
        self.video_list = []
        if VIDEO.exists():
            for keyword_dir in VIDEO.iterdir():
                if not keyword_dir.is_dir():
                    continue
                for video_file in keyword_dir.glob("*.mp4"):
                    size_mb = video_file.stat().st_size / (1024 * 1024)
                    self.video_list.append({
                        "path": str(video_file),
                        "name": video_file.stem,
                        "keyword": keyword_dir.name,
                        "size": size_mb,
                        "duration": "N/A",
                        "favorite": "N/A",
                        "play": "N/A",
                        "status": "已下载"
                    })

        self.history_table.setRowCount(0)
        for video in self.video_list:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)

            chk = QCheckBox()
            self.history_table.setCellWidget(row, 0, chk)
            self.history_table.setItem(row, 1, QTableWidgetItem(video["name"]))
            self.history_table.setItem(row, 2, QTableWidgetItem(video["keyword"]))
            self.history_table.setItem(row, 3, QTableWidgetItem(f"{video['size']:.1f}"))
            self.history_table.setItem(row, 4, QTableWidgetItem(video["duration"]))
            self.history_table.setItem(row, 5, QTableWidgetItem(str(video.get("favorite", "N/A"))))
            self.history_table.setItem(row, 6, QTableWidgetItem(str(video.get("play", "N/A"))))
            self.history_table.setItem(row, 7, QTableWidgetItem(video["status"]))

    def add_selected_videos_to_asr(self):
        """将选中视频加入 ASR 队列"""
        selected = []
        for row in range(self.history_table.rowCount()):
            chk_widget = self.history_table.cellWidget(row, 0)
            if chk_widget and chk_widget.isChecked():
                video = self.video_list[row]
                if video not in self.asr_queue:
                    self.asr_queue.append(video)
                selected.append(video["name"])

        if selected:
            self.refresh_asr_table()
            QMessageBox.information(self, "提示", f"已添加 {len(selected)} 个视频到 ASR 队列")
        else:
            QMessageBox.warning(self, "提示", "请先选择要处理的视频")

    # --- ASR 转文字 ---

    def refresh_asr_table(self):
        """刷新 ASR 表格"""
        self.asr_table.setRowCount(0)
        for video in self.asr_queue:
            row = self.asr_table.rowCount()
            self.asr_table.insertRow(row)
            self.asr_table.setItem(row, 0, QTableWidgetItem(video["name"]))
            self.asr_table.setItem(row, 1, QTableWidgetItem(video["keyword"]))
            self.asr_table.setItem(row, 2, QTableWidgetItem("待处理"))

            del_btn = QPushButton("移除")
            del_btn.setObjectName("dangerBtn")
            del_btn.clicked.connect(lambda _, r=row: self.remove_from_asr(r))
            self.asr_table.setCellWidget(row, 3, del_btn)

    def remove_from_asr(self, row: int):
        if 0 <= row < len(self.asr_queue):
            self.asr_queue.pop(row)
            self.refresh_asr_table()

    def start_transcription(self):
        """开始 ASR 转文字"""
        if not self.asr_queue:
            QMessageBox.warning(self, "提示", "ASR 队列为空")
            return

        self.start_transcribe_btn.setEnabled(False)
        self.status_bar.showMessage("正在处理 ASR...")

        video = self.asr_queue[0]
        self.asr_worker = ASRWorker(video["path"])
        self.asr_worker.progress.connect(self.status_bar.showMessage)
        self.asr_worker.finished.connect(self.on_asr_finished)
        self.asr_worker.start()

    def on_asr_finished(self, success: bool, message: str):
        self.start_transcribe_btn.setEnabled(True)
        if success:
            self.asr_queue.pop(0)
            self.refresh_asr_table()
            self.refresh_transcription_files()
        self.status_bar.showMessage(message)
        QMessageBox.information(self, "结果", message)

    def refresh_transcription_files(self):
        """刷新转文字文件列表"""
        files = []
        if DOCS.exists():
            for f in DOCS.glob("*.md"):
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "time": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                })

        self.transcription_table.setRowCount(0)
        for f in files:
            row = self.transcription_table.rowCount()
            self.transcription_table.insertRow(row)
            self.transcription_table.setItem(row, 0, QTableWidgetItem(f["name"]))
            self.transcription_table.setItem(row, 1, QTableWidgetItem(f["name"].replace(".md", "")))
            self.transcription_table.setItem(row, 2, QTableWidgetItem(f["time"]))

            to_summary_btn = QPushButton("→ 提炼")
            to_summary_btn.clicked.connect(lambda _, p=f["path"]: self.add_to_summary_queue(p))
            self.transcription_table.setCellWidget(row, 3, to_summary_btn)

    # --- 提炼总结 ---

    def generate_summary_from_trans(self):
        """从转文字文件生成总结"""
        # 获取选中的文件
        selected_files = []
        for row in range(self.transcription_table.rowCount()):
            item = self.transcription_table.item(row, 0)
            if item:
                file_path = DOCS / item.text()
                if file_path.exists():
                    selected_files.append(str(file_path))

        if not selected_files:
            QMessageBox.warning(self, "提示", "没有可提炼的文件")
            return

        self.generate_summary_btn.setEnabled(False)
        self.status_bar.showMessage("正在提炼总结...")

        # 逐个处理
        self._process_summary_batch(selected_files, 0)

    def _process_summary_batch(self, files: list, index: int):
        """批量处理总结"""
        if index >= len(files):
            self.generate_summary_btn.setEnabled(True)
            self.refresh_summary_files()
            self.status_bar.showMessage("提炼完成")
            QMessageBox.information(self, "完成", f"已处理 {len(files)} 个文件")
            return

        file_path = files[index]
        self.status_bar.showMessage(f"正在提炼 ({index+1}/{len(files)}): {Path(file_path).name}")

        self.summary_worker = SummaryWorker(file_path)
        self.summary_worker.progress.connect(self.status_bar.showMessage)
        self.summary_worker.finished.connect(
            lambda success, msg: self._process_summary_batch(files, index + 1)
        )
        self.summary_worker.start()

    def add_to_summary_queue(self, file_path: str):
        """添加文件到总结队列并处理"""
        self.status_bar.showMessage(f"正在提炼: {Path(file_path).name}")
        self.summary_worker = SummaryWorker(file_path)
        self.summary_worker.finished.connect(
            lambda success, msg: (self.refresh_summary_files(), self.status_bar.showMessage(msg))
        )
        self.summary_worker.start()

    def refresh_summary_files(self):
        """刷新总结文件列表"""
        files = []
        if SUMMARY.exists():
            for f in SUMMARY.glob("*.md"):
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "time": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                })

        self.summary_table.setRowCount(0)
        for f in files:
            row = self.summary_table.rowCount()
            self.summary_table.insertRow(row)
            self.summary_table.setItem(row, 0, QTableWidgetItem(f["name"]))
            self.summary_table.setItem(row, 1, QTableWidgetItem(f["name"]))
            self.summary_table.setItem(row, 2, QTableWidgetItem(f["time"]))
            self.summary_table.setItem(row, 3, QTableWidgetItem("✅ 完成"))

    # ==================== 关闭事件 ====================

    def closeEvent(self, event):
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.stop()
            self.download_worker.wait()
        if self.asr_worker and self.asr_worker.isRunning():
            self.asr_worker.terminate()
        if self.summary_worker and self.summary_worker.isRunning():
            self.summary_worker.terminate()
        event.accept()


# ===================== 入口 =====================

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
