# 玄光 (XuraLight)

<div align="center">
  <img src="media/xura.jpeg" alt="玄光 Logo" width="200" style="background: transparent; mix-blend-mode: multiply;"/>
</div>

## 项目简介

玄光对甄选信息生成每日摘要，通过微信公众号推送。助您在通勤间隙"听"见世界的深度。

愿破茧者执此光刃，劈开字节浇筑的囹圄，在信息迷雾中照亮求真之路。

**本项目代码完全由cursor自动编写完成。**

## 主要功能

- 🔍 每日自动抓取Hacker News和量子位的最新内容
- 🤖 AI 生成智能摘要
- 📱 自动发布到微信公众号“烛幽阁”

欢迎关注微信公众号 ​​“烛幽阁”​​，“收听”每日精选新闻摘要。私信添加更多信息源，一起对抗信息茧房！
<div align="center">
  <img src="media/zhuyouge.jpg" alt="烛幽阁 Logo" width="200" style="background: transparent; mix-blend-mode: multiply;"/>
</div>


## 安装步骤

1. 克隆项目
```bash
git clone https://github.com/yourusername/xuralight.git
cd xuralight
```

2. 安装依赖
```bash
pip install -r requirements.txt
```

3. 配置环境变量
```bash
# OpenAI API 配置
export TENCENT_LLM_API_KEY="your_api_key_here"

# 微信公众号配置
export WECHAT_APP_ID="your_app_id_here"
export WECHAT_APP_SECRET="your_app_secret_here"
```

## 运行方式

1. 初始化数据库
```bash
python src/db.py
```

2. 启动服务
```bash
python src/service.py start
```

3. 查看服务状态
```bash
python src/service.py status
```

4. 停止服务
```bash
python src/service.py stop
```

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件