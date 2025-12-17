from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import logging
import asyncio
from datetime import datetime

from config import settings
from agent import create_research_graph, create_checkpointer, AgentState

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.debug else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Manus Research Agent API",
    description="Deep research AI agent with code execution capabilities",
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agent graph
checkpointer = create_checkpointer(settings.database_url) if settings.database_url else None
research_graph = create_research_graph(checkpointer=checkpointer)


# Request/Response models
class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    stream: bool = True
    model: Optional[str] = "gpt-4o"
    search_mode: Optional[str] = "agent"  # web, agent, deep


class ChatResponse(BaseModel):
    id: str
    content: str
    role: str = "assistant"
    timestamp: str


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Manus Research Agent",
        "version": "0.1.0"
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "database": "connected" if checkpointer else "not configured",
        "timestamp": datetime.now().isoformat()
    }


async def format_stream_event(event_type: str, data: Any) -> str:
    """
    Format events in Vercel AI SDK Data Stream Protocol format.

    Format: {type}:{json_data}\n
    """
    payload = {
        "type": event_type,
        "data": data
    }
    return f"0:{json.dumps(payload)}\n"


async def stream_agent_events(input_text: str, thread_id: str = "default", model: str = "gpt-4o", search_mode: str = "agent"):
    """
    Stream agent execution events in real-time.

    Converts LangGraph events to Vercel AI SDK format.
    """
    try:
        # Initialize state
        initial_state: AgentState = {
            "input": input_text,
            "messages": [],
            "research_plan": [],
            "current_step": 0,
            "scraped_content": [],
            "code_results": [],
            "final_report": "",
            "is_complete": False,
            "errors": []
        }

        config = {
            "configurable": {
                "thread_id": thread_id,
                "model": model,
                "search_mode": search_mode
            },
            "recursion_limit": 50
        }

        # Send initial status
        yield await format_stream_event("status", {
            "text": "Initializing research agent...",
            "step": "init"
        })

        # Stream graph execution
        async for event in research_graph.astream_events(
            initial_state,
            config=config,
            version="v1"
        ):
            event_type = event.get("event")
            name = event.get("name", "")
            data_dict = event.get("data", {})

            # Handle different event types
            if event_type == "on_chain_start":
                if "planner" in name:
                    yield await format_stream_event("status", {
                        "text": "Creating research plan...",
                        "step": "planning"
                    })
                elif "researcher" in name or "perform_parallel_search" in name:
                    yield await format_stream_event("status", {
                        "text": "Conducting research...",
                        "step": "researching"
                    })
                elif "writer" in name:
                    yield await format_stream_event("status", {
                        "text": "Synthesizing findings...",
                        "step": "writing"
                    })

            elif event_type == "on_chain_end":
                output = data_dict.get("output", {})

                # Extract messages from output
                if isinstance(output, dict):
                    messages = output.get("messages", [])
                    if messages:
                        for msg in messages:
                            content = msg.content if hasattr(msg, 'content') else str(msg)
                            yield await format_stream_event("message", {
                                "content": content
                            })

                    # Check for completion and final report artifact
                    if output.get("is_complete"):
                        final_report = output.get("final_report", "")
                        if final_report:
                            yield await format_stream_event("completion", {
                                "content": final_report
                            })
                            
                            # Also emit as artifact
                            yield await format_stream_event("artifact", {
                                "id": f"report_{datetime.now().timestamp()}",
                                "type": "report",
                                "title": "Research Report",
                                "content": final_report
                            })

            elif event_type == "on_tool_start":
                tool_name = data_dict.get("name", "unknown")
                tool_input = data_dict.get("input", {})

                if "search" in tool_name.lower():
                    query = tool_input.get("query", "unknown")
                    yield await format_stream_event("tool", {
                        "name": "search",
                        "status": "running",
                        "query": query
                    })
                elif "code" in tool_name.lower():
                    yield await format_stream_event("tool", {
                        "name": "code_execution",
                        "status": "running"
                    })

            elif event_type == "on_tool_end":
                tool_name = data_dict.get("name", "unknown")
                output = data_dict.get("output", {})
                
                yield await format_stream_event("tool", {
                    "name": tool_name,
                    "status": "completed"
                })

                # Check for artifacts from code execution
                if tool_name == "execute_python_code" and isinstance(output, dict):
                    image_data = output.get("image")
                    
                    if image_data:
                        yield await format_stream_event("artifact", {
                            "id": f"art_{datetime.now().timestamp()}",
                            "type": "chart",
                            "title": "Generated Visualization",
                            "content": "Chart generated from Python code",
                            "image": image_data
                        })

            elif event_type == "on_chat_model_stream":
                # Stream LLM tokens
                chunk = data_dict.get("chunk")
                if chunk and hasattr(chunk, 'content'):
                    content = chunk.content
                    if content:
                        yield await format_stream_event("text", {
                            "content": content
                        })

        # Send final completion
        yield await format_stream_event("done", {
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Stream error: {str(e)}", exc_info=True)
        yield await format_stream_event("error", {
            "message": str(e)
        })


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Main chat endpoint with streaming support.

    Compatible with Vercel AI SDK useChat hook.
    """
    try:
        # Get the last user message
        user_messages = [msg for msg in request.messages if msg.role == "user"]
        if not user_messages:
            raise HTTPException(status_code=400, detail="No user message found")

        last_message = user_messages[-1].content

        logger.info(f"Processing chat request: {last_message[:100]}... Mode: {request.search_mode}")

        if request.stream:
            # Return streaming response
            return StreamingResponse(
                stream_agent_events(last_message, model=request.model, search_mode=request.search_mode),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        else:
            # Non-streaming response (fallback)
            initial_state: AgentState = {
                "input": last_message,
                "messages": [],
                "research_plan": [],
                "current_step": 0,
                "scraped_content": [],
                "code_results": [],
                "final_report": "",
                "is_complete": False,
                "errors": []
            }

            result = await research_graph.ainvoke(initial_state)
            final_report = result.get("final_report", "No response generated")

            return ChatResponse(
                id=f"msg_{datetime.now().timestamp()}",
                content=final_report,
                timestamp=datetime.now().isoformat()
            )

    except Exception as e:
        logger.error(f"Chat error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/research")
async def research(query: str):
    """
    Dedicated research endpoint for long-running queries.

    Returns streaming response with research progress.
    """
    return StreamingResponse(
        stream_agent_events(query),
        media_type="text/event-stream"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )