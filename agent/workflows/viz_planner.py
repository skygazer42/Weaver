"""
Visualization Planner for Research Reports.

Analyzes research findings and generates appropriate visualizations.
Creates charts, diagrams, and infographics from data.

Key Features:
1. Data pattern detection in compressed knowledge
2. Chart type recommendation
3. Matplotlib-based chart generation
4. Base64 image embedding for reports
"""

import base64
import io
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Check for matplotlib
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    plt = None
    MATPLOTLIB_AVAILABLE = False


class ChartType(str, Enum):
    """Supported chart types."""
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    TABLE = "table"


@dataclass
class ChartSpec:
    """Specification for a chart to generate."""
    chart_type: ChartType
    title: str
    data: Dict[str, Any]
    description: str = ""
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chart_type": self.chart_type.value,
            "title": self.title,
            "data": self.data,
            "description": self.description,
            "source": self.source,
        }


@dataclass
class GeneratedChart:
    """A generated chart with image data."""
    spec: ChartSpec
    image_base64: str
    width: int = 800
    height: int = 600
    format: str = "png"

    def to_markdown(self) -> str:
        """Generate markdown for embedding the chart."""
        return f"""
### {self.spec.title}

![{self.spec.title}](data:image/{self.format};base64,{self.image_base64})

*{self.spec.description}*
"""

    def to_html(self) -> str:
        """Generate HTML for embedding the chart."""
        return f"""
<figure class="chart">
    <img src="data:image/{self.format};base64,{self.image_base64}"
         alt="{self.spec.title}"
         style="max-width: 100%; height: auto;">
    <figcaption>{self.spec.title}: {self.spec.description}</figcaption>
</figure>
"""


class ChartDataResponse(BaseModel):
    """LLM response for chart data extraction."""
    has_chartable_data: bool = Field(description="Whether the content has data suitable for visualization")
    charts: List[Dict[str, Any]] = Field(default_factory=list, description="List of chart specifications")


DATA_EXTRACTION_PROMPT = """
# 任务
分析以下研究内容，识别可以可视化的数据。

# 研究内容
{content}

# 要求
1. 识别可以图表化的数据（数字、比较、趋势、分布）
2. 为每个可图表化的数据点提供结构化规格

# 可用图表类型
- bar: 柱状图（用于比较不同类别）
- line: 折线图（用于趋势和时间序列）
- pie: 饼图（用于占比分布）
- comparison: 对比图（用于A vs B比较）
- table: 表格（用于多维数据）

# 输出格式
对每个可图表化的数据，提供：
- chart_type: 图表类型
- title: 图表标题
- data: 数据 (格式: {{"labels": [...], "values": [...]}})
- description: 简短描述
- source: 数据来源

# 示例
```json
{{
    "has_chartable_data": true,
    "charts": [
        {{
            "chart_type": "bar",
            "title": "全球AI市场规模对比",
            "data": {{"labels": ["2020", "2021", "2022", "2023"], "values": [50, 80, 120, 180]}},
            "description": "全球AI市场规模持续增长",
            "source": "来源1"
        }}
    ]
}}
```
"""


class VizPlanner:
    """
    Plans and generates visualizations for research reports.

    Analyzes research findings, identifies chartable data,
    and generates appropriate visualizations.
    """

    def __init__(self, llm: BaseChatModel, config: Dict[str, Any] = None):
        self.llm = llm
        self.config = config or {}

    def analyze_for_charts(
        self,
        compressed_knowledge: Dict[str, Any],
        report_text: str = "",
    ) -> List[ChartSpec]:
        """
        Analyze research content for chartable data.

        Args:
            compressed_knowledge: Compressed knowledge dict
            report_text: Optional report text for additional context

        Returns:
            List of ChartSpec objects
        """
        # Build content for analysis
        content_parts = []

        # Add statistics from compressed knowledge
        stats = compressed_knowledge.get("statistics", [])
        if stats:
            content_parts.append("## 统计数据")
            for s in stats:
                content_parts.append(f"- {s.get('metric', '')}: {s.get('value', '')} ({s.get('context', '')})")

        # Add facts that might contain numbers
        facts = compressed_knowledge.get("facts", [])
        numeric_facts = [f for f in facts if any(c.isdigit() for c in f.get("fact", ""))]
        if numeric_facts:
            content_parts.append("## 数值相关发现")
            for f in numeric_facts[:10]:
                content_parts.append(f"- {f.get('fact', '')}")

        # Add relevant parts of report
        if report_text:
            # Extract sections with numbers
            lines = report_text.split("\n")
            numeric_lines = [l for l in lines if re.search(r'\d+[%万亿]|\d+\.\d+', l)]
            if numeric_lines:
                content_parts.append("## 报告中的数据")
                content_parts.extend(numeric_lines[:15])

        if not content_parts:
            return []

        content = "\n".join(content_parts)

        prompt = ChatPromptTemplate.from_messages([
            ("user", DATA_EXTRACTION_PROMPT)
        ])

        try:
            structured_llm = self.llm.with_structured_output(ChartDataResponse)
            response = structured_llm.invoke(
                prompt.format_messages(content=content[:6000]),
                config=self.config,
            )

            if not response.has_chartable_data:
                return []

            chart_specs = []
            for chart_data in response.charts:
                try:
                    chart_type = ChartType(chart_data.get("chart_type", "bar"))
                    spec = ChartSpec(
                        chart_type=chart_type,
                        title=chart_data.get("title", "Chart"),
                        data=chart_data.get("data", {}),
                        description=chart_data.get("description", ""),
                        source=chart_data.get("source", ""),
                    )
                    chart_specs.append(spec)
                except Exception as e:
                    logger.debug(f"Failed to parse chart spec: {e}")

            logger.info(f"[VizPlanner] Identified {len(chart_specs)} chartable datasets")
            return chart_specs

        except Exception as e:
            logger.warning(f"Chart analysis failed: {e}")
            return []

    def generate_chart(self, spec: ChartSpec) -> Optional[GeneratedChart]:
        """
        Generate a chart image from specification.

        Args:
            spec: Chart specification

        Returns:
            GeneratedChart with base64 image or None if failed
        """
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("Matplotlib not available for chart generation")
            return None

        try:
            # Set up Chinese font support
            plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS']
            plt.rcParams['axes.unicode_minus'] = False

            fig, ax = plt.subplots(figsize=(10, 6), dpi=100)

            data = spec.data
            labels = data.get("labels", [])
            values = data.get("values", [])

            if not labels or not values:
                logger.warning(f"No data for chart: {spec.title}")
                plt.close(fig)
                return None

            # Generate chart based on type
            if spec.chart_type == ChartType.BAR:
                self._draw_bar_chart(ax, labels, values, spec.title)
            elif spec.chart_type == ChartType.LINE:
                self._draw_line_chart(ax, labels, values, spec.title)
            elif spec.chart_type == ChartType.PIE:
                self._draw_pie_chart(ax, labels, values, spec.title)
            elif spec.chart_type == ChartType.COMPARISON:
                self._draw_comparison_chart(ax, labels, values, spec.title)
            else:
                self._draw_bar_chart(ax, labels, values, spec.title)

            # Convert to base64
            buf = io.BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight', facecolor='white')
            buf.seek(0)
            image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
            plt.close(fig)

            return GeneratedChart(
                spec=spec,
                image_base64=image_base64,
                width=1000,
                height=600,
            )

        except Exception as e:
            logger.error(f"Chart generation failed: {e}")
            if 'fig' in locals():
                plt.close(fig)
            return None

    def _draw_bar_chart(self, ax, labels: List, values: List, title: str) -> None:
        """Draw a bar chart."""
        colors = plt.cm.Blues([0.4 + 0.1 * i for i in range(len(labels))])
        bars = ax.bar(labels, values, color=colors, edgecolor='white')
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_ylabel('Value')

        # Add value labels on bars
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    f'{val}', ha='center', va='bottom', fontsize=10)

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

    def _draw_line_chart(self, ax, labels: List, values: List, title: str) -> None:
        """Draw a line chart."""
        ax.plot(labels, values, marker='o', linewidth=2, markersize=8, color='#3498db')
        ax.fill_between(labels, values, alpha=0.3, color='#3498db')
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_ylabel('Value')
        ax.grid(True, alpha=0.3)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

    def _draw_pie_chart(self, ax, labels: List, values: List, title: str) -> None:
        """Draw a pie chart."""
        colors = plt.cm.Set3([i/len(labels) for i in range(len(labels))])
        wedges, texts, autotexts = ax.pie(
            values, labels=labels, autopct='%1.1f%%',
            colors=colors, startangle=90,
            explode=[0.02] * len(labels),
        )
        ax.set_title(title, fontsize=14, fontweight='bold')
        plt.tight_layout()

    def _draw_comparison_chart(self, ax, labels: List, values: List, title: str) -> None:
        """Draw a horizontal comparison chart."""
        colors = ['#3498db' if v >= 0 else '#e74c3c' for v in values]
        bars = ax.barh(labels, values, color=colors, edgecolor='white')
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.axvline(x=0, color='gray', linestyle='-', linewidth=0.5)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        plt.tight_layout()

    def generate_all_charts(
        self,
        compressed_knowledge: Dict[str, Any],
        report_text: str = "",
        max_charts: int = 3,
    ) -> List[GeneratedChart]:
        """
        Analyze content and generate all appropriate charts.

        Args:
            compressed_knowledge: Compressed knowledge dict
            report_text: Optional report text
            max_charts: Maximum charts to generate

        Returns:
            List of GeneratedChart objects
        """
        specs = self.analyze_for_charts(compressed_knowledge, report_text)

        if not specs:
            return []

        charts = []
        for spec in specs[:max_charts]:
            chart = self.generate_chart(spec)
            if chart:
                charts.append(chart)

        logger.info(f"[VizPlanner] Generated {len(charts)} charts")
        return charts


def embed_charts_in_report(
    report: str,
    charts: List[GeneratedChart],
    format: str = "markdown",
) -> str:
    """
    Embed generated charts into a report.

    Args:
        report: Original report text
        charts: Generated charts to embed
        format: Output format (markdown or html)

    Returns:
        Report with embedded charts
    """
    if not charts:
        return report

    # Find a good insertion point (after introduction/before conclusion)
    chart_section = "\n\n## 数据可视化\n\n"

    for chart in charts:
        if format == "html":
            chart_section += chart.to_html() + "\n\n"
        else:
            chart_section += chart.to_markdown() + "\n\n"

    # Try to insert before "结论" or "参考" section
    conclusion_patterns = [r'\n##\s*结论', r'\n##\s*总结', r'\n##\s*参考']
    for pattern in conclusion_patterns:
        match = re.search(pattern, report)
        if match:
            insert_pos = match.start()
            return report[:insert_pos] + chart_section + report[insert_pos:]

    # Fallback: append at the end (before references if present)
    return report + chart_section
