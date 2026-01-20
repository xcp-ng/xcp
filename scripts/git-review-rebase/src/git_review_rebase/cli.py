"""Command-line argument parsing."""

import argparse
import os

from .constants import CacheFlags


def parse_args() -> argparse.Namespace:
    """Parse the arguments and return them."""
    parser = argparse.ArgumentParser(
        prog="git-review-rebase", description="Interactive tool for reviewing rebased git branches"
    )
    parser.add_argument(
        "--repository",
        type=str,
        default=".",
        help="Path to git repository (default: current directory)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_false",
        default=True,
        dest="cache",
        help="Disable patchid caching",
    )
    parser.add_argument("left_range", help="Left range in format: base..branch")
    parser.add_argument("right_range", help="Right range in format: base..branch")
    args = parser.parse_args()

    args.repository = os.path.expanduser(args.repository)

    args.cache_flags = CacheFlags(0)
    if args.cache:
        args.cache_flags = CacheFlags.READ_FROM_CACHE | CacheFlags.WRITE_TO_CACHE

    return args
