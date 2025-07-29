#!/usr/bin/env python3
"""
Hacker News 爬虫

该脚本用于爬取 Hacker News 网站的内容，并以 JSON 格式输出结果。
输出的内容包括文章标题、URL 和爬取时间。

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
    
    Args:
        page_num: 页码数，从 1 开始
    
    Returns:
        页面内容的 HTML 字符串
    """
    base_url = "https://news.ycombinator.com/"
    
    if page_num == 1:
        url = urljoin(base_url, "front")
    else:
        url = urljoin(base_url, f"front?p={page_num}")
    
    print(f"正在请求页面: {url}", file=sys.stderr)
    
    try:
        # 使用 curl 通过代理下载
        proxy_url = "http://localhost:7890"
        print(f"使用代理: {proxy_url}", file=sys.stderr)
        
        # 构建 curl 命令
        curl_cmd = [
            "curl",
            "-s",  # 静默模式
            "-L",  # 跟随重定向
            "-m", "30",  # 超时30秒
            "--proxy", proxy_url,
            "--proxy-insecure",  # 忽略代理SSL证书验证
            url
        ]
        
        print(f"执行 curl 命令: {' '.join(curl_cmd)}", file=sys.stderr)
        
        # 执行 curl 命令
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=35)
        
        if result.returncode == 0:
            content = result.stdout
            print(f"curl 请求成功，获取到页面内容，大小: {len(content)} 字节", file=sys.stderr)
            return content
        else:
            print(f"curl 请求失败，返回码: {result.returncode}", file=sys.stderr)
            print(f"错误输出: {result.stderr}", file=sys.stderr)
            return None
            
    except subprocess.TimeoutExpired:
        print("curl 请求超时", file=sys.stderr)
        return None
    except Exception as e:
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
    
    print(f"开始解析 HTML 内容，长度: {len(html_content)}", file=sys.stderr)
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 查找所有文章条目
    items = soup.find_all('tr', class_='athing')
    print(f"找到 {len(items)} 个 'athing' 条目", file=sys.stderr)
    
    stories = []
    for idx, item in enumerate(items):
        try:
            # 在 <span class="titleline"> 中查找链接
            title_span = item.find('span', class_='titleline')
            if not title_span:
                print(f"跳过第 {idx+1} 项: 未找到 titleline span", file=sys.stderr)
                continue
                
            # 在 titleline span 中查找第一个链接
            title_link = title_span.find('a')
            if not title_link:
                print(f"跳过第 {idx+1} 项: 在 titleline 中未找到链接", file=sys.stderr)
                continue
                
            title = title_link.get_text(strip=True)
            url = title_link.get('href')
            
            print(f"处理第 {idx+1} 项: 标题='{title}', URL='{url}'", file=sys.stderr)
            
            # 如果 URL 是相对路径，则转换为绝对路径
            if url and not url.startswith('http'):
                original_url = url
                url = urljoin("https://news.ycombinator.com/", url)
                print(f"  - 将相对路径 '{original_url}' 转换为绝对路径 '{url}'", file=sys.stderr)
            
            # 过滤内部链接的逻辑(可选)
            if "item?id=" in url and not title.startswith(("Ask HN", "Tell HN", "Show HN")):
                print(f"  - 跳过内部链接: {url}", file=sys.stderr)
                continue
            
            if title and url:
                timestamp = datetime.now().isoformat()
                story = {
                    "title": title,
                    "url": url,
                    "published_date": timestamp
                }
                stories.append(story)
                print(f"  - 已添加到结果列表", file=sys.stderr)
        except Exception as e:
            print(f"处理第 {idx+1} 项时出错: {e}", file=sys.stderr)
    
    print(f"共解析出 {len(stories)} 个文章", file=sys.stderr)
    return stories


def crawl_hacker_news(num_pages=1):
    """
    爬取 Hacker News 网站
    
    Args:
        num_pages: 要爬取的页数
    
    Returns:
        包含所有文章信息的列表
    """
    all_stories = []
    
    for page in range(1, num_pages + 1):
        print(f"\n开始爬取第 {page} 页", file=sys.stderr)
        html_content = get_hacker_news_page(page)
        if html_content:
            stories = parse_stories(html_content)
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