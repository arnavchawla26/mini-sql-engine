"""Recursive-descent parser: token stream -> `SelectStmt` AST.

Supported grammar (case-insensitive keywords, roughly in EBNF):

    select_stmt  := SELECT [DISTINCT] select_list
                    FROM table_ref join_clause*
                    [WHERE condition]
                    [GROUP BY column_ref (',' column_ref)*]
                    [HAVING condition]
                    [ORDER BY order_item (',' order_item)*]
                    [LIMIT NUMBER] [';']

    select_list  := '*' | select_item (',' select_item)*
    select_item  := (IDENT '.' '*') | expr [[AS] IDENT]
    expr         := column_ref | literal | aggregate_call
    aggregate_call := (COUNT|SUM|AVG|MIN|MAX) '(' [DISTINCT] ('*' | expr) ')'
    column_ref   := IDENT ['.' IDENT]
    table_ref    := IDENT [[AS] IDENT]
    join_clause  := [INNER | LEFT [OUTER]] JOIN table_ref ON comparison

    condition    := or_expr
    or_expr      := and_expr (OR and_expr)*
    and_expr     := unary_cond (AND unary_cond)*
    unary_cond   := [NOT] primary_cond
    primary_cond := '(' condition ')' | comparison
    comparison   := expr (('=' | '!=' | '<>' | '<' | '<=' | '>' | '>=') expr
                           | IS [NOT] NULL)

    order_item   := column_ref [ASC | DESC]
"""

from __future__ import annotations

from typing import List

from .ast_nodes import (
    AggregateCall,
    ColumnRef,
    Comparison,
    JoinClause,
    Literal,
    Logical,
    Not,
    OrderItem,
    SelectItem,
    SelectStmt,
    Star,
    TableRef,
)
from .errors import ParseError
from .lexer import Token, tokenize

_AGGREGATE_FUNCS = {"COUNT", "SUM", "AVG", "MIN", "MAX"}
_COMPARISON_OPS = {"=", "!=", "<>", "<", "<=", ">", ">="}


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    # -- token stream helpers -------------------------------------------------
    def _peek(self, offset: int = 0) -> Token:
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.kind != "EOF":
            self.pos += 1
        return tok

    def _check_keyword(self, *words: str) -> bool:
        tok = self._peek()
        return tok.kind == "KEYWORD" and tok.value in words

    def _check_punct(self, value: str) -> bool:
        tok = self._peek()
        return tok.kind == "PUNCT" and tok.value == value

    def _check_op(self, value: str) -> bool:
        tok = self._peek()
        return tok.kind == "OP" and tok.value == value

    def _expect_keyword(self, word: str) -> Token:
        if not self._check_keyword(word):
            self._error(f"expected {word!r}")
        return self._advance()

    def _expect_punct(self, value: str) -> Token:
        if not self._check_punct(value):
            self._error(f"expected {value!r}")
        return self._advance()

    def _expect_ident(self) -> Token:
        tok = self._peek()
        if tok.kind != "IDENT":
            self._error("expected an identifier")
        return self._advance()

    def _error(self, message: str) -> None:
        tok = self._peek()
        raise ParseError(
            f"{message}, got {tok.kind} {tok.value!r} at line {tok.line}, col {tok.col}"
        )

    # -- entry point ------------------------------------------------------
    def parse_select(self) -> SelectStmt:
        self._expect_keyword("SELECT")

        distinct = False
        if self._check_keyword("DISTINCT"):
            self._advance()
            distinct = True

        select_items = self._parse_select_list()

        self._expect_keyword("FROM")
        from_table = self._parse_table_ref()

        joins: List[JoinClause] = []
        while self._check_keyword("JOIN", "INNER", "LEFT"):
            joins.append(self._parse_join_clause())

        where = None
        if self._check_keyword("WHERE"):
            self._advance()
            where = self._parse_condition()

        group_by: List[ColumnRef] = []
        if self._check_keyword("GROUP"):
            self._advance()
            self._expect_keyword("BY")
            group_by.append(self._parse_column_ref())
            while self._check_punct(","):
                self._advance()
                group_by.append(self._parse_column_ref())

        having = None
        if self._check_keyword("HAVING"):
            self._advance()
            having = self._parse_condition()

        order_by: List[OrderItem] = []
        if self._check_keyword("ORDER"):
            self._advance()
            self._expect_keyword("BY")
            order_by.append(self._parse_order_item())
            while self._check_punct(","):
                self._advance()
                order_by.append(self._parse_order_item())

        limit = None
        if self._check_keyword("LIMIT"):
            self._advance()
            tok = self._peek()
            if tok.kind != "NUMBER":
                self._error("expected a number after LIMIT")
            self._advance()
            limit = int(float(tok.value))

        if self._check_punct(";"):
            self._advance()

        if self._peek().kind != "EOF":
            self._error("unexpected trailing input")

        return SelectStmt(
            select_items=select_items,
            from_table=from_table,
            joins=joins,
            where=where,
            group_by=group_by,
            having=having,
            order_by=order_by,
            limit=limit,
            distinct=distinct,
        )

    # -- select list --------------------------------------------------------
    def _parse_select_list(self) -> List[SelectItem]:
        if self._check_punct("*"):
            self._advance()
            return [SelectItem(expr=Star())]

        items = [self._parse_select_item()]
        while self._check_punct(","):
            self._advance()
            items.append(self._parse_select_item())
        return items

    def _parse_select_item(self) -> SelectItem:
        # table.*
        if self._peek().kind == "IDENT" and self._peek(1).kind == "PUNCT" and self._peek(1).value == "." \
                and self._peek(2).kind == "PUNCT" and self._peek(2).value == "*":
            table = self._advance().value
            self._advance()  # '.'
            self._advance()  # '*'
            return SelectItem(expr=Star(table=table))

        expr = self._parse_scalar_expr()
        alias = None
        if self._check_keyword("AS"):
            self._advance()
            alias = self._expect_ident().value
        elif self._peek().kind == "IDENT":
            # bare alias, e.g. `SELECT price AS p` written as `SELECT price p`
            alias = self._advance().value
        return SelectItem(expr=expr, alias=alias)

    # -- expressions (column ref / literal / aggregate) ----------------------
    def _parse_scalar_expr(self):
        if self._peek().kind == "KEYWORD" and self._peek().value in _AGGREGATE_FUNCS:
            return self._parse_aggregate_call()
        if self._peek().kind in ("NUMBER", "STRING") or self._check_keyword("TRUE", "FALSE", "NULL"):
            return self._parse_literal()
        return self._parse_column_ref()

    def _parse_aggregate_call(self) -> AggregateCall:
        func = self._advance().value  # COUNT/SUM/AVG/MIN/MAX keyword
        self._expect_punct("(")
        distinct = False
        if self._check_keyword("DISTINCT"):
            self._advance()
            distinct = True
        if self._check_punct("*"):
            if func != "COUNT":
                self._error("only COUNT supports '*' as its argument")
            self._advance()
            arg = None
        else:
            arg = self._parse_column_ref()
        self._expect_punct(")")
        return AggregateCall(func=func, arg=arg, distinct=distinct)

    def _parse_column_ref(self) -> ColumnRef:
        first = self._expect_ident().value
        if self._check_punct("."):
            self._advance()
            second = self._expect_ident().value
            return ColumnRef(name=second, table=first)
        return ColumnRef(name=first)

    def _parse_literal(self) -> Literal:
        tok = self._peek()
        if tok.kind == "NUMBER":
            self._advance()
            if "." in tok.value:
                return Literal(float(tok.value))
            return Literal(int(tok.value))
        if tok.kind == "STRING":
            self._advance()
            return Literal(tok.value)
        if tok.kind == "KEYWORD" and tok.value == "TRUE":
            self._advance()
            return Literal(True)
        if tok.kind == "KEYWORD" and tok.value == "FALSE":
            self._advance()
            return Literal(False)
        if tok.kind == "KEYWORD" and tok.value == "NULL":
            self._advance()
            return Literal(None)
        self._error("expected a literal")
        raise AssertionError("unreachable")  # pragma: no cover

    # -- table references / joins -------------------------------------------
    def _parse_table_ref(self) -> TableRef:
        name = self._expect_ident().value
        alias = None
        if self._check_keyword("AS"):
            self._advance()
            alias = self._expect_ident().value
        elif self._peek().kind == "IDENT":
            alias = self._advance().value
        return TableRef(name=name, alias=alias)

    def _parse_join_clause(self) -> JoinClause:
        kind = "INNER"
        if self._check_keyword("INNER"):
            self._advance()
        elif self._check_keyword("LEFT"):
            self._advance()
            kind = "LEFT"
            if self._check_keyword("OUTER"):
                self._advance()
        self._expect_keyword("JOIN")
        table = self._parse_table_ref()
        self._expect_keyword("ON")
        cond = self._parse_condition()
        if not isinstance(cond, Comparison):
            self._error("JOIN ... ON currently supports a single comparison")
        return JoinClause(table=table, on=cond, kind=kind)

    # -- conditions (WHERE / HAVING / JOIN ON) -------------------------------
    def _parse_condition(self):
        return self._parse_or()

    def _parse_or(self):
        left = self._parse_and()
        while self._check_keyword("OR"):
            self._advance()
            right = self._parse_and()
            left = Logical(op="OR", left=left, right=right)
        return left

    def _parse_and(self):
        left = self._parse_unary_cond()
        while self._check_keyword("AND"):
            self._advance()
            right = self._parse_unary_cond()
            left = Logical(op="AND", left=left, right=right)
        return left

    def _parse_unary_cond(self):
        if self._check_keyword("NOT"):
            self._advance()
            return Not(self._parse_unary_cond())
        return self._parse_primary_cond()

    def _parse_primary_cond(self):
        if self._check_punct("("):
            self._advance()
            cond = self._parse_condition()
            self._expect_punct(")")
            return cond
        return self._parse_comparison()

    def _parse_comparison(self) -> Comparison:
        left = self._parse_scalar_expr()

        if self._check_keyword("IS"):
            self._advance()
            negate = False
            if self._check_keyword("NOT"):
                self._advance()
                negate = True
            self._expect_keyword("NULL")
            op = "IS NOT" if negate else "IS"
            return Comparison(left=left, op=op, right=Literal(None))

        tok = self._peek()
        if not (tok.kind == "OP" and tok.value in _COMPARISON_OPS):
            self._error("expected a comparison operator")
        op = self._advance().value
        right = self._parse_scalar_expr()
        return Comparison(left=left, op=op, right=right)

    # -- ORDER BY items -------------------------------------------------------
    def _parse_order_item(self) -> OrderItem:
        col = self._parse_column_ref()
        descending = False
        if self._check_keyword("ASC"):
            self._advance()
        elif self._check_keyword("DESC"):
            self._advance()
            descending = True
        return OrderItem(expr=col, descending=descending)


def parse(sql: str) -> SelectStmt:
    tokens = tokenize(sql)
    return Parser(tokens).parse_select()
