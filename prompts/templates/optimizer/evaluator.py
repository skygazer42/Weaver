"""
Prompt 评估函数模块

提供不同任务类型的评估函数，用于衡量 Prompt 效果。
"""

import json
import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def eval_planner_quality(results: List[Dict]) -> Tuple[float, List[Dict]]:
    """
    评估 planner 输出质量

    评估维度：
    1. 查询数量是否在合理范围 (3-7)
    2. 查询是否与问题相关
    3. 查询是否具体可执行
    4. 查询是否有多样性

    Args:
        results: 预测结果列表
            [{"input": ..., "output": ..., "expected_queries": [...], ...}, ...]

    Returns:
        (准确率, 带标注的结果列表)
    """
    if not results:
        return 0.0, []

    correct = 0
    annotated = []

    for item in results:
        output = item.get("output", "")
        expected = item.get("expected_queries", [])
        input_text = item.get("input", "")

        # 解析输出
        generated = _parse_queries(output)

        # 评估各维度
        scores = {}

        # 1. 数量评分 (3-7 个查询)
        query_count = len(generated)
        if 3 <= query_count <= 7:
            scores["count"] = 1.0
        elif 1 <= query_count <= 2 or 8 <= query_count <= 10:
            scores["count"] = 0.5
        else:
            scores["count"] = 0.0

        # 2. 相关性评分 (基于关键词重叠)
        if expected:
            expected_keywords = _extract_keywords(" ".join(expected))
            generated_keywords = _extract_keywords(" ".join(generated))
            overlap = len(expected_keywords & generated_keywords)
            total = len(expected_keywords | generated_keywords)
            scores["relevance"] = overlap / total if total > 0 else 0.0
        else:
            # 无期望值时，检查查询是否包含输入关键词
            input_keywords = _extract_keywords(input_text)
            generated_keywords = _extract_keywords(" ".join(generated))
            overlap = len(input_keywords & generated_keywords)
            scores["relevance"] = min(1.0, overlap / 3) if input_keywords else 0.5

        # 3. 具体性评分 (查询长度和词数)
        if generated:
            avg_words = sum(len(q.split()) for q in generated) / len(generated)
            if 3 <= avg_words <= 10:
                scores["specificity"] = 1.0
            elif 2 <= avg_words < 3 or 10 < avg_words <= 15:
                scores["specificity"] = 0.7
            else:
                scores["specificity"] = 0.3
        else:
            scores["specificity"] = 0.0

        # 4. 多样性评分 (查询之间的差异)
        if len(generated) >= 2:
            unique_words = set()
            total_words = 0
            for q in generated:
                words = set(q.lower().split())
                unique_words.update(words)
                total_words += len(words)
            scores["diversity"] = len(unique_words) / total_words if total_words > 0 else 0.0
        else:
            scores["diversity"] = 0.5

        # 综合评分
        weights = {"count": 0.2, "relevance": 0.4, "specificity": 0.2, "diversity": 0.2}
        total_score = sum(scores[k] * weights[k] for k in weights)

        is_correct = total_score >= 0.6

        if is_correct:
            correct += 1

        annotated.append(
            {
                **item,
                "generated_queries": generated,
                "scores": scores,
                "total_score": total_score,
                "is_correct": is_correct,
            }
        )

    accuracy = correct / len(results)
    logger.info(f"Planner evaluation: accuracy={accuracy:.2%}, total={len(results)}")

    return accuracy, annotated


def eval_writer_quality(results: List[Dict]) -> Tuple[float, List[Dict]]:
    """
    评估 writer 输出质量

    评估维度：
    1. 结构完整性 (标题、段落、列表)
    2. 引用规范性
    3. 内容长度适当性
    4. 格式正确性 (Markdown)

    Args:
        results: 预测结果列表

    Returns:
        (准确率, 带标注的结果列表)
    """
    if not results:
        return 0.0, []

    correct = 0
    annotated = []

    for item in results:
        output = item.get("output", "") or item.get("generated_report", "")

        scores = {}

        # 1. 结构评分
        has_headers = bool(re.search(r"^#{1,3}\s+.+", output, re.MULTILINE))
        has_lists = bool(re.search(r"^[-*]\s+.+", output, re.MULTILINE)) or bool(
            re.search(r"^\d+\.\s+.+", output, re.MULTILINE)
        )
        has_paragraphs = len(output.split("\n\n")) >= 2

        structure_score = (
            (0.4 if has_headers else 0) + (0.3 if has_lists else 0) + (0.3 if has_paragraphs else 0)
        )
        scores["structure"] = structure_score

        # 2. 引用评分
        citation_pattern = r"\[S\d+-\d+\]"
        citations = re.findall(citation_pattern, output)
        if citations:
            unique_citations = len(set(citations))
            scores["citations"] = min(1.0, unique_citations / 3)
        else:
            scores["citations"] = 0.0

        # 3. 长度评分
        word_count = len(output.split())
        if 200 <= word_count <= 1500:
            scores["length"] = 1.0
        elif 100 <= word_count < 200 or 1500 < word_count <= 2500:
            scores["length"] = 0.7
        elif 50 <= word_count < 100 or 2500 < word_count <= 4000:
            scores["length"] = 0.4
        else:
            scores["length"] = 0.1

        # 4. 格式评分 (Markdown 语法)
        has_bold = "**" in output or "__" in output
        has_code = "`" in output
        has_links = bool(re.search(r"\[.+\]\(.+\)", output))

        format_features = sum([has_bold, has_code, has_links, has_headers])
        scores["format"] = min(1.0, format_features / 3)

        # 综合评分
        weights = {"structure": 0.35, "citations": 0.25, "length": 0.2, "format": 0.2}
        total_score = sum(scores[k] * weights[k] for k in weights)

        is_correct = total_score >= 0.5

        if is_correct:
            correct += 1

        annotated.append(
            {
                **item,
                "scores": scores,
                "total_score": total_score,
                "is_correct": is_correct,
                "word_count": word_count,
                "citation_count": len(citations) if citations else 0,
            }
        )

    accuracy = correct / len(results)
    logger.info(f"Writer evaluation: accuracy={accuracy:.2%}, total={len(results)}")

    return accuracy, annotated


def eval_generic_quality(
    results: List[Dict], criteria: Dict[str, Dict[str, Any]] = None
) -> Tuple[float, List[Dict]]:
    """
    通用质量评估函数

    支持自定义评估标准

    Args:
        results: 预测结果列表
        criteria: 评估标准配置
            {
                "criterion_name": {
                    "type": "contains" | "regex" | "length" | "json_valid",
                    "value": ...,
                    "weight": 0.25
                }
            }

    Returns:
        (准确率, 带标注的结果列表)
    """
    if not results:
        return 0.0, []

    # 默认标准
    if criteria is None:
        criteria = {
            "not_empty": {"type": "length", "min": 10, "weight": 0.3},
            "reasonable_length": {"type": "length", "min": 50, "max": 5000, "weight": 0.3},
            "has_content": {"type": "contains", "values": ["。", ".", ",", "，"], "weight": 0.4},
        }

    correct = 0
    annotated = []

    for item in results:
        output = item.get("output", "")
        scores = {}

        for name, config in criteria.items():
            criterion_type = config.get("type")
            weight = config.get("weight", 1.0 / len(criteria))

            if criterion_type == "contains":
                values = config.get("values", [])
                if isinstance(values, str):
                    values = [values]
                scores[name] = 1.0 if any(v in output for v in values) else 0.0

            elif criterion_type == "regex":
                pattern = config.get("pattern", "")
                scores[name] = 1.0 if re.search(pattern, output) else 0.0

            elif criterion_type == "length":
                length = len(output)
                min_len = config.get("min", 0)
                max_len = config.get("max", float("inf"))
                scores[name] = 1.0 if min_len <= length <= max_len else 0.0

            elif criterion_type == "json_valid":
                try:
                    json.loads(output)
                    scores[name] = 1.0
                except:
                    # 尝试提取 JSON
                    start = output.find("{")
                    end = output.rfind("}") + 1
                    if start >= 0 and end > start:
                        try:
                            json.loads(output[start:end])
                            scores[name] = 0.8
                        except:
                            scores[name] = 0.0
                    else:
                        scores[name] = 0.0

            elif criterion_type == "custom":
                custom_func = config.get("function")
                if callable(custom_func):
                    scores[name] = custom_func(output, item)
                else:
                    scores[name] = 0.5

        # 计算加权总分
        total_weight = sum(c.get("weight", 1.0 / len(criteria)) for c in criteria.values())
        total_score = (
            sum(scores[name] * criteria[name].get("weight", 1.0 / len(criteria)) for name in scores)
            / total_weight
            if total_weight > 0
            else 0
        )

        is_correct = total_score >= 0.6

        if is_correct:
            correct += 1

        annotated.append(
            {**item, "scores": scores, "total_score": total_score, "is_correct": is_correct}
        )

    accuracy = correct / len(results)
    return accuracy, annotated


def _parse_queries(output: str) -> List[str]:
    """
    从输出中解析查询列表

    支持 JSON 格式和纯文本格式
    """
    queries = []

    # 尝试解析 JSON
    try:
        start = output.find("{")
        end = output.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(output[start:end])
            if isinstance(data.get("queries"), list):
                queries = [q for q in data["queries"] if isinstance(q, str) and q.strip()]
                if queries:
                    return queries
    except json.JSONDecodeError:
        pass

    # 尝试解析数组
    try:
        start = output.find("[")
        end = output.rfind("]") + 1
        if start >= 0 and end > start:
            data = json.loads(output[start:end])
            if isinstance(data, list):
                queries = [q for q in data if isinstance(q, str) and q.strip()]
                if queries:
                    return queries
    except json.JSONDecodeError:
        pass

    # 回退到按行解析
    for line in output.split("\n"):
        line = line.strip()
        # 移除列表标记
        line = re.sub(r"^[\d]+[.)]\s*", "", line)
        line = re.sub(r"^[-*]\s*", "", line)
        line = re.sub(r'^"(.+)"$', r"\1", line)
        if line and len(line) > 5:
            queries.append(line)

    return queries[:10]  # 最多返回 10 个


def _extract_keywords(text: str) -> set:
    """
    从文本中提取关键词

    移除停用词，返回有意义的词汇
    """
    # 简单的英文停用词
    stop_words = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "dare",
        "ought",
        "used",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "and",
        "but",
        "if",
        "or",
        "because",
        "until",
        "while",
        "what",
        "which",
        "who",
        "this",
        "that",
        "these",
        "those",
        "i",
        "me",
        "my",
        "myself",
        "we",
        "our",
        "ours",
    }

    # 中文停用词
    chinese_stop_words = {
        "的",
        "了",
        "和",
        "是",
        "就",
        "都",
        "而",
        "及",
        "与",
        "着",
        "或",
        "一个",
        "没有",
        "我们",
        "你们",
        "他们",
        "它们",
        "这个",
        "那个",
        "什么",
        "怎么",
        "如何",
        "为什么",
        "哪里",
        "哪个",
    }

    stop_words.update(chinese_stop_words)

    # 分词并过滤
    words = re.findall(r"\b\w+\b", text.lower())
    keywords = {w for w in words if w not in stop_words and len(w) > 1}

    return keywords
