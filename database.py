# -*- coding: utf-8 -*-
"""
SQLite 数据库模块 - 记录任务执行过程中的重要数据
无需安装，直接使用 SQLite 文件数据库
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

# 数据库文件路径（放在项目根目录）
from config.settings import BASE_DIR

DB_PATH = BASE_DIR / "sjcode.db"


def get_db_path() -> Path:
    """获取数据库文件路径"""
    return DB_PATH


@contextmanager
def get_connection():
    """获取数据库连接的上下文管理器"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 支持按列名访问
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def init_database():
    """初始化数据库，创建所有表"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 任务表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                order_type TEXT DEFAULT 'totalrank',
                limit_count INTEGER DEFAULT 5,
                channel TEXT DEFAULT 'B站',
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                started_at TEXT,
                completed_at TEXT
            )
        """)

        # 视频表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                bvid TEXT,
                title TEXT NOT NULL,
                file_path TEXT,
                file_size REAL,
                duration TEXT,
                favorites INTEGER,
                likes INTEGER,
                plays INTEGER,
                keyword TEXT,
                status TEXT DEFAULT 'downloaded',
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)

        # 转文字表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transcriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER,
                video_path TEXT NOT NULL,
                output_path TEXT,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                started_at TEXT,
                completed_at TEXT,
                FOREIGN KEY (video_id) REFERENCES videos(id)
            )
        """)

        # 提炼总结表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transcription_id INTEGER,
                input_path TEXT NOT NULL,
                output_path TEXT,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                started_at TEXT,
                completed_at TEXT,
                FOREIGN KEY (transcription_id) REFERENCES transcriptions(id)
            )
        """)

        # 关键词历史表（用于去重提醒）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS keyword_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE NOT NULL,
                last_used_at TEXT DEFAULT (datetime('now', 'localtime')),
                total_runs INTEGER DEFAULT 1
            )
        """)

        print(f"[数据库] 初始化完成: {DB_PATH}")


# ==================== 任务操作 ====================

def add_task(keyword: str, order_type: str = 'totalrank',
             limit_count: int = 5, channel: str = 'B站') -> int:
    """添加新任务，返回任务ID"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tasks (keyword, order_type, limit_count, channel, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (keyword, order_type, limit_count, channel))
        return cursor.lastrowid


def get_pending_tasks() -> List[Dict]:
    """获取所有待执行任务"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, keyword, order_type, limit_count, channel, status, created_at
            FROM tasks WHERE status = 'pending'
            ORDER BY created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_all_tasks() -> List[Dict]:
    """获取所有任务"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, keyword, order_type, limit_count, channel, status,
                   created_at, started_at, completed_at
            FROM tasks ORDER BY created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def update_task_status(task_id: int, status: str):
    """更新任务状态"""
    with get_connection() as conn:
        cursor = conn.cursor()
        if status == 'running':
            cursor.execute("""
                UPDATE tasks SET status = ?, started_at = datetime('now', 'localtime')
                WHERE id = ?
            """, (status, task_id))
        elif status in ('completed', 'failed'):
            cursor.execute("""
                UPDATE tasks SET status = ?, completed_at = datetime('now', 'localtime')
                WHERE id = ?
            """, (status, task_id))
        else:
            cursor.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))


def clear_completed_tasks():
    """清空已完成的任务"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE status = 'completed'")


# ==================== 视频操作 ====================

def add_video(task_id: int, bvid: str, title: str, file_path: str,
              file_size: float, duration: str, favorites: int = 0,
              likes: int = 0, plays: int = 0, keyword: str = '') -> int:
    """添加视频记录"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO videos (task_id, bvid, title, file_path, file_size,
                              duration, favorites, likes, plays, keyword, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'downloaded')
        """, (task_id, bvid, title, file_path, file_size, duration,
              favorites, likes, plays, keyword))
        return cursor.lastrowid


def get_all_videos() -> List[Dict]:
    """获取所有视频"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, task_id, bvid, title, file_path, file_size, duration,
                   favorites, likes, plays, keyword, status, created_at
            FROM videos ORDER BY created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_video_by_id(video_id: int) -> Optional[Dict]:
    """根据ID获取视频"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_videos_by_task(task_id: int) -> List[Dict]:
    """获取指定任务下的视频"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos WHERE task_id = ?", (task_id,))
        return [dict(row) for row in cursor.fetchall()]


# ==================== 转文字操作 ====================

def add_transcription(video_id: int, video_path: str) -> int:
    """添加转文字任务"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transcriptions (video_id, video_path, status)
            VALUES (?, ?, 'pending')
        """, (video_id, video_path))
        return cursor.lastrowid


def add_transcription_direct(video_path: str) -> int:
    """直接添加转文字任务（不关联视频ID）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transcriptions (video_id, video_path, status)
            VALUES (NULL, ?, 'pending')
        """, (video_path,))
        return cursor.lastrowid


def get_pending_transcriptions() -> List[Dict]:
    """获取待处理的转文字任务"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, video_id, video_path, output_path, status, error_message,
                   created_at, started_at, completed_at
            FROM transcriptions WHERE status = 'pending'
            ORDER BY created_at ASC
        """)
        return [dict(row) for row in cursor.fetchall()]


def is_video_in_transcriptions(video_id: int) -> bool:
    """检查视频是否已在转文字队列中（避免重复添加）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM transcriptions WHERE video_id = ? LIMIT 1", (video_id,))
        return cursor.fetchone() is not None


def is_video_path_in_transcriptions(video_path: str) -> bool:
    """检查视频路径是否已在转文字队列中（用于无 video_id 的情况）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM transcriptions WHERE video_path = ? LIMIT 1", (video_path,))
        return cursor.fetchone() is not None


def get_all_transcriptions() -> List[Dict]:
    """获取所有转文字记录"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, video_id, video_path, output_path, status, error_message,
                   created_at, started_at, completed_at
            FROM transcriptions ORDER BY created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def update_transcription(transcription_id: int, status: str,
                         output_path: str = None, error_message: str = None):
    """更新转文字状态"""
    with get_connection() as conn:
        cursor = conn.cursor()
        if status == 'running':
            cursor.execute("""
                UPDATE transcriptions
                SET status = ?, started_at = datetime('now', 'localtime')
                WHERE id = ?
            """, (status, transcription_id))
        elif status in ('completed', 'failed'):
            if output_path:
                cursor.execute("""
                    UPDATE transcriptions
                    SET status = ?, output_path = ?,
                        completed_at = datetime('now', 'localtime')
                    WHERE id = ?
                """, (status, output_path, transcription_id))
            else:
                cursor.execute("""
                    UPDATE transcriptions
                    SET status = ?, error_message = ?,
                        completed_at = datetime('now', 'localtime')
                    WHERE id = ?
                """, (status, error_message, transcription_id))


# ==================== 提炼总结操作 ====================

def add_summary(transcription_id: int, input_path: str) -> int:
    """添加提炼总结任务"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO summaries (transcription_id, input_path, status)
            VALUES (?, ?, 'pending')
        """, (transcription_id, input_path))
        return cursor.lastrowid


def add_summary_direct(input_path: str) -> int:
    """直接添加提炼总结任务"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO summaries (transcription_id, input_path, status)
            VALUES (NULL, ?, 'pending')
        """, (input_path,))
        return cursor.lastrowid


def get_pending_summaries() -> List[Dict]:
    """获取待处理的提炼任务"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, transcription_id, input_path, output_path, status,
                   error_message, created_at, started_at, completed_at
            FROM summaries WHERE status = 'pending'
            ORDER BY created_at ASC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_all_summaries() -> List[Dict]:
    """获取所有提炼记录"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, transcription_id, input_path, output_path, status,
                   error_message, created_at, started_at, completed_at
            FROM summaries ORDER BY created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def update_summary(summary_id: int, status: str,
                    output_path: str = None, error_message: str = None):
    """更新提炼总结状态"""
    with get_connection() as conn:
        cursor = conn.cursor()
        if status == 'running':
            cursor.execute("""
                UPDATE summaries
                SET status = ?, started_at = datetime('now', 'localtime')
                WHERE id = ?
            """, (status, summary_id))
        elif status in ('completed', 'failed'):
            if output_path:
                cursor.execute("""
                    UPDATE summaries
                    SET status = ?, output_path = ?,
                        completed_at = datetime('now', 'localtime')
                    WHERE id = ?
                """, (status, output_path, summary_id))
            else:
                cursor.execute("""
                    UPDATE summaries
                    SET status = ?, error_message = ?,
                        completed_at = datetime('now', 'localtime')
                    WHERE id = ?
                """, (status, error_message, summary_id))


# ==================== 关键词历史操作 ====================

def check_keyword_exists(keyword: str) -> bool:
    """检查关键词是否已存在（用于重复提醒）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM keyword_history WHERE keyword = ?
        """, (keyword,))
        return cursor.fetchone() is not None


def clear_all_pending_tasks():
    """清空所有待执行任务"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE status = 'pending'")
        conn.commit()

# ==================== 数据管理 ====================

def clear_table(table_name: str) -> int:
    """清空指定表，返回删除的行数"""
    if table_name not in ['tasks', 'videos', 'transcriptions', 'summaries', 'keyword_history']:
        raise ValueError(f"无效的表名: {table_name}")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        cursor.execute(f"DELETE FROM {table_name}")
        conn.commit()
        return count


def clear_all_tables() -> dict:
    """清空所有表，返回每个表删除的行数"""
    tables = ['tasks', 'videos', 'transcriptions', 'summaries', 'keyword_history']
    result = {}
    for table in tables:
        try:
            result[table] = clear_table(table)
        except Exception as e:
            result[table] = f"错误: {e}"
    return result


def get_all_stats() -> dict:
    """获取所有表的统计数据"""
    tables = ['tasks', 'videos', 'transcriptions', 'summaries', 'keyword_history']
    result = {}
    for table in tables:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            result[table] = cursor.fetchone()[0]
    return result

def add_keyword_history(keyword: str):
    """添加或更新关键词历史"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO keyword_history (keyword, last_used_at, total_runs)
            VALUES (?, datetime('now', 'localtime'), 1)
            ON CONFLICT(keyword) DO UPDATE SET
                last_used_at = datetime('now', 'localtime'),
                total_runs = total_runs + 1
        """, (keyword,))


def get_keyword_history() -> List[Dict]:
    """获取关键词使用历史"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT keyword, last_used_at, total_runs
            FROM keyword_history ORDER BY last_used_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


# ==================== 统计操作 ====================

def get_statistics() -> Dict:
    """获取统计数据"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 任务统计
        cursor.execute("SELECT COUNT(*) as total FROM tasks")
        total_tasks = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as completed FROM tasks WHERE status = 'completed'")
        completed_tasks = cursor.fetchone()['completed']

        cursor.execute("SELECT COUNT(*) as pending FROM tasks WHERE status = 'pending'")
        pending_tasks = cursor.fetchone()['pending']

        # 视频统计
        cursor.execute("SELECT COUNT(*) as total FROM videos")
        total_videos = cursor.fetchone()['total']

        # 转文字统计
        cursor.execute("SELECT COUNT(*) as total FROM transcriptions")
        total_transcriptions = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as completed FROM transcriptions WHERE status = 'completed'")
        completed_transcriptions = cursor.fetchone()['completed']

        # 提炼总结统计
        cursor.execute("SELECT COUNT(*) as total FROM summaries")
        total_summaries = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as completed FROM summaries WHERE status = 'completed'")
        completed_summaries = cursor.fetchone()['completed']

        return {
            'tasks': {'total': total_tasks, 'completed': completed_tasks, 'pending': pending_tasks},
            'videos': {'total': total_videos},
            'transcriptions': {'total': total_transcriptions, 'completed': completed_transcriptions},
            'summaries': {'total': total_summaries, 'completed': completed_summaries}
        }


# ==================== 初始化 ====================

if __name__ == "__main__":
    # 初始化数据库
    init_database()
    print(f"数据库文件: {DB_PATH}")
