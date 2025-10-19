import subprocess
import threading
import schedule
import time
from datetime import datetime
import logging
import os
import sys
import signal
import argparse
import json
import atexit
import daemon
from daemon import pidfile
import pwd
import grp
import logging.handlers

from db import get_all_sources
from generate_reports import generate_report

# 服务配置
DEFAULT_DAILY_TIME = '05:00'  # 每日任务执行时间，格式为 HH:MM

# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(BASE_DIR, 'service.log')

# 创建一个日志格式化器
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 创建文件处理器
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(log_formatter)

# 创建控制台处理器
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

# 配置根日志记录器
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# 修改服务状态文件路径
PID_FILE = os.path.join(BASE_DIR, 'xura_service.pid')
STATUS_FILE = os.path.join(BASE_DIR, 'xura_service_status.json')

class ServiceExit(Exception):
    """用于优雅退出的自定义异常"""
    pass

def signal_handler(signum, frame):
    """信号处理函数"""
    raise ServiceExit

def save_service_status(status: dict):
    """保存服务状态"""
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(status, f)
    except Exception as e:
        logger.error(f"保存服务状态失败: {e}")

def load_service_status() -> dict:
    """加载服务状态"""
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"加载服务状态失败: {e}")
    return {}

def is_service_running() -> bool:
    """检查服务是否在运行"""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            # 检查进程是否存在
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, ValueError, OSError):
            # 进程不存在，清理PID文件
            try:
                os.remove(PID_FILE)
            except OSError:
                pass
    return False

def save_pid():
    """保存当前进程PID"""
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

def cleanup():
    """清理函数"""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        if os.path.exists(STATUS_FILE):
            os.remove(STATUS_FILE)
    except Exception as e:
        logger.error(f"清理文件失败: {e}")

def setup_logging(log_level=logging.INFO):
    """设置日志配置"""
    # 创建日志格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    
    # 获取项目根目录的绝对路径
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LOG_FILE = os.path.join(BASE_DIR, 'service.log')
    
    # 创建 RotatingFileHandler，限制单个日志文件大小为 10MB，保留 5 个备份
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 清除现有的处理器
    root_logger.handlers = []
    
    # 添加新的处理器
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    return root_logger

def run_aggregator(source):
    """运行聚合器"""
    try:
        logger.debug(f"准备处理源 {source['name']} (ID: {source['id']})")
        logger.debug(f"源配置信息: {source}")
        
        from aggregator import do
        logger.debug(f"开始调用 aggregator.do 函数处理源 {source['name']}")
        
        start_time = datetime.now()
        success = do(source['id'])
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        if success:
            logger.info(f"源 {source['name']} 处理成功，耗时 {duration:.2f} 秒")
            return True
        else:
            logger.error(f"源 {source['name']} 处理失败，耗时 {duration:.2f} 秒")
            return False
            
    except Exception as e:
        logger.exception(f"处理源时发生异常 ({source['name']})")
        return False

def daily_task():
    """每日任务：爬取数据并生成报告"""
    logger.info("开始执行每日任务")
    start_time = datetime.now()
    
    try:
        # 1. 获取所有激活的源
        logger.debug("正在获取所有激活的源信息...")
        sources = get_all_sources(only_actived=True)
        logger.debug(f"获取到 {len(sources) if sources else 0} 个激活的源")
        
        if not sources:
            logger.warning("没有找到任何源")
            return
            
        # 2. 对每个源运行聚合器
        for idx, source in enumerate(sources, 1):
            try:
                logger.debug(f"开始处理第 {idx}/{len(sources)} 个源: {source['name']}")
                success = run_aggregator(source)
                
                if not success:
                    logger.error(f"源 {source['name']} 的处理任务失败")
                    continue
                    
                logger.info(f"源 {source['name']} 的处理任务完成")
            except Exception as e:
                logger.error(f"处理源 {source['name']} 时发生异常: {e}")
                logger.exception("详细错误信息：")
                continue
            
    except Exception as e:
        logger.error(f"执行每日任务时发生异常: {e}")
        logger.exception("详细错误信息：")
    finally:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"每日任务执行完成，总耗时：{duration:.2f} 秒")

def schedule_task():
    """调度任务"""
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except ServiceExit:
            break

def run_daemon(daily_time=DEFAULT_DAILY_TIME):
    """在守护进程中运行服务"""
    try:
        # 保存PID
        save_pid()
        
        # 注册信号处理
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGHUP, signal_handler)
        
        # 设置每日任务执行时间
        schedule.every().day.at(daily_time).do(daily_task)
        logger.info(f"每日任务设置为 {daily_time} 执行")
        
        # 创建并启动调度线程
        schedule_thread = threading.Thread(target=schedule_task)
        schedule_thread.daemon = True
        schedule_thread.start()
        logger.info("调度服务已启动")
        
        # 显示下次执行时间
        next_run = schedule.next_run()
        logger.info(f"下次任务将在 {next_run.strftime('%Y-%m-%d %H:%M:%S')} 执行")
        
        # 保持主线程运行
        while True:
            try:
                time.sleep(60)  # 每分钟检查一次
                # 检查调度线程是否还活着
                if not schedule_thread.is_alive():
                    logger.error("调度线程已停止，重新启动...")
                    schedule_thread = threading.Thread(target=schedule_task)
                    schedule_thread.daemon = True
                    schedule_thread.start()
                    logger.info("调度线程已重新启动")
                
                # 检查下次运行时间
                next_run = schedule.next_run()
                if next_run:
                    logger.debug(f"下次任务将在 {next_run.strftime('%Y-%m-%d %H:%M:%S')} 执行")
                
            except Exception as e:
                logger.error(f"主循环发生错误: {e}")
                logger.exception("详细错误信息：")
                time.sleep(60)  # 发生错误时等待一分钟再继续
                continue
            
    except ServiceExit:
        logger.info("服务正在停止...")
    except Exception as e:
        logger.error(f"服务运行出错: {e}")
        logger.exception("详细错误信息：")
    finally:
        logger.info("服务正在清理资源...")
        cleanup()
        logger.info("服务已停止")
        sys.exit(1)

def check_clash_proxy():
    """检查 Clash 代理是否正常运行"""
    try:
        import clash_service
        if not clash_service.status():
            logger.error("Clash 代理服务未运行，请先启动 Clash 代理")
            return False
            
        # 测试代理连接
        import requests
        proxies = {
            "http": "http://localhost:7890",
            "https": "http://localhost:7890"
        }
        
        try:
            response = requests.get("https://www.google.com", proxies=proxies, timeout=5)
            response.raise_for_status()
            logger.info("Clash 代理连接测试成功")
            return True
        except Exception as e:
            logger.error(f"Clash 代理连接测试失败: {e}")
            return False
            
    except Exception as e:
        logger.error(f"检查 Clash 代理时出错: {e}")
        return False

def check_llm_api_key():
    """检查 LLM API key 是否已设置"""
    api_key = os.getenv("TENCENT_LLM_API_KEY")
    if not api_key:
        logger.error("未设置 TENCENT_LLM_API_KEY 环境变量")
        return False
        
    return True

def start_service(daily_time=DEFAULT_DAILY_TIME):
    """启动服务"""
    if is_service_running():
        print("服务已经在运行中")
        return False
        
    # 检查必要的依赖和配置
    logger.info("正在检查服务依赖...")
    
    # 1. 检查 Clash 代理
    if not check_clash_proxy():
        print("启动失败：Clash 代理未正确配置或未运行")
        return False
        
    # 2. 检查 LLM API key
    if not check_llm_api_key():
        print("启动失败：LLM API key 未正确配置")
        return False
    
    logger.info("所有依赖检查通过，开始启动服务...")
    
    # 获取当前用户
    uid = os.getuid()
    gid = os.getgid()
    
    # 设置工作目录为项目根目录
    work_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 确保日志文件所在目录存在
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    # 打开日志文件，确保它存在并可写
    log_file = open(LOG_FILE, 'a+')
    
    # 配置守护进程上下文
    context = daemon.DaemonContext(
        working_directory=work_dir,
        umask=0o002,
        pidfile=pidfile.TimeoutPIDLockFile(PID_FILE),
        detach_process=True,
        signal_map={
            signal.SIGTERM: signal_handler,
            signal.SIGINT: signal_handler,
            signal.SIGHUP: signal_handler
        },
        uid=uid,
        gid=gid,
        files_preserve=[
            log_file.fileno(),  # 保留日志文件描述符
            sys.stdout.fileno(),  # 保留标准输出
            sys.stderr.fileno()   # 保留标准错误
        ],
        stdout=log_file,  # 重定向标准输出到日志文件
        stderr=log_file,  # 重定向标准错误到日志文件
        prevent_core=True  # 防止生成核心转储文件
    )
    
    print(f"服务正在启动，每日任务将在 {daily_time} 执行")
    print(f"查看日志文件 {LOG_FILE} 获取详细信息")
    
    try:
        # 使用守护进程上下文运行服务
        with context:
            # 重新配置日志处理器
            logger.handlers = []  # 清除所有处理器
            file_handler = logging.FileHandler(LOG_FILE)
            file_handler.setFormatter(log_formatter)
            logger.addHandler(file_handler)
            
            # 运行守护进程
            run_daemon(daily_time)
    except Exception as e:
        logger.error(f"启动服务时出错: {e}")
        logger.exception("详细错误信息：")
        cleanup()
        sys.exit(1)

def stop_service():
    """停止服务"""
    if not is_service_running():
        print("服务未在运行")
        return
        
    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        # 发送终止信号
        os.kill(pid, signal.SIGTERM)
        
        # 等待进程结束
        max_wait = 10
        while max_wait > 0 and is_service_running():
            time.sleep(1)
            max_wait -= 1
        
        if is_service_running():
            print("服务未能正常停止，强制终止")
            os.kill(pid, signal.SIGKILL)
        else:
            print("服务已停止")
            
        cleanup()
        
    except Exception as e:
        print(f"停止服务时出错: {e}")
        sys.exit(1)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='文章聚合服务管理')
    parser.add_argument('action', choices=['start', 'stop', 'status'], help='启动、停止或查看服务状态')
    parser.add_argument('--debug', action='store_true', help='启用调试日志')
    parser.add_argument('--daily-time', 
                       default=DEFAULT_DAILY_TIME,
                       help=f'每日任务执行时间，格式为 HH:MM，默认为 {DEFAULT_DAILY_TIME}')
    
    args = parser.parse_args()
    
    try:
        if args.action == 'start':
            # 验证时间格式
            hour, minute = map(int, args.daily_time.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            
            # 设置日志级别
            log_level = logging.DEBUG if args.debug else logging.INFO
            setup_logging(log_level)
            
            if args.debug:
                logger.debug("调试模式已启用")
            
            # 保存配置到状态文件
            save_service_status({
                'daily_time': args.daily_time
            })
            
            start_service(daily_time=args.daily_time)
            
        elif args.action == 'stop':
            stop_service()
        elif args.action == 'status':
            if is_service_running():
                with open(PID_FILE, 'r') as f:
                    pid = f.read().strip()
                print(f"服务正在运行 (PID: {pid})")
                # 显示上次执行时间和下次执行时间
                status = load_service_status()
                if status:
                    print(f"每日任务执行时间: {status.get('daily_time', DEFAULT_DAILY_TIME)}")
            else:
                print("服务未运行")
    except ValueError:
        print("时间格式错误，请使用 HH:MM 格式，例如 05:00")
        sys.exit(1)

if __name__ == "__main__":
    main() 


# python src/service.py start
# python src/service.py stop
# python src/service.py start --daily-time 10:00
# python src/service.py start --debug