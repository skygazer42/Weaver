# Development Guide

## Quick Start

### 1. Initial Setup

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Run setup script
./scripts/setup.sh

# Edit .env file with your API keys
vim .env
```

### 2. Start Development

```bash
# Option 1: Use the dev script
./scripts/dev.sh

# Option 2: Use npm script (recommended)
npm run dev

# Option 3: Start individually
npm run dev:backend  # Backend only
npm run dev:frontend # Web only
```

### 3. Access the Application

- **Web**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## Project Structure

```
manus-app/
├── web/              # Next.js 14 application
│   ├── app/              # App router
│   │   ├── page.tsx      # Main page
│   │   ├── layout.tsx    # Root layout
│   │   └── globals.css   # Global styles
│   ├── components/       # React components
│   │   ├── ui/          # Shadcn UI components
│   │   └── chat/        # Chat-specific components
│   └── lib/             # Utilities
│
├── backend/              # Python FastAPI application
│   ├── agent/           # LangGraph agent
│   │   ├── state.py     # Agent state schema
│   │   ├── nodes.py     # Agent nodes (planner, researcher, writer)
│   │   └── graph.py     # Graph construction
│   ├── tools/           # Agent tools
│   │   ├── search.py    # Tavily search integration
│   │   └── code_executor.py  # E2B code execution
│   ├── main.py          # FastAPI app & streaming endpoint
│   └── config.py        # Configuration
│
└── scripts/             # Utility scripts
```

## Architecture

### Backend Flow

```
User Query
    ↓
FastAPI /api/chat (main.py)
    ↓
LangGraph Agent (agent/graph.py)
    ↓
┌─────────────────┐
│  Planner Node   │ → Creates research plan
└────────┬────────┘
         ↓
┌─────────────────┐
│ Researcher Node │ → Executes searches (Tavily)
└────────┬────────┘
         ↓ (loop until done)
┌─────────────────┐
│  Writer Node    │ → Synthesizes report
└────────┬────────┘
         ↓
Stream Events to Web
```

### Web Flow

```
User Input
    ↓
Chat.tsx
    ↓
POST /api/chat (streaming)
    ↓
Parse SSE stream
    ↓
Update UI:
├── Messages (MessageItem.tsx)
├── Tool Status (ToolInvocationCard)
└── Artifacts (ArtifactsPanel.tsx)
```

## Key Features Implementation

### 1. Deep Search

**Backend** (agent/nodes.py:44-82):
- Planner creates 3-7 targeted queries
- Researcher executes each query using Tavily
- Advanced search depth returns full content

**Configuration**:
- Model: `o1-mini` for planning (reasoning)
- Search: Tavily with `search_depth="advanced"`

### 2. Streaming

**Backend** (main.py:116-209):
- Uses `research_graph.astream_events()` for real-time updates
- Converts LangGraph events to Vercel AI SDK format
- Event types: status, text, tool, completion

**Web** (web/components/chat/Chat.tsx:48-122):
- Fetches streaming response
- Parses data stream protocol (`0:{json}\n`)
- Updates UI in real-time

### 3. Code Execution

**Backend** (tools/code_executor.py):
- E2B Sandbox for safe Python execution
- Supports matplotlib for visualizations
- Returns base64 encoded images

**Enable**:
```bash
# Add to .env
E2B_API_KEY=your_key_here
```

### 4. Persistence

**Database** (PostgreSQL with pgvector):
- Stores agent state checkpoints
- Allows pause/resume for long tasks
- Enables retry on failure

**Setup**:
```bash
docker-compose up -d postgres
```

## Development Tips

### Backend Development

```bash
# Activate virtual environment
# Backend now in root
source venv/bin/activate

# Run with auto-reload
uvicorn main:app --reload

# Run with debug logging
DEBUG=True uvicorn main:app --reload

# Test API directly
curl http://localhost:8000/health
```

### Web Development

```bash
cd frontend

# Development server
npm run dev

# Type checking
npm run lint

# Build for production
npm run build
```

### Database Management

```bash
# Start database
docker-compose up -d postgres

# Stop database
docker-compose down

# View logs
docker-compose logs -f postgres

# Connect to database
docker exec -it manus_postgres psql -U manus -d manus_db
```

## Troubleshooting

### Port Already in Use

```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Kill process on port 3000
lsof -ti:3000 | xargs kill -9
```

### Database Connection Failed

```bash
# Restart database
docker-compose restart postgres

# Check database status
docker-compose ps
```

### Import Errors (Python)

```bash
# Backend now in root
source venv/bin/activate
pip install -r requirements.txt
```

### TypeScript Errors

```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

## Testing

### Manual Testing

1. **Basic Chat**:
   - Query: "What is LangGraph?"
   - Expected: Planner → Researcher → Writer flow

2. **Deep Research**:
   - Query: "Analyze the top 5 AI companies in 2024"
   - Expected: Multiple search queries, comprehensive report

3. **Code Execution** (if E2B configured):
   - Query: "Create a chart showing Python vs JavaScript popularity"
   - Expected: Code execution + visualization

### API Testing

```bash
# Health check
curl http://localhost:8000/health

# Non-streaming chat
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

## Environment Variables

### Backend (.env)

```bash
# Required
OPENAI_API_KEY=sk-...          # OpenAI API key
TAVILY_API_KEY=tvly-...        # Tavily search API
DATABASE_URL=postgresql://...   # PostgreSQL connection

# Optional
E2B_API_KEY=e2b_...            # Code execution
ANTHROPIC_API_KEY=sk-ant-...   # Claude models
DEBUG=True                      # Enable debug logs
```

### Web (.env.local)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Performance Optimization

### Backend

1. **Use reasoning model only for planning**:
   - Planner: `o1-mini` (slow but accurate)
   - Researcher/Writer: `gpt-4o-mini` (fast)

2. **Limit context size**:
   - Truncate scraped content in writer node
   - Use summarization for very long documents

3. **Parallel searches**:
   - Use LangGraph's `Send` API for concurrent queries
   - Set `max_concurrency` to avoid rate limits

### Web

1. **Optimize re-renders**:
   - Use React.memo for MessageItem
   - Virtualize long message lists

2. **Debounce input**:
   - Add input debouncing for better UX

## Deployment

See main README.md for deployment instructions.

## Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Vercel AI SDK](https://sdk.vercel.ai/docs)
- [Tavily API](https://docs.tavily.com/)
- [E2B Documentation](https://e2b.dev/docs)
- [Shadcn UI](https://ui.shadcn.com/)
