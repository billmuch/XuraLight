#!/usr/bin/env python3
"""
Hacker News 爬虫

该脚本使用 Hacker News 官方 Algolia API 获取内容，并以 JSON 格式输出结果。
输出的内容包括文章标题、URL、发布时间和评论页面链接。

优势：
- 使用官方 API，更稳定可靠
- 避免网页解析问题
- 速度更快

用法:
    python crawler_hackernews.py [--pages N]

选项:
    --pages N    要爬取的页数，默认为 1
"""

import argparse
import json
import re
import sys
import time
import subprocess
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def get_hacker_news_page(page_num=1):
    """
    获取 Hacker News 指定页码的内容
    使用 Algolia API 获取数据，更稳定可靠
    
    Args:
        page_num: 页码数，从 0 开始（API 使用 0-based 索引）
    
    Returns:
        JSON 数据字典
    """
    # 使用 Hacker News 官方 Algolia API
    # front page 故事
    api_url = f"https://hn.algolia.com/api/v1/search?tags=front_page&page={page_num - 1}&hitsPerPage=30"
    
    print(f"正在请求 API: {api_url}", file=sys.stderr)
    
    try:
        # 尝试使用代理
        proxy_url = "http://localhost:9674"
        print(f"尝试使用代理: {proxy_url}", file=sys.stderr)
        
        # 构建 curl 命令
        curl_cmd = [
            "curl",
            "-s",  # 静默模式
            "-L",  # 跟随重定向
            "-m", "30",  # 超时30秒
            "--proxy", proxy_url,
            "-k",  # 忽略SSL证书验证
            api_url
        ]
        
        print(f"执行 curl 命令: {' '.join(curl_cmd)}", file=sys.stderr)
        
        # 执行 curl 命令
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=35)
        
        if result.returncode == 0 and result.stdout and len(result.stdout) > 100:
            content = result.stdout
            print(f"API 请求成功（使用代理），获取到数据，大小: {len(content)} 字节", file=sys.stderr)
            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                print(f"JSON 解析失败: {e}", file=sys.stderr)
                return None
        else:
            print(f"代理请求失败，尝试直接连接...", file=sys.stderr)
            
            # 不使用代理重试
            curl_cmd_no_proxy = [
                "curl",
                "-s",
                "-L",
                "-m", "30",
                api_url
            ]
            
            result = subprocess.run(curl_cmd_no_proxy, capture_output=True, text=True, timeout=35)
            
            if result.returncode == 0:
                content = result.stdout
                print(f"API 请求成功（直接连接），获取到数据，大小: {len(content)} 字节", file=sys.stderr)
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"JSON 解析失败: {e}", file=sys.stderr)
                    return None
            else:
                print(f"API 请求失败，返回码: {result.returncode}", file=sys.stderr)
                print(f"错误输出: {result.stderr}", file=sys.stderr)
                return None
            
    except subprocess.TimeoutExpired:
        print("API 请求超时", file=sys.stderr)
        return None
    except Exception as e:
        print(f"获取 API 数据时出错: {e}", file=sys.stderr)
        return None


def parse_stories(api_data):
    """
    解析 API 返回的 JSON 数据，提取文章信息
    
    Args:
        api_data: API 返回的 JSON 数据字典
    
    Returns:
        包含文章信息的列表
    """
    if not api_data:
        print("API 数据为空，无法解析", file=sys.stderr)
        return []
    
    if not isinstance(api_data, dict) or 'hits' not in api_data:
        print(f"API 数据格式错误: {type(api_data)}", file=sys.stderr)
        return []
    
    hits = api_data.get('hits', [])
    print(f"开始解析 API 数据，找到 {len(hits)} 个条目", file=sys.stderr)
    
    stories = []
    for idx, hit in enumerate(hits):
        try:
            # 从 API 数据中提取信息
            title = hit.get('title', '')
            url = hit.get('url', '')
            
            # 如果没有外部 URL，使用 HN 的讨论链接
            if not url:
                object_id = hit.get('objectID', '')
                if object_id:
                    url = f"https://news.ycombinator.com/item?id={object_id}"
                    print(f"处理第 {idx+1} 项: 标题='{title}', 使用讨论链接", file=sys.stderr)
                else:
                    print(f"跳过第 {idx+1} 项: 没有 URL 和 objectID", file=sys.stderr)
                    continue
            else:
                print(f"处理第 {idx+1} 项: 标题='{title}', URL='{url}'", file=sys.stderr)
            
            # 获取创建时间，如果没有则使用当前时间
            created_at = hit.get('created_at', '')
            if created_at:
                # API 返回的时间格式: "2023-10-12T10:30:00.000Z"
                try:
                    published_date = datetime.fromisoformat(created_at.replace('Z', '+00:00')).isoformat()
                except:
                    published_date = datetime.now().isoformat()
            else:
                published_date = datetime.now().isoformat()
            
            # 构建评论页面 URL
            object_id = hit.get('objectID', '')
            comments_url = f"https://news.ycombinator.com/item?id={object_id}" if object_id else ""
            
            if title and url:
                story = {
                    "title": title,
                    "url": url,
                    "published_date": published_date,
                    "comments_url": comments_url
                }
                stories.append(story)
                print(f"  - 已添加到结果列表，评论链接: {comments_url}", file=sys.stderr)
        except Exception as e:
            print(f"处理第 {idx+1} 项时出错: {e}", file=sys.stderr)
    
    print(f"共解析出 {len(stories)} 个文章", file=sys.stderr)
    return stories


def crawl_hacker_news(num_pages=1):
    """
    爬取 Hacker News 网站
    使用 Algolia API 获取数据
    
    Args:
        num_pages: 要爬取的页数
    
    Returns:
        包含所有文章信息的列表
    """
    all_stories = []
    
    for page in range(1, num_pages + 1):
        print(f"\n开始爬取第 {page} 页", file=sys.stderr)
        api_data = get_hacker_news_page(page)
        if api_data:
            stories = parse_stories(api_data)
            all_stories.extend(stories)
            print(f"第 {page} 页爬取完成，获取到 {len(stories)} 个文章", file=sys.stderr)
            
            # 添加一个小延迟，避免请求过快
            if page < num_pages:
                print(f"等待 1 秒后爬取下一页...", file=sys.stderr)
                time.sleep(1)
        else:
            print(f"第 {page} 页获取失败，跳过", file=sys.stderr)
    
    print(f"\n爬取完成，共获取到 {len(all_stories)} 个文章", file=sys.stderr)
    return all_stories


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='爬取 Hacker News 网站内容')
    parser.add_argument('--pages', type=int, default=1, help='要爬取的页数，默认为 1')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    args = parser.parse_args()
    
    print(f"开始爬取 Hacker News，页数: {args.pages}", file=sys.stderr)
    
    stories = crawl_hacker_news(args.pages)
    
    # 输出 JSON 格式的结果
    result_json = json.dumps(stories, ensure_ascii=False, indent=2)
    print(result_json)
    
    print(f"爬取完成，共输出 {len(stories)} 个文章的信息", file=sys.stderr)


if __name__ == "__main__":
    main()


# # 抓取首页内容
# python src/crawler_hackernews.py

# # 抓取多页内容（例如抓取前 3 页）
# python src/crawler_hackernews.py --pages 3