#!/usr/bin/env python3
# SPDX-FileCopyrightText: Philippe Coval <philippe.coval@vates.tech>
#
# SPDX-License-Identifier: MIT

"""
List all source packages from a Koji tag.

Usage:
    uv run list_source_packages.py <tag> [OPTIONS]

Examples:
    uv run list_source_packages.py c9s
    uv run list_source_packages.py f40 --latest
    uv run list_source_packages.py epel9 --output packages.txt
"""

# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "koji",
# ]
# ///

import argparse
import pdb
import sys

import koji


def get_session(opts):
    """Create and return a Koji client session."""
    if opts.no_verify_ssl:
        # Disable SSL verification warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    session = koji.ClientSession(
        opts.server,
        opts={"no_ssl_verify": opts.no_verify_ssl},
    )
    return session


def list_source_packages(session, tag, latest=False):
    """
    List all source packages in the given tag.

    Returns a dict mapping package name to its info:
        - nvr: name-version-release string
    """
    # Get the tag info
    tag_info = session.getTag(tag, strict=True)

    # Get all source builds in the tag
    builds = session.listTagged(tag, latest=latest)

    results = {}
    for build in builds:
        name = build["package_name"]
        if name not in results:
            results[name] = {
                "nvr": build["nvr"]
            }

    return tag_info, results


def main():
    parser = argparse.ArgumentParser(
        description="List all source packages from a Koji tag."
    )
    parser.add_argument(
        "tag",
        help="The Koji tag to query (e.g., c9s, f40, epel9)",
    )
    parser.add_argument(
        "--server",
        default="https://kojihub.xcp-ng.org",
        help="Koji hub server URL (default: %(default)s)",
    )
    parser.add_argument(
        "--web-url",
        default="https://koji.xcp-ng.org/",
        help="Koji web UI URL (default: %(default)s)",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Only show the latest build per package",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--pdb",
        action="store_true",
        help="Drop into pdb on error",
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Ignore SSL certificate verification errors",
    )

    global opts
    opts = parser.parse_args()
    session = get_session(opts)

    try:
        tag_info, packages = list_source_packages(
            session, opts.tag, latest=opts.latest
        )
    except Exception as e:
        if opts.pdb:
            print(f"Error: {e}", file=sys.stderr)
            pdb.post_mortem()
        else:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    if not packages:
        print(f"No source packages found in tag '{opts.tag}'.", file=sys.stderr)
        sys.exit(0)

    # Format output
    lines = []
    lines.append(f"Tag: {tag_info['name']}")
    lines.append(f"Total source packages: {len(packages)}")
    lines.append("-" * 60)

    for name, info in sorted(packages.items()):
        lines.append(f"{info['nvr']}")

    output_text = "\n".join(lines) + "\n"

    if opts.output:
        with open(opts.output, "w") as f:
            f.write(output_text)
        print(f"Output written to {opts.output}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
