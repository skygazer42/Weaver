"""
Customer Support Agent with Mem0 memory.

Provides a simple LangGraph that:
- Retrieves relevant memories for the user
- Adds a system prompt with context
- Stores the interaction back to memory
"""

from typing import Annotated, List, TypedDict
import json

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain_openai import ChatOpenAI

from common.config import settings
from tools.memory_client import fetch_memories, store_interaction


class SupportState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    user_id: str


def _support_model() -> ChatOpenAI:
    params = {
        "temperature": 0.3,
        "model": settings.primary_model,
        "api_key": settings.openai_api_key,
        "timeout": settings.openai_timeout or None,
    }
    if settings.use_azure:
        params.update({
            "azure_endpoint": settings.azure_endpoint or None,
            "azure_deployment": settings.primary_model,
            "api_version": settings.azure_api_version or None,
            "api_key": settings.azure_api_key or settings.openai_api_key,
        })
    elif settings.openai_base_url:
        params["base_url"] = settings.openai_base_url

    extra = {}
    if settings.openai_extra_body:
        try:
            extra.update(json.loads(settings.openai_extra_body))
        except Exception:
            pass
    if extra:
        params["extra_body"] = extra
    return ChatOpenAI(**params)


def support_node(state: SupportState):
    messages = state["messages"]
    user_id = state.get("user_id") or settings.memory_user_id
    last_user_message = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_message = msg.content
            break

    # Retrieve memories
    mem_entries = fetch_memories(query=last_user_message, user_id=user_id)
    context = ""
    if mem_entries:
        context = "Relevant information from previous conversations:\n" + "\n".join(
            f"- {m}" for m in mem_entries
        )

    system_prompt = "You are a helpful customer support assistant. Use provided context to personalize and remember user preferences."
    if context:
        system_prompt += f"\n{context}"

    llm = _support_model()
    response = llm.invoke([SystemMessage(content=system_prompt)] + messages)
    reply_text = response.content if hasattr(response, "content") else str(response)

    # Store interaction
    if last_user_message:
        store_interaction(last_user_message, reply_text, user_id=user_id)

    return {
        "messages": [AIMessage(content=reply_text)]
    }


def create_support_graph(checkpointer=None):
    graph = StateGraph(SupportState)
    graph.add_node("support", support_node)
    graph.add_edge(START, "support")
    graph.add_edge("support", END)
    return graph.compile(checkpointer=checkpointer)
