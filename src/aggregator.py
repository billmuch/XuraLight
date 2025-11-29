#!/usr/bin/env python3

import os
import sys
import json
import subprocess
from typing import Optional, Dict, List, Union, Tuple  # 添加 Tuple
from datetime import datetime
from pathlib import Path
import html2text
import requests
from typing import Optional, Dict, List, Union
import logging
import argparse
import PyPDF2
import io
import re
import time
import brotli
import httpx

from db import (
    get_source, 
    get_source_by_name, 
    add_article, 
    get_article_by_url,
    get_active_sources
)
from summarizer_agent import summarize

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加常量
MAX_SUMMARY_TEXT_LENGTH = 120000  # 用于生成摘要的最大文本长度

def download_hackernews_comments(item_id: str) -> Optional[str]:
    """
    从 HackerNews Algolia API 下载评论内容
    
    Args:
        item_id: HackerNews 文章ID
    
    Returns:
        格式化的评论文本或None
    """
    try:
        api_url = f"https://hn.algolia.com/api/v1/items/{item_id}"
        logger.info(f"从 Algolia API 获取评论: {api_url}")
        
        # 尝试使用代理
        proxies = {
            'http': 'http://127.0.0.1:7890',
            'https': 'http://127.0.0.1:7890'
        }
        
        # 首先尝试不使用代理
        try:
            response = requests.get(api_url, timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.warning(f"直接请求失败，尝试使用代理: {str(e)}")
            response = requests.get(api_url, proxies=proxies, timeout=30)
            response.raise_for_status()
        
        data = response.json()
        
        # 递归提取评论文本
        def extract_comments(item, level=0):
            comments = []
            if not item:
                return comments
            
            # 提取当前评论文本
            if 'text' in item and item['text']:
                # 使用html2text转换HTML格式的评论
                h = html2text.HTML2Text()
                h.ignore_links = True
                h.ignore_images = True
                h.body_width = 0
                comment_text = h.handle(item['text']).strip()
                
                # 添加作者和缩进
                author = item.get('author', 'anonymous')
                indent = "  " * level
                comments.append(f"{indent}[{author}]: {comment_text}")
            
            # 递归处理子评论
            if 'children' in item and item['children']:
                for child in item['children']:
                    comments.extend(extract_comments(child, level + 1))
            
            return comments
        
        # 提取所有评论
        all_comments = extract_comments(data)
        
        if all_comments:
            comments_text = "\n\n".join(all_comments)
            logger.info(f"成功获取 {len(all_comments)} 条评论，总长度: {len(comments_text)} 字符")
            return comments_text
        else:
            logger.info("该文章没有评论")
            return None
            
    except Exception as e:
        logger.error(f"从 Algolia API 获取评论失败: {str(e)}")
        return None

def get_source_info(source_identifier: Union[int, str]) -> Optional[Dict]:
    """
    根据ID或名称获取源信息
    
    Args:
        source_identifier: 源ID或名称
    
    Returns:
        源信息字典或None
    """
    if isinstance(source_identifier, int):
        return get_source(source_identifier)
    else:
        return get_source_by_name(source_identifier)

def extract_text_from_pdf(pdf_content: bytes) -> str:
    """
    从PDF内容中提取文本
    
    Args:
        pdf_content: PDF文件的二进制内容
    
    Returns:
        提取的文本内容
    """
    try:
        # 使用BytesIO创建内存文件对象
        pdf_file = io.BytesIO(pdf_content)
        
        # 创建PDF阅读器对象
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        # 提取所有页面的文本
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        
        # 清理文本
        text = re.sub(r'\s+', ' ', text)  # 替换多个空白字符为单个空格
        text = text.strip()
        
        return text
    except Exception as e:
        logger.error(f"PDF文本提取失败: {str(e)}")
        return ""

def download_and_convert_to_text(url: str) -> Optional[str]:
    """
    下载并转换文章内容为文本
    
    Args:
        url: 文章URL
    
    Returns:
        转换后的文本内容或None
    """
    max_retries = 2
    retry_count = 0
    last_error = None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Referer": url
    }
    proxies = None
    
    while retry_count <= max_retries:
        try:
            # 下载内容
            if retry_count == 0:
                # 第一次尝试，使用简单请求
                response = requests.get(url, headers=headers, timeout=30)
            else:
                # 重试时使用headers和可能的代理
                logger.info(f"第{retry_count}次重试获取URL: {url}")
                response = requests.get(url, headers=headers, proxies=proxies, timeout=30)
            
            response.raise_for_status()
            
            # 检查内容类型
            content_type = response.headers.get('Content-Type', '').lower()
            
            # 初始化文本变量
            text = None
            
            # 1. 如果是PDF，使用extract_text_from_pdf处理
            if 'application/pdf' in content_type:
                text = extract_text_from_pdf(response.content)
                
            # 2. 如果是HTML/XML格式，使用html2text处理
            elif 'html' in content_type or 'xml' in content_type:
                h = html2text.HTML2Text()
                h.ignore_links = True
                h.ignore_images = True
                h.ignore_emphasis = True  # 忽略强调标记
                h.ignore_tables = True    # 忽略表格
                h.body_width = 0          # 不限制行宽
                
                # 处理HTML内容
                text = h.handle(response.text)
                
            # 3. 其他文本类型，直接使用响应内容
            elif 'text/' in content_type:
                text = response.text
                
            # 4. 其他类型，尝试直接使用响应内容
            else:
                logger.info(f"未知内容类型: {content_type}，尝试作为纯文本处理")
                # 尝试将内容解码为文本
                try:
                    text = response.text
                except UnicodeDecodeError:
                    logger.warning(f"无法解码内容为文本: {url}")
                    return None
            
            # 如果提取的文本为None，返回None
            if text is None:
                logger.warning(f"无法提取文本内容: {url}")
                return None
                
            # 清理和标准化文本 (应用于所有类型)
            text = text.strip()
            text = re.sub(r'\n{3,}', '\n\n', text)  # 将3个以上的换行替换为2个
            text = re.sub(r'[^\S\n]+', ' ', text)   # 将非换行的空白字符替换为单个空格
            
            # 检查文本是否为空或只包含空白字符
            if not text or text.isspace():
                logger.warning(f"转换后的文本为空或只包含空白字符: {url}")
                return None
            
            # 限制文本长度
            if len(text) > MAX_SUMMARY_TEXT_LENGTH:
                logger.info(f"文本长度超过{MAX_SUMMARY_TEXT_LENGTH}字符，将只使用前{MAX_SUMMARY_TEXT_LENGTH}字符")
                text = text[:MAX_SUMMARY_TEXT_LENGTH]
            
            return text
        
        except Exception as e:
            last_error = e
            retry_count += 1
            logger.warning(f"请求出错 ({retry_count}/{max_retries+1}): {url}, 错误: {str(e)}")
            proxies = {
                'http': 'http://127.0.0.1:7890',
                'https': 'http://127.0.0.1:7890'
            }
            time.sleep(3)
    
    # 所有重试都失败了
    logger.error(f"下载或处理URL失败，已重试{max_retries}次: {url}, 错误: {str(last_error)}")
    return None


def sanitize_filename(title: str) -> str:
    """
    处理文件名中的特殊字符
    
    Args:
        title: 原始标题
    
    Returns:
        处理后的安全文件名
    """
    # 替换文件系统不安全的字符
    unsafe_chars = {
        '/': '／',
        '\\': '＼',
        ':': '：',
        '*': '＊',
        '?': '？',
        '"': '＂',
        '<': '＜',
        '>': '＞',
        '|': '｜',
        '\n': '_',
        '\r': '_',
        '\t': '_',
        ' ': '_'  # 添加空格到下划线的替换
    }
    
    safe_title = title
    for char, replacement in unsafe_chars.items():
        safe_title = safe_title.replace(char, replacement)
    
    # 移除前后空格（虽然空格会被替换，但以防万一）
    safe_title = safe_title.strip()
    
    # 处理连续的下划线（可能由连续空格产生）
    while '__' in safe_title:
        safe_title = safe_title.replace('__', '_')
    
    # 如果标题太长，截断它
    max_length = 100  # 文件名最大长度（不包括时间戳和扩展名）
    if len(safe_title) > max_length:
        safe_title = safe_title[:max_length-3] + '...'
    
    return safe_title

def save_abstract_with_audio(text: str, source_name: str, timestamp: int, title: str, generate_audio: bool = False) -> Tuple[Optional[str], Optional[str]]:
    """
    保存摘要文件并可选生成语音文件
    
    Args:
        text: 摘要文本
        source_name: 源名称
        timestamp: 发布时间戳
        title: 文章标题
        generate_audio: 是否生成语音文件，默认为False
    
    Returns:
        Tuple[Optional[str], Optional[str]]: (摘要文件路径, 语音文件路径)
    """
    try:
        # 处理源名称中的空格
        safe_source_name = source_name.replace(' ', '_')
        
        # 创建目录结构
        date_str = datetime.fromtimestamp(timestamp).strftime('%Y%m%d')
        abstract_dir = Path('abstraction') / safe_source_name / date_str
        abstract_dir.mkdir(parents=True, exist_ok=True)
        
        # 处理标题并生成文件名
        safe_title = sanitize_filename(title)
        abstract_file_name = f"{timestamp}_{safe_title}.txt"
        audio_file_name = f"{timestamp}_{safe_title}.mp3"
        
        abstract_file_path = abstract_dir / abstract_file_name
        audio_file_path = abstract_dir / audio_file_name
        
        # 保存摘要
        try:
            with open(abstract_file_path, 'w', encoding='utf-8') as f:
                f.write(text)
            
            # 验证文件是否成功写入
            if not abstract_file_path.exists() or abstract_file_path.stat().st_size == 0:
                logger.error(f"摘要文件写入失败或为空: {abstract_file_path}")
                return None, None
                
            logger.info(f"成功保存摘要文件: {abstract_file_path}")
            
            # 如果需要生成语音文件
            if generate_audio:
                # 生成语音文件
                # from tts import text_to_speech
                # audio_success = text_to_speech(text, str(audio_file_path))
                audio_success = False
                
                if not audio_success:
                    logger.error(f"生成语音文件失败: {title}")
                    return str(abstract_file_path), None
                    
                return str(abstract_file_path), str(audio_file_path)
            
            return str(abstract_file_path), None
            
        except UnicodeEncodeError as e:
            logger.error(f"保存摘要时发生编码错误: {e}")
            # 尝试使用不同的编码方式
            try:
                with open(abstract_file_path, 'w', encoding='gbk') as f:
                    f.write(text)
                logger.info(f"使用GBK编码成功保存摘要文件: {abstract_file_path}")
                return str(abstract_file_path), None
            except Exception as e2:
                logger.error(f"使用GBK编码保存摘要也失败: {e2}")
                return None, None
                
    except Exception as e:
        logger.error(f"保存摘要和语音文件失败: {str(e)}")
        return None, None

def process_crawler_output(output: str, source_info: Dict, limit: Optional[int] = None, debug_mode: bool = False) -> List[Dict]:
    """
    处理爬虫输出
    
    Args:
        output: 爬虫输出的JSON字符串
        source_info: 源信息字典
        limit: 限制处理的文章数量，None表示处理所有文章
        debug_mode: 是否启用调试模式，True时会保存原始文本到temp目录
    
    Returns:
        处理后的文章列表
    """
    try:
        articles = json.loads(output)
        if not isinstance(articles, list):
            raise ValueError("爬虫输出必须是文章列表")
        
        # 如果设置了限制，只取前N篇文章
        if limit is not None:
            articles = articles[:limit]
            logger.info(f"限制处理前 {limit} 篇文章")
        
        processed_articles = []
        for idx, article in enumerate(articles, 1):
            logger.info(f"处理第 {idx}/{len(articles)} 篇文章")
            
            # 检查必要字段
            if not all(k in article for k in ('url', 'title', 'published_date')):
                logger.warning(f"跳过格式不正确的文章: {article}")
                continue
            
            # 检查文章是否已存在
            if get_article_by_url(article['url']):
                logger.info(f"文章已存在，跳过: {article['url']}")
                continue
            
            # 下载并转换文章内容
            text = download_and_convert_to_text(article['url'])
            if not text:
                logger.warning(f"无法获取文章内容，跳过: {article['url']}")
                continue
            
            # 下载并转换评论内容
            comments_text = ""
            if 'comments_url' in article and article['comments_url']:
                # 检测是否是 HackerNews 评论链接
                hn_match = re.search(r'news\.ycombinator\.com/item\?id=(\d+)', article['comments_url'])
                if hn_match:
                    # 使用 Algolia API 获取评论
                    item_id = hn_match.group(1)
                    logger.info(f"检测到 HackerNews 评论链接，使用 Algolia API 获取评论: {item_id}")
                    comments_text = download_hackernews_comments(item_id) or ""
                else:
                    # 其他来源的评论，使用原来的方法
                    comments_text = download_and_convert_to_text(article['comments_url']) or ""
                
                if comments_text:
                    logger.info(f"成功获取评论内容，长度: {len(comments_text)} 字符")
                else:
                    logger.warning(f"无法获取评论内容: {article['comments_url']}")
            else:
                logger.info("文章没有评论链接，跳过评论下载")

            
                
            # 调试：保存原始文本到temp目录（仅在调试模式下执行）
            if debug_mode:
                try:
                    temp_dir = Path('temp')
                    temp_dir.mkdir(exist_ok=True)
                    
                    # 使用文章标题和时间戳创建文件名
                    safe_title = sanitize_filename(article['title'])
                    timestamp = int(datetime.now().timestamp())
                    debug_file = temp_dir / f"{timestamp}_{safe_title}_raw.txt"
                    
                    # 保存原始文本
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        f.write(text)
                    logger.info(f"已保存原始文本到: {debug_file}")
                except Exception as e:
                    logger.error(f"保存调试文件失败: {str(e)}")
            
            # 生成摘要
            success, result = summarize(text, comments_text)
            if not success:
                logger.error(f"生成摘要失败: {result}")
                continue
            
            # 计算时间戳
            try:
                dt = datetime.fromisoformat(article['published_date'].replace('Z', '+00:00'))
                timestamp = int(dt.timestamp())
            except ValueError:
                timestamp = int(datetime.now().timestamp())
            
            # 保存摘要（不生成语音）
            abstract_file, audio_file = save_abstract_with_audio(
                result,
                source_info['name'],
                timestamp,
                article['title'],
                generate_audio=False  # 明确指定不生成语音
            )
            
            if not abstract_file:
                logger.warning(f"保存摘要失败，跳过: {article['url']}")
                continue
            
            processed_articles.append({
                'url': article['url'],
                'title': article['title'],
                'source_id': source_info['id'],
                'abstract_file': abstract_file,
                'audio_file': audio_file,
                'publish_timestamp': timestamp
            })
            
        return processed_articles
    except Exception as e:
        logger.error(f"处理爬虫输出失败: {str(e)}")
        return []
    
def do(source_identifier: Union[int, str], limit: Optional[int] = None, debug_mode: bool = False) -> bool:
    """
    执行聚合操作
    
    Args:
        source_identifier: 源ID或名称
        limit: 限制处理的文章数量，None表示处理所有文章
        debug_mode: 是否启用调试模式，True时会保存原始文本到temp目录
    
    Returns:
        是否成功
    """
    try:
        # 1. 获取源信息
        source_info = get_source_info(source_identifier)
        if not source_info:
            logger.error(f"未找到源: {source_identifier}")
            return False
        
        logger.info(f"开始处理源: {source_info['name']}" + 
                   (f"，限制处理前 {limit} 篇文章" if limit else "，处理所有文章"))
        
        # 2. 执行爬虫命令
        # 移除命令中的 src/ 前缀
        crawler_command = source_info['crawler_command'].replace('src/', '')
        crawler_command = crawler_command.split()
        
        # 确保在正确的目录下执行爬虫
        current_dir = os.getcwd()
        src_dir = os.path.join(current_dir, 'src')
        
        try:
            logger.info(f"在目录 {src_dir} 下执行爬虫命令: {' '.join(crawler_command)}")
            result = subprocess.run(
                crawler_command,
                capture_output=True,
                text=True,
                check=True,
                cwd=src_dir  # 在src目录下执行命令
            )
            
            # 检查爬虫输出
            if not result.stdout.strip():
                logger.error("爬虫没有输出任何内容")
                return False
                
            try:
                # 验证输出是否为有效的JSON
                articles = json.loads(result.stdout)
                if not articles:
                    logger.error("爬虫返回空列表")
                    return False
                logger.info(f"爬虫成功获取 {len(articles)} 篇文章")
            except json.JSONDecodeError as e:
                logger.error(f"爬虫输出不是有效的JSON格式: {e}")
                logger.error(f"爬虫输出内容: {result.stdout[:200]}...")  # 只显示前200个字符
                return False
                
            crawler_output = result.stdout
            
            # 如果有错误输出，记录下来
            if result.stderr:
                logger.warning(f"爬虫错误输出: {result.stderr}")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"爬虫执行失败: {str(e)}")
            if e.stderr:
                logger.error(f"爬虫错误输出: {e.stderr}")
            if e.stdout:
                logger.error(f"爬虫标准输出: {e.stdout}")
            return False
        
        # 3. 处理爬虫输出
        articles = process_crawler_output(crawler_output, source_info, limit, debug_mode)
        
        if not articles:
            logger.warning("没有新文章需要处理")
            return True
        
        # 4. 保存到数据库
        success_count = 0
        for article in articles:
            article_id = add_article(
                url=article['url'],
                title=article['title'],
                source_id=article['source_id'],
                abstract_file=article['abstract_file'],
                audio_file=article['audio_file'],
                publish_timestamp=article['publish_timestamp']
            )
            
            if article_id > 0:
                success_count += 1
                logger.info(f"成功添加文章: {article['title']}")
            else:
                logger.warning(f"添加文章失败: {article['title']}")
        
        logger.info(f"处理完成。成功添加 {success_count}/{len(articles)} 篇文章")
        
        # 5. 生成并发布报告
        try:
            # 生成报告
            from generate_reports import generate_report
            result = generate_report(articles, source_info['id'])
            
            if result and source_info['name'] in result:
                report_file = result[source_info['name']]
                logger.info(f"生成报告成功: {report_file}")
                
                # 发布报告
                from publish_report import publish_report
                publish_success = publish_report(report_file, source_info['name'], source_info.get('media_path'))
                if publish_success:
                    logger.info(f"成功发布报告: {report_file}")
                else:
                    logger.error(f"发布报告失败: {report_file}")
            else:
                logger.warning("没有生成新的报告")
                
        except Exception as e:
            logger.error(f"生成或发布报告时发生错误: {str(e)}")
        
        return True
        
    except Exception as e:
        logger.error(f"聚合过程失败: {str(e)}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='聚合所有激活源的文章')
    parser.add_argument('-n', '--num-articles', type=int, help='限制每个源处理的文章数量，默认处理所有文章')
    parser.add_argument('-d', '--debug', action='store_true', help='启用调试模式，保存原始文本到temp目录')
    
    args = parser.parse_args()
    
    # 获取所有激活的源
    sources = get_active_sources()
    
    if not sources:
        logger.error("没有找到激活的源")
        sys.exit(1)
    
    logger.info(f"找到 {len(sources)} 个激活的源")
    
    # 处理每个激活的源
    success_count = 0
    for source in sources:
        logger.info(f"开始处理源: {source['name']}")
        if do(source['id'], args.num_articles, args.debug):
            success_count += 1
        else:
            logger.error(f"处理源 {source['name']} 失败")
    
    logger.info(f"处理完成。成功处理 {success_count}/{len(sources)} 个源")
    sys.exit(0 if success_count == len(sources) else 1)

# 使用示例：
# 处理所有激活的源的所有文章
# python src/aggregator.py

# 处理所有激活的源，每个源只处理前5篇文章
# python src/aggregator.py -n 5