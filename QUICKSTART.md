# Quick Start Guide

Get your Manus AI Research Agent running in 5 minutes!

## Prerequisites

- Node.js 18+ ([Download](https://nodejs.org/))
- Python 3.11+ ([Download](https://www.python.org/))
- Docker & Docker Compose ([Download](https://www.docker.com/))

## Step 1: Get API Keys

### Required:

1. **OpenAI API Key** (for AI model)
   - Go to https://platform.openai.com/api-keys
   - Create a new API key
   - Copy it for later

2. **Tavily API Key** (for search)
   - Go to https://tavily.com
   - Sign up and get your API key
   - Copy it for later

### Optional:

3. **E2B API Key** (for code execution)
   - Go to https://e2b.dev
   - Sign up and get your API key

## Step 2: Setup Project

```bash
# Clone or navigate to project
cd /data/temp39/Weaver

# Make setup script executable
chmod +x scripts/setup.sh

# Run setup (installs dependencies, creates env files)
./scripts/setup.sh
```

## Step 3: Configure API Keys

Edit the `.env` file and add your API keys:

```bash
# Open .env file
nano .env

# Or use your favorite editor:
# vim .env
# code .env
```

Add your keys:
```env
OPENAI_API_KEY=sk-your-openai-key-here
TAVILY_API_KEY=tvly-your-tavily-key-here
E2B_API_KEY=e2b_your-e2b-key-here  # Optional
```

Save and exit.

## Step 4: Start the Application

```bash
# Start everything (database + backend + frontend)
npm run dev
```

Wait 10-20 seconds for all services to start.

## Step 5: Open in Browser

Open http://localhost:3000

You should see the Manus interface!

## Try It Out

### Example Queries:

1. **Simple Question**:
   ```
   What is LangGraph and how does it work?
   ```

2. **Deep Research**:
   ```
   Analyze the top 3 AI frameworks in 2024 and compare their features
   ```

3. **Data Analysis** (requires E2B):
   ```
   Research Python's popularity and create a trend chart
   ```

## What You Should See

### 1. Planning Phase
The AI will create a research plan:
- "Creating research plan..."
- Shows 3-7 specific search queries

### 2. Research Phase
The AI searches for information:
- "Searching: AI frameworks 2024"
- "Searching: TensorFlow features"
- You'll see search progress in real-time

### 3. Writing Phase
The AI synthesizes a report:
- "Synthesizing findings..."
- Generates comprehensive markdown report

## Troubleshooting

### "Connection refused" error

The backend isn't running. Check:
```bash
# Check if backend is running
curl http://localhost:8000/health

# If not, restart:
npm run dev:backend
```

### "Database connection failed"

Database isn't running:
```bash
# Start database
docker-compose up -d postgres

# Check status
docker-compose ps
```

### "Invalid API key" error

Check your `.env` file:
```bash
cat .env

# Make sure keys are correct and have no quotes
# ✅ OPENAI_API_KEY=sk-abc123
# ❌ OPENAI_API_KEY="sk-abc123"
```

### Web shows blank page

```bash
# Check frontend logs
cd frontend
npm run dev
```

### Port already in use

Kill the process:
```bash
# For port 8000 (backend)
lsof -ti:8000 | xargs kill -9

# For port 3000 (frontend)
lsof -ti:3000 | xargs kill -9
```

## Next Steps

### Explore Features

1. **Try different query types**:
   - Research questions
   - Data analysis
   - Comparisons
   - Trend analysis

2. **Watch the thinking process**:
   - See how the AI plans
   - Monitor search queries
   - View tool invocations

3. **Check the API docs**:
   - Visit http://localhost:8000/docs
   - Try the interactive API explorer

### Customize

1. **Change AI models** (config.py):
   ```python
   primary_model = "gpt-4o"  # For better quality
   reasoning_model = "o1-preview"  # For deeper reasoning
   ```

2. **Adjust search depth** (tools/search.py):
   ```python
   max_results = 10  # More results per query
   ```

3. **Modify UI** (web/components/):
   - Customize colors in `tailwind.config.ts`
   - Edit components in `components/chat/`

## Development Workflow

### Making Changes

1. **Backend changes**:
   - Edit files in `backend/`
   - Server auto-reloads (uvicorn --reload)
   - Check terminal for errors

2. **Web changes**:
   - Edit files in `web/`
   - Next.js auto-reloads
   - Check browser console for errors

### Testing

```bash
# Test backend
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}],"stream":false}'

# Test frontend
# Just use the browser at http://localhost:3000
```

## Understanding the Output

### Research Report Structure

A typical report includes:

1. **Executive Summary**
   - Key findings
   - Quick overview

2. **Detailed Analysis**
   - Organized by topic
   - Evidence from sources
   - Comparisons and insights

3. **Sources**
   - URLs and references
   - Credibility indicators

### Tool Invocations

You'll see:
- 🔍 **Search**: Blue boxes showing search queries
- 💻 **Code**: Orange boxes for code execution
- ✅ **Completed**: Green when done

## Cost Considerations

### API Costs (Approximate)

- **Simple query** (~5 searches): $0.01 - $0.05
- **Deep research** (~20 searches): $0.10 - $0.50
- **With code execution**: +$0.01 per execution

### Tips to Reduce Costs

1. **Use cheaper models**:
   ```python
   primary_model = "gpt-4o-mini"  # Instead of gpt-4o
   ```

2. **Limit search results**:
   ```python
   max_results = 3  # Instead of 5-10
   ```

3. **Cache responses** (future feature)

## Getting Help

### Documentation

- **Development Guide**: See `DEVELOPMENT.md`
- **API Reference**: See `API.md`
- **Architecture**: See `README.md`

### Common Issues

1. **Slow responses**: Normal for deep research (5-10 min)
2. **Rate limits**: Wait and retry
3. **Search errors**: Check Tavily API quota

### Community

- GitHub Issues: Report bugs
- Discussions: Ask questions
- Pull Requests: Contribute!

## Success Checklist

- [ ] All dependencies installed
- [ ] API keys configured
- [ ] Database running
- [ ] Backend started (port 8000)
- [ ] Web started (port 3000)
- [ ] Can access http://localhost:3000
- [ ] Can send a test query
- [ ] Receives a response

If all checked, you're ready to go! 🎉

## Example Session

```
You: Research the benefits of TypeScript over JavaScript

AI: Creating research plan...

Research Plan:
1. TypeScript core features and benefits
2. JavaScript limitations that TypeScript addresses
3. Developer productivity comparison
4. Industry adoption statistics

Searching: TypeScript core features...
Found 5 results

Searching: JavaScript vs TypeScript comparison...
Found 5 results

Searching: TypeScript adoption 2024...
Found 5 results

Synthesizing findings...

# TypeScript vs JavaScript: Key Benefits

## Executive Summary
TypeScript offers significant advantages over JavaScript...

[Full detailed report follows]
```

---

**Time to first response**: 30-60 seconds
**Average research time**: 2-5 minutes
**Success rate**: 95%+

Happy researching! 🚀
