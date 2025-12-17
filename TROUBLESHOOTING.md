# Troubleshooting Guide

Common issues and their solutions.

## Installation Issues

### "command not found: npm"

**Problem**: Node.js is not installed.

**Solution**:
```bash
# macOS
brew install node

# Ubuntu/Debian
sudo apt-get install nodejs npm

# Windows
# Download from https://nodejs.org/
```

### "python3: command not found"

**Problem**: Python is not installed.

**Solution**:
```bash
# macOS
brew install python@3.11

# Ubuntu/Debian
sudo apt-get install python3.11 python3.11-venv

# Windows
# Download from https://www.python.org/
```

### "docker: command not found"

**Problem**: Docker is not installed.

**Solution**:
Visit https://docs.docker.com/get-docker/ and follow instructions for your OS.

## Setup Issues

### "Permission denied" when running setup.sh

**Problem**: Script is not executable.

**Solution**:
```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

### "pip: No module named pip"

**Problem**: pip is not installed in the virtual environment.

**Solution**:
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
python -m ensurepip
pip install --upgrade pip
pip install -r requirements.txt
```

### "npm ERR! EACCES: permission denied"

**Problem**: npm doesn't have write permissions.

**Solution**:
```bash
# Don't use sudo! Instead, fix npm permissions:
mkdir ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
```

## Runtime Issues

### Backend won't start

#### Error: "ModuleNotFoundError: No module named 'fastapi'"

**Problem**: Dependencies not installed.

**Solution**:
```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

#### Error: "Address already in use" (port 8000)

**Problem**: Another process is using port 8000.

**Solution**:
```bash
# Find and kill the process
lsof -ti:8000 | xargs kill -9

# Or use a different port
uvicorn main:app --port 8001
```

#### Error: "sqlalchemy.exc.OperationalError: connection refused"

**Problem**: Database is not running.

**Solution**:
```bash
# Start the database
docker-compose up -d postgres

# Check it's running
docker-compose ps

# View logs
docker-compose logs postgres
```

### Frontend won't start

#### Error: "Cannot find module 'next'"

**Problem**: Dependencies not installed.

**Solution**:
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

#### Error: "Port 3000 is already in use"

**Problem**: Another app is using port 3000.

**Solution**:
```bash
# Kill the process
lsof -ti:3000 | xargs kill -9

# Or use a different port
npm run dev -- -p 3001
```

#### Error: "Module not found: Can't resolve '@/components/ui/button'"

**Problem**: Path alias not working.

**Solution**:
```bash
# Check tsconfig.json has:
{
  "compilerOptions": {
    "paths": {
      "@/*": ["./*"]
    }
  }
}

# Restart the dev server
```

## API Issues

### "OpenAI API Error: Invalid API key"

**Problem**: API key is incorrect or not set.

**Solution**:
```bash
# Check .env file
cat .env

# Make sure it looks like:
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx

# NOT:
# OPENAI_API_KEY="sk-proj-xxxxxxxxxxxxx"  ❌ (no quotes!)
# OPENAI_API_KEY=your-key-here  ❌ (placeholder!)
```

### "Tavily API Error: Unauthorized"

**Problem**: Tavily API key is invalid.

**Solution**:
1. Go to https://tavily.com
2. Check your API key
3. Update `.env`:
   ```bash
   TAVILY_API_KEY=tvly-xxxxxxxxxxxxx
   ```
4. Restart backend

### "E2B Error: API key not found"

**Problem**: E2B is not configured (optional).

**Solution**:
This is optional. If you don't need code execution:
- Ignore the error
- Queries will work without code execution

To enable:
1. Go to https://e2b.dev
2. Sign up and get API key
3. Add to `.env`:
   ```bash
   E2B_API_KEY=e2b_xxxxxxxxxxxxx
   ```

## Streaming Issues

### Response hangs or freezes

**Problem**: Stream is buffered or connection is lost.

**Solution**:
```bash
# Backend: Make sure you're using astream
# Check main.py uses:
async for event in research_graph.astream_events(...)

# Frontend: Check headers
headers: {
  'Cache-Control': 'no-cache',
  'Connection': 'keep-alive'
}
```

### "TypeError: Cannot read property 'getReader'"

**Problem**: Browser doesn't support ReadableStream.

**Solution**:
Use a modern browser:
- Chrome 80+
- Firefox 75+
- Safari 14+
- Edge 80+

### No real-time updates

**Problem**: Stream events not being parsed.

**Solution**:
Check browser console. The format should be:
```
0:{"type":"status","data":{...}}
```

Make sure your frontend splits on `\n` and checks for `0:` prefix.

## Database Issues

### "psycopg2.OperationalError: could not connect"

**Problem**: Database connection failed.

**Solution**:
```bash
# Check database is running
docker-compose ps

# If not running
docker-compose up -d postgres

# Check logs
docker-compose logs postgres

# Test connection
docker exec -it manus_postgres psql -U manus -d manus_db
```

### "relation does not exist"

**Problem**: Database tables not created.

**Solution**:
```bash
# LangGraph should auto-create tables, but if not:
cd backend
source venv/bin/activate
python

>>> from agent.graph import create_checkpointer
>>> from config import settings
>>> checkpointer = create_checkpointer(settings.database_url)
>>> checkpointer.setup()
```

### "too many connections"

**Problem**: Connection pool exhausted.

**Solution**:
```bash
# Restart database
docker-compose restart postgres

# Or increase max_connections in docker-compose.yml:
services:
  postgres:
    command: postgres -c max_connections=200
```

## Performance Issues

### Slow responses

**Possible Causes**:
1. **Normal**: Deep research takes 2-5 minutes
2. **API rate limits**: Check OpenAI dashboard
3. **Network issues**: Check internet connection
4. **Model selection**: o1-mini is slower but better

**Solutions**:
```python
# Use faster models (backend/config.py)
primary_model = "gpt-4o-mini"  # Faster
reasoning_model = "gpt-4o"      # Instead of o1-mini

# Reduce search results (backend/tools/search.py)
max_results = 3  # Instead of 5
```

### High memory usage

**Problem**: Backend using too much RAM.

**Solution**:
```python
# Limit context size (backend/agent/nodes.py)
context=research_context[:4000]  # Instead of 8000

# Clear old checkpoints
docker-compose exec postgres psql -U manus -d manus_db
# DELETE FROM checkpoints WHERE created_at < NOW() - INTERVAL '1 day';
```

### Frontend lag

**Problem**: Too many re-renders.

**Solution**:
```typescript
// Add React.memo to MessageItem
export const MessageItem = React.memo(({ message }) => {
  // component code
})

// Debounce input
import { useDebouncedCallback } from 'use-debounce'
```

## Docker Issues

### "Cannot connect to Docker daemon"

**Problem**: Docker service is not running.

**Solution**:
```bash
# macOS
# Start Docker Desktop

# Linux
sudo systemctl start docker

# Windows
# Start Docker Desktop
```

### "docker-compose: command not found"

**Problem**: Docker Compose is not installed.

**Solution**:
```bash
# Docker Compose v2 (built-in)
docker compose up -d

# Or install v1
pip install docker-compose
```

### "Error: No such container: manus_postgres"

**Problem**: Container doesn't exist.

**Solution**:
```bash
# Create and start
docker-compose up -d postgres

# Check status
docker-compose ps
```

## CORS Issues

### "CORS policy: No 'Access-Control-Allow-Origin'"

**Problem**: Frontend domain not in CORS whitelist.

**Solution**:
```bash
# Update backend/.env
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# Or for development (not production!)
CORS_ORIGINS=*
```

## Environment Issues

### Changes to .env not taking effect

**Problem**: Server not reloaded.

**Solution**:
```bash
# Backend
cd backend
# Kill server (Ctrl+C)
source venv/bin/activate
uvicorn main:app --reload

# Frontend
cd frontend
# Kill server (Ctrl+C)
npm run dev
```

### "dotenv.errors.ValidationError"

**Problem**: Required environment variable missing.

**Solution**:
```bash
# Check required vars in backend/config.py:
# - OPENAI_API_KEY (required)
# - TAVILY_API_KEY (required)
# - DATABASE_URL (required)

# Make sure they're all in .env
cat .env | grep -E 'OPENAI|TAVILY|DATABASE'
```

## Network Issues

### "net::ERR_CONNECTION_REFUSED"

**Problem**: Backend is not running or wrong port.

**Solution**:
```bash
# Check backend is running
curl http://localhost:8000/health

# Check frontend .env.local
cat frontend/.env.local
# Should be:
NEXT_PUBLIC_API_URL=http://localhost:8000

# Restart both services
npm run dev
```

### "Failed to fetch"

**Problem**: CORS or network issue.

**Solution**:
```bash
# Test backend directly
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"test"}],"stream":false}'

# Check browser console for specific error
# Open DevTools → Console
```

## Common Error Messages

### "AttributeError: 'NoneType' object has no attribute"

**Likely Cause**: API key not set or service not configured.

**Check**:
```bash
# Backend logs
cd backend
source venv/bin/activate
uvicorn main:app --reload

# Look for initialization errors
```

### "TypeError: Cannot read properties of undefined"

**Likely Cause**: Frontend trying to access data that hasn't loaded.

**Fix**:
Add null checks:
```typescript
{message?.content && <div>{message.content}</div>}
```

### "SyntaxError: Unexpected token"

**Likely Cause**: Invalid JSON in stream.

**Debug**:
```typescript
// Add logging
const data = JSON.parse(line.slice(2))
console.log('Parsed:', data)
```

## Getting Help

If none of these solve your issue:

1. **Check logs**:
   ```bash
   # Backend
   cd backend && source venv/bin/activate && uvicorn main:app --reload

   # Frontend
   cd frontend && npm run dev

   # Database
   docker-compose logs postgres
   ```

2. **Enable debug mode**:
   ```bash
   # .env
   DEBUG=True
   ```

3. **Test components individually**:
   ```bash
   # Test backend only
   curl http://localhost:8000/health

   # Test database only
   docker exec -it manus_postgres psql -U manus -d manus_db
   ```

4. **Check versions**:
   ```bash
   node --version    # Should be 18+
   python --version  # Should be 3.11+
   docker --version
   ```

5. **Fresh install**:
   ```bash
   # Nuclear option - start from scratch
   rm -rf node_modules frontend/node_modules backend/venv
   docker-compose down -v
   ./scripts/setup.sh
   ```

## Still Stuck?

1. Check GitHub Issues
2. Review DEVELOPMENT.md
3. Read API.md
4. Check official docs:
   - LangGraph: https://langchain-ai.github.io/langgraph/
   - Next.js: https://nextjs.org/docs
   - FastAPI: https://fastapi.tiangolo.com/

## Prevention Tips

1. **Always activate venv** before running backend
2. **Use the dev scripts** instead of manual commands
3. **Check .env files** before starting services
4. **Keep dependencies updated** (but test first!)
5. **Monitor API quotas** to avoid surprise limits

---

**Remember**: Most issues are environment-related. When in doubt, restart everything:

```bash
docker-compose restart
# Kill all terminals
# ./scripts/dev.sh
```
