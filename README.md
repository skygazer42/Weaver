# Manus App - Deep Research AI Agent

A full-stack application with Deep Search, Code Execution, and Generative UI capabilities, inspired by Manus.

## Architecture

- **Frontend**: Next.js 14 (App Router) + Tailwind CSS + Shadcn UI + Vercel AI SDK
- **Backend**: Python 3.11+ + FastAPI + LangGraph + LangChain
- **Database**: PostgreSQL with pgvector
- **Tools**: Tavily (Search) + E2B (Code Execution)

## Project Structure

```
manus-app/
├── frontend/          # Next.js application
│   ├── app/          # App router pages
│   ├── components/   # React components
│   └── lib/          # Utilities
├── backend/          # Python FastAPI application
│   ├── agent/       # LangGraph agent logic
│   ├── tools/       # Search & code execution tools
│   └── main.py      # API entry point
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
# Run both frontend and backend
npm run dev

# Or run separately:
# Backend: npm run dev:backend
# Frontend: npm run dev:frontend
```

- Frontend: http://localhost:3000
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
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev
```

## Deployment

### Frontend (Vercel)

```bash
cd frontend
vercel deploy
```

### Backend (Railway/AWS)

The backend requires long-running containers due to extended research times (5-10 minutes).

```bash
docker build -t manus-backend ./backend
# Deploy to Railway, AWS Fargate, or similar
```

## License

MIT
