"""
Multi-Model Research Support.

Inspired by Open Deep Research's multi-model approach.
Enables using different LLM providers/models for different research phases.

Key Features:
1. Task-type based model routing
2. Provider abstraction (OpenAI, Anthropic, Azure, Ollama)
3. Fallback chains for reliability
4. Cost and latency tracking
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from langchain_core.language_models import BaseChatModel
from langchain_openai import AzureChatOpenAI, ChatOpenAI

# Optional import for Anthropic
try:
    from langchain_anthropic import ChatAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ChatAnthropic = None  # type: ignore
    ANTHROPIC_AVAILABLE = False

from common.config import settings

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Types of tasks in the research workflow."""
    ROUTING = "routing"           # Smart router decision
    PLANNING = "planning"         # Research plan generation
    QUERY_GEN = "query_gen"       # Search query generation
    RESEARCH = "research"         # Information gathering and analysis
    CRITIQUE = "critique"         # URL selection and quality assessment
    SYNTHESIS = "synthesis"       # Summarizing and synthesizing findings
    WRITING = "writing"           # Final report writing
    EVALUATION = "evaluation"     # Report quality evaluation
    REFLECTION = "reflection"     # Self-critique and strategy adjustment
    GAP_ANALYSIS = "gap_analysis" # Knowledge gap detection


class ModelProvider(str, Enum):
    """Supported model providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"
    CUSTOM = "custom"


@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    provider: ModelProvider
    model_name: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    timeout: Optional[int] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider.value,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }


@dataclass
class ModelUsageStats:
    """Track model usage statistics."""
    task_type: TaskType
    model_name: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0
    success: bool = True
    error: Optional[str] = None


class ModelRouter:
    """
    Routes tasks to appropriate models based on task type.

    Supports:
    - Task-specific model configuration
    - Provider abstraction
    - Fallback chains for reliability
    - Usage tracking
    """

    # Default temperature settings per task type
    DEFAULT_TEMPERATURES = {
        TaskType.ROUTING: 0.3,      # Deterministic routing
        TaskType.PLANNING: 0.6,     # Creative but structured
        TaskType.QUERY_GEN: 0.8,    # More exploratory
        TaskType.RESEARCH: 0.4,     # Balanced analysis
        TaskType.CRITIQUE: 0.2,     # Precise judgment
        TaskType.SYNTHESIS: 0.5,    # Balanced synthesis
        TaskType.WRITING: 0.6,      # Creative writing
        TaskType.EVALUATION: 0.3,   # Consistent evaluation
        TaskType.REFLECTION: 0.5,   # Thoughtful reflection
        TaskType.GAP_ANALYSIS: 0.4, # Analytical
    }

    def __init__(
        self,
        default_provider: ModelProvider = ModelProvider.OPENAI,
        task_model_map: Optional[Dict[TaskType, ModelConfig]] = None,
        fallback_configs: Optional[Dict[str, List[ModelConfig]]] = None,
    ):
        """
        Initialize the ModelRouter.

        Args:
            default_provider: Default provider for unspecified tasks
            task_model_map: Mapping of task types to model configs
            fallback_configs: Fallback chains per model (model_name -> fallback list)
        """
        self.default_provider = default_provider
        self.task_model_map = task_model_map or {}
        self.fallback_configs = fallback_configs or {}
        self.usage_stats: List[ModelUsageStats] = []

        # Load from settings
        self._load_from_settings()

    def _load_from_settings(self) -> None:
        """Load model configurations from settings."""
        # Map task types to setting attributes
        task_settings_map = {
            TaskType.PLANNING: "planner_model",
            TaskType.RESEARCH: "researcher_model",
            TaskType.WRITING: "writer_model",
            TaskType.EVALUATION: "evaluator_model",
            TaskType.CRITIQUE: "critic_model",
        }

        for task_type, setting_name in task_settings_map.items():
            model_name = getattr(settings, setting_name, None)
            if model_name:
                provider = self._detect_provider(model_name)
                temp = self.DEFAULT_TEMPERATURES.get(task_type, 0.5)
                self.task_model_map[task_type] = ModelConfig(
                    provider=provider,
                    model_name=model_name,
                    temperature=temp,
                )
                logger.debug(f"[ModelRouter] Loaded {task_type.value} -> {model_name}")

    def _detect_provider(self, model_name: str) -> ModelProvider:
        """Detect provider from model name."""
        model_lower = model_name.lower()

        if "claude" in model_lower:
            return ModelProvider.ANTHROPIC
        elif "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
            return ModelProvider.OPENAI
        elif "deepseek" in model_lower:
            return ModelProvider.DEEPSEEK
        elif settings.use_azure:
            return ModelProvider.AZURE
        elif settings.openai_base_url and "ollama" in settings.openai_base_url.lower():
            return ModelProvider.OLLAMA

        return ModelProvider.OPENAI

    # Task types that default to reasoning_model instead of primary_model
    REASONING_TASKS = {
        TaskType.ROUTING,
        TaskType.PLANNING,
        TaskType.EVALUATION,
        TaskType.CRITIQUE,
        TaskType.REFLECTION,
        TaskType.GAP_ANALYSIS,
    }

    def get_model_config(self, task_type: TaskType) -> ModelConfig:
        """
        Get model configuration for a specific task type.

        Args:
            task_type: The type of task to get config for

        Returns:
            ModelConfig for the specified task
        """
        if task_type in self.task_model_map:
            return self.task_model_map[task_type]

        # Use reasoning_model for analytical tasks, primary_model for others
        if task_type in self.REASONING_TASKS:
            default_model = getattr(settings, "reasoning_model", "") or getattr(
                settings, "primary_model", "gpt-4o"
            )
        else:
            default_model = getattr(settings, "primary_model", "gpt-4o")
        temp = self.DEFAULT_TEMPERATURES.get(task_type, 0.5)

        return ModelConfig(
            provider=self._detect_provider(default_model),
            model_name=default_model,
            temperature=temp,
        )

    def get_model_name(
        self,
        task_type: TaskType,
        config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Get model name for a task, respecting runtime config overrides.

        Priority:
        1. Runtime config task-specific override (e.g., configurable.planning_model)
        2. Runtime config general override (configurable.reasoning_model or configurable.model)
        3. Settings task-specific field (e.g., planner_model)
        4. Settings reasoning_model (for reasoning tasks) or primary_model

        Args:
            task_type: The type of task
            config: RunnableConfig dict with optional overrides

        Returns:
            Model name string
        """
        if config:
            cfg = config.get("configurable") or {}
            if isinstance(cfg, dict):
                # Check task-specific runtime override
                task_key = f"{task_type.value}_model"
                val = cfg.get(task_key)
                if isinstance(val, str) and val.strip():
                    return val.strip()

                # Check general runtime override
                if task_type in self.REASONING_TASKS:
                    val = cfg.get("reasoning_model")
                    if isinstance(val, str) and val.strip():
                        return val.strip()

                val = cfg.get("model")
                if isinstance(val, str) and val.strip():
                    return val.strip()

        # Fall back to settings-based config
        return self.get_model_config(task_type).model_name

    def build_model(
        self,
        task_type: TaskType,
        temperature_override: Optional[float] = None,
        config_override: Optional[Dict[str, Any]] = None,
    ) -> BaseChatModel:
        """
        Build and return a chat model for the specified task.

        Args:
            task_type: The type of task
            temperature_override: Override the default temperature
            config_override: Additional config overrides

        Returns:
            A configured BaseChatModel instance
        """
        model_config = self.get_model_config(task_type)

        temperature = temperature_override or model_config.temperature
        extra_params = {**model_config.extra_params, **(config_override or {})}

        logger.debug(
            f"[ModelRouter] Building model for {task_type.value}: "
            f"{model_config.model_name} (temp={temperature})"
        )

        return self._create_model(model_config, temperature, extra_params)

    def _create_model(
        self,
        config: ModelConfig,
        temperature: float,
        extra_params: Dict[str, Any],
    ) -> BaseChatModel:
        """Create a chat model instance from config."""
        provider = config.provider
        model_name = config.model_name

        common_params = {
            "model": model_name,
            "temperature": temperature,
            "timeout": config.timeout or settings.openai_timeout or None,
        }

        if config.max_tokens:
            common_params["max_tokens"] = config.max_tokens

        # Merge extra params
        common_params.update(extra_params)

        if provider == ModelProvider.ANTHROPIC:
            if not ANTHROPIC_AVAILABLE or ChatAnthropic is None:
                logger.warning(
                    f"[ModelRouter] Anthropic not available, falling back to OpenAI for {model_name}"
                )
                # Fall through to OpenAI
            else:
                return ChatAnthropic(
                    model=model_name,
                    temperature=temperature,
                    anthropic_api_key=config.api_key or settings.anthropic_api_key,
                    max_tokens=config.max_tokens or 4096,
                    timeout=config.timeout,
                )

        if provider == ModelProvider.AZURE:
            return AzureChatOpenAI(
                azure_deployment=model_name,
                azure_endpoint=settings.azure_endpoint,
                api_version=settings.azure_api_version,
                api_key=config.api_key or settings.azure_api_key,
                temperature=temperature,
                timeout=config.timeout,
            )

        elif provider == ModelProvider.OLLAMA:
            return ChatOpenAI(
                model=model_name,
                temperature=temperature,
                base_url=config.base_url or settings.openai_base_url or "http://localhost:11434/v1",
                api_key="ollama",  # Ollama doesn't require real API key
                timeout=config.timeout,
            )

        elif provider == ModelProvider.DEEPSEEK:
            return ChatOpenAI(
                model=model_name,
                temperature=temperature,
                api_key=config.api_key or settings.openai_api_key,
                base_url=config.base_url or settings.openai_base_url or "https://api.deepseek.com/v1",
                timeout=config.timeout,
            )

        else:  # OpenAI or Custom
            params = {
                "model": model_name,
                "temperature": temperature,
                "api_key": config.api_key or settings.openai_api_key,
                "timeout": config.timeout,
            }

            if config.base_url or settings.openai_base_url:
                params["base_url"] = config.base_url or settings.openai_base_url

            if settings.openai_extra_body:
                try:
                    params["extra_body"] = json.loads(settings.openai_extra_body)
                except json.JSONDecodeError:
                    pass

            return ChatOpenAI(**params)

    def get_fallback_chain(self, model_name: str) -> List[ModelConfig]:
        """Get fallback models for a given model."""
        return self.fallback_configs.get(model_name, [])

    def build_model_with_fallback(
        self,
        task_type: TaskType,
        temperature_override: Optional[float] = None,
    ) -> Tuple[BaseChatModel, List[BaseChatModel]]:
        """
        Build primary model and its fallback chain.

        Returns:
            Tuple of (primary_model, fallback_models_list)
        """
        primary_config = self.get_model_config(task_type)
        temperature = temperature_override or primary_config.temperature

        primary = self._create_model(primary_config, temperature, {})

        fallbacks = []
        for fb_config in self.get_fallback_chain(primary_config.model_name):
            fallbacks.append(self._create_model(fb_config, temperature, {}))

        return primary, fallbacks

    def set_task_model(self, task_type: TaskType, config: ModelConfig) -> None:
        """Set the model configuration for a specific task type."""
        self.task_model_map[task_type] = config
        logger.info(f"[ModelRouter] Set {task_type.value} -> {config.model_name}")

    def record_usage(self, stats: ModelUsageStats) -> None:
        """Record model usage statistics."""
        self.usage_stats.append(stats)

    def get_usage_summary(self) -> Dict[str, Any]:
        """Get summary of model usage."""
        if not self.usage_stats:
            return {"total_calls": 0}

        total_input = sum(s.input_tokens for s in self.usage_stats)
        total_output = sum(s.output_tokens for s in self.usage_stats)
        total_latency = sum(s.latency_ms for s in self.usage_stats)
        success_count = sum(1 for s in self.usage_stats if s.success)

        by_task = {}
        for s in self.usage_stats:
            task = s.task_type.value
            if task not in by_task:
                by_task[task] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
            by_task[task]["calls"] += 1
            by_task[task]["input_tokens"] += s.input_tokens
            by_task[task]["output_tokens"] += s.output_tokens

        return {
            "total_calls": len(self.usage_stats),
            "success_rate": success_count / len(self.usage_stats) if self.usage_stats else 0,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_latency_ms": total_latency,
            "by_task": by_task,
        }


# Global model router instance (lazy initialized)
_global_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get or create the global model router."""
    global _global_router
    if _global_router is None:
        _global_router = ModelRouter()
    return _global_router


def get_model_for_task(
    task_type: TaskType,
    temperature: Optional[float] = None,
    config: Optional[Dict[str, Any]] = None,
) -> BaseChatModel:
    """
    Convenience function to get a model for a specific task type.

    Args:
        task_type: The type of task
        temperature: Optional temperature override
        config: Optional config overrides

    Returns:
        Configured BaseChatModel
    """
    router = get_model_router()
    return router.build_model(task_type, temperature, config)


def build_research_models(config: Dict[str, Any] = None) -> Dict[str, BaseChatModel]:
    """
    Build all models needed for research workflow.

    Returns:
        Dict mapping task type name to model
    """
    router = get_model_router()

    return {
        "planner": router.build_model(TaskType.PLANNING),
        "researcher": router.build_model(TaskType.RESEARCH),
        "critic": router.build_model(TaskType.CRITIQUE),
        "writer": router.build_model(TaskType.WRITING),
        "evaluator": router.build_model(TaskType.EVALUATION),
    }
