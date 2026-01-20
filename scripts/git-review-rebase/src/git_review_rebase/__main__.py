"""Entry point for git-review-rebase."""

from .app import GitReviewRebase
from .cli import parse_args


def main():
    """Main entry point."""
    args = parse_args()
    app = GitReviewRebase(args)
    app.run()


if __name__ == "__main__":
    main()
