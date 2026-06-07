# -*- coding: utf-8 -*-
"""
SJCode 桌面应用 - 主窗口

功能：
  - Excel 任务上传和管理
  - B站视频下载
  - 视频列表展示和 ASR 队列管理
  - 任务进度跟踪
  - 关键词历史记录
"""

import os
import sys
import json
import openpyxl
from pathlib import Path
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QCheckBox,
    QProgressBar, QFileDialog, QMessageBox, QGroupBox, QScrollArea,
    QStatusBar, QListWidget, QListWidgetItem, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer
from PySide6.QtGui import QColor, QFont

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import OUTPUT_DIR


# ===================== 配置路径 =====================

BASE_DIR = Path(__file__).resolve().parent.parent
TASKS_DIR = BASE_DIR / "output" / "tasks"
HISTORY_FILE = BASE_DIR / "output" / "history" / "keywords_history.json"
VIDEOS_DIR = BASE_DIR / "output" / "video"


# ===================== 关键词历史管理 =====================

class KeywordHistory:
    """关键词历史记录管理"""

    def __init__(self, history_file: Path):
        self.history_file = history_file
        self.keywords: dict[str, dict] = {}  # keyword -> {date, count, status}
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
    progress = Signal(str)  # 发送进度信息
    finished = Signal(bool, str)  # 完成信号
    video_added = Signal(dict)  # 新视频添加信号

    def __init__(self, tasks: list[dict], parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self._running = True

    def run(self):
        """执行下载任务"""
        try:
            for i, task in enumerate(self.tasks):
                if not self._running:
                    break

                keyword = task["keyword"]
                order = task.get("order", "totalrank")
                limit = task.get("limit", 5)

                self.progress.emit(f"[{i+1}/{len(self.tasks)}] 开始下载: {keyword}")

                # 导入并执行下载（复用现有代码）
                from core.bilibili_search_download_v2_ui import download_keyword_videos
                videos = download_keyword_videos(
                    keyword, order=order, limit=limit,
                    progress_callback=lambda msg: self.progress.emit(f"  {msg}")
                )

                for video in videos:
                    self.video_added.emit(video)

                self.progress.emit(f"  完成: {keyword} ({len(videos)} 个视频)")

            self.finished.emit(True, "所有任务已完成")

        except Exception as e:
            self.finished.emit(False, f"下载失败: {str(e)}")

    def stop(self):
        """停止下载"""
        self._running = False


# ===================== 主窗口 =====================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.keyword_history = KeywordHistory(HISTORY_FILE)
        self.download_worker: Optional[DownloadWorker] = None
        self.current_tasks: list[dict] = []
        self.video_list: list[dict] = []  # 当前视频列表
        self.asr_queue: list[dict] = []   # ASR 待处理队列

        self._init_ui()
        self._load_video_history()

    def _init_ui(self):
        """初始化 UI"""
        self.setWindowTitle("SJCode - 视频内容处理工具")
        self.setGeometry(100, 100, 1200, 800)

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)

        # 1. 任务上传区域
        task_group = self._create_task_group()
        main_layout.addWidget(task_group)

        # 2. 下载控制区域
        download_group = self._create_download_group()
        main_layout.addWidget(download_group)

        # 3. 视频列表区域
        video_group = self._create_video_group()
        main_layout.addWidget(video_group)

        # 4. 进度区域
        progress_group = self._create_progress_group()
        main_layout.addWidget(progress_group)

        # 状态栏
        self.statusBar().showMessage("就绪")

    def _create_task_group(self) -> QGroupBox:
        """创建任务上传区域"""
        group = QGroupBox("任务管理")
        layout = QVBoxLayout()

        # 上传和预览布局
        btn_layout = QHBoxLayout()

        self.btn_upload = QPushButton("📁 上传 Excel 任务")
        self.btn_upload.clicked.connect(self._upload_excel)
        btn_layout.addWidget(self.btn_upload)

        self.btn_preview = QPushButton("🔍 预览任务列表")
        self.btn_preview.clicked.connect(self._preview_tasks)
        btn_layout.addWidget(self.btn_preview)

        self.btn_clear = QPushButton("🗑️ 清空任务")
        self.btn_clear.clicked.connect(self._clear_tasks)
        btn_layout.addWidget(self.btn_clear)

        layout.addLayout(btn_layout)

        # 任务列表显示
        self.task_table = QTableWidget()
        self.task_table.setColumnCount(4)
        self.task_table.setHorizontalHeaderLabels(["关键词", "排序方式", "数量", "状态"])
        self.task_table.setMaximumHeight(120)
        layout.addWidget(self.task_table)

        # 历史记录
        history_layout = QHBoxLayout()
        history_layout.addWidget(QLabel("已处理关键词:"))
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(60)
        self.history_list.addItems(list(self.keyword_history.get_all().keys()))
        history_layout.addWidget(self.history_list)
        layout.addLayout(history_layout)

        group.setLayout(layout)
        return group

    def _create_download_group(self) -> QGroupBox:
        """创建下载控制区域"""
        group = QGroupBox("视频下载")
        layout = QHBoxLayout()

        self.checkbox_bilibili = QCheckBox("B站下载")
        self.checkbox_bilibili.setChecked(True)
        layout.addWidget(self.checkbox_bilibili)

        self.btn_start_download = QPushButton("▶️ 开始下载")
        self.btn_start_download.clicked.connect(self._start_download)
        self.btn_start_download.setEnabled(False)
        layout.addWidget(self.btn_start_download)

        self.btn_stop_download = QPushButton("⏹️ 停止下载")
        self.btn_stop_download.clicked.connect(self._stop_download)
        self.btn_stop_download.setEnabled(False)
        layout.addWidget(self.btn_stop_download)

        layout.addStretch()

        self.download_status = QLabel("等待上传任务...")
        layout.addWidget(self.download_status)

        group.setLayout(layout)
        return group

    def _create_video_group(self) -> QGroupBox:
        """创建视频列表区域"""
        group = QGroupBox("已下载视频列表")
        layout = QVBoxLayout()

        # 视频列表
        self.video_table = QTableWidget()
        self.video_table.setColumnCount(7)
        self.video_table.setHorizontalHeaderLabels([
            "选择", "视频名称", "关键词", "时长", "大小", "收藏数", "状态"
        ])
        self.video_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.video_table)

        # 操作按钮
        btn_layout = QHBoxLayout()

        self.btn_refresh_videos = QPushButton("🔄 刷新列表")
        self.btn_refresh_videos.clicked.connect(self._refresh_videos)
        btn_layout.addWidget(self.btn_refresh_videos)

        self.btn_add_to_asr = QPushButton("📝 加入 ASR 队列")
        self.btn_add_to_asr.clicked.connect(self._add_to_asr_queue)
        btn_layout.addWidget(self.btn_add_to_asr)

        self.btn_start_asr = QPushButton("🎤 开始语音转文字")
        self.btn_start_asr.clicked.connect(self._start_asr)
        btn_layout.addWidget(self.btn_start_asr)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        # ASR 队列
        asr_layout = QHBoxLayout()
        asr_layout.addWidget(QLabel("ASR 队列:"))
        self.asr_queue_list = QListWidget()
        self.asr_queue_list.setMaximumHeight(50)
        asr_layout.addWidget(self.asr_queue_list)
        layout.addLayout(asr_layout)

        group.setLayout(layout)
        return group

    def _create_progress_group(self) -> QGroupBox:
        """创建进度显示区域"""
        group = QGroupBox("任务进度")
        layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(20)
        layout.addWidget(self.progress_bar)

        self.log_text = QLabel()
        self.log_text.setWordWrap(True)
        self.log_text.setStyleSheet("background-color: #f5f5f5; padding: 5px;")
        layout.addWidget(self.log_text)

        group.setLayout(layout)
        return group

    # ===================== 事件处理 =====================

    def _upload_excel(self):
        """上传 Excel 文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 Excel 文件", "",
            "Excel 文件 (*.xlsx *.xls);;所有文件 (*)"
        )

        if not file_path:
            return

        try:
            wb = openpyxl.load_workbook(file_path)
            ws = wb.active

            # 解析 Excel（跳过表头）
            tasks = []
            duplicates = []

            for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                if not row or not row[0]:
                    continue

                keyword = str(row[0]).strip()
                if not keyword:
                    continue

                order = str(row[1]) if len(row) > 1 and row[1] else "totalrank"
                limit = int(row[2]) if len(row) > 2 and row[2] else 5

                # 检查是否重复
                is_dup = self.keyword_history.is_processed(keyword)
                if is_dup:
                    duplicates.append(keyword)

                tasks.append({
                    "keyword": keyword,
                    "order": order,
                    "limit": limit,
                    "is_duplicate": is_dup
                })

            self.current_tasks = tasks
            self._display_tasks()

            # 保存到 output/tasks
            TASKS_DIR.mkdir(parents=True, exist_ok=True)
            original_name = Path(file_path).name
            dest_path = TASKS_DIR / original_name
            import shutil
            shutil.copy(file_path, dest_path)

            msg = f"已加载 {len(tasks)} 个任务"
            if duplicates:
                msg += f"\n⚠️ 警告: {len(duplicates)} 个关键词已处理过: {', '.join(duplicates)}"
                QMessageBox.warning(self, "重复关键词", msg)
            else:
                self.statusBar().showMessage(msg)

            self.btn_start_download.setEnabled(len(tasks) > 0)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"读取 Excel 失败:\n{str(e)}")

    def _display_tasks(self):
        """显示任务列表"""
        self.task_table.setRowCount(0)

        for task in self.current_tasks:
            row = self.task_table.rowCount()
            self.task_table.insertRow(row)

            # 关键词
            item_keyword = QTableWidgetItem(task["keyword"])
            if task.get("is_duplicate"):
                item_keyword.setBackground(QColor(255, 200, 200))  # 红色背景标记重复
            self.task_table.setItem(row, 0, item_keyword)

            # 排序方式
            order_map = {
                "totalrank": "综合排序",
                "click": "播放量",
                "pubdate": "最新发布",
                "dm": "弹幕数",
                "stow": "收藏数"
            }
            self.task_table.setItem(row, 1, QTableWidgetItem(order_map.get(task["order"], task["order"])))

            # 数量
            self.task_table.setItem(row, 2, QTableWidgetItem(str(task["limit"])))

            # 状态
            status = "⚠️ 已处理" if task.get("is_duplicate") else "⏳ 待处理"
            item_status = QTableWidgetItem(status)
            if task.get("is_duplicate"):
                item_status.setBackground(QColor(255, 200, 200))
            self.task_table.setItem(row, 3, item_status)

        # 调整列宽
        self.task_table.resizeColumnsToContents()

    def _preview_tasks(self):
        """预览任务（显示在表格中）"""
        if not self.current_tasks:
            QMessageBox.information(self, "提示", "请先上传 Excel 文件")
            return
        self._display_tasks()

    def _clear_tasks(self):
        """清空任务"""
        self.current_tasks = []
        self.task_table.setRowCount(0)
        self.btn_start_download.setEnabled(False)
        self.statusBar().showMessage("任务已清空")

    def _start_download(self):
        """开始下载"""
        if not self.checkbox_bilibili.isChecked():
            QMessageBox.warning(self, "提示", "请至少选择一个下载渠道")
            return

        if not self.current_tasks:
            QMessageBox.warning(self, "提示", "没有待处理的任务")
            return

        self.btn_start_download.setEnabled(False)
        self.btn_stop_download.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(self.current_tasks))

        # 过滤掉重复的关键词（仅下载未处理的）
        valid_tasks = [t for t in self.current_tasks if not t.get("is_duplicate")]
        if not valid_tasks:
            QMessageBox.warning(self, "提示", "所有关键词都已处理过，无法下载")
            self.btn_start_download.setEnabled(True)
            self.btn_stop_download.setEnabled(False)
            return

        # 启动下载线程
        self.download_worker = DownloadWorker(valid_tasks)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.video_added.connect(self._on_video_added)
        self.download_worker.start()

        self.statusBar().showMessage("下载中...")

    def _stop_download(self):
        """停止下载"""
        if self.download_worker:
            self.download_worker.stop()
            self.download_worker.wait()
            self.download_worker = None

        self.btn_start_download.setEnabled(True)
        self.btn_stop_download.setEnabled(False)
        self.statusBar().showMessage("下载已停止")

    def _on_download_progress(self, message: str):
        """下载进度更新"""
        self.log_text.setText(message)

    def _on_download_finished(self, success: bool, message: str):
        """下载完成"""
        self.btn_start_download.setEnabled(True)
        self.btn_stop_download.setEnabled(False)

        # 更新历史记录
        for task in self.current_tasks:
            if not task.get("is_duplicate"):
                self.keyword_history.add(task["keyword"])

        # 刷新历史列表
        self.history_list.clear()
        self.history_list.addItems(list(self.keyword_history.get_all().keys()))

        self._refresh_videos()
        self.statusBar().showMessage(message)
        QMessageBox.information(self, "完成", message)

    def _on_video_added(self, video: dict):
        """新视频添加"""
        self.video_list.append(video)
        self._display_videos()

    def _refresh_videos(self):
        """刷新视频列表"""
        self.video_list = self._scan_video_directory()
        self._display_videos()

    def _scan_video_directory(self) -> list[dict]:
        """扫描视频目录"""
        videos = []

        if not VIDEOS_DIR.exists():
            return videos

        for keyword_dir in VIDEOS_DIR.iterdir():
            if not keyword_dir.is_dir():
                continue

            for video_file in keyword_dir.glob("*.mp4"):
                videos.append({
                    "path": str(video_file),
                    "name": video_file.stem,
                    "keyword": keyword_dir.name,
                    "duration": "N/A",
                    "size": video_file.stat().st_size / (1024 * 1024),  # MB
                    "favorite": "N/A",
                    "selected": False
                })

        return videos

    def _display_videos(self):
        """显示视频列表"""
        self.video_table.setRowCount(0)

        for video in self.video_list:
            row = self.video_table.rowCount()
            self.video_table.insertRow(row)

            # 选择框
            checkbox = QCheckBox()
            checkbox.setChecked(video.get("selected", False))
            checkbox.stateChanged.connect(
                lambda state, v=video: v.update({"selected": state == Qt.CheckState.Checked})
            )
            self.video_table.setCellWidget(row, 0, checkbox)

            # 其他信息
            self.video_table.setItem(row, 1, QTableWidgetItem(video["name"]))
            self.video_table.setItem(row, 2, QTableWidgetItem(video["keyword"]))
            self.video_table.setItem(row, 3, QTableWidgetItem(str(video["duration"])))
            self.video_table.setItem(row, 4, QTableWidgetItem(f"{video['size']:.1f} MB"))
            self.video_table.setItem(row, 5, QTableWidgetItem(str(video["favorite"])))
            self.video_table.setItem(row, 6, QTableWidgetItem("✅ 已下载"))

        # 调整列宽
        self.video_table.resizeColumnsToContents()

    def _add_to_asr_queue(self):
        """添加到 ASR 队列"""
        selected = [v for v in self.video_list if v.get("selected")]

        if not selected:
            QMessageBox.warning(self, "提示", "请先选择要转换的视频")
            return

        for video in selected:
            if video not in self.asr_queue:
                self.asr_queue.append(video)
                self.asr_queue_list.addItem(video["name"])

        self.statusBar().showMessage(f"已添加 {len(selected)} 个视频到 ASR 队列")

    def _start_asr(self):
        """开始 ASR 处理"""
        if not self.asr_queue:
            QMessageBox.warning(self, "提示", "ASR 队列为空")
            return

        self.statusBar().showMessage("正在处理 ASR...")
        self.log_text.setText("开始语音转文字处理...")

        # 在主线程执行（避免复杂的多线程同步）
        try:
            from parser.main import main as asr_main

            for video in self.asr_queue[:]:  # 使用切片避免修改迭代中的列表
                self.log_text.setText(f"处理: {video['name']}")
                QApplication.processEvents()  # 保持 UI 响应

                try:
                    # 调用现有的 ASR 处理
                    # 注意：这会阻塞，需要较长时间
                    import subprocess
                    result = subprocess.run(
                        [sys.executable, "-m", "parser.main", video["path"]],
                        capture_output=True, text=True, cwd=str(BASE_DIR)
                    )

                    if result.returncode == 0:
                        self.asr_queue.remove(video)
                        self.asr_queue_list.takeItem(self.asr_queue_list.row(
                            self.asr_queue_list.findItems(video["name"], Qt.MatchExactly)[0]
                        ))
                        self.log_text.setText(f"✅ 完成: {video['name']}")
                    else:
                        self.log_text.setText(f"❌ 失败: {video['name']}")

                except Exception as e:
                    self.log_text.setText(f"❌ 错误: {str(e)}")

            self.statusBar().showMessage("ASR 处理完成")
            QMessageBox.information(self, "完成", "所有视频已处理完成")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"ASR 处理失败:\n{str(e)}")

    def _load_video_history(self):
        """加载视频历史"""
        self._refresh_videos()

    def closeEvent(self, event):
        """关闭事件"""
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.stop()
            self.download_worker.wait()
        event.accept()


# ===================== 入口 =====================

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
