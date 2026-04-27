import pytest
from app.owner_name import parse_owner_name


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Doe, John", ("Doe", "John")),
        ("  Doe ,  John  ", ("Doe", "John")),
        ("John Smith", ("John", "Smith")),
        ("Mary Jane Watson", ("Mary", "Jane Watson")),
        ("Cher", ("Cher", "")),
        ("", ("", "")),
        ("   ", ("", "")),
        ("a, b, c", ("a", "b, c")),
        ("  Solo  ", ("Solo", "")),
    ],
)
def test_parse_owner_name(raw, expected):
    assert parse_owner_name(raw) == expected
