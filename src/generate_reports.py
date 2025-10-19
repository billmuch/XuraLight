#!/usr/bin/env python3

import os
import logging
import argparse
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Union
from pydub import AudioSegment
import json
import pytz
from pathlib import Path
import sys

from db import (
    get_all_sources,
    get_articles_by_source,
    get_articles_by_source_and_timerange,
    get_source,
    add_report,
    get_article_by_url
)

# 配置logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定义中国标准时区
CST = pytz.timezone('Asia/Shanghai')

def to_cst_time(dt):
    """将日期时间转换为中国标准时间（+8时区）"""
    if dt is None:
        return None
    
    # 如果时间没有时区信息，假定它是UTC时间
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    
    # 转换到中国标准时间
    return dt.astimezone(CST)

def get_current_cst_time():
    """获取当前的中国标准时间"""
    return datetime.now(CST)

def ensure_directories():
    """确保必要的目录存在"""
    # 创建基础目录
    base_dirs = ['reports', 'audio']
    for directory in base_dirs:
        dir_path = Path(directory)
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"创建目录: {directory}")
    
    # 确保reports目录有正确的权限
    reports_dir = Path('reports')
    if reports_dir.exists():
        try:
            # 设置目录权限为 755
            os.chmod(str(reports_dir), 0o755)
            logger.info(f"设置reports目录权限: 755")
        except Exception as e:
            logger.error(f"设置reports目录权限失败: {e}")

def generate_report(articles: List[Dict], source_id: Optional[int] = None) -> Dict[str, str]:
    """
    为指定的文章列表生成报告
    
    Args:
        articles: 文章列表，每个文章是一个字典
        source_id: 可选的源ID，如果提供则只为该源生成报告
    
    Returns:
        包含报告文件路径的字典，key为源名称，value为报告文件路径
    """
    # 确保目录存在
    ensure_directories()
    
    # 获取源
    if source_id is not None:
        source = get_source(source_id)
        if not source:
            logger.error(f"未找到源ID: {source_id}")
            return {}
        sources = [source]
    else:
        sources = get_all_sources(only_actived=True)
        if not sources:
            logger.error("没有找到任何激活的源")
            return {}
    
    report_files = {}  # 存储每个源对应的报告文件
    audio_files = {}   # 存储每个源对应的音频文件
    
    # 使用当前时间
    current_time = datetime.now()
    
    # 按源分组文章
    articles_by_source = {}
    for article in articles:
        # 处理不同格式的文章数据
        article_source_id = article.get('source_id')
        if article_source_id is None:
            # 如果文章数据中没有source_id，尝试从数据库获取
            if 'url' in article:
                db_article = get_article_by_url(article['url'])
                if db_article:
                    # 使用get方法安全地获取source_id
                    article_source_id = db_article.get('source_id')
                    if article_source_id is None:
                        logger.warning(f"数据库中的文章没有source_id: {article.get('title', 'Unknown')}")
                        continue
                else:
                    logger.warning(f"无法在数据库中找到文章: {article.get('title', 'Unknown')}")
                    continue
            else:
                logger.warning(f"文章数据缺少必要字段: {article}")
                continue
        
        if article_source_id not in articles_by_source:
            articles_by_source[article_source_id] = []
        articles_by_source[article_source_id].append(article)
    
    # 为每个源生成报告
    for source_info in sources:
        source_id = source_info['id']
        source_name = source_info['name']
        
        # 获取该源的文章
        target_articles = articles_by_source.get(source_id, [])
        
        if target_articles:
            for article in target_articles:
                article_time = datetime.fromtimestamp(article['publish_timestamp'], pytz.UTC)
                article_time_cst = article_time.astimezone(CST)
                logger.info(f"找到文章: {article['title']} (发布时间: {article_time_cst})")
        
        # 如果没有找到该源的文章，则跳过
        if not target_articles:
            logger.info(f"源 {source_name} 没有新文章")
            continue
        
        # 创建报告目录结构
        date_str = current_time.strftime('%Y%m%d')
        safe_source_name = source_name.replace(' ', '_')
        report_dir = Path('reports') / date_str / safe_source_name
        
        try:
            # 确保目录存在并设置正确的权限
            report_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(str(report_dir), 0o755)
            logger.info(f"创建报告目录: {report_dir}")
        except Exception as e:
            logger.error(f"创建报告目录失败: {e}")
            continue
        
        # 生成报告文件名
        timestamp = current_time.strftime('%Y%m%d_%H%M%S')
        report_filename = report_dir / f"report_{timestamp}.md"
        audio_filename = report_dir / f"report_{timestamp}.mp3"
        
        # 生成报告内容（Markdown格式）
        with open(report_filename, 'w', encoding='utf-8') as f:
            header_text = f"**本次共有 {len(target_articles)} 篇文章更新**\n\n"
            header_text += "---\n\n"
            f.write(header_text)
            
            for i, article in enumerate(target_articles, 1):
                # 读取摘要文件
                abstract = ""
                if article.get('abstract_file') and os.path.exists(article['abstract_file']):
                    try:
                        with open(article['abstract_file'], 'r', encoding='utf-8') as af:
                            abstract = af.read().strip()
                    except Exception as e:
                        logger.error(f"读取摘要文件失败: {e}")
                
                # 转换文章发布时间为CST时区
                publish_timestamp_cst = to_cst_time(datetime.fromtimestamp(article['publish_timestamp'], pytz.UTC))
                
                # 使用Markdown格式
                article_text = (
                    f"## {i}. {article['title']}\n\n"
                    f"**时间**: {publish_timestamp_cst.strftime('%Y-%m-%d %H:%M:%S')} \n"
                    f"**链接**: [{article['url']}]({article['url']})  \n\n"
                    f"**摘要**: \n\n{abstract}\n\n"
                )
                
                if article.get('audio_file'):
                    article_text += f"**音频**: [收听语音摘要](file://{article['audio_file']})\n\n"
                article_text += "---\n\n"
                
                f.write(article_text)
        
        # 为整个报告生成语音文件 - 连接各个文章的音频文件
        try:
            # 检查是否有音频文件可以连接
            audio_files_to_concat = []
            for article in target_articles:
                if article.get('audio_file') and os.path.exists(article['audio_file']):
                    audio_files_to_concat.append(article['audio_file'])
            
            if audio_files_to_concat:
                # 创建3.2秒的静音间隔
                silence = AudioSegment.silent(duration=3200)  # 3.2秒，单位为毫秒
                
                # 连接所有音频文件
                combined_audio = AudioSegment.empty()
                for i, audio_file in enumerate(audio_files_to_concat):
                    try:
                        segment = AudioSegment.from_mp3(audio_file)
                        combined_audio += segment
                        
                        # 在每个音频之后添加静音间隔（最后一个音频后不添加）
                        if i < len(audio_files_to_concat) - 1:
                            combined_audio += silence
                    except Exception as e:
                        logger.error(f"处理音频文件 {audio_file} 时出错: {e}")
                
                # 导出合并后的音频文件
                combined_audio.export(str(audio_filename), format="mp3")
                logger.info(f"成功将 {len(audio_files_to_concat)} 个音频文件合并为报告音频: {audio_filename}")
                audio_files[source_name] = str(audio_filename)
            else:
                logger.warning(f"没有找到可用的 {source_name} 文章音频文件，跳过音频报告生成")
                audio_files[source_name] = None
        except Exception as e:
            logger.error(f"合并 {source_name} 音频文件失败: {e}")
            audio_files[source_name] = None
        
        # 存储报告文件路径
        report_files[source_name] = str(report_filename)
        
        # 添加报告记录到数据库
        report_id = add_report(
            source_id=source_id,
            report_file=str(report_filename),
            audio_report_file=audio_files[source_name]
        )
        
        if report_id < 0:
            logger.error(f"添加报告记录失败: {source_name}")
    
    return report_files

def generate_test_articles(source_id: Optional[int] = None, days: int = 1) -> List[Dict]:
    """
    从数据库生成测试用的文章列表
    
    Args:
        source_id: 可选的源ID，如果提供则只获取该源的文章
        days: 获取最近几天的文章，默认1天
    
    Returns:
        文章列表
    """
    # 计算时间范围
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)
    
    # 转换为UTC时间戳
    start_timestamp = int(start_time.astimezone(pytz.UTC).timestamp())
    end_timestamp = int(end_time.astimezone(pytz.UTC).timestamp())
    
    # 获取源
    if source_id is not None:
        source = get_source(source_id)
        if not source:
            logger.error(f"未找到源ID: {source_id}")
            return []
        sources = [source]
    else:
        sources = get_all_sources(only_actived=True)
        if not sources:
            logger.error("没有找到任何激活的源")
            return []
    
    # 获取所有文章
    all_articles = []
    for source_info in sources:
        articles = get_articles_by_source_and_timerange(
            source_info['id'],
            start_timestamp,
            end_timestamp
        )
        # 确保每篇文章都有source_id
        for article in articles:
            article['source_id'] = source_info['id']
        all_articles.extend(articles)
    
    return all_articles

def save_test_articles(articles: List[Dict], output_file: str = 'test_articles.json'):
    """
    保存测试用的文章列表到文件
    
    Args:
        articles: 文章列表
        output_file: 输出文件路径
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        logger.info(f"测试文章列表已保存到: {output_file}")
        return True
    except Exception as e:
        logger.error(f"保存测试文章列表失败: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='生成文章报告')
    parser.add_argument('-s', '--source-id', type=int, help='可选的源ID，如果提供则只为该源生成报告')
    parser.add_argument('-a', '--articles', type=str, help='JSON格式的文章列表文件路径')
    parser.add_argument('-d', '--days', type=int, default=1, help='获取最近几天的文章用于测试，默认1天')
    parser.add_argument('-t', '--test', action='store_true', help='生成测试用的文章列表文件')
    parser.add_argument('-o', '--output', type=str, help='测试模式下指定输出文件路径')
    
    args = parser.parse_args()
    
    # 处理测试模式
    if args.test:
        articles = generate_test_articles(args.source_id, args.days)
        if not articles:
            print("没有找到符合条件的文章", file=sys.stderr)
            return 1
        
        # 如果指定了输出文件，则保存到文件
        if args.output:
            if save_test_articles(articles, args.output):
                print(f"测试文章列表已保存到: {args.output}", file=sys.stderr)
                return 0
            else:
                print("生成测试文章列表失败", file=sys.stderr)
                return 1
        # 否则输出到标准输出
        else:
            json.dump(articles, sys.stdout, ensure_ascii=False, indent=2)
            return 0
    
    # 正常模式：从文件或标准输入加载文章列表
    try:
        if args.articles:
            # 从文件读取
            with open(args.articles, 'r', encoding='utf-8') as f:
                articles = json.load(f)
        else:
            # 从标准输入读取
            articles = json.load(sys.stdin)
    except Exception as e:
        print(f"读取文章列表失败: {e}", file=sys.stderr)
        return 1
    
    result = generate_report(articles, args.source_id)
    if result:
        print("报告生成成功:", file=sys.stderr)
        for source, file_path in result.items():
            print(f"- {source}: {file_path}", file=sys.stderr)
    else:
        print("没有新的报告生成或生成报告失败", file=sys.stderr)

if __name__ == "__main__":
    main()

# 使用示例：
# 1. 生成测试文件：
# python src/generate_reports.py -t -o test_articles.json  # 保存到文件
# python src/generate_reports.py -t  # 输出到标准输出

# 2. 使用文件生成报告：
# python src/generate_reports.py -a test_articles.json  # 从文件读取
# python src/generate_reports.py -a test_articles.json -s 1  # 指定源

# 3. 使用管道直接生成报告（推荐用于测试）：
# python src/generate_reports.py -t | python src/generate_reports.py  # 生成最近1天的报告
# python src/generate_reports.py -t -d 7 | python src/generate_reports.py  # 生成最近7天的报告
# python src/generate_reports.py -t -s 1 | python src/generate_reports.py -s 1  # 生成指定源的报告