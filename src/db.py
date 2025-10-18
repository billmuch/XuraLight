import sqlite3
import os
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_PATH = "xura.db"

def get_db_connection():
    """建立并返回数据库连接"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # 使查询结果可以通过列名访问
    return conn

def init_db():
    """初始化数据库，创建所需的表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 创建源表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        crawler_command TEXT,
        actived BOOLEAN DEFAULT 1,
        media_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 创建reports表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER,
        report_file TEXT,
        audio_report_file TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (source_id) REFERENCES sources (id)
    )
    ''')
    
    # 创建文章表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE,
        title TEXT,
        source INTEGER,  -- 关联到sources表的id
        abstract_file TEXT,
        publish_timestamp INTEGER,
        audio_file TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 添加默认的0号源网站：Hacker News
    cursor.execute('''
    INSERT OR IGNORE INTO sources (id, name, crawler_command, actived, media_path)
    VALUES (0, 'Hacker News', 'python src/crawler_hackernews.py', 1, './media/hacker_news.jpg')
    ''')
    
    # 添加量子位源（默认禁用）
    cursor.execute('''
    INSERT OR IGNORE INTO sources (name, crawler_command, actived, media_path)
    VALUES ('量子位', 'python src/crawler_qbitai.py', 0, './media/liangziwei.png')
    ''')
    
    conn.commit()
    conn.close()

# ===================== 源表操作 =====================

def add_source(name: str, crawler_command: str, actived: bool = True, media_path: str = None) -> int:
    """添加新的源"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO sources (name, crawler_command, actived, media_path) VALUES (?, ?, ?, ?)",
            (name, crawler_command, actived, media_path)
        )
        source_id = cursor.lastrowid
        conn.commit()
        return source_id
    except sqlite3.IntegrityError:
        # 如果名称已存在，则返回-1
        return -1
    finally:
        conn.close()

def get_source(source_id: int) -> Optional[Dict]:
    """根据ID获取源信息"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sources WHERE id = ?", (source_id,))
    source = cursor.fetchone()
    conn.close()
    
    if source:
        return dict(source)
    return None

def get_source_by_name(name: str) -> Optional[Dict]:
    """根据名称获取源信息"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sources WHERE name = ?", (name,))
    source = cursor.fetchone()
    conn.close()
    
    if source:
        return dict(source)
    return None

def get_all_sources(only_actived: bool = False) -> List[Dict]:
    """获取所有源"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if only_actived:
        cursor.execute("SELECT * FROM sources WHERE actived = 1")
    else:
        cursor.execute("SELECT * FROM sources")
        
    sources = cursor.fetchall()
    conn.close()
    
    return [dict(source) for source in sources]

def update_source(source_id: int, name: str = None, crawler_command: str = None, actived: bool = None, media_path: str = None) -> bool:
    """更新源信息"""
    if not any([name, crawler_command, actived is not None, media_path is not None]):
        return False
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    update_fields = []
    params = []
    
    if name is not None:
        update_fields.append("name = ?")
        params.append(name)
    if crawler_command is not None:
        update_fields.append("crawler_command = ?")
        params.append(crawler_command)
    if actived is not None:
        update_fields.append("actived = ?")
        params.append(actived)
    if media_path is not None:
        update_fields.append("media_path = ?")
        params.append(media_path)
    
    params.append(source_id)
    
    try:
        cursor.execute(
            f"UPDATE sources SET {', '.join(update_fields)} WHERE id = ?",
            tuple(params)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def set_source_active(source_id: int, active: bool) -> bool:
    """设置源的激活状态"""
    return update_source(source_id, actived=active)

def get_active_sources() -> List[Dict]:
    """获取所有激活的源"""
    return get_all_sources(only_actived=True)

def delete_source(source_id: int) -> bool:
    """删除源"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success

def set_source_media(source_id: int, media_path: str) -> bool:
    """设置源的媒体文件路径"""
    return update_source(source_id, media_path=media_path)

# ===================== 文章表操作 =====================

def add_article(url: str, title: str, source_id: int, abstract_file: str = None,
                publish_timestamp: int = None, audio_file: str = None) -> int:
    """添加新文章"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if publish_timestamp is None:
        publish_timestamp = int(time.time())
    
    try:
        cursor.execute(
            """INSERT INTO articles 
               (url, title, source, abstract_file, publish_timestamp, audio_file) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (url, title, source_id, abstract_file, publish_timestamp, audio_file)
        )
        
        article_id = cursor.lastrowid
        conn.commit()
        return article_id
    except sqlite3.IntegrityError:
        # URL已存在
        return -1
    finally:
        conn.close()

def get_article(article_id: int) -> Optional[Dict]:
    """根据ID获取文章"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    article = cursor.fetchone()
    conn.close()
    
    if article:
        return dict(article)
    return None

def get_article_by_url(url: str) -> Optional[Dict]:
    """根据URL获取文章"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM articles WHERE url = ?", (url,))
    article = cursor.fetchone()
    conn.close()
    
    if article:
        return dict(article)
    return None

def get_articles_by_source(source_id: int, limit: int = 100, offset: int = 0) -> List[Dict]:
    """获取特定源的文章"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM articles WHERE source = ? ORDER BY publish_timestamp DESC LIMIT ? OFFSET ?",
        (source_id, limit, offset)
    )
    articles = cursor.fetchall()
    conn.close()
    
    return [dict(article) for article in articles]

def get_latest_articles(sources: List[int] = None, limit: int = 20) -> List[Dict]:
    """获取最新文章，可以指定源"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if sources and len(sources) > 0:
        placeholders = ','.join('?' for _ in sources)
        cursor.execute(
            f"SELECT * FROM articles WHERE source IN ({placeholders}) ORDER BY publish_timestamp DESC LIMIT ?",
            sources + [limit]
        )
    else:
        cursor.execute(
            "SELECT * FROM articles ORDER BY publish_timestamp DESC LIMIT ?",
            (limit,)
        )
    
    articles = cursor.fetchall()
    conn.close()
    
    return [dict(article) for article in articles]

def update_article(article_id: int, title: str = None, abstract_file: str = None,
                  audio_file: str = None) -> bool:
    """更新文章信息"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    update_fields = []
    params = []
    
    if title is not None:
        update_fields.append("title = ?")
        params.append(title)
    if abstract_file is not None:
        update_fields.append("abstract_file = ?")
        params.append(abstract_file)
    if audio_file is not None:
        update_fields.append("audio_file = ?")
        params.append(audio_file)
    
    if not update_fields:
        conn.close()
        return True  # 没有需要更新的字段，认为更新成功
    
    params.append(article_id)
    
    cursor.execute(
        f"UPDATE articles SET {', '.join(update_fields)} WHERE id = ?",
        tuple(params)
    )
    
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    return success

def delete_article(article_id: int) -> bool:
    """删除文章"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return success

# ===================== reports表操作 =====================

def add_report(source_id: int, report_file: str, audio_report_file: str = None) -> int:
    """添加新的报告记录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """INSERT INTO reports 
               (source_id, report_file, audio_report_file) 
               VALUES (?, ?, ?)""",
            (source_id, report_file, audio_report_file)
        )
        report_id = cursor.lastrowid
        conn.commit()
        return report_id
    except Exception as e:
        logger.error(f"添加报告记录失败: {e}")
        return -1
    finally:
        conn.close()

def get_source_reports(source_id: int) -> List[Dict]:
    """获取源的报告记录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """SELECT * FROM reports 
           WHERE source_id = ?
           ORDER BY created_at DESC""",
        (source_id,)
    )
    
    reports = cursor.fetchall()
    conn.close()
    
    return [dict(report) for report in reports]

def get_latest_report(source_id: int) -> Optional[Dict]:
    """获取源的最新报告"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        """SELECT * FROM reports 
           WHERE source_id = ?
           ORDER BY created_at DESC LIMIT 1""",
        (source_id,)
    )
    
    report = cursor.fetchone()
    conn.close()
    
    return dict(report) if report else None

def get_articles_by_source_and_timerange(source_id: int, start_timestamp: int, end_timestamp: int, limit: int = 100) -> List[Dict]:
    """
    获取指定源ID和时间范围内的所有文章
    
    Args:
        source_id: 源ID
        start_timestamp: 开始时间戳（UTC）
        end_timestamp: 结束时间戳（UTC）
        limit: 最大返回文章数量
        
    Returns:
        符合条件的文章列表
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """SELECT * FROM articles 
               WHERE source = ? 
               AND publish_timestamp >= ? 
               AND publish_timestamp < ? 
               ORDER BY publish_timestamp DESC 
               LIMIT ?""",
            (source_id, start_timestamp, end_timestamp, limit)
        )
        articles = cursor.fetchall()
        return [dict(article) for article in articles]
    except Exception as e:
        logger.error(f"查询时间范围内的文章失败: {e}")
        return []
    finally:
        conn.close()

# 初始化数据库
if __name__ == "__main__":
    init_db()
    print(f"数据库已初始化，路径：{os.path.abspath(DATABASE_PATH)}") 