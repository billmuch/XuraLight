#!/usr/bin/env python3
"""
量子位网站爬虫

该脚本用于爬取量子位网站的内容，并以 JSON 格式输出结果。
输出的内容包括文章标题、URL 和发布时间。

用法:
    python crawler_qbitai.py [--pages N]

选项:
    --pages N    要爬取的页数，默认为 1
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def parse_relative_time(time_str):
    """
    将相对时间转换为标准时间格式
    
    Args:
        time_str: 相对时间字符串，如"3小时前"、"昨天 16:01"等
    
    Returns:
        datetime对象
    """
    now = datetime.now()
    
    if "小时前" in time_str:
        hours = int(time_str.replace("小时前", "").strip())
        return now - timedelta(hours=hours)
    elif "昨天" in time_str:
        time_part = time_str.split(" ")[1]
        yesterday = now - timedelta(days=1)
        hour, minute = map(int, time_part.split(":"))
        return yesterday.replace(hour=hour, minute=minute, second=0, microsecond=0)
    elif "前天" in time_str:
        time_part = time_str.split(" ")[1]
        before_yesterday = now - timedelta(days=2)
        hour, minute = map(int, time_part.split(":"))
        return before_yesterday.replace(hour=hour, minute=minute, second=0, microsecond=0)
    else:
        # 处理具体日期格式 "2025-04-11"
        try:
            date = datetime.strptime(time_str, "%Y-%m-%d")
            # 对于只有日期的情况，设置时间为当天的 00:00:00
            return date.replace(hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            print(f"无法解析的时间格式: {time_str}", file=sys.stderr)
            return now


def get_qbitai_page(page_num=1):
    """
    获取量子位指定页码的内容
    
    Args:
        page_num: 页码数，从 1 开始
    
    Returns:
        页面内容的 HTML 字符串
    """
    base_url = "https://www.qbitai.com/"
    
    if page_num == 1:
        url = base_url
    else:
        url = urljoin(base_url, f"?paged={page_num}")
    
    print(f"正在请求页面: {url}", file=sys.stderr)
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # 设置编码
        response.encoding = 'utf-8'
        
        content = response.text
        print(f"获取到页面内容，大小: {len(content)} 字节", file=sys.stderr)
        
        return content
    except requests.RequestException as e:
        print(f"获取页面时出错: {e}", file=sys.stderr)
        return None


def parse_stories(html_content):
    """
    解析 HTML 内容，提取文章信息
    
    Args:
        html_content: HTML 字符串
    
    Returns:
        包含文章信息的列表
    """
    if not html_content:
        print("HTML 内容为空，无法解析", file=sys.stderr)
        return []
    
    print("开始解析 HTML 内容", file=sys.stderr)
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 查找所有文章条目
    items = soup.find_all('div', class_='picture_text')
    print(f"找到 {len(items)} 个文章条目", file=sys.stderr)
    
    stories = []
    for idx, item in enumerate(items):
        try:
            # 查找标题和链接
            title_link = item.find('h4').find('a')
            if not title_link:
                print(f"跳过第 {idx+1} 项: 未找到标题链接", file=sys.stderr)
                continue
            
            title = title_link.get_text(strip=True)
            url = title_link.get('href')
            
            # 查找发布时间
            time_element = item.find('span', class_='time')
            if not time_element:
                print(f"跳过第 {idx+1} 项: 未找到发布时间", file=sys.stderr)
                continue
                
            relative_time = time_element.get_text(strip=True)
            publish_time = parse_relative_time(relative_time)
            
            print(f"处理第 {idx+1} 项: 标题='{title}', URL='{url}', 相对时间='{relative_time}', 发布时间='{publish_time.isoformat()}'", file=sys.stderr)
            
            if title and url:
                story = {
                    "title": title,
                    "url": url,
                    "published_date": publish_time.isoformat()  # 使用 published_date 替代 crawled_at
                }
                stories.append(story)
                print(f"  - 已添加到结果列表", file=sys.stderr)
        except Exception as e:
            print(f"处理第 {idx+1} 项时出错: {e}", file=sys.stderr)
    
    print(f"共解析出 {len(stories)} 个文章", file=sys.stderr)
    return stories


def crawl_qbitai(num_pages=1):
    """
    爬取量子位网站
    
    Args:
        num_pages: 要爬取的页数
    
    Returns:
        包含所有文章信息的列表
    """
    all_stories = []
    
    for page in range(1, num_pages + 1):
        print(f"\n开始爬取第 {page} 页", file=sys.stderr)
        html_content = get_qbitai_page(page)
        if html_content:
            stories = parse_stories(html_content)
            all_stories.extend(stories)
            print(f"第 {page} 页爬取完成，获取到 {len(stories)} 个文章", file=sys.stderr)
            
            # 添加延迟，避免请求过快
            if page < num_pages:
                delay = 2
                print(f"等待 {delay} 秒后爬取下一页...", file=sys.stderr)
                time.sleep(delay)
        else:
            print(f"第 {page} 页获取失败，跳过", file=sys.stderr)
    
    print(f"\n爬取完成，共获取到 {len(all_stories)} 个文章", file=sys.stderr)
    return all_stories


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='爬取量子位网站内容')
    parser.add_argument('--pages', type=int, default=1, help='要爬取的页数，默认为 1')
    args = parser.parse_args()
    
    print(f"开始爬取量子位，页数: {args.pages}", file=sys.stderr)
    
    stories = crawl_qbitai(args.pages)
    
    # 输出 JSON 格式的结果
    result_json = json.dumps(stories, ensure_ascii=False, indent=2)
    print(result_json)
    
    print(f"爬取完成，共输出 {len(stories)} 个文章的信息", file=sys.stderr)


if __name__ == "__main__":
    main() 


# # 抓取首页内容
# python src/crawler_qbitai.py

# # 抓取多页内容（例如抓取前 3 页）
# python src/crawler_qbitai.py --pages 3