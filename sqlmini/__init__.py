"""mini-sql-engine: a small hand-written SQL engine over in-memory CSV tables."""

from .engine import Engine, QueryResult
from .errors import SqlMiniError, ParseError, ExecutionError, PlanError

__all__ = [
    "Engine",
    "QueryResult",
    "SqlMiniError",
    "ParseError",
    "ExecutionError",
    "PlanError",
]

__version__ = "0.1.0"
