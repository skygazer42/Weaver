# Manus App - Deep Research AI Agent

A full-stack application with Deep Search, Code Execution, and Generative UI capabilities, inspired by Manus.

## Architecture

- **Web**: Next.js 14 (App Router) + Tailwind CSS + Shadcn UI + Vercel AI SDK
- **Backend**: Python 3.11+ + FastAPI + LangGraph + LangChain
- **Database**: PostgreSQL with pgvector
- **Tools**: Tavily (Search) + E2B (Code Execution)
- **New (LangGraph 1.x)**: routeable workflows (direct / web / agent / deep), evaluator-optimizer loop, optional human-in-the-loop interrupts, MCP tool bridge.

## Project Structure

```
manus-app/
├── web/              # Next.js application
│   ├── app/          # App router pages
│   ├── components/   # React components
│   └── lib/          # Utilities
├── agent/            # LangGraph agent logic
├── tools/            # Search & code execution tools
├── main.py           # FastAPI API entry point
├── config.py         # Configuration
├── requirements.txt  # Python dependencies
└── docker-compose.yml
```

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.11+
- Docker & Docker Compose

### 1. Environment Setup

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

Required API keys:
- **OpenAI API Key**: Get from https://platform.openai.com/api-keys
- **Tavily API Key**: Get from https://tavily.com
- **E2B API Key**: Get from https://e2b.dev

### 2. Start Database

```bash
docker-compose up postgres -d
```

### 3. Install Dependencies

```bash
npm run install:all
```

### 4. Run Development Servers

```bash
# Run both backend and web
npm run dev

# Or run separately:
# Backend: npm run dev:backend
# Web: npm run dev:web
```

- Web: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Features

### 🔍 Deep Search
- Multi-step research planning
- Parallel search execution
- Content scraping and analysis

### 💻 Code Execution
- Python code interpreter in sandboxed environment
- Matplotlib visualization support
- Safe execution with E2B

### 🎨 Generative UI
- Real-time streaming responses
- Interactive artifacts (reports, charts, code)
- Tool invocation visualization

### 🔄 Human-in-the-loop
- Interrupt and resume capability
- Plan confirmation workflow
- Manual feedback integration

## Development

### Backend Development

```bash
# Backend is now in root directory
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

### Web Development

```bash
cd web
npm install
npm run dev
```

## Deployment

### Web (Vercel)

```bash
cd web
vercel deploy
```

### Backend (Railway/AWS)

The backend requires long-running containers due to extended research times (5-10 minutes).

```bash
docker build -t manus-backend .
# Deploy to Railway, AWS Fargate, or similar
```

## License

MIT
