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

如果文章内容是提示需要启用JavaScript才能使用,请仅返回文章内容的中文翻译,和“本文需要启用JavaScript才能使用”,不要包含其他内容。

如果文章是论文，请在摘要中包含论文主要针对什么行业/技术，用了什么方法，解决了什么问题，有什么前景。

输出字数限制在250字内。
"""

# 加载prompt模板
PROMPT_COMMENTS =  """{comments_content}
请归纳总结前面文章的评论，用自然语言列举其中的主要观点以及支持和反对这些观点的主要论据。
输出格式如下：

观点1,支持方，反对方；
观点2,支持方，反对方；
......

输出字数限制在200字内。
"""

def summarize(
    content: str,
    comments: str = "",
) -> Tuple[bool, str]:
    """
    生成文章摘要
    
    Args:
        content: 文章内容
        comments: 评论内容（可选）
    
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
        
        # 如果有评论内容，生成评论总结
        if comments and comments.strip():
            logger.info("开始生成评论总结")
            comments_prompt = PROMPT_COMMENTS.format(comments_content=comments)
            
            comments_response = client.chat.completions.create(
                model="deepseek-r1",
                messages=[
                    {"role": "user", "content": comments_prompt}
                ],
                temperature=0
            )
            
            # 获取评论总结
            comments_summary = comments_response.choices[0].message.content.strip()
            
            # 将评论总结添加到文章摘要后面
            summary = f"{summary}\n\n评论总结：\n{comments_summary}"
            logger.info("评论总结生成完成")
        
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
