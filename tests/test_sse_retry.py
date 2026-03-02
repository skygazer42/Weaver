import pytest


def test_format_sse_retry_renders_standard_frame():
    from common.sse import format_sse_retry

    assert format_sse_retry(2000) == "retry: 2000\n\n"


@pytest.mark.parametrize("value,expected", [(0, "retry: 0\n\n"), (-10, "retry: 0\n\n")])
def test_format_sse_retry_clamps_negative_to_zero(value, expected):
    from common.sse import format_sse_retry

    assert format_sse_retry(value) == expected

