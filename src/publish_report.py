import os
import requests
import json
import logging
from datetime import datetime, timedelta
import pytz
import re
import sys
import markdown  # 添加markdown库用于转换md到html
from bs4 import BeautifulSoup  # 添加BeautifulSoup用于修复HTML
# 配置logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定义中国标准时区
CST = pytz.timezone('Asia/Shanghai')

def get_access_token():
    """
    从微信获取access_token
    
    Returns:
        str: 获取到的access_token，如果获取失败则返回None
    """
    # 从环境变量中获取apiid和secret
    appid = os.environ.get('WECHAT_APP_ID')
    secret = os.environ.get('WECHAT_APP_SECRET')
    
    if not appid or not secret:
        logger.error("未设置WECHAT_APPID或WECHAT_SECRET环境变量")
        return None
    
    # 微信获取access_token的API地址
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={appid}&secret={secret}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if 'access_token' in data:
            logger.info("成功获取微信access_token")
            return data['access_token']
        else:
            logger.error(f"获取access_token失败: {data.get('errmsg', '未知错误')}")
            return None
    except Exception as e:
        logger.error(f"请求微信API失败: {e}")
        return None

def publish_to_wechat(access_token, title, content, media_path=None):
    """
    发布文章到微信公众号
    
    Args:
        access_token (str): 微信API的access_token
        title (str): 文章标题
        content (str): 文章内容，支持HTML
        media_path (str, optional): 封面图片的路径
        
    Returns:
        bool: 是否发布成功
    """
    thumb_media_id = None
    
    # 上传封面图片
    if media_path:
        upload_url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
        
        try:
            # 检查图片文件是否存在
            if not os.path.exists(media_path):
                logger.warning(f"封面图片文件不存在: {media_path}")
            else:
                # 获取文件扩展名
                _, ext = os.path.splitext(media_path)
                mime_type = f'image/{ext[1:]}' if ext else 'image/jpg'
                
                # 检查文件类型
                with open(media_path, 'rb') as f:
                    files = {'media': (os.path.basename(media_path), f, mime_type)}
                    response = requests.post(upload_url, files=files)
                    result = response.json()
                    
                    if 'media_id' in result:
                        logger.info(f"成功上传封面图片: {result['media_id']}")
                        thumb_media_id = result['media_id']
                    else:
                        logger.error(f"上传封面图片失败: {result.get('errmsg', '未知错误')}")
        except Exception as e:
            logger.error(f"上传封面图片失败: {e}")

    url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}"
    
    # 构建发布请求
    article = {
        "title": title,
        "content": content,
        "author": "",
        "digest": "",
        "content_source_url": "",
        "thumb_media_id": thumb_media_id if thumb_media_id else "",
        "need_open_comment": 1,
        "only_fans_can_comment": 0
    }
    
    data = {
        "articles": [article]
    }
    
    try:
        # 确保请求头包含正确的编码信息
        headers = {
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        # 将数据转换为JSON字符串，确保正确处理中文
        json_data = json.dumps(data, ensure_ascii=False)
        
        # 发送请求
        response = requests.post(url, data=json_data.encode('utf-8'), headers=headers)
        result = response.json()
        
        if 'media_id' in result:
            logger.info(f"成功创建草稿: {result['media_id']}")
            
            # 发布草稿
            publish_url = f"https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token={access_token}"
            publish_data = {"media_id": result['media_id']}
            publish_json = json.dumps(publish_data, ensure_ascii=False)
            publish_response = requests.post(publish_url, data=publish_json.encode('utf-8'), headers=headers)
            publish_result = publish_response.json()
            
            if 'publish_id' in publish_result:
                logger.info(f"成功发布文章: {publish_result['publish_id']}")
                # 发布成功后删除微信服务器上的图片素材
                if thumb_media_id:
                    try:
                        delete_url = f"https://api.weixin.qq.com/cgi-bin/material/del_material?access_token={access_token}"
                        delete_data = {"media_id": thumb_media_id}
                        delete_json = json.dumps(delete_data, ensure_ascii=False)
                        delete_response = requests.post(delete_url, data=delete_json.encode('utf-8'), headers=headers)
                        delete_result = delete_response.json()
                        
                        if delete_result.get('errcode') == 0:
                            logger.info(f"成功删除微信服务器上的图片素材: {thumb_media_id}")
                        else:
                            logger.error(f"删除图片素材失败: {delete_result.get('errmsg', '未知错误')}")
                    except Exception as e:
                        logger.error(f"删除图片素材时发生错误: {e}")
                return True
            else:
                logger.error(f"发布草稿失败: {publish_result.get('errmsg', '未知错误')}")
                return False
        else:
            logger.error(f"创建草稿失败: {result.get('errmsg', '未知错误')}")
            return False
    except Exception as e:
        logger.error(f"发布到微信失败: {e}")
        return False

def publish_report(report_file, source_name, media_path=None):
    """
    发布报告到微信公众号
    
    Args:
        report_file (str): 报告文件路径
        source_name (str): 数据源名称（网站名）
        media_path (str, optional): 封面图片的路径
        
    Returns:
        bool: 是否发布成功
    """
    # 检查文件是否存在
    if not os.path.exists(report_file):
        logger.error(f"报告文件不存在: {report_file}")
        return False
    
    # 获取当前日期（中国标准时间）
    now = datetime.now(CST)
    date_str = now.strftime('%Y年%m月%d日')
    
    # 读取报告内容
    try:
        with open(report_file, 'r', encoding='utf-8') as f:
            report_content = f.read()
    except Exception as e:
        logger.error(f"读取报告文件失败: {e}")
        return False
    
    # 构建文章标题
    title = f"{source_name} {date_str} 摘要"
    
    # 检查文件是否为Markdown格式
    is_markdown = report_file.lower().endswith('.md')
    
    # 格式化文章内容
    if is_markdown:
        try:
            # 使用markdown库将Markdown转换为HTML
            html_content = markdown.markdown(
                report_content,
                extensions=['extra', 'codehilite', 'tables', 'toc']  # 使用额外扩展支持更多Markdown特性
            )
            
            # 使用BeautifulSoup修复可能的HTML问题，确保符合微信要求
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 处理链接，确保它们在新窗口打开
            for a_tag in soup.find_all('a'):
                a_tag['target'] = '_blank'
                
            # 处理图片，添加样式使其适应微信文章
            for img_tag in soup.find_all('img'):
                img_tag['style'] = 'max-width: 100%; height: auto;'
            
            # 在文章分隔符（hr标签）后添加两行空行，使文章间隔更明显
            from bs4 import NavigableString
            for hr_tag in soup.find_all('hr'):
                # 在hr标签后插入两个br标签
                br1 = soup.new_tag('br')
                br2 = soup.new_tag('br')
                hr_tag.insert_after(br2)
                hr_tag.insert_after(br1)
            
            # 转换回字符串
            formatted_html = str(soup)
            
            # 构建完整的HTML内容
            formatted_content = f"""
            <h1>{title}</h1>
            <div>{formatted_html}</div>
            """
            
            logger.info("成功将Markdown内容转换为HTML")
        except Exception as e:
            logger.error(f"Markdown转换HTML失败: {e}")
            # 如果转换失败，回退到原始处理方式
            formatted_content = f"""
            <h1>{title}</h1>
            <p>以下是{source_name}的今日新闻摘要：</p>
            <div>
            {report_content.replace('\n', '<br>')}
            </div>
            """
    else:
        # 非Markdown文件，使用原始的处理方式
        formatted_content = f"""
        <h1>{title}</h1>
        <p>以下是{source_name}的今日新闻摘要：</p>
        <div>
        {report_content.replace('\n', '<br>')}
        </div>
        """
    
    # 获取access_token
    access_token = get_access_token()
    if not access_token:
        return False
    
    # 发布到微信
    return publish_to_wechat(access_token, title, formatted_content, media_path)

if __name__ == "__main__":
    # 从命令行获取参数
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print("Usage: python publish_report.py <report_file> <source_name> [media_path]")
        sys.exit(1)
        
    report_file = sys.argv[1]
    source_name = sys.argv[2]
    
    # 可选的媒体路径参数
    media_path = None
    if len(sys.argv) == 4:
        media_path = sys.argv[3]
    
    # 发布报告
    success = publish_report(report_file, source_name, media_path)
    if success:
        print(f"成功发布{source_name}的报告")
    else:
        print(f"发布{source_name}的报告失败")
        sys.exit(1)

# 更新使用示例
# python src/publish_report.py ./reports/hacker_news_20250430.txt "hacker news" ./images/cover.jpg