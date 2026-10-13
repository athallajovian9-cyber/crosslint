"""crosslint: find portability hazards before CI does."""

from .finding import Finding
from .rules import RULE_DOCS, RULES

__all__ = ["Finding", "RULES", "RULE_DOCS", "lint", "__version__"]
__version__ = "0.1.0"


def lint(paths, disabled=(), exclude=()):
    from .engine import lint as _lint

    return _lint(paths, disabled, exclude)
