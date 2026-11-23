"""Persist completed research steps when running inside a durable graph."""

from langgraph.func import task


def run_research_step(run_config, function, *args, **kwargs):
    if not (run_config or {}).get("configurable", {}).get("checkpoint_research_steps"):
        return function(*args, **kwargs)

    @task(name=function.__name__)
    def execute():
        return function(*args, **kwargs)

    return execute().result()
