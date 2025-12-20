# Weaver - AI Agent Platform

An open-source AI Agent platform with Deep Research, Code Execution, Browser Automation, and Generative UI capabilities. Inspired by Manus, built with LangGraph.

## Features

### Core Capabilities

| Feature | Description |
|---------|-------------|
| **Deep Search** | Multi-step research with parallel search, content scraping, and analysis |
| **Code Execution** | Python interpreter in E2B sandboxed environment with visualization support |
| **Browser Automation** | Playwright-based browser control with real-time screenshots |
| **Desktop Automation** | Mouse, keyboard, and screen control via PyAutoGUI |
| **Task Management** | Structured task tracking with progress visualization |
| **Trigger System** | Scheduled, Webhook, and Event-based agent triggers |
| **MCP Integration** | Model Context Protocol tool bridge for extensibility |

### Tool Categories

```
Sandbox Tools (E2B)
├── sandbox_browser      # Chromium browser automation
├── sandbox_web_search   # Visual web search with screenshots
├── sandbox_files        # File operations (CRUD, upload/download)
└── sandbox_shell        # Command execution, package installation

Desktop Tools
├── computer_use         # Mouse, keyboard, screenshots
└── task_list            # Task management and progress tracking

Search & Crawl
├── web_search           # Tavily API search
└── crawl                # URL content extraction

Code Execution
└── python               # Sandboxed Python interpreter
```

## Architecture

```
weaver/
├── agent/                  # LangGraph agent logic
│   ├── graph.py            # Workflow definitions
│   ├── nodes.py            # Agent nodes
│   ├── agent_prompts.py    # System prompts
│   ├── agent_tools.py      # Tool builder
│   ├── context_manager.py  # Token counting & message truncation
│   └── events.py           # Event emission system
│
├── tools/                  # Tool implementations
│   ├── sandbox_browser_tools.py      # Browser automation
│   ├── sandbox_browser_session.py    # Browser session management
│   ├── sandbox_web_search_tool.py    # Visual web search
│   ├── sandbox_files_tool.py         # File operations
│   ├── sandbox_shell_tool.py         # Shell commands
│   ├── computer_use_tool.py          # Desktop automation
│   ├── task_list_tool.py             # Task management
│   ├── screenshot_service.py         # Screenshot storage
│   ├── crawl_tools.py                # URL crawling
│   ├── mcp.py                        # MCP integration
│   └── registry.py                   # Tool registry
│
├── triggers/               # Trigger system
│   ├── models.py           # Trigger data models
│   ├── manager.py          # Trigger management
│   ├── scheduler.py        # Scheduled triggers
│   └── webhook.py          # Webhook handlers
│
├── web/                    # Next.js frontend
│   ├── app/                # App router pages
│   ├── components/         # React components
│   └── lib/                # Utilities
│
├── main.py                 # FastAPI entry point
├── config.py               # Configuration
└── docker-compose.yml      # Docker services
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Next.js 14, Tailwind CSS, Shadcn UI, Vercel AI SDK |
| **Backend** | Python 3.11+, FastAPI, LangGraph, LangChain |
| **Database** | PostgreSQL with pgvector |
| **Sandbox** | E2B (Code Execution, Browser) |
| **Search** | Tavily API |
| **Desktop** | PyAutoGUI, Pillow |
| **Browser** | Playwright |

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose

### 1. Environment Setup

```bash
cp .env.example .env
```

Required API keys:

| Key | Description | Get from |
|-----|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API | https://platform.openai.com/api-keys |
| `TAVILY_API_KEY` | Web search | https://tavily.com |
| `E2B_API_KEY` | Sandbox execution | https://e2b.dev |

Optional:

| Key | Description |
|-----|-------------|
| `ANTHROPIC_API_KEY` | Claude models |
| `GOOGLE_API_KEY` | Gemini models |
| `ENABLE_MEMORY=true` + `MEM0_API_KEY` | Long-term memory |
| `ENABLE_MCP=true` + `MCP_SERVERS` | MCP tool servers |

### 2. Install Dependencies

```bash
# All dependencies
npm run install:all

# Or backend only
pip install -r requirements.txt

# Optional: Desktop automation
pip install pyautogui pillow

# Optional: Browser automation
pip install playwright
playwright install chromium
```

### 3. Start Services

```bash
# Start database
docker-compose up postgres -d

# Run both backend and web
npm run dev

# Or separately:
# Backend: npm run dev:backend
# Web: npm run dev:web
```

Access points:
- Web UI: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Configuration

### Agent Profile

Configure tools in `agent_profile.enabled_tools`:

```json
{
  "enabled_tools": {
    "web_search": true,
    "crawl": true,
    "python": false,
    "browser": false,
    "sandbox_browser": true,
    "sandbox_web_search": true,
    "sandbox_files": true,
    "sandbox_shell": true,
    "sandbox_sheets": true,
    "sandbox_presentation": true,
    "sandbox_vision": true,
    "task_list": true,
    "computer_use": false,
    "mcp": true
  }
}
```

### Context Management

The context manager handles token limits automatically:

```python
from agent.context_manager import ContextManager

manager = ContextManager(
    model_name="gpt-4o",
    max_tokens=128000,
    truncation_strategy="smart"  # smart, fifo, or middle
)
```

### Trigger System

Create automated agent triggers:

```python
from triggers import TriggerManager, ScheduledTrigger

manager = TriggerManager()

# Run agent every hour
trigger = ScheduledTrigger(
    name="hourly_report",
    agent_id="agent_123",
    schedule="0 * * * *",  # Cron format
    input_message="Generate hourly status report"
)
manager.register(trigger)
```

## API Reference

### Chat Endpoint

```bash
POST /api/chat
Content-Type: application/json

{
  "messages": [{"role": "user", "content": "Search for latest AI news"}],
  "thread_id": "thread_123",
  "agent_profile": {
    "enabled_tools": {"web_search": true, "sandbox_browser": true}
  }
}
```

### SSE Events

The `/api/chat` endpoint streams Server-Sent Events:

| Event Type | Description |
|------------|-------------|
| `tool_start` | Tool execution started |
| `tool_result` | Tool execution completed |
| `screenshot` | Screenshot available |
| `task_update` | Task status changed |
| `content` | Text content chunk |
| `done` | Stream completed |

### Screenshot API

```bash
GET /api/screenshots/{filename}
```

### Trigger API

```bash
# List triggers
GET /api/triggers

# Create trigger
POST /api/triggers

# Webhook endpoint
POST /api/triggers/webhook/{trigger_id}
```

## Tool Reference

### Sandbox Browser Tools

| Tool | Description |
|------|-------------|
| `sb_browser_navigate` | Navigate to URL |
| `sb_browser_click` | Click element |
| `sb_browser_type` | Type text |
| `sb_browser_scroll` | Scroll page |
| `sb_browser_screenshot` | Take screenshot |
| `sb_browser_get_html` | Get page content |

### Sandbox File Tools

| Tool | Description |
|------|-------------|
| `sandbox_create_file` | Create new file |
| `sandbox_read_file` | Read file content |
| `sandbox_update_file` | Rewrite file |
| `sandbox_str_replace` | Replace text in file |
| `sandbox_delete_file` | Delete file |
| `sandbox_list_files` | List directory |
| `sandbox_upload_file` | Upload (Base64) |
| `sandbox_download_file` | Download (Base64) |

### Sandbox Shell Tools

| Tool | Description |
|------|-------------|
| `sandbox_execute_command` | Run command (blocking/background) |
| `sandbox_check_output` | Get background command output |
| `sandbox_kill_process` | Kill process |
| `sandbox_list_processes` | List running processes |
| `sandbox_install_package` | Install npm/pip/apt package |
| `sandbox_expose_port` | Expose port for public access |

### Computer Use Tools

| Tool | Description |
|------|-------------|
| `computer_move_mouse` | Move cursor |
| `computer_click` | Mouse click |
| `computer_type` | Type text |
| `computer_press` | Press key/hotkey |
| `computer_scroll` | Scroll |
| `computer_screenshot` | Capture screen |
| `computer_screen_info` | Get screen dimensions |
| `computer_drag` | Drag operation |

### Task List Tools

| Tool | Description |
|------|-------------|
| `create_tasks` | Create task list |
| `view_tasks` | View all tasks |
| `update_task` | Update task status |
| `get_next_task` | Get next pending task |

### Sandbox Sheets Tools

| Tool | Description |
|------|-------------|
| `sandbox_create_spreadsheet` | Create Excel/CSV file |
| `sandbox_write_data` | Write 2D data array |
| `sandbox_read_spreadsheet` | Read spreadsheet data |
| `sandbox_format_cells` | Apply cell formatting |
| `sandbox_add_formula` | Add Excel formula |
| `sandbox_create_chart` | Create chart (bar/line/pie) |
| `sandbox_add_sheet` | Add worksheet |

### Sandbox Presentation Tools

| Tool | Description |
|------|-------------|
| `sandbox_create_presentation` | Create PPTX file |
| `sandbox_add_slide` | Add slide with layout |
| `sandbox_update_slide` | Update slide content |
| `sandbox_delete_slide` | Delete slide |
| `sandbox_add_image_to_slide` | Add image to slide |
| `sandbox_add_table_to_slide` | Add table to slide |
| `sandbox_add_shape_to_slide` | Add shape to slide |
| `sandbox_get_presentation_info` | Get presentation info |

### Sandbox Vision Tools

| Tool | Description |
|------|-------------|
| `sandbox_extract_text` | OCR text extraction |
| `sandbox_get_image_info` | Get image metadata |
| `sandbox_resize_image` | Resize image |
| `sandbox_convert_image` | Convert image format |
| `sandbox_crop_image` | Crop image |
| `sandbox_read_qr_code` | Read QR/barcode |
| `sandbox_compare_images` | Compare two images |

## Development

### Run Tests

```bash
# Smoke test
pytest tests/test_smoke_api.py -q

# All tests
pytest tests/ -v
```

### Code Style

```bash
# Format
black .
isort .

# Lint
ruff check .
```

## Deployment

### Docker

```bash
docker build -t weaver-backend .
docker run -p 8000:8000 --env-file .env weaver-backend
```

### Docker Compose (Full Stack)

```bash
docker-compose up -d
```

### Vercel (Frontend)

```bash
cd web
vercel deploy
```

## Documentation

| Document | Description |
|----------|-------------|
| [MANUS_AGENT_EXTRACTION_PROGRESS.md](docs/MANUS_AGENT_EXTRACTION_PROGRESS.md) | Feature extraction progress |
| [AGENT_VISUAL_IMPLEMENTATION_PLAN.md](docs/AGENT_VISUAL_IMPLEMENTATION_PLAN.md) | Visual agent implementation |
| [MANUS_FEATURE_ANALYSIS.md](docs/MANUS_FEATURE_ANALYSIS.md) | Manus feature comparison |
| [FRONTEND_INTEGRATION.md](docs/FRONTEND_INTEGRATION.md) | Frontend SSE integration guide |

## Roadmap

### Completed (92%)

- [x] Agent execution engine
- [x] Context management (token counting, truncation)
- [x] Browser automation with screenshots
- [x] Web search (API + Visual)
- [x] Task management
- [x] Desktop automation
- [x] Sandbox file operations
- [x] Sandbox shell commands
- [x] Trigger system (Scheduled/Webhook/Event)
- [x] SSE event streaming
- [x] MCP integration
- [x] Smart query routing (LLM-based)
- [x] Document generation (Excel, PPT)
- [x] Image processing (OCR, resize, convert)

### Planned

- [ ] Advanced image editing (filters, effects)
- [ ] Web development tools (scaffolding, deploy)
- [ ] Authentication system
- [ ] Knowledge base / RAG

## License

MIT

## Acknowledgments

- Inspired by [Manus](https://manus.im)
- Built with [LangGraph](https://github.com/langchain-ai/langgraph)
- Sandbox by [E2B](https://e2b.dev)
