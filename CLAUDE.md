# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

XuraLight (玄光) is a Python-based automated news aggregation and summarization system that crawls content from multiple sources (Hacker News, QbitAI), generates AI-powered summaries using ZhipuAI's GLM-4.7 model, and publishes formatted reports to WeChat Official Accounts. It runs as a daemon service with scheduled daily operations.

## Common Commands

### Service Management
```bash
# Initialize database (first time setup)
python src/db.py

# Start the daemon service (default daily time: 05:00)
python src/service.py start

# Start with custom schedule
python src/service.py start --daily-time 08:00

# Start with debug logging
python src/service.py start --debug

# Check service status
python src/service.py status

# Stop the service
python src/service.py stop
```

### Manual Processing
```bash
# Process all active sources manually
python src/aggregator.py

# Process with article limit (for testing)
python src/aggregator.py -n 5

# Process with debug mode (saves raw text to temp/)
python src/aggregator.py -d
```

### Dependencies
```bash
# Install dependencies
pip install -r requirements.txt
```

## Architecture

### Data Flow
The system follows a pipeline architecture:

1. **Service Daemon** (`service.py`) - Manages scheduling, runs daily tasks at configured time
2. **Aggregator** (`aggregator.py`) - Orchestrates the entire processing pipeline per source
3. **Crawlers** (source-specific scripts in `src/`) - Fetch article metadata via subprocess
4. **Content Processor** - Downloads articles, extracts text from HTML/PDF, fetches comments
5. **Summarizer** (`summarizer_agent.py`) - Generates summaries using ZhipuAI GLM-4.7
6. **Report Generator** (`generate_reports.py`) - Creates Markdown reports with concatenated audio
7. **Publisher** (`publish_report.py`) - Publishes to WeChat Official Account API

### Key Components

**service.py** - Main daemon with PID file management (`xura_service.pid`), rotating logs (`service.log`, 10MB max, 5 backups), and Clash proxy dependency validation. Uses `schedule` library for daily task execution.

**aggregator.py** - Core orchestrator that:
- Executes crawler scripts via subprocess in `src/` directory
- Downloads content with retry logic and proxy fallback (localhost:7890)
- Extracts text from HTML/PDF using `html2text` and `PyPDF2`
- Fetches HackerNews comments via Algolia API (`download_hackernews_comments()`)
- Enforces `MAX_SUMMARY_TEXT_LENGTH = 120000` characters
- Saves summaries to `abstraction/{source_name}/{YYYYMMDD}/` hierarchy

**summarizer_agent.py** - AI service using ZhipuAI's GLM-4.7 model (previously used Tencent LLM, code is commented out). Uses dual prompts: `PROMPT` for articles (250 char limit) and `PROMPT_COMMENTS` for comments (200 char limit).

**Database** (`src/db.py`) - SQLite database (`xura.db`) with three tables:
- `sources` - Source configuration with crawler commands and activation status
- `articles` - Article metadata with file paths and timestamps
- `reports` - Published report tracking

### Adding New Sources

1. Create a crawler script that outputs JSON to stdout:
```json
[
  {
    "title": "Article Title",
    "url": "https://...",
    "published_date": "2025-01-20T...",
    "comments_url": "https://..."
  }
]
```

2. Insert source into database:
```sql
INSERT INTO sources (name, crawler_command, actived, media_path)
VALUES ('SourceName', 'python src/crawler_source.py', 1, './media/source.jpg');
```

3. Place media file at specified path for WeChat cover image

### Environment Variables

Required:
- `ZHIPU_API_KEY` - ZhipuAI API key for GLM-4.7 model
- `WECHAT_APP_ID` - WeChat Official Account app ID
- `WECHAT_APP_SECRET` - WeChat Official Account app secret

Optional:
- Clash proxy on localhost:7890 (checked by service at startup)

### Directory Structure

- `abstraction/` - Generated summaries by source and date
- `reports/` - Published Markdown reports
- `audio/` - Audio report files (legacy, not actively used)
- `media/` - Source-specific cover images
- `temp/` - Debug raw text (only with `-d` flag)
- `src/` - All Python modules and crawler scripts

### Important Implementation Details

- Crawler commands are executed via `subprocess.run()` with `cwd=src_dir`
- Text length is capped at 120k characters before summarization to prevent API token exhaustion
- HackerNews comments are fetched via Algolia API, not HTML scraping
- Proxy fallback: tries direct request first, then localhost:7890 on failure
- File sanitization replaces unsafe filesystem characters with full-width equivalents
- Service runs as daemon with signal handling (SIGTERM, SIGINT, SIGHUP)
- Audio generation (`generate_audio=False`) is currently disabled

### Model Switching

The system has switched from Tencent LLM (deepseek-v3-0324) to ZhipuAI (glm-4.7). The old code is preserved in comments. To switch models, update the client initialization and model name in `summarizer_agent.py`.
