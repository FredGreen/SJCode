#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SJCode V2 - 桌面端精简版入口
功能：视频下载 + 视频转文本
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from v2.ui.main_window import MainWindow
from PySide6.QtWidgets import QApplication


def main():
    """主入口"""
    app = QApplication(sys.argv)
    app.setApplicationName("SJCode V2")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
