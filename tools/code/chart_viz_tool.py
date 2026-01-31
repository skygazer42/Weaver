import base64
import io
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
from langchain.tools import tool


@tool
def chart_visualize(
    series: List[float],
    labels: Optional[List[str]] = None,
    title: str = "Chart",
    kind: str = "line",
) -> Dict[str, Any]:
    """
    Generate a simple chart (line/bar) from numeric series; returns base64 PNG.
    """
    plt.clf()
    fig, ax = plt.subplots(figsize=(5, 3))
    x = list(range(len(series)))
    if kind == "bar":
        ax.bar(x, series)
    else:
        ax.plot(x, series, marker="o")
    if labels and len(labels) == len(series):
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    buf = io.BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format="png")
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    plt.close(fig)
    return {"image": data, "title": title, "kind": kind}
