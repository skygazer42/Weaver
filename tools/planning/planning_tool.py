from typing import List, Dict, Any
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from common.config import settings


@tool
def plan_steps(goal: str, max_steps: int = 5) -> List[str]:
    """
    Generate 3-5 concise steps to achieve the goal.
    """
    llm = ChatOpenAI(
        model=settings.reasoning_model or settings.primary_model,
        temperature=0.2,
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout or None,
    )
    prompt = f"Goal: {goal}\nReturn {max_steps} short steps as a numbered list."
    resp = llm.invoke(prompt)
    content = getattr(resp, "content", "") or ""
    lines = [line.strip(" -") for line in content.splitlines() if line.strip()]
    steps = []
    for line in lines:
        if line and len(steps) < max_steps:
            # strip leading numbering
            if line[:2].isdigit() or line[:1].isdigit():
                line = line.split(" ",1)[1] if " " in line else line
            steps.append(line.strip())
    return steps[:max_steps]
