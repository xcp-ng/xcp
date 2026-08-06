#!/usr/bin/env python3
# SPDX-FileCopyrightText: Philippe Coval <philippe.coval@vates.tech>
#
# SPDX-License-Identifier: MIT

"""
List all source packages from a Koji tag.

Usage:
    uv run koji-helper.py list <tag> [OPTIONS]
    uv run koji-helper.py update <to_tag> <from_tag> [OPTIONS]

Examples:
    uv run koji-helper.py list c9s
    uv run koji-helper.py list f40 --latest
    uv run koji-helper.py list epel9 --output packages.txt
    uv run koji-helper.py update c9s f40
    uv run koji-helper.py update c9s f40 --output updates.txt
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


def list_update_source_packages(session, to_tag, from_tag=None, latest=False):
    """
    List source packages that have been updated from from_tag to to_tag.

    If from_tag is provided, returns packages where the NVR in to_tag
    is different from the NVR in from_tag.

    Returns a dict mapping package name to its info:
        - nvr: name-version-release string in to_tag
        - base_nvr: name-version-release string in from_tag (if provided)
    """
    to_tag_info, to_packages = list_source_packages(session, to_tag, latest=latest)

    base_packages = {}
    if from_tag:
        _, base_packages = list_source_packages(session, from_tag, latest=latest)

    results = {}
    for name, info in to_packages.items():
        to_nvr = info["nvr"]
        if from_tag:
            base_nvr = base_packages.get(name, {}).get("nvr")
            if base_nvr and base_nvr != to_nvr:
                results[name] = {"nvr": to_nvr, "base_nvr": base_nvr}
        else:
            results[name] = {"nvr": to_nvr}

    return to_tag_info, results


def do_list(session, opts):
    tag_info, packages = list_source_packages(
        session, opts.tag, latest=opts.latest
    )

    if not packages:
        print(f"No source packages found in tag '{opts.tag}'.", file=sys.stderr)
        sys.exit(0)

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


def do_list_update(session, opts):
    tag_info, packages = list_update_source_packages(
        session, opts.tag, from_tag=opts.base_tag, latest=opts.latest
    )

    if not packages:
        print(f"No updated source packages found.", file=sys.stderr)
        sys.exit(0)

    lines = []
    lines.append(f"Updated packages from {opts.base_tag or 'any tag'} to {tag_info['name']}")
    lines.append(f"Total updated source packages: {len(packages)}")
    lines.append("-" * 60)

    for name, info in sorted(packages.items()):
        lines.append(f"{name}: {info['base_nvr']} -> {info['nvr']}")

    output_text = "\n".join(lines) + "\n"

    if opts.output:
        with open(opts.output, "w") as f:
            f.write(output_text)
        print(f"Output written to {opts.output}")
    else:
        print(output_text)


def main():
    parser = argparse.ArgumentParser(
        description="Koji helper script."
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

    subparsers = parser.add_subparsers(dest="command")

    # list command
    list_parser = subparsers.add_parser("list", help="List all source packages from a tag")
    list_parser.add_argument("tag", help="The Koji tag to query (e.g., c9s, f40, epel9)")

    # list-update command
    list_update_parser = subparsers.add_parser("list-update", help="List updated source packages between tags")
    list_update_parser.add_argument("tag", help="The target Koji tag")
    list_update_parser.add_argument("base_tag", help="The source Koji tag to compare against")

    global opts
    opts = parser.parse_args()

    if not opts.command:
        parser.print_help()
        sys.exit(1)

    session = get_session(opts)

    try:
        if opts.command == "list":
            do_list(session, opts)
        elif opts.command == "list-update":
            do_list_update(session, opts)
    except Exception as e:
        if opts.pdb:
            print(f"Error: {e}", file=sys.stderr)
            pdb.post_mortem()
        else:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
