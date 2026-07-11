#!/usr/bin/env python3
"""
SJCode V1 - 完整版入口
功能：B站视频下载、ASR转文字、LLM处理、UI界面
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v1.ui.main_window import MainWindow
from PySide6.QtWidgets import QApplication


def main():
    """主入口"""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
