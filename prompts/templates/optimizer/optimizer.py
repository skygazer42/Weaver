"""
Prompt 迭代优化器核心模块

实现 Prompt 的自动优化循环：预测 -> 评估 -> 分析 -> 优化
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from common.config import settings

from .analyzer import ErrorAnalyzer
from .config import OptimizationConfig

logger = logging.getLogger(__name__)


class PromptOptimizer:
    """
    Prompt 迭代自动优化器

    核心流程：
    1. 使用当前 Prompt 在测试数据上预测
    2. 评估预测结果，计算准确率
    3. 分析错误样本，找出问题
    4. 生成优化后的 Prompt
    5. 重复以上步骤直到达到目标或轮次上限

    使用示例:
        config = OptimizationConfig.for_planner()
        optimizer = PromptOptimizer(config)
        result = await optimizer.optimize(test_data)
        print(result["best_prompt"])
    """

    OPTIMIZE_PROMPT = """你是一个专业的 Prompt 工程师。基于错误分析结果，优化以下 Prompt。

## 当前 Prompt
```
{current_prompt}
```

## 错误分析结果
- **错误模式**: {error_patterns}
- **Prompt 问题**: {prompt_issues}
- **改进建议**: {improvement_suggestions}
- **优先修复**: {priority_fix}

## 历史准确率变化
{accuracy_history}

## 优化要求
1. 保持 Prompt 的核心功能不变
2. 针对性地解决发现的问题
3. 保持简洁，避免过度复杂
4. 确保输出格式要求清晰明确
5. 如果之前的修改导致准确率下降，考虑回退部分改动

请直接输出优化后的完整 Prompt，不要有任何解释或额外文字。"""

    def __init__(self, config: OptimizationConfig):
        """
        初始化优化器

        Args:
            config: 优化配置
        """
        # 验证配置
        errors = config.validate()
        if errors:
            raise ValueError(f"Invalid config: {errors}")

        self.config = config

        resolved_base_url = config.api_base_url or settings.openai_base_url or None
        resolved_api_key = config.api_key or settings.openai_api_key or None
        resolved_timeout = config.timeout or settings.openai_timeout or None
        resolved_extra_body = None
        if settings.openai_extra_body:
            try:
                resolved_extra_body = json.loads(settings.openai_extra_body)
            except Exception:
                resolved_extra_body = None

        self.analyzer = ErrorAnalyzer(
            model=config.optimizer_model,
            temperature=0.3,
            api_base_url=resolved_base_url,
            api_key=resolved_api_key,
        )

        # 优化器 LLM
        optimizer_params = {
            "model": config.optimizer_model,
            "temperature": config.optimizer_temperature,
            "timeout": resolved_timeout,
        }
        if settings.use_azure and not resolved_base_url:
            optimizer_params.update(
                {
                    "azure_endpoint": settings.azure_endpoint or None,
                    "azure_deployment": config.optimizer_model,
                    "api_version": settings.azure_api_version or None,
                    "api_key": settings.azure_api_key or resolved_api_key,
                }
            )
        else:
            if resolved_base_url:
                optimizer_params["base_url"] = resolved_base_url
            optimizer_params["api_key"] = resolved_api_key
        if resolved_extra_body:
            optimizer_params["extra_body"] = resolved_extra_body

        self.optimizer_llm = ChatOpenAI(**optimizer_params)

        # 目标 LLM（被优化的模型）
        target_params = {
            "model": config.target_model,
            "temperature": config.temperature,
            "timeout": resolved_timeout,
        }
        if settings.use_azure and not resolved_base_url:
            target_params.update(
                {
                    "azure_endpoint": settings.azure_endpoint or None,
                    "azure_deployment": config.target_model,
                    "api_version": settings.azure_api_version or None,
                    "api_key": settings.azure_api_key or resolved_api_key,
                }
            )
        else:
            if resolved_base_url:
                target_params["base_url"] = resolved_base_url
            target_params["api_key"] = resolved_api_key
        if resolved_extra_body:
            target_params["extra_body"] = resolved_extra_body

        self.target_llm = ChatOpenAI(**target_params)

        # 状态追踪
        self.current_prompt = config.init_prompt
        self.best_prompt = config.init_prompt
        self.best_accuracy = 0.0
        self.accuracy_history: List[float] = []
        self.optimization_log: List[Dict] = []

        # 创建输出目录
        self.output_dir = config.output_dir / config.task_name
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def optimize(
        self,
        test_data: List[Dict],
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> Dict[str, Any]:
        """
        执行优化循环

        Args:
            test_data: 测试数据列表 [{"input": ..., "expected": ...}, ...]
            progress_callback: 进度回调 (epoch, total_epochs, accuracy)

        Returns:
            优化结果 {
                "best_prompt": str,
                "best_accuracy": float,
                "final_prompt": str,
                "final_accuracy": float,
                "accuracy_history": List[float],
                "optimization_log": List[Dict]
            }
        """
        logger.info(f"=" * 60)
        logger.info(f"Starting Prompt Optimization: {self.config.task_name}")
        logger.info(f"Test data: {len(test_data)} samples")
        logger.info(f"Epochs: {self.config.epochs}")
        logger.info(f"Target model: {self.config.target_model}")
        logger.info(f"=" * 60)

        no_improvement_count = 0

        for epoch in range(self.config.epochs):
            logger.info(f"\n{'=' * 50}")
            logger.info(f"Epoch {epoch + 1}/{self.config.epochs}")
            logger.info(f"{'=' * 50}")

            # Step 1: 预测
            logger.info("Step 1: Running predictions...")
            results = await self._predict_batch(test_data)
            logger.info(f"  Completed {len(results)} predictions")

            # Step 2: 评估
            logger.info("Step 2: Evaluating results...")
            accuracy, annotated_results = self.config.eval_function(results)
            self.accuracy_history.append(accuracy)
            logger.info(f"  Accuracy: {accuracy:.2%}")

            # 进度回调
            if progress_callback:
                progress_callback(epoch + 1, self.config.epochs, accuracy)

            # 更新最佳 Prompt
            if accuracy > self.best_accuracy:
                self.best_accuracy = accuracy
                self.best_prompt = self.current_prompt
                no_improvement_count = 0
                logger.info(f"  ✓ New best accuracy: {accuracy:.2%}")
            else:
                no_improvement_count += 1
                logger.info(f"  No improvement ({no_improvement_count} rounds)")

            # Step 3: 检查停止条件
            if accuracy >= self.config.accuracy_threshold:
                logger.info(
                    f"  ✓ Reached accuracy threshold ({self.config.accuracy_threshold:.0%})"
                )
                break

            if no_improvement_count >= self.config.no_improvement_rounds:
                logger.info(f"  ✓ No improvement for {no_improvement_count} rounds, stopping")
                break

            # Step 4: 分离样本
            correct_samples = [r for r in annotated_results if r.get("is_correct")]
            incorrect_samples = [r for r in annotated_results if not r.get("is_correct")]

            logger.info(f"Step 3: Analyzing {len(incorrect_samples)} incorrect samples...")

            if len(incorrect_samples) < self.config.min_error_samples:
                logger.info(
                    f"  Too few error samples ({len(incorrect_samples)}), skipping optimization"
                )
                continue

            # Step 5: 分析错误
            analysis = await self.analyzer.analyze(
                self.current_prompt,
                correct_samples[: self.config.error_sample_count],
                incorrect_samples[: self.config.error_sample_count],
            )

            logger.info(f"  Error patterns: {len(analysis.get('error_patterns', []))}")
            logger.info(f"  Prompt issues: {len(analysis.get('prompt_issues', []))}")

            # Step 6: 生成优化 Prompt
            logger.info("Step 4: Generating optimized prompt...")
            new_prompt = await self._generate_optimized_prompt(analysis)

            # 验证新 Prompt
            if not new_prompt or len(new_prompt) < 50:
                logger.warning("  Generated prompt too short, keeping current")
                continue

            self.current_prompt = new_prompt
            logger.info(f"  New prompt length: {len(new_prompt)} chars")

            # 记录日志
            self.optimization_log.append(
                {
                    "epoch": epoch + 1,
                    "accuracy": accuracy,
                    "correct_count": len(correct_samples),
                    "incorrect_count": len(incorrect_samples),
                    "analysis_summary": {
                        "error_patterns": analysis.get("error_patterns", [])[:3],
                        "priority_fix": analysis.get("priority_fix", ""),
                    },
                    "prompt_length": len(self.current_prompt),
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # 保存检查点
            if self.config.save_intermediate:
                self._save_checkpoint(epoch)

        # 汇总结果
        result = {
            "best_prompt": self.best_prompt,
            "best_accuracy": self.best_accuracy,
            "final_prompt": self.current_prompt,
            "final_accuracy": self.accuracy_history[-1] if self.accuracy_history else 0,
            "accuracy_history": self.accuracy_history,
            "optimization_log": self.optimization_log,
            "config": self.config.to_dict(),
            "completed_at": datetime.now().isoformat(),
        }

        self._save_final_result(result)

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Optimization Complete!")
        logger.info(f"Best accuracy: {self.best_accuracy:.2%}")
        logger.info(f"Accuracy history: {[f'{a:.1%}' for a in self.accuracy_history]}")
        logger.info(f"Results saved to: {self.output_dir}")
        logger.info(f"{'=' * 60}")

        return result

    async def _predict_batch(self, data: List[Dict]) -> List[Dict]:
        """批量预测"""
        from common.concurrency import get_concurrency_controller

        controller = get_concurrency_controller()
        results = []

        async def predict_one(item: Dict) -> Dict:
            try:
                # 格式化 Prompt
                try:
                    full_prompt = self.current_prompt.format(**item)
                except KeyError as e:
                    # 处理缺少的变量
                    full_prompt = self.current_prompt
                    for key, value in item.items():
                        full_prompt = full_prompt.replace(f"{{{key}}}", str(value))

                response = await self.target_llm.ainvoke(full_prompt)
                output = response.content if hasattr(response, "content") else str(response)

                return {**item, "output": output, "prompt_used": full_prompt[:500]}

            except Exception as e:
                logger.error(f"Prediction error: {e}")
                return {**item, "output": "", "error": str(e)}

        # 使用并发控制批量处理
        results = await controller.batch_process(
            data, predict_one, batch_size=min(self.config.sample_size, len(data))
        )

        # 过滤异常
        return [r for r in results if not isinstance(r, Exception)]

    async def _generate_optimized_prompt(self, analysis: Dict) -> str:
        """生成优化后的 Prompt"""
        prompt = ChatPromptTemplate.from_template(self.OPTIMIZE_PROMPT)

        try:
            response = await self.optimizer_llm.ainvoke(
                prompt.format_messages(
                    current_prompt=self.current_prompt,
                    error_patterns=json.dumps(
                        analysis.get("error_patterns", []), ensure_ascii=False, indent=2
                    ),
                    prompt_issues=json.dumps(
                        analysis.get("prompt_issues", []), ensure_ascii=False, indent=2
                    ),
                    improvement_suggestions=json.dumps(
                        analysis.get("improvement_suggestions", []), ensure_ascii=False, indent=2
                    ),
                    priority_fix=analysis.get("priority_fix", ""),
                    accuracy_history=str([f"{a:.1%}" for a in self.accuracy_history]),
                )
            )

            new_prompt = response.content.strip()

            # 清理可能的 markdown 代码块标记
            if new_prompt.startswith("```"):
                lines = new_prompt.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                new_prompt = "\n".join(lines).strip()

            return new_prompt

        except Exception as e:
            logger.error(f"Prompt optimization failed: {e}")
            return self.current_prompt

    def _save_checkpoint(self, epoch: int):
        """保存检查点"""
        checkpoint = {
            "epoch": epoch + 1,
            "current_prompt": self.current_prompt,
            "best_prompt": self.best_prompt,
            "best_accuracy": self.best_accuracy,
            "accuracy_history": self.accuracy_history,
            "timestamp": datetime.now().isoformat(),
        }

        path = self.output_dir / f"checkpoint_epoch_{epoch + 1}.json"
        path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2))
        logger.debug(f"Checkpoint saved: {path}")

    def _save_final_result(self, result: Dict):
        """保存最终结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 完整结果
        result_path = self.output_dir / f"result_{timestamp}.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

        # 最佳 Prompt
        prompt_path = self.output_dir / f"best_prompt_{timestamp}.txt"
        prompt_path.write_text(result["best_prompt"])

        # 最新结果链接（覆盖）
        latest_path = self.output_dir / "latest_result.json"
        latest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

        latest_prompt_path = self.output_dir / "best_prompt.txt"
        latest_prompt_path.write_text(result["best_prompt"])

        logger.info(f"Results saved to {self.output_dir}")

    def reset(self):
        """重置优化器状态"""
        self.current_prompt = self.config.init_prompt
        self.best_prompt = self.config.init_prompt
        self.best_accuracy = 0.0
        self.accuracy_history = []
        self.optimization_log = []


async def run_optimization(
    task_name: str,
    init_prompt: str,
    test_data: List[Dict],
    eval_function: Callable,
    **config_kwargs,
) -> Dict[str, Any]:
    """
    便捷函数：运行一次 Prompt 优化

    Args:
        task_name: 任务名称
        init_prompt: 初始 Prompt
        test_data: 测试数据
        eval_function: 评估函数
        **config_kwargs: 其他配置参数

    Returns:
        优化结果
    """
    config = OptimizationConfig(
        task_name=task_name, init_prompt=init_prompt, eval_function=eval_function, **config_kwargs
    )

    optimizer = PromptOptimizer(config)
    return await optimizer.optimize(test_data)
