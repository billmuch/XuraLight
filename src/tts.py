import json
import requests
import time
import logging
import os
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.tts.v20190823 import tts_client, models

# 配置logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def text_to_speech(text, output_filename):
    """将文本转换为语音并保存为MP3文件"""
    try:
        # 实例化一个认证对象，入参需要传入腾讯云账户 SecretId 和 SecretKey
        secret_id = os.getenv("TENCENT_TTS_ID")
        secret_key = os.getenv("TENCENT_TTS_KEY")
        cred = credential.Credential(secret_id, secret_key)
        
        # 实例化一个http选项
        httpProfile = HttpProfile()
        httpProfile.endpoint = "tts.tencentcloudapi.com"
        
        # 实例化一个client选项
        clientProfile = ClientProfile()
        clientProfile.httpProfile = httpProfile
        
        # 实例化要请求产品的client对象
        client = tts_client.TtsClient(cred, "", clientProfile)
        
        # 实例化一个请求对象
        req = models.CreateTtsTaskRequest()
        params = {
            "Text": text[:800]  # 限制文本长度，腾讯云TTS有字数限制
        }
        
        # 如果文章被截断，logger用warning记录此事件
        if len(text) > 800:
            logger.warning(f"文本已被截断，原始长度: {len(text)}，截断后长度: 800")
            
        req.from_json_string(json.dumps(params))
        
        # 创建TTS任务
        resp = client.CreateTtsTask(req)
        
        # 从响应中获取TaskId
        task_id = json.loads(resp.to_json_string())["Data"]["TaskId"]
        
        # 实例化一个请求对象，用于查询任务状态
        status_req = models.DescribeTtsTaskStatusRequest()
        status_params = {
            "TaskId": task_id
        }
        status_req.from_json_string(json.dumps(status_params))
        
        # 轮询任务状态
        max_retries = 100
        retry_count = 0
        
        while retry_count < max_retries:
            resp = client.DescribeTtsTaskStatus(status_req)
            resp_data = json.loads(resp.to_json_string())["Data"]
            
            if resp_data.get("ErrorMsg"):
                logger.error(f"TTS任务失败: {resp_data['ErrorMsg']}")
                return False
                
            if resp_data.get("ResultUrl"):
                # 下载音频文件
                audio_resp = requests.get(resp_data["ResultUrl"])
                with open(output_filename, "wb") as f:
                    f.write(audio_resp.content)
                logger.info(f"语音文件已保存为 {output_filename}")
                return True
            else:
                logger.info(f"TTS任务正在处理，StatusStr: {resp_data['StatusStr']}, 等待60秒后重试...")
                time.sleep(5)
                retry_count += 1
            time.sleep(60)
            retry_count += 1
        
        logger.error("TTS任务超时")
        return False
        
    except TencentCloudSDKException as err:
        logger.error(f"TTS转换失败: {err}")
        return False
    except Exception as e:
        logger.error(f"TTS处理过程中发生错误: {e}")
        return False 