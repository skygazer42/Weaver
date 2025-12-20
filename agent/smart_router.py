"""
Smart Router - LLM-based intelligent query routing.

Inspired by Manus's intelligent routing that classifies user queries
into the most appropriate execution mode.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from common.config import settings

logger = logging.getLogger(__name__)

# Route types
RouteType = Literal["direct", "agent", "web", "deep", "clarify"]


class RouteDecision(BaseModel):
    """Structured output for routing decisions."""

    route: RouteType = Field(
        description="The execution route: 'direct' for simple answers, 'agent' for tool-calling tasks, 'web' for quick web search, 'deep' for comprehensive research, 'clarify' for ambiguous queries"
    )
    reasoning: str = Field(
        description="Brief explanation of why this route was chosen"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence level of this routing decision (0-1)"
    )
    suggested_queries: List[str] = Field(
        default_factory=list,
        description="For 'deep' or 'web' routes, suggested search queries"
    )
    clarification_question: str = Field(
        default="",
        description="For 'clarify' route, the question to ask the user"
    )


ROUTER_SYSTEM_PROMPT = """You are an intelligent query router. Analyze the user's query and determine the best execution path.

## Route Types:

1. **direct** - Simple questions that can be answered from knowledge
   - Factual questions with clear answers
   - Simple calculations or conversions
   - Common knowledge questions
   - Examples: "What is the capital of France?", "Convert 100 USD to EUR", "What is 2+2?"

2. **agent** - Tasks requiring tool usage or multi-step actions
   - Code execution or analysis
   - File operations
   - Browser automation
   - API calls or external tool usage
   - Multi-step workflows
   - Examples: "Write a Python script that...", "Browse to example.com and...", "Create a file with..."

3. **web** - Quick web search for current information
   - Recent events or news
   - Current prices, weather, or data
   - Simple lookup queries
   - Examples: "What's the weather in NYC?", "Latest news about...", "Current stock price of..."

4. **deep** - Comprehensive research requiring multiple searches
   - Complex research questions
   - Comparative analysis
   - In-depth topic exploration
   - Multi-faceted queries
   - Examples: "Compare the AI strategies of...", "Analyze the market trends...", "Research the pros and cons of..."

5. **clarify** - Ambiguous queries needing clarification
   - Unclear or incomplete requests
   - Multiple possible interpretations
   - Missing key information
   - Examples: "Help me with this", "Fix the bug", "Make it better"

## Decision Guidelines:

- Default to 'direct' for simple queries
- Use 'agent' when tools are explicitly or implicitly needed
- Use 'web' for time-sensitive or current information
- Use 'deep' for research-heavy queries requiring synthesis
- Use 'clarify' only when truly ambiguous

## Response Format:

Provide your decision as a JSON object with:
- route: one of "direct", "agent", "web", "deep", "clarify"
- reasoning: brief explanation
- confidence: 0.0 to 1.0
- suggested_queries: for web/deep routes, 2-3 search queries
- clarification_question: for clarify route, the question to ask
"""


class SmartRouter:
    """
    LLM-based intelligent router that classifies user queries.

    Features:
    - Structured output for reliable parsing
    - Confidence-based fallback
    - Intent detection
    - Tool requirement detection
    """

    def __init__(
        self,
        model: str = None,
        temperature: float = 0.1,
        fallback_route: RouteType = "direct",
    ):
        self.model = model or settings.reasoning_model or "gpt-4o-mini"
        self.temperature = temperature
        self.fallback_route = fallback_route
        self._llm = None

    def _get_llm(self) -> ChatOpenAI:
        """Lazy initialization of LLM."""
        if self._llm is None:
            params = {
                "model": self.model,
                "temperature": self.temperature,
                "api_key": settings.openai_api_key,
                "timeout": settings.openai_timeout or 30,
            }
            if settings.use_azure:
                params.update({
                    "azure_endpoint": settings.azure_endpoint,
                    "azure_deployment": self.model,
                    "api_version": settings.azure_api_version,
                    "api_key": settings.azure_api_key or settings.openai_api_key,
                })
            elif settings.openai_base_url:
                params["base_url"] = settings.openai_base_url

            self._llm = ChatOpenAI(**params)
        return self._llm

    def route(
        self,
        query: str,
        images: Optional[List[Dict[str, Any]]] = None,
        context: Optional[str] = None,
        config: Optional[RunnableConfig] = None,
    ) -> RouteDecision:
        """
        Route a query to the appropriate execution path.

        Args:
            query: User's input query
            images: Optional list of image data
            context: Optional additional context
            config: Optional runnable config

        Returns:
            RouteDecision with route type and metadata
        """
        try:
            llm = self._get_llm()

            # Build messages
            messages = [SystemMessage(content=ROUTER_SYSTEM_PROMPT)]

            # Build user content
            user_content = query
            if context:
                user_content = f"Context: {context}\n\nQuery: {query}"
            if images:
                user_content += f"\n\n[User has attached {len(images)} image(s)]"

            messages.append(HumanMessage(content=user_content))

            # Get structured output
            response = llm.with_structured_output(RouteDecision).invoke(
                messages,
                config=config,
            )

            logger.info(f"[smart_router] route={response.route} confidence={response.confidence:.2f}")
            return response

        except Exception as e:
            logger.warning(f"[smart_router] failed: {e}, using fallback")
            return RouteDecision(
                route=self.fallback_route,
                reasoning=f"Routing failed: {str(e)}",
                confidence=0.5,
            )

    def detect_tool_requirements(self, query: str) -> List[str]:
        """
        Detect which tools might be needed for a query.

        Returns list of tool categories that might be needed.
        """
        query_lower = query.lower()
        tools_needed = []

        # Code execution indicators
        if any(kw in query_lower for kw in [
            "python", "code", "script", "program", "execute", "run",
            "calculate", "compute", "analyze data", "plot", "chart", "graph"
        ]):
            tools_needed.append("python")

        # Browser indicators
        if any(kw in query_lower for kw in [
            "browse", "website", "webpage", "click", "navigate", "open url",
            "login", "fill form", "screenshot", "scrape"
        ]):
            tools_needed.append("browser")

        # Search indicators
        if any(kw in query_lower for kw in [
            "search", "find", "look up", "latest", "current", "recent",
            "news", "weather", "price", "today"
        ]):
            tools_needed.append("web_search")

        # File indicators
        if any(kw in query_lower for kw in [
            "file", "create", "write", "read", "save", "download", "upload",
            "document", "pdf", "excel", "csv"
        ]):
            tools_needed.append("files")

        # Shell/command indicators
        if any(kw in query_lower for kw in [
            "command", "terminal", "shell", "install", "package", "npm", "pip",
            "git", "docker", "build", "deploy"
        ]):
            tools_needed.append("shell")

        return tools_needed


# Singleton instance
_router_instance: Optional[SmartRouter] = None


def get_smart_router() -> SmartRouter:
    """Get the singleton SmartRouter instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = SmartRouter()
    return _router_instance


def smart_route(
    query: str,
    images: Optional[List[Dict[str, Any]]] = None,
    context: Optional[str] = None,
    config: Optional[RunnableConfig] = None,
    override_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Smart routing function for use in graph nodes.

    Args:
        query: User's input query
        images: Optional list of image data
        context: Optional additional context
        config: Optional runnable config
        override_mode: If set, skip LLM routing and use this mode

    Returns:
        Dict with route info for state update
    """
    # Check for explicit mode override from config
    if override_mode:
        logger.info(f"[smart_route] using override mode: {override_mode}")
        return {
            "route": override_mode,
            "routing_reasoning": f"Mode override: {override_mode}",
            "routing_confidence": 1.0,
        }

    # Use LLM-based routing
    router = get_smart_router()
    decision = router.route(query, images, context, config)

    result = {
        "route": decision.route,
        "routing_reasoning": decision.reasoning,
        "routing_confidence": decision.confidence,
    }

    # Add suggested queries for research routes
    if decision.route in ("web", "deep") and decision.suggested_queries:
        result["suggested_queries"] = decision.suggested_queries

    # Add clarification question
    if decision.route == "clarify" and decision.clarification_question:
        result["clarification_question"] = decision.clarification_question

    return result
