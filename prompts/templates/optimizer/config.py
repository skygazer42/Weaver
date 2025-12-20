"""
Prompt 优化配置模块
"""

from dataclasses import dataclass, field
from typing import Callable, List, Dict, Any, Optional
from pathlib import Path
from enum import Enum


class TaskType(Enum):
    """任务类型枚举"""
    PLANNER = "planner"       # 研究规划任务
    WRITER = "writer"         # 报告写作任务
    EVALUATOR = "evaluator"   # 评估任务
    CUSTOM = "custom"         # 自定义任务


@dataclass
class OptimizationConfig:
    """
    Prompt 优化任务配置

    Attributes:
        task_name: 任务名称，用于标识和存储
        task_type: 任务类型
        init_prompt: 初始 Prompt 模板
        eval_function: 评估函数 (results) -> (accuracy, annotated_results)
        epochs: 优化迭代轮次
        sample_size: 每轮评估样本数
        error_sample_count: 错误分析时使用的样本数
        output_dir: 结果输出目录
        save_intermediate: 是否保存中间结果
        optimizer_model: 用于优化的模型
        target_model: 被优化的目标模型
        temperature: 目标模型温度
        accuracy_threshold: 提前停止的准确率阈值
    """

    task_name: str
    task_type: TaskType = TaskType.CUSTOM
    init_prompt: str = ""
    eval_function: Optional[Callable[[List[Dict]], tuple]] = None

    # 优化参数
    epochs: int = 3
    sample_size: int = 50
    error_sample_count: int = 10
    min_error_samples: int = 3  # 最少需要的错误样本数才进行分析

    # 输出配置
    output_dir: Path = field(default_factory=lambda: Path("prompts/results"))
    save_intermediate: bool = True
    save_best_only: bool = False  # 只保存最佳结果

    # 模型配置
    optimizer_model: str = "gpt-4o"
    target_model: str = "gpt-4o-mini"
    temperature: float = 0.3
    optimizer_temperature: float = 0.5

    # 停止条件
    accuracy_threshold: float = 0.95  # 达到此准确率提前停止
    no_improvement_rounds: int = 2    # 连续无提升轮数则停止

    # API 配置
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout: int = 60

    def __post_init__(self):
        """初始化后处理"""
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_planner(
        cls,
        init_prompt: Optional[str] = None,
        **kwargs
    ) -> "OptimizationConfig":
        """
        创建 planner 任务配置

        Args:
            init_prompt: 初始 Prompt，为 None 时使用默认值
            **kwargs: 其他配置参数
        """
        from .evaluator import eval_planner_quality

        default_prompt = """你是一个专业的研究规划专家。根据用户的问题，生成 3-7 个有针对性的搜索查询。

要求：
1. 查询应该具体、可执行
2. 覆盖问题的不同方面
3. 避免重复或过于宽泛的查询

用户问题: {input}

返回 JSON 格式:
{{"queries": ["query1", "query2", ...], "reasoning": "规划理由"}}"""

        return cls(
            task_name="planner",
            task_type=TaskType.PLANNER,
            init_prompt=init_prompt or default_prompt,
            eval_function=eval_planner_quality,
            **kwargs
        )

    @classmethod
    def for_writer(
        cls,
        init_prompt: Optional[str] = None,
        **kwargs
    ) -> "OptimizationConfig":
        """
        创建 writer 任务配置
        """
        from .evaluator import eval_writer_quality

        default_prompt = """你是一个专业的研究分析师。基于提供的研究资料，撰写一份结构清晰的报告。

要求：
1. 包含执行摘要
2. 使用 Markdown 格式
3. 引用来源 [S1-1] 格式
4. 突出关键发现

研究资料:
{context}

问题: {query}

请撰写报告:"""

        return cls(
            task_name="writer",
            task_type=TaskType.WRITER,
            init_prompt=init_prompt or default_prompt,
            eval_function=eval_writer_quality,
            **kwargs
        )

    def validate(self) -> List[str]:
        """
        验证配置是否完整

        Returns:
            错误消息列表，为空表示验证通过
        """
        errors = []

        if not self.task_name:
            errors.append("task_name is required")

        if not self.init_prompt:
            errors.append("init_prompt is required")

        if self.eval_function is None:
            errors.append("eval_function is required")

        if self.epochs < 1:
            errors.append("epochs must be >= 1")

        if self.sample_size < 1:
            errors.append("sample_size must be >= 1")

        return errors

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_name": self.task_name,
            "task_type": self.task_type.value,
            "epochs": self.epochs,
            "sample_size": self.sample_size,
            "error_sample_count": self.error_sample_count,
            "output_dir": str(self.output_dir),
            "optimizer_model": self.optimizer_model,
            "target_model": self.target_model,
            "temperature": self.temperature,
            "accuracy_threshold": self.accuracy_threshold,
        }
