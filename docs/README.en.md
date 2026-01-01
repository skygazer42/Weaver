# Weaver - AI Agent Platform

<div align="right">
  <details>
    <summary>🌐 Language / 语言</summary>
    <div>  
      <div align="center">
        <strong>English</strong> | <a href="../README.md">简体中文</a>
      </div>
    </div>
  </details>
</div>

<div align="center">

**Open-source AI Agent platform with Deep Research, Code Execution, Browser Automation, and Generative UI capabilities.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Node.js 18+](https://img.shields.io/badge/node-18+-green.svg)](https://nodejs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-purple.svg)](https://github.com/langchain-ai/langgraph)

[Demo](https://weaver-demo.vercel.app) · [Documentation](docs/) · [Report Bug](https://github.com/skygazer42/weaver/issues) · [Request Feature](https://github.com/skygazer42/weaver/issues)

<img src="docs/images/dashboard.png" alt="Weaver Dashboard" width="100%" style="border-radius: 8px; margin-top: 20px;" />

</div>

---

## ✨ Highlights

- 🔍 **Smart Routing** - LLM-based intelligent query routing (Direct/Web/Agent/Deep Search)
- 🧠 **Deep Research** - Multi-epoch iterative research with parallel search and content analysis
- 💻 **Code Execution** - Sandboxed Python interpreter with visualization support (E2B)
- 🌐 **Browser Automation** - Full Chromium control with screenshots (Playwright + E2B)
- 🖥️ **Desktop Automation** - Mouse, keyboard, and screen control (PyAutoGUI)
- 📊 **Document Generation** - Excel spreadsheets and PowerPoint presentations
- 🔄 **Trigger System** - Scheduled, Webhook, and Event-based automation
- 🎤 **Voice I/O** - Speech recognition (ASR) and text-to-speech (TTS)
- 🛑 **Cancellable Tasks** - Real-time task cancellation with token-based tracking
- 🎨 **Generative UI** - Real-time event streaming with artifacts

## 📋 Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Tool Reference](#tool-reference)
- [Development](#development)
- [Deployment](#deployment)
- [Documentation](#documentation)
- [Roadmap](#roadmap)

## 🚀 Features

### Core Capabilities

| Feature | Description | Status |
|---------|-------------|--------|
| **Smart Router** | LLM-based query classification with confidence thresholds | ✅ |
| **Deep Search** | Multi-step research with parallel search and content scraping | ✅ |
| **Code Execution** | Python interpreter in E2B sandbox with matplotlib, pandas, numpy | ✅ |
| **Browser Automation** | Playwright-based browser control with real-time screenshots | ✅ |
| **Desktop Automation** | Mouse, keyboard, and screen control via PyAutoGUI | ✅ |
| **Task Management** | Structured task tracking with progress visualization | ✅ |
| **Trigger System** | Scheduled (Cron), Webhook, and Event-based triggers | ✅ |
| **MCP Integration** | Model Context Protocol tool bridge for extensibility | ✅ |
| **Voice I/O** | ASR (DashScope Paraformer) + TTS (DashScope Sambert) | ✅ |
| **Cancellation** | Token-based task cancellation with graceful shutdown | ✅ |
| **Memory** | Long-term memory with PostgreSQL/Redis store + Mem0 | ✅ |

### Tool Categories

```
🔧 Sandbox Tools (E2B)
├── Browser Automation
│   ├── sb_browser_navigate        # Navigate to URL
│   ├── sb_browser_click           # Click elements
│   ├── sb_browser_type            # Type text
│   ├── sb_browser_screenshot      # Capture screenshots
│   └── sb_browser_get_html        # Extract page content
├── File Operations
│   ├── sandbox_create_file        # Create files
│   ├── sandbox_read_file          # Read content
│   ├── sandbox_str_replace        # Find/replace
│   └── sandbox_download_file      # Download as Base64
├── Shell & Packages
│   ├── sandbox_execute_command    # Run shell commands
│   ├── sandbox_install_package    # Install npm/pip/apt packages
│   └── sandbox_expose_port        # Expose ports for web apps
└── Document Generation
    ├── sandbox_create_spreadsheet # Create Excel/CSV files
    └── sandbox_create_presentation # Create PowerPoint slides

🖥️ Desktop Tools
├── computer_move_mouse            # Move cursor
├── computer_click                 # Mouse click
├── computer_type                  # Keyboard input
├── computer_screenshot            # Screen capture
└── task_list                      # Task management

🌐 Search & Crawl
├── web_search                     # Tavily API search
├── sandbox_web_search             # Visual web search with screenshots
└── crawl                          # URL content extraction

💻 Code Execution
└── execute_python_code            # Sandboxed Python interpreter
```

## ⚡ Quick Start

### Prerequisites

- **Python 3.11+** - [Download](https://www.python.org/downloads/)
- **Node.js 18+** - [Download](https://nodejs.org/)
- **Docker & Docker Compose** - [Install](https://docs.docker.com/get-docker/)

### 1️⃣ Clone & Setup

```bash
git clone https://github.com/skygazer42/weaver.git
cd weaver

# Copy environment template
cp .env.example .env
```

### 2️⃣ Configure API Keys

Edit `.env` with your API keys:

```bash
# Required
OPENAI_API_KEY=sk-...                    # https://platform.openai.com/api-keys
TAVILY_API_KEY=tvly-...                   # https://tavily.com
E2B_API_KEY=e2b_...                       # https://e2b.dev

# Optional (choose one or more)
ANTHROPIC_API_KEY=sk-ant-...              # Claude models
GOOGLE_API_KEY=...                        # Gemini models
DASHSCOPE_API_KEY=sk-...                  # Qwen models + TTS/ASR

# Optional Features
ENABLE_MEMORY=false                       # Long-term memory
MEM0_API_KEY=...                          # Mem0 memory service
ENABLE_MCP=false                          # MCP tool servers
```

### 3️⃣ Install Dependencies

```bash
# Backend
pip install -r requirements.txt

# Frontend
cd web
pnpm install
cd ..

# Optional: Browser automation
pip install playwright
playwright install chromium

# Optional: Desktop automation
pip install pyautogui pillow
```

### 4️⃣ Start Services

```bash
# Terminal 1: Start backend
python main.py

# Terminal 2: Start frontend
cd web
pnpm run dev
```

**Access points:**
- 🌐 **Web UI**: http://localhost:3000
- 🔌 **Backend API**: http://localhost:8000
- 📖 **API Docs**: http://localhost:8000/docs

## 🏗️ Architecture

### Project Structure

```
weaver/
├── agent/                          # LangGraph Agent Logic
│   ├── graph.py                    # Workflow graph (nodes + edges)
│   ├── nodes.py                    # Agent nodes (route, plan, search, write)
│   ├── smart_router.py             # LLM-based query routing
│   ├── deepsearch.py               # Multi-epoch deep research
│   ├── agent_prompts.py            # System prompts
│   ├── agent_tools.py              # Tool builder
│   ├── context_manager.py          # Token counting & truncation
│   ├── events.py                   # Event emission system
│   └── state.py                    # State definitions
│
├── tools/                          # Tool Implementations
│   ├── sandbox/                    # E2B sandbox tools
│   │   ├── browser_tools.py        # Browser automation
│   │   ├── browser_session.py      # Session management
│   │   ├── web_search_tool.py      # Visual web search
│   │   ├── files_tool.py           # File operations
│   │   ├── shell_tool.py           # Shell commands
│   │   ├── sheets_tool.py          # Excel generation
│   │   ├── presentation_tool.py    # PowerPoint generation
│   │   └── vision_tool.py          # Image processing (OCR, resize)
│   ├── computer_use_tool.py        # Desktop automation
│   ├── task_list_tool.py           # Task management
│   ├── screenshot_service.py       # Screenshot storage
│   ├── crawl_tools.py              # URL crawling
│   ├── asr.py                      # Speech recognition
│   ├── tts.py                      # Text-to-speech
│   ├── mcp.py                      # MCP integration
│   └── registry.py                 # Tool registry
│
├── triggers/                       # Trigger System
│   ├── models.py                   # Trigger data models
│   ├── manager.py                  # Trigger lifecycle management
│   ├── scheduler.py                # Cron-based scheduler
│   └── webhook.py                  # Webhook handlers
│
├── common/                         # Shared Utilities
│   ├── config.py                   # Settings & environment
│   ├── logger.py                   # Structured logging
│   ├── metrics.py                  # Performance metrics
│   ├── cancellation.py             # Task cancellation
│   └── agents_store.py             # Agent profile storage
│
├── web/                            # Next.js Frontend
│   ├── app/                        # App router pages
│   ├── components/                 # React components
│   │   ├── chat/                   # Chat interface
│   │   ├── views/                  # Discover, Library
│   │   └── settings/               # Settings dialog
│   ├── hooks/                      # React hooks
│   │   ├── useChatStream.ts        # SSE streaming
│   │   └── useChatHistory.ts       # LocalStorage history
│   └── lib/                        # Utilities
│
├── main.py                         # FastAPI entry point
├── docker/                         # Docker configuration
│   ├── docker-compose.yml          # Service orchestration
│   └── Dockerfile                  # Container image
└── .env.example                    # Environment template
```

### Tech Stack

| Layer | Technology | Version |
|-------|------------|---------|
| **Frontend** | Next.js | 14.2+ |
| | Tailwind CSS | 3.4+ |
| | Shadcn UI | Latest |
| | Vercel AI SDK | 3.x |
| **Backend** | Python | 3.11+ |
| | FastAPI | 0.110+ |
| | LangGraph | 0.2+ |
| | LangChain | 0.2+ |
| **Database** | PostgreSQL | 15+ |
| | pgvector | 0.5+ |
| **Sandbox** | E2B | Latest |
| **Search** | Tavily API | v1 |
| **Desktop** | PyAutoGUI | 0.9+ |
| | Pillow | 10.0+ |
| **Browser** | Playwright | 1.40+ |
| **Voice** | DashScope | Latest |

### Agent Execution Flow

```mermaid
graph TD
    A[User Query] --> B[Smart Router]
    B --> C{Route Decision}
    C -->|direct| D[Direct Answer]
    C -->|web| E[Web Search Plan]
    C -->|agent| F[Tool Agent]
    C -->|deep| G[Deep Search]
    C -->|clarify| H[Clarify Node]

    E --> I[Parallel Search]
    I --> J[Writer Node]
    J --> K[Evaluator]
    K -->|pass| L[Complete]
    K -->|revise| M[Refine Plan]
    M --> I

    G --> N[Multi-Epoch Research]
    N --> O[Query Generation]
    O --> P[Parallel Search]
    P --> Q[Summarization]
    Q --> R{More Epochs?}
    R -->|yes| O
    R -->|no| L

    F --> S[Tool Execution]
    S --> L

    D --> L
    H --> T[User Response]
```

## ⚙️ Configuration

### Environment Variables

#### Core Settings

```bash
# API Keys
OPENAI_API_KEY=sk-...                     # OpenAI API key
OPENAI_BASE_URL=https://api.openai.com/v1 # Optional: Custom endpoint
TAVILY_API_KEY=tvly-...                   # Tavily search API
E2B_API_KEY=e2b_...                       # E2B sandbox API

# Models
PRIMARY_MODEL=gpt-4o                      # Main LLM model
REASONING_MODEL=o1-mini                   # Planning/reasoning model

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/weaver

# Memory
MEMORY_STORE_BACKEND=postgres             # postgres|redis|memory
MEMORY_STORE_URL=postgresql://...         # Store connection URL
ENABLE_MEMORY=false                       # Enable Mem0 integration
MEM0_API_KEY=...                          # Mem0 API key (optional)

# Features
ENABLE_MCP=false                          # MCP tool servers
DEBUG=false                               # Debug mode
TOOL_APPROVAL=false                       # Require approval for tools
HUMAN_REVIEW=false                        # Require review before completion
MAX_REVISIONS=2                           # Max report revision iterations
```

#### Advanced Settings

```bash
# Context Management
CONTEXT_MAX_TOKENS=128000                 # Token limit per request
CONTEXT_TRUNCATION_STRATEGY=smart         # smart|fifo|middle

# Search
TOOL_RETRY=true                           # Retry failed tool calls
TOOL_RETRY_MAX_ATTEMPTS=3                 # Max retry attempts
TOOL_RETRY_BACKOFF=exponential            # exponential|linear|constant

# Performance
OPENAI_TIMEOUT=120                        # API timeout (seconds)
ENABLE_PROMETHEUS=false                   # Prometheus metrics
CORS_ORIGINS=http://localhost:3000        # CORS allowed origins

# Voice
DASHSCOPE_API_KEY=sk-...                  # DashScope for TTS/ASR

# Logging
LOG_LEVEL=INFO                            # DEBUG|INFO|WARNING|ERROR
ENABLE_FILE_LOGGING=true                  # Log to files
LOG_FILE=logs/weaver.log                  # Log file path
```

### Agent Profiles

Configure agent tools in `data/agents.json`:

```json
{
  "id": "default",
  "name": "Weaver Default Agent",
  "description": "Default tool-using agent",
  "system_prompt": "You are a helpful AI assistant...",
  "model": "gpt-4o",
  "enabled_tools": {
    "web_search": true,
    "browser": false,
    "sandbox_browser": true,
    "sandbox_web_search": true,
    "sandbox_files": true,
    "sandbox_shell": true,
    "sandbox_sheets": true,
    "sandbox_presentation": true,
    "sandbox_vision": true,
    "python": true,
    "crawl": true,
    "task_list": true,
    "computer_use": false,
    "mcp": true
  },
  "metadata": {
    "protected": true
  }
}
```

**Built-in Agent Profiles:**
- `default` - Basic tools (web search, browser, python, crawl)
- `manus` - Full-featured (all sandbox tools, documents, desktop)

### Context Management

```python
from agent.core.context_manager import ContextManager

manager = ContextManager(
    model_name="gpt-4o",
    max_tokens=128000,
    truncation_strategy="smart"  # smart|fifo|middle
)

# Automatically truncate messages
truncated_messages = manager.truncate_messages(messages)
```

**Truncation Strategies:**
- `smart` - Keep system + first/last messages, truncate middle (default)
- `fifo` - First In First Out, remove oldest messages
- `middle` - Keep start and end, remove middle messages

### Trigger System

Create automated agent workflows:

```python
from triggers import TriggerManager, ScheduledTrigger, WebhookTrigger

manager = TriggerManager()

# Scheduled trigger (Cron)
trigger = ScheduledTrigger(
    name="hourly_report",
    agent_id="default",
    task="Generate hourly status report",
    schedule="0 * * * *",  # Every hour
    timezone="Asia/Shanghai",
    run_immediately=False
)
await manager.add_trigger(trigger)

# Webhook trigger
webhook = WebhookTrigger(
    name="github_webhook",
    agent_id="default",
    task="Process GitHub webhook: {payload.action}",
    http_methods=["POST"],
    require_auth=True,
    rate_limit=100  # requests per hour
)
await manager.add_trigger(webhook)
```

## 📡 API Reference

### Chat Endpoint

**POST** `/api/chat`

Start a new chat session with streaming response.

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "Search for latest AI news"}
  ],
  "stream": true,
  "model": "gpt-4o",
  "search_mode": "deep",  // direct|web|agent|deep
  "agent_id": "default",
  "user_id": "user_123",
  "images": [
    {
      "name": "screenshot.png",
      "mime": "image/png",
      "data": "base64_encoded_data"
    }
  ]
}
```

**Response (SSE):**
```
0:{"type":"status","data":{"text":"Initializing...","step":"init"}}
0:{"type":"text","data":{"content":"Hello"}}
0:{"type":"tool","data":{"name":"web_search","status":"running"}}
0:{"type":"screenshot","data":{"url":"...","image":"data:image/png;base64,..."}}
0:{"type":"artifact","data":{"id":"...","type":"chart","content":"..."}}
0:{"type":"done","data":{"timestamp":"..."}}
```

**SSE Event Types:**

| Event | Description | Data Fields |
|-------|-------------|-------------|
| `status` | Status update | `text`, `step` |
| `text` | Text chunk | `content` |
| `message` | Full message | `content` |
| `tool` | Tool execution | `name`, `status`, `query` |
| `tool_start` | Tool started | `tool_name`, `args` |
| `tool_result` | Tool completed | `tool_name`, `result` |
| `tool_error` | Tool failed | `tool_name`, `error` |
| `screenshot` | Screenshot available | `url`, `image` |
| `task_update` | Task status changed | `task_id`, `status`, `progress` |
| `artifact` | Artifact generated | `id`, `type`, `title`, `content` |
| `completion` | Final report | `content` |
| `interrupt` | Requires approval | `thread_id`, `prompts` |
| `cancelled` | Task cancelled | `message` |
| `error` | Error occurred | `message` |
| `done` | Stream completed | `timestamp`, `metrics` |

### Cancel Endpoint

**POST** `/api/chat/cancel/{thread_id}`

Cancel a running chat task.

**Request:**
```json
{
  "reason": "User requested cancellation"
}
```

**Response:**
```json
{
  "status": "cancelled",
  "thread_id": "thread_abc123",
  "reason": "User requested cancellation",
  "timestamp": "2025-01-01T00:00:00"
}
```

### Resume Interrupt

**POST** `/api/interrupt/resume`

Resume after tool approval interrupt.

**Request:**
```json
{
  "thread_id": "thread_abc123",
  "payload": {
    "tool_approved": true,
    "tool_calls": [...]
  },
  "model": "gpt-4o",
  "search_mode": "agent"
}
```

### Screenshot API

**GET** `/api/screenshots/{filename}`

Retrieve a screenshot by filename.

**Response:** Image file (PNG/JPEG)

**GET** `/api/screenshots?thread_id=thread_123&limit=50`

List screenshots for a thread.

**Response:**
```json
{
  "screenshots": [
    {
      "filename": "screenshot_1234567890.png",
      "thread_id": "thread_123",
      "url": "/api/screenshots/screenshot_1234567890.png",
      "created_at": "2025-01-01T00:00:00"
    }
  ],
  "count": 1
}
```

### Trigger API

**GET** `/api/triggers`

List all triggers.

**Query Parameters:**
- `trigger_type` - Filter by type (scheduled|webhook|event)
- `status` - Filter by status (active|paused|error)
- `user_id` - Filter by user

**POST** `/api/triggers/scheduled`

Create scheduled trigger.

**Request:**
```json
{
  "name": "daily_summary",
  "description": "Generate daily summary report",
  "schedule": "0 9 * * *",
  "agent_id": "default",
  "task": "Generate daily summary",
  "timezone": "Asia/Shanghai",
  "run_immediately": false
}
```

**POST** `/api/triggers/webhook`

Create webhook trigger.

**Request:**
```json
{
  "name": "github_webhook",
  "agent_id": "default",
  "task": "Process: {payload.action}",
  "http_methods": ["POST"],
  "require_auth": true,
  "rate_limit": 100
}
```

**Response:**
```json
{
  "success": true,
  "trigger_id": "trigger_abc123",
  "endpoint": "/api/webhook/trigger_abc123",
  "auth_token": "secret_token_xyz"  // if require_auth=true
}
```

### Voice API

**POST** `/api/asr/recognize`

Speech recognition (ASR).

**Request:**
```json
{
  "audio_data": "base64_encoded_audio",
  "format": "wav",
  "sample_rate": 16000,
  "language_hints": ["zh", "en"]
}
```

**Response:**
```json
{
  "success": true,
  "text": "Transcribed text here",
  "metrics": {
    "duration_ms": 123
  }
}
```

**POST** `/api/tts/synthesize`

Text-to-speech (TTS).

**Request:**
```json
{
  "text": "Hello, how can I help you?",
  "voice": "longxiaochun"  // See /api/tts/voices for options
}
```

**Response:**
```json
{
  "success": true,
  "audio": "base64_encoded_mp3",
  "format": "mp3",
  "voice": "longxiaochun"
}
```

## 🛠️ Tool Reference

### Complete Tool List

See [TOOL_REFERENCE.md](docs/TOOL_REFERENCE.md) for detailed tool documentation.

**Quick Reference:**

- **Sandbox Browser**: `sb_browser_*` (11 tools)
- **Sandbox Files**: `sandbox_*_file` (8 tools)
- **Sandbox Shell**: `sandbox_*_command`, `sandbox_install_package` (5 tools)
- **Sandbox Sheets**: `sandbox_*_spreadsheet` (7 tools)
- **Sandbox Presentation**: `sandbox_*_presentation`, `sandbox_*_slide` (8 tools)
- **Sandbox Vision**: `sandbox_*_image`, `sandbox_extract_text` (7 tools)
- **Computer Use**: `computer_*` (9 tools)
- **Task Management**: `create_tasks`, `view_tasks`, `update_task` (4 tools)
- **Search & Crawl**: `web_search`, `crawl` (2 tools)
- **Code**: `execute_python_code` (1 tool)

**Total: 62 tools**

## 🧪 Development

### Run Tests

```bash
# Smoke test (API endpoints)
python test_api_endpoints.py

# Deep search routing test
python scripts/test_deep_search_routing.py

# Unit tests
pytest tests/ -v

# Specific test
pytest tests/test_smoke_api.py -q
```

### Code Style

```bash
# Format
black . --line-length 120
isort . --profile black

# Lint
ruff check .

# Type check
mypy agent/ tools/ common/
```

### Debug Mode

Enable debug logging:

```bash
# .env
DEBUG=true
LOG_LEVEL=DEBUG
ENABLE_FILE_LOGGING=true
```

View logs:
```bash
tail -f logs/weaver.log
tail -f logs/threads/{thread_id}.log
```

### Local Development

```bash
# Backend only (with auto-reload)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend only
cd web
pnpm run dev

# Database
docker-compose -f docker/docker-compose.yml up postgres -d
```

## 🚢 Deployment

### Docker

**Build:**
```bash
docker build -t weaver-backend .
```

**Run:**
```bash
docker run -p 8000:8000 \
  --env-file .env \
  --name weaver \
  weaver-backend
```

### Docker Compose (Full Stack)

```bash
# Start all services
docker-compose -f docker/docker-compose.yml up -d

# View logs
docker-compose -f docker/docker-compose.yml logs -f

# Stop
docker-compose -f docker/docker-compose.yml down
```

**Services:**
- `postgres` - PostgreSQL database (port 5432)
- `redis` - Redis cache (port 6379)
- `backend` - FastAPI backend (port 8000)
- `web` - Next.js frontend (port 3000)

### Vercel (Frontend)

```bash
cd web
vercel deploy --prod
```

**Environment Variables (Vercel):**
- `NEXT_PUBLIC_API_URL` - Backend API URL

### Railway/Render (Backend)

**Start Command:**
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Environment:**
- Set all required API keys
- Add PostgreSQL database addon
- Set `DATABASE_URL` automatically

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [MANUS_AGENT_EXTRACTION_PROGRESS.md](docs/MANUS_AGENT_EXTRACTION_PROGRESS.md) | Feature extraction from Manus (92% complete) |
| [AGENT_VISUAL_IMPLEMENTATION_PLAN.md](docs/AGENT_VISUAL_IMPLEMENTATION_PLAN.md) | Visual agent implementation plan |
| [MANUS_FEATURE_ANALYSIS.md](docs/MANUS_FEATURE_ANALYSIS.md) | Manus feature comparison and analysis |
| [FRONTEND_INTEGRATION.md](docs/FRONTEND_INTEGRATION.md) | Frontend SSE integration guide |
| [DEEP_SEARCH_ROUTING_ANALYSIS.md](docs/DEEP_SEARCH_ROUTING_ANALYSIS.md) | Deep search routing flow analysis |
| [DEEP_SEARCH_TROUBLESHOOTING.md](docs/DEEP_SEARCH_TROUBLESHOOTING.md) | Deep search diagnostic guide |
| [DEBUG_ALIGNMENT_ISSUE.md](docs/DEBUG_ALIGNMENT_ISSUE.md) | Message alignment debugging guide |
| [TOOL_REFERENCE.md](docs/TOOL_REFERENCE.md) | Complete tool documentation |

## 🗺️ Roadmap

### ✅ Completed (v0.9 - 92%)

**Core Agent System**
- [x] LangGraph workflow engine
- [x] Smart query routing with LLM classification
- [x] Context management (token counting, truncation)
- [x] Event streaming (SSE)
- [x] Task cancellation system
- [x] Multi-agent profiles (GPTs-like)

**Search & Research**
- [x] Deep Search (multi-epoch iterative research)
- [x] Smart Router (confidence-based routing)
- [x] Parallel search with deduplication
- [x] Result aggregation with ranking
- [x] Web search (Tavily API)
- [x] Visual web search (screenshots)
- [x] URL crawling

**Code Execution**
- [x] Python interpreter (E2B sandbox)
- [x] Matplotlib, pandas, numpy support
- [x] Visualization artifacts

**Browser Automation**
- [x] Playwright integration
- [x] E2B browser sandbox
- [x] Real-time screenshots
- [x] Session management
- [x] Element interaction (click, type, scroll)

**Desktop Automation**
- [x] Mouse control (PyAutoGUI)
- [x] Keyboard input
- [x] Screen capture
- [x] Hotkey support

**Document Generation**
- [x] Excel spreadsheets (openpyxl)
- [x] PowerPoint presentations (python-pptx)
- [x] CSV export
- [x] Charts and formatting

**Image Processing**
- [x] OCR text extraction (Tesseract)
- [x] Image resize/crop/convert
- [x] QR code reading
- [x] Image comparison

**File & Shell**
- [x] Sandbox file operations (CRUD)
- [x] Shell command execution
- [x] Package installation (npm/pip/apt)
- [x] Port exposure for web apps

**Trigger System**
- [x] Scheduled triggers (Cron)
- [x] Webhook triggers
- [x] Event-based triggers
- [x] Trigger management UI

**Voice I/O**
- [x] Speech recognition (ASR - DashScope Paraformer)
- [x] Text-to-speech (TTS - DashScope Sambert)
- [x] Multiple voice options

**Memory & Storage**
- [x] Short-term memory (checkpointer)
- [x] Long-term memory (PostgreSQL/Redis store)
- [x] Mem0 integration
- [x] Chat history persistence

**Other**
- [x] MCP integration
- [x] Task management
- [x] Prometheus metrics (optional)
- [x] Structured logging
- [x] Docker deployment

### 🚧 In Progress (v1.0)

**Frontend**
- [ ] Message alignment fixes for Deep Research
- [ ] Artifact gallery view
- [ ] Advanced search filters
- [ ] Theme customization

**Backend**
- [ ] Agent runs persistence (database)
- [ ] Advanced image editing (filters, effects)
- [ ] Web development scaffolding
- [ ] Deploy to Vercel/Netlify from sandbox

### 🔮 Future Plans

We are continuously improving Weaver. Feel free to contribute or suggest new features!

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Quick Start:**
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

**Development Setup:**
```bash
# Clone your fork
git clone https://github.com/skygazer42/weaver.git
cd weaver

# Install dependencies
pnpm run install:all

# Create .env
cp .env.example .env

# Start development
pnpm run dev
```

**Code Standards:**
- Follow PEP 8 for Python
- Use Black for formatting
- Add type hints
- Write tests for new features
- Update documentation

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Inspired by**: [Manus](https://manus.im) - The best AI agent platform
- **Built with**: [LangGraph](https://github.com/langchain-ai/langgraph) - Agent orchestration
- **Powered by**: [E2B](https://e2b.dev) - Code execution sandbox
- **Search**: [Tavily](https://tavily.com) - AI-optimized search API
- **UI Components**: [Shadcn UI](https://ui.shadcn.com) - Beautiful React components

## 📞 Contact & Support

- **Issues**: [GitHub Issues](https://github.com/skygazer42/weaver/issues)
- **Discussions**: [GitHub Discussions](https://github.com/skygazer42/weaver/discussions)
- **Twitter**: [@WeaverAI](https://twitter.com/WeaverAI)
- **Discord**: [Join our community](https://discord.gg/weaver)

---

<div align="center">

**[⬆ Back to Top](#weaver---ai-agent-platform)**

Made with ❤️ by the Weaver Team

</div>
