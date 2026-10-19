import pytest

from app.multi_agent.router import parse_agent_label


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("presale", "presale"),
        ("postsale", "postsale"),
        ("complaint", "complaint"),
        (" PRESALE\n", "presale"),
        ("`complaint`", "complaint"),
        ("", None),
        (None, None),
        ("unknown", None),
        ("the answer is presale", None),
    ],
)
def test_parse_agent_label(raw, expected):
    assert parse_agent_label(raw) == expected