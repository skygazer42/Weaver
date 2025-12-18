"""
Prompt 迭代自动优化系统

提供 Prompt 的自动评估、分析和优化功能。
参考 prompt-engineering 项目的 prompt 自动优化模式。
"""

from .config import OptimizationConfig, TaskType
from .optimizer import PromptOptimizer
from .analyzer import ErrorAnalyzer
from .evaluator import (
    eval_planner_quality,
    eval_writer_quality,
    eval_generic_quality
)

__all__ = [
    "OptimizationConfig",
    "TaskType",
    "PromptOptimizer",
    "ErrorAnalyzer",
    "eval_planner_quality",
    "eval_writer_quality",
    "eval_generic_quality",
]
