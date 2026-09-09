import pytest

from sqlmini.errors import LexError
from sqlmini.lexer import tokenize


def kinds_values(tokens):
    return [(t.kind, t.value) for t in tokens]


def test_tokenizes_simple_select():
    tokens = tokenize("SELECT a, b FROM t")
    assert kinds_values(tokens) == [
        ("KEYWORD", "SELECT"),
        ("IDENT", "a"),
        ("PUNCT", ","),
        ("IDENT", "b"),
        ("KEYWORD", "FROM"),
        ("IDENT", "t"),
        ("EOF", ""),
    ]


def test_keywords_are_case_insensitive():
    tokens = tokenize("select * from t where x = 1")
    kinds = [t.kind for t in tokens]
    assert kinds[0] == "KEYWORD"
    assert tokens[0].value == "SELECT"  # normalized to uppercase
    assert tokens[4].value == "WHERE"


def test_multi_char_operators_prefer_longest_match():
    tokens = tokenize("a <= b AND c <> d AND e >= f AND g != h")
    ops = [t.value for t in tokens if t.kind == "OP"]
    assert ops == ["<=", "<>", ">=", "!="]


def test_string_literal_with_escaped_quote():
    tokens = tokenize("SELECT 'it''s' FROM t")
    strings = [t for t in tokens if t.kind == "STRING"]
    assert len(strings) == 1
    assert strings[0].value == "it's"


def test_number_literals_integer_and_float():
    tokens = tokenize("SELECT 42, 3.14 FROM t")
    numbers = [t.value for t in tokens if t.kind == "NUMBER"]
    assert numbers == ["42", "3.14"]


def test_line_comment_is_skipped():
    tokens = tokenize("SELECT a -- this is a comment\nFROM t")
    assert kinds_values(tokens) == [
        ("KEYWORD", "SELECT"),
        ("IDENT", "a"),
        ("KEYWORD", "FROM"),
        ("IDENT", "t"),
        ("EOF", ""),
    ]


def test_unterminated_string_raises():
    with pytest.raises(LexError):
        tokenize("SELECT 'unterminated FROM t")


def test_unexpected_character_raises():
    with pytest.raises(LexError):
        tokenize("SELECT a FROM t WHERE a $ 1")


def test_qualified_column_dot_is_punct():
    tokens = tokenize("SELECT t.a FROM t")
    assert kinds_values(tokens)[1:5] == [
        ("IDENT", "t"),
        ("PUNCT", "."),
        ("IDENT", "a"),
        ("KEYWORD", "FROM"),
    ]
