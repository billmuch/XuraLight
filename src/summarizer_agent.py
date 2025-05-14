#!/usr/bin/env python3

import sys
import logging
from typing import Optional, Dict, Any, Tuple
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 加载prompt模板
PROMPT =  """{article_content}
请深入阅读分析上面的内容，找到文章主要的核心要点，以摘要形式做下介绍。
摘要请包含文章标题的中文翻译。
介绍应避免使用术语，尽量口语化，使用通俗易懂的语言完成。
用户应该可以通过摘要了解文章的主要思想内容。

如果文章是论文，请在摘要中包含论文主要针对什么行业/技术，用了什么方法，解决了什么问题，有什么前景。

输出字数限制在250字内。
"""

def summarize(
    content: str,
) -> Tuple[bool, str]:
    """
    生成文章摘要
    
    Args:
        content: 文章内容
    
    Returns:
        Tuple[bool, str]: (是否成功, 摘要内容或错误信息)
    """
    # 填充prompt模板
    prompt = PROMPT.format(article_content=content)
    
    try:
        # 调用 OpenAI API 生成摘要
        from openai import OpenAI
        
        client = OpenAI(
            api_key=os.getenv("TENCENT_LLM_API_KEY"),
            base_url="https://api.lkeap.cloud.tencent.com/v1",
        )
        
        response = client.chat.completions.create(
            model="deepseek-r1",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        
        # 获取摘要
        summary = response.choices[0].message.content
        
        # 清理摘要文本
        summary = summary.strip()
        
        return True, summary
        
    except Exception as e:
        error_msg = f"生成摘要时出错: {str(e)}"
        logger.error(error_msg)
        return False, error_msg


if __name__ == "__main__":
    # 从标准输入读取内容
    content = sys.stdin.read()
    
    # 生成摘要
    success, result = summarize(content)
    
    # 输出到标准输出
    if success:
        print(result)
    else:
        sys.exit(1)  # 如果失败，返回非零退出码
