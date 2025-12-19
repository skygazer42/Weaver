# LLM client abstraction (step13)
- _chat_model already supports Azure/base_url/extra_body; add model registry with defaults per task (planner/writer/evaluator).
- Add timeout/retry per node via settings; enable httpx client reuse for connection pooling.
- Consider vendor routing (groq/deepseek/gemini) behind same interface.
