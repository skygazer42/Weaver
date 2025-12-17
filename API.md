# API Documentation

## Base URL

```
http://localhost:8000
```

## Endpoints

### 1. Health Check

**GET** `/health`

Check the health status of the API and database connection.

**Response**:
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2024-01-15T10:30:00"
}
```

### 2. Chat (Streaming)

**POST** `/api/chat`

Main chat endpoint with streaming support. Compatible with Vercel AI SDK.

**Request**:
```json
{
  "messages": [
    {
      "role": "user",
      "content": "What are the latest trends in AI?"
    }
  ],
  "stream": true
}
```

**Response** (Server-Sent Events):

The response is a stream of events in the format: `0:{json}\n`

Event types:

1. **Status Event**:
```json
{
  "type": "status",
  "data": {
    "text": "Creating research plan...",
    "step": "planning"
  }
}
```

2. **Text Event** (streaming tokens):
```json
{
  "type": "text",
  "data": {
    "content": "The latest"
  }
}
```

3. **Message Event** (complete message):
```json
{
  "type": "message",
  "data": {
    "content": "Research Plan:\n1. Search for...\n2. Analyze..."
  }
}
```

4. **Tool Event**:
```json
{
  "type": "tool",
  "data": {
    "name": "search",
    "status": "running",
    "query": "AI trends 2024"
  }
}
```

5. **Completion Event**:
```json
{
  "type": "completion",
  "data": {
    "content": "# Research Report\n\nBased on extensive research..."
  }
}
```

6. **Done Event**:
```json
{
  "type": "done",
  "data": {
    "timestamp": "2024-01-15T10:35:00"
  }
}
```

7. **Error Event**:
```json
{
  "type": "error",
  "data": {
    "message": "Search API rate limit exceeded"
  }
}
```

### 3. Chat (Non-Streaming)

**POST** `/api/chat`

Same endpoint as above, but with `stream: false`.

**Request**:
```json
{
  "messages": [
    {
      "role": "user",
      "content": "Explain quantum computing"
    }
  ],
  "stream": false
}
```

**Response**:
```json
{
  "id": "msg_1705315800.123",
  "content": "# Quantum Computing\n\nQuantum computing is...",
  "role": "assistant",
  "timestamp": "2024-01-15T10:30:00"
}
```

### 4. Research (Dedicated)

**POST** `/api/research?query={query}`

Dedicated research endpoint for long-running queries.

**Request**:
```
POST /api/research?query=Analyze%20the%20GPU%20market
```

**Response**: Same streaming format as `/api/chat`

## Event Flow Example

```
User sends: "Research the top 5 AI frameworks"

1. status → "Initializing research agent..."
2. status → "Creating research plan..."
3. message → "Research Plan: 1. TensorFlow 2. PyTorch..."
4. status → "Conducting research..."
5. tool → {name: "search", status: "running", query: "TensorFlow features"}
6. tool → {name: "search", status: "completed"}
7. tool → {name: "search", status: "running", query: "PyTorch comparison"}
8. tool → {name: "search", status: "completed"}
9. status → "Synthesizing findings..."
10. text → "# Top 5" (streaming)
11. text → " AI" (streaming)
12. text → " Frameworks" (streaming)
13. completion → "# Top 5 AI Frameworks\n\n## 1. TensorFlow..."
14. done → {timestamp: "..."}
```

## Integration Examples

### JavaScript (Fetch API)

```javascript
const response = await fetch('http://localhost:8000/api/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    messages: [{ role: 'user', content: 'Hello' }],
    stream: true,
  }),
})

const reader = response.body.getReader()
const decoder = new TextDecoder()

while (true) {
  const { done, value } = await reader.read()
  if (done) break

  const chunk = decoder.decode(value)
  const lines = chunk.split('\n').filter(line => line.trim())

  for (const line of lines) {
    if (line.startsWith('0:')) {
      const data = JSON.parse(line.slice(2))
      console.log('Event:', data)
    }
  }
}
```

### Python (httpx)

```python
import httpx
import json

async with httpx.AsyncClient() as client:
    async with client.stream(
        'POST',
        'http://localhost:8000/api/chat',
        json={
            'messages': [{'role': 'user', 'content': 'Hello'}],
            'stream': True
        }
    ) as response:
        async for line in response.aiter_lines():
            if line.startswith('0:'):
                data = json.loads(line[2:])
                print('Event:', data)
```

### cURL

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is LangGraph?"}
    ],
    "stream": true
  }' \
  --no-buffer
```

## Error Responses

### 400 Bad Request

```json
{
  "detail": "No user message found"
}
```

### 500 Internal Server Error

```json
{
  "detail": "Search API error: Rate limit exceeded"
}
```

## Rate Limits

- No built-in rate limiting (depends on OpenAI/Tavily limits)
- OpenAI: Varies by tier
- Tavily: Check your plan

## Best Practices

1. **Use streaming for better UX**: Show real-time progress
2. **Handle timeouts**: Research can take 5-10 minutes
3. **Parse events carefully**: Check event type before processing
4. **Implement retry logic**: Network issues can interrupt streams
5. **Show tool invocations**: Display search progress to users

## WebSocket Alternative (Future)

For production, consider implementing WebSocket support:

```python
# Backend: Use FastAPI WebSocket
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    # Stream events via WebSocket
```

This provides:
- Bi-directional communication
- Better error handling
- Automatic reconnection
- Lower overhead

## Deployment Considerations

### CORS

Configure CORS for production:

```python
# config.py
cors_origins = "https://your-frontend.com"
```

### HTTPS

Always use HTTPS in production:
```
https://api.your-domain.com/api/chat
```

### Long-Running Requests

- Use long-running containers (not serverless)
- Railway, AWS Fargate, or similar
- Configure appropriate timeouts (10+ minutes)

### Load Balancing

For high traffic:
- Use Redis for state persistence
- Scale backend horizontally
- Implement request queuing (BullMQ)
