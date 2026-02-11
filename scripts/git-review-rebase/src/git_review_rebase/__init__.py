"""git-review-rebase: Interactive tool for reviewing rebased git branches."""

__version__ = "0.1.0"

from .app import GitReviewRebase
from .cli import parse_args

__all__ = ["GitReviewRebase", "parse_args"]
