from __future__ import annotations

import asyncio
import html
import json
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from agent.core.llm_factory import create_chat_model
from common.config import settings

CSV_SKILL = Path(__file__).parent / "skills" / "csv-analysis"


class AnalysisError(Exception):
    """A user-actionable analysis error."""


def _sandbox_profile(contents: bytes) -> dict:
    script = (CSV_SKILL / "analyze.py").read_text(encoding="utf-8")
    if settings.e2b_api_key.strip():
        from e2b import CommandExitException
        from e2b_code_interpreter import Sandbox

        with Sandbox.create(api_key=settings.e2b_api_key, timeout=120) as sandbox:
            sandbox.files.write("/tmp/weaver-csv.py", script)
            sandbox.files.write("/tmp/weaver-input.csv", contents)
            try:
                output = sandbox.commands.run(
                    "python /tmp/weaver-csv.py < /tmp/weaver-input.csv", timeout=45
                ).stdout
            except CommandExitException as error:
                if error.stderr.startswith("Invalid CSV:"):
                    raise AnalysisError(error.stderr.strip()[:300]) from error
                raise
    else:
        docker = shutil.which("docker")
        if docker is None:
            raise AnalysisError("启动 Docker 或设置 E2B_API_KEY 后即可运行分析。")
        result = subprocess.run(
            [
                docker,
                "run",
                "--rm",
                "-i",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "64",
                "--memory",
                "128m",
                "--cpus",
                "1",
                "python:3.11-slim",
                "python",
                "-c",
                script,
            ],
            input=contents,
            capture_output=True,
            timeout=75,
            check=False,
        )
        if result.returncode:
            error = result.stderr.decode("utf-8", errors="replace").strip()
            if error.startswith("Invalid CSV:"):
                raise AnalysisError(error[:300])
            raise AnalysisError("Docker 沙盒执行失败。请检查 Docker 和 Python 镜像。")
        output = result.stdout
    return json.loads(output)


def _chart_svg(profile: dict) -> str:
    columns = profile["columns"][:20]
    height = 70 + 30 * len(columns)
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="720" height="{height}" viewBox="0 0 720 {height}" role="img">',
        "<title>各列非空值占比</title>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<g font-family="system-ui, sans-serif" font-size="14" fill="#172434">',
        '<text x="24" y="32" font-size="19" font-weight="600">各列非空值占比</text>',
    ]
    for index, column in enumerate(columns):
        y = 49 + index * 30
        ratio = column["filled"] / max(profile["rows"], 1)
        label = column["name"]
        if len(label) > 13:
            label = label[:12] + "…"
        elements.extend(
            (
                f'<text x="24" y="{y + 14}">{html.escape(label)}</text>',
                f'<rect x="232" y="{y}" width="382" height="18" rx="3" fill="#e7edf2"/>',
                f'<rect x="232" y="{y}" width="{382 * ratio:.2f}" height="18" rx="3" fill="#227e75"/>',
                f'<text x="633" y="{y + 14}">{ratio:.0%}</text>',
            )
        )
    return "\n".join([*elements, "</g></svg>"])


def _profile_markdown(profile: dict) -> str:
    rows = profile["rows"]
    report = [
        "# CSV 分析报告",
        "",
        f"共 {rows} 条数据和 {len(profile['columns'])} 列。",
        "",
        "| 列 | 非空 | 缺失 | 数字 | 最小值 | 最大值 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for column in profile["columns"]:
        name = html.escape(column["name"]).replace("\\", "\\\\").replace("|", "\\|")
        minimum = "—" if column["min"] is None else f"{column['min']:g}"
        maximum = "—" if column["max"] is None else f"{column['max']:g}"
        report.append(
            f"| {name} | {column['filled']} | {rows - column['filled']} | "
            f"{column['numeric']} | {minimum} | {maximum} |"
        )
    if len(profile["columns"]) > 20:
        report.extend(("", "图表展示前 20 列。表格包含所有列。"))
    return "\n".join(report)


async def run_csv_analysis(
    contents: bytes,
    model: str,
    prompt: str,
    on_report: Callable[[], Awaitable[None]],
) -> tuple[str, str]:
    sandbox_run = asyncio.create_task(asyncio.to_thread(_sandbox_profile, contents))
    try:
        profile = await asyncio.shield(sandbox_run)
    except asyncio.CancelledError:
        with suppress(Exception):
            await sandbox_run
        raise
    await on_report()
    skill = (CSV_SKILL / "SKILL.md").read_text(encoding="utf-8")
    request = "分析重点\n" + (prompt or "概述数据质量并指出值得复核的地方。")
    request += "\n\n沙盒统计\n" + json.dumps(profile, ensure_ascii=False)
    llm = create_chat_model(model, temperature=0).bind(max_tokens=1600)
    async with asyncio.timeout(90):
        result = await llm.ainvoke([SystemMessage(content=skill), HumanMessage(content=request)])
    interpretation = result.text.strip()
    if not interpretation:
        raise AnalysisError("模型没有返回可用的解读。请重试或选择其他模型。")

    report = _profile_markdown(profile) + "\n\n## 模型解读\n\n" + interpretation + "\n"
    return report, _chart_svg(profile)
