from agent.workflows.deepsearch_optimized import _parse_list_output


def test_parse_list_output_parses_simple_python_list():
    assert _parse_list_output('["a", "b"]') == ["a", "b"]


def test_parse_list_output_does_not_execute_python_expressions():
    # If eval() is used, this becomes [0, 1, 2]. We want to avoid executing any
    # python expressions and instead fall back to a safe, non-evaluated parse.
    assert _parse_list_output("[x for x in range(3)]") == ["[x for x in range(3)]"]
