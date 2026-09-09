"""Hand-written tokenizer for the supported SQL subset.

Produces a flat list of `Token`s terminated by an EOF token. Keeps line/column
info so the parser can raise errors that point at the right place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .errors import LexError

KEYWORDS = {
    "SELECT", "FROM", "WHERE", "AS", "AND", "OR", "NOT",
    "JOIN", "INNER", "LEFT", "OUTER", "ON",
    "GROUP", "BY", "HAVING", "ORDER", "ASC", "DESC", "LIMIT",
    "NULL", "TRUE", "FALSE", "IS", "DISTINCT",
    "COUNT", "SUM", "AVG", "MIN", "MAX",
}

# Longest-match-first so `<=` isn't tokenized as `<` then `=`.
SYMBOLS = [
    "<=", ">=", "!=", "<>", "=", "<", ">",
    "(", ")", ",", ".", "*", ";",
]


@dataclass(frozen=True)
class Token:
    kind: str  # KEYWORD | IDENT | NUMBER | STRING | OP | PUNCT | EOF
    value: str
    line: int
    col: int

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Token({self.kind}, {self.value!r})"


def tokenize(text: str) -> List[Token]:
    tokens: List[Token] = []
    i = 0
    n = len(text)
    line = 1
    col = 1

    def advance(k: int = 1) -> None:
        nonlocal i, line, col
        for _ in range(k):
            if i < n and text[i] == "\n":
                line += 1
                col = 1
            else:
                col += 1
            i += 1

    while i < n:
        ch = text[i]

        if ch in " \t\r\n":
            advance()
            continue

        # -- comments: `--` to end of line -----------------------------
        if ch == "-" and i + 1 < n and text[i + 1] == "-":
            while i < n and text[i] != "\n":
                advance()
            continue

        start_line, start_col = line, col

        # -- string literal: 'single quoted', '' escapes a quote -------
        if ch == "'":
            advance()
            buf = []
            closed = False
            while i < n:
                if text[i] == "'" and i + 1 < n and text[i + 1] == "'":
                    buf.append("'")
                    advance(2)
                    continue
                if text[i] == "'":
                    advance()
                    closed = True
                    break
                buf.append(text[i])
                advance()
            if not closed:
                raise LexError(f"Unterminated string literal starting at line {start_line}, col {start_col}")
            tokens.append(Token("STRING", "".join(buf), start_line, start_col))
            continue

        # -- number literal: 123, 123.45 --------------------------------
        if ch.isdigit():
            buf = [ch]
            advance()
            seen_dot = False
            while i < n and (text[i].isdigit() or (text[i] == "." and not seen_dot)):
                if text[i] == ".":
                    seen_dot = True
                buf.append(text[i])
                advance()
            tokens.append(Token("NUMBER", "".join(buf), start_line, start_col))
            continue

        # -- identifier / keyword: letters, digits, underscore ----------
        if ch.isalpha() or ch == "_":
            buf = [ch]
            advance()
            while i < n and (text[i].isalnum() or text[i] == "_"):
                buf.append(text[i])
                advance()
            word = "".join(buf)
            upper = word.upper()
            if upper in KEYWORDS:
                tokens.append(Token("KEYWORD", upper, start_line, start_col))
            else:
                tokens.append(Token("IDENT", word, start_line, start_col))
            continue

        # -- multi/single char symbols -----------------------------------
        matched = None
        for sym in SYMBOLS:
            if text.startswith(sym, i):
                matched = sym
                break
        if matched is not None:
            # '*' is only ever a select-list wildcard in this grammar (there's
            # no arithmetic), so it's tagged PUNCT alongside the other
            # structural characters; the comparison operators are OP.
            kind = "PUNCT" if matched in "(),.;*" else "OP"
            tokens.append(Token(kind, matched, start_line, start_col))
            advance(len(matched))
            continue

        raise LexError(f"Unexpected character {ch!r} at line {start_line}, col {start_col}")

    tokens.append(Token("EOF", "", line, col))
    return tokens
