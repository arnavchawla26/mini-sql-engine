"""Exception hierarchy shared by every stage of the engine (lex -> parse -> plan -> execute)."""


class SqlMiniError(Exception):
    """Base class for every error this package raises."""


class LexError(SqlMiniError):
    """Raised when the tokenizer finds a character it doesn't understand."""


class ParseError(SqlMiniError):
    """Raised when the token stream doesn't match the supported grammar."""


class PlanError(SqlMiniError):
    """Raised when a syntactically valid statement can't be turned into a plan
    (unknown table/column, aggregate misuse, ambiguous column reference, ...)."""


class ExecutionError(SqlMiniError):
    """Raised for errors that only show up while running a plan (type mismatches, ...)."""
