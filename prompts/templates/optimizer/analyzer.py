"""
错误样本分析器模块

分析正确和错误样本，找出 Prompt 的问题并给出改进建议。
"""

import json
import logging
from typing import List, Dict, Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


class ErrorAnalyzer:
    """
    错误样本分析器

    对比正确和错误样本，使用 LLM 分析问题原因并给出改进建议。
    """

    ANALYSIS_PROMPT = """你是一个 Prompt 工程优化专家。请分析以下 Prompt 执行结果，找出问题并给出改进建议。

## 当前 Prompt
```
{current_prompt}
```

## 正确样本（模型输出符合预期）
{correct_samples}

## 错误样本（模型输出不符合预期）
{incorrect_samples}

## 评分详情
{score_details}

请深入分析：

1. **错误模式分析**：错误样本有哪些共同特征？是什么导致模型输出不符合预期？

2. **Prompt 问题诊断**：当前 Prompt 存在哪些问题？
   - 指令是否清晰？
   - 格式要求是否明确？
   - 是否缺少必要的约束或示例？

3. **改进建议**：具体如何修改 Prompt 来解决这些问题？

请返回 JSON 格式的分析结果：
```json
{{
    "error_patterns": [
        "错误模式1：描述",
        "错误模式2：描述"
    ],
    "prompt_issues": [
        "问题1：描述",
        "问题2：描述"
    ],
    "improvement_suggestions": [
        "建议1：具体修改方案",
        "建议2：具体修改方案"
    ],
    "priority_fix": "最需要优先解决的问题",
    "confidence": 0.8
}}
```"""

    QUICK_ANALYSIS_PROMPT = """快速分析以下错误样本，找出主要问题：

Prompt: {current_prompt}

错误样本:
{incorrect_samples}

返回 JSON:
{{"main_issue": "主要问题", "suggestion": "改进建议"}}"""

    def __init__(
        self,
        model: str = "gpt-4o",
        temperature: float = 0.3,
        api_base_url: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        params = {
            "model": model,
            "temperature": temperature
        }
        if api_base_url:
            params["base_url"] = api_base_url
        if api_key:
            params["api_key"] = api_key

        self.llm = ChatOpenAI(**params)
        self.model = model

    async def analyze(
        self,
        current_prompt: str,
        correct_samples: List[Dict],
        incorrect_samples: List[Dict],
        max_samples: int = 5
    ) -> Dict[str, Any]:
        """
        分析错误样本，返回改进建议

        Args:
            current_prompt: 当前使用的 Prompt
            correct_samples: 正确样本列表
            incorrect_samples: 错误样本列表
            max_samples: 每类样本的最大数量

        Returns:
            分析结果字典
        """
        if not incorrect_samples:
            logger.info("No incorrect samples to analyze")
            return {
                "error_patterns": [],
                "prompt_issues": [],
                "improvement_suggestions": [],
                "priority_fix": "No issues detected",
                "confidence": 1.0
            }

        prompt = ChatPromptTemplate.from_template(self.ANALYSIS_PROMPT)

        # 格式化样本
        correct_text = self._format_samples(correct_samples[:max_samples], "correct")
        incorrect_text = self._format_samples(incorrect_samples[:max_samples], "incorrect")
        score_details = self._format_score_details(incorrect_samples[:max_samples])

        try:
            response = await self.llm.ainvoke(
                prompt.format_messages(
                    current_prompt=current_prompt[:2000],  # 限制长度
                    correct_samples=correct_text,
                    incorrect_samples=incorrect_text,
                    score_details=score_details
                )
            )

            content = response.content

            # 解析 JSON
            result = self._parse_json_response(content)

            logger.info(f"Analysis complete: {len(result.get('error_patterns', []))} patterns found")
            return result

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return {
                "error_patterns": [f"Analysis error: {str(e)}"],
                "prompt_issues": [],
                "improvement_suggestions": [],
                "priority_fix": "Unable to analyze",
                "confidence": 0.0
            }

    async def quick_analyze(
        self,
        current_prompt: str,
        incorrect_samples: List[Dict],
        max_samples: int = 3
    ) -> Dict[str, str]:
        """
        快速分析，只返回主要问题和建议

        用于迭代过程中的快速反馈
        """
        if not incorrect_samples:
            return {"main_issue": "None", "suggestion": "No changes needed"}

        prompt = ChatPromptTemplate.from_template(self.QUICK_ANALYSIS_PROMPT)

        try:
            response = await self.llm.ainvoke(
                prompt.format_messages(
                    current_prompt=current_prompt[:1000],
                    incorrect_samples=self._format_samples(incorrect_samples[:max_samples], "error")
                )
            )

            result = self._parse_json_response(response.content)
            return {
                "main_issue": result.get("main_issue", "Unknown"),
                "suggestion": result.get("suggestion", "Review prompt")
            }

        except Exception as e:
            logger.error(f"Quick analysis failed: {e}")
            return {"main_issue": str(e), "suggestion": "Manual review needed"}

    def analyze_sync(
        self,
        current_prompt: str,
        correct_samples: List[Dict],
        incorrect_samples: List[Dict],
        max_samples: int = 5
    ) -> Dict[str, Any]:
        """
        同步版本的分析方法
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self.analyze(current_prompt, correct_samples, incorrect_samples, max_samples)
        )

    def _format_samples(
        self,
        samples: List[Dict],
        sample_type: str = "sample"
    ) -> str:
        """格式化样本为文本"""
        if not samples:
            return f"无{sample_type}样本"

        lines = []
        for i, s in enumerate(samples, 1):
            lines.append(f"### 样本 {i}")
            lines.append(f"**输入**: {str(s.get('input', ''))[:300]}")
            lines.append(f"**输出**: {str(s.get('output', ''))[:500]}")

            if 'expected' in s:
                lines.append(f"**预期**: {str(s.get('expected', ''))[:300]}")

            if 'total_score' in s:
                lines.append(f"**得分**: {s.get('total_score', 0):.2f}")

            lines.append("")

        return "\n".join(lines)

    def _format_score_details(self, samples: List[Dict]) -> str:
        """格式化评分详情"""
        if not samples:
            return "无评分详情"

        lines = ["| 样本 | 总分 | 详细分数 |", "| --- | --- | --- |"]

        for i, s in enumerate(samples, 1):
            scores = s.get("scores", {})
            score_str = ", ".join(f"{k}:{v:.2f}" for k, v in scores.items())
            total = s.get("total_score", 0)
            lines.append(f"| {i} | {total:.2f} | {score_str} |")

        return "\n".join(lines)

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """从响应中解析 JSON"""
        # 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 块
        try:
            # 查找 ```json ... ```
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))

            # 查找裸 JSON
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])

        except json.JSONDecodeError:
            pass

        # 回退：返回原始内容
        logger.warning("Failed to parse JSON response, returning raw content")
        return {
            "error_patterns": [],
            "prompt_issues": [content[:500]],
            "improvement_suggestions": [],
            "priority_fix": "Parse error",
            "confidence": 0.0
        }


class ComparativeAnalyzer:
    """
    对比分析器

    对比不同版本 Prompt 的效果差异
    """

    def __init__(self, model: str = "gpt-4o"):
        self.llm = ChatOpenAI(model=model, temperature=0.2)

    async def compare_prompts(
        self,
        prompt_a: str,
        prompt_b: str,
        results_a: List[Dict],
        results_b: List[Dict]
    ) -> Dict[str, Any]:
        """
        对比两个 Prompt 的效果

        Returns:
            对比分析结果
        """
        # 计算统计数据
        accuracy_a = sum(1 for r in results_a if r.get("is_correct")) / len(results_a) if results_a else 0
        accuracy_b = sum(1 for r in results_b if r.get("is_correct")) / len(results_b) if results_b else 0

        avg_score_a = sum(r.get("total_score", 0) for r in results_a) / len(results_a) if results_a else 0
        avg_score_b = sum(r.get("total_score", 0) for r in results_b) / len(results_b) if results_b else 0

        return {
            "prompt_a": {
                "accuracy": accuracy_a,
                "avg_score": avg_score_a,
                "sample_count": len(results_a)
            },
            "prompt_b": {
                "accuracy": accuracy_b,
                "avg_score": avg_score_b,
                "sample_count": len(results_b)
            },
            "improvement": {
                "accuracy_delta": accuracy_b - accuracy_a,
                "score_delta": avg_score_b - avg_score_a,
                "is_better": accuracy_b > accuracy_a
            }
        }
