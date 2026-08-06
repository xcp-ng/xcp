#!/usr/bin/env python3
# SPDX-FileCopyrightText: Philippe Coval <philippe.coval@vates.tech>
#
# SPDX-License-Identifier: MIT

"""
List all source packages from a Koji tag.

Usage:
    uv run koji-helper.py list <tag> [OPTIONS]
    uv run koji-helper.py list-update \
      <to_tag> <from_tag> [from_others_tags] [OPTIONS]

Examples:
    uv run koji-helper.py list v8.3-ci
    uv run koji-helper.py list-update v8.3-ci v8.3-updates
    uv run koji-helper.py --no-verify-ssl list-update v8.3-ci \
      v8.3-testing v8.3-candidates v8.3-updates v8.3-base


"""

# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "koji",
# ]
# ///

import argparse
import sys
from typing import Any, NotRequired, TypedDict

import koji


class PackageInfo(TypedDict):
    """Information about a source package build."""

    nvr: str
    version: str
    release: str
    base_version: NotRequired["PackageInfo | None"]


Packages = dict[str, PackageInfo]


def get_session(args: argparse.Namespace) -> koji.ClientSession:
    """Create and return a Koji client session."""
    session = koji.ClientSession(
        args.server,
        opts={"no_ssl_verify": args.no_verify_ssl},
    )
    return session


def list_source_packages(
    session: koji.ClientSession, tag: str, latest: bool = True
) -> tuple[dict[str, Any], Packages]:
    """
    List all source packages in the given tag.

    Returns a tuple of (tag_info, packages) where:
        - tag_info: dict with tag metadata (name, id, etc.)
        - packages: Packages type mapping package name to its info:
            - nvr: name-version-release string
            - version: package version
            - release: package release
    """
    # Get the tag info
    tag_info = session.getTag(tag, strict=True)

    # Get all source builds in the tag
    builds = session.listTagged(tag, latest=latest)

    results: Packages = {}
    for build in builds:
        name = build["package_name"]
        if name not in results:
            results[name] = {
                "nvr": build["nvr"],
                "version": build["version"],
                "release": build["release"],
            }

    return tag_info, results


def list_update_source_packages(
    session: koji.ClientSession,
    to_tag: str,
    from_tags: list[str] | None = None,
    latest: bool = True,
) -> tuple[dict[str, Any], Packages]:
    """
    List source packages that have been updated from one or more
    from_tags to to_tag.

    Returns a tuple of (tag_info, packages) where:
        - tag_info: dict with tag metadata (name, id, etc.)
        - packages: Packages type mapping package name to its info:
            - nvr: name-version-release string in to_tag
            - version: package version in to_tag
            - release: package release in to_tag
            - base_version: matching info from base tag or None
    """
    if not from_tags:
        msg = "At least one from_tag is required"
        raise ValueError(msg)

    to_tag_info, to_packages = list_source_packages(session, to_tag)

    base_packages: dict[str, Packages] = {}
    for from_tag in from_tags:
        _, from_packages = list_source_packages(session, from_tag)
        base_packages[from_tag] = from_packages

    results: Packages = {}
    for name, info in to_packages.items():
        to_nvr = info["nvr"]
        base_version: PackageInfo | None = None
        for from_tag in from_tags:
            from_pkgs = base_packages[from_tag]
            if name in from_pkgs:
                base_info = from_pkgs[name]
                base_nvr = base_info.get("nvr")
                if base_nvr and base_nvr != to_nvr:
                    base_version = base_info
                    break

        results[name] = {
            "nvr": to_nvr,
            "version": info["version"],
            "release": info["release"],
            "base_version": base_version,
        }

    return to_tag_info, results


def do_list(session: koji.ClientSession, args: argparse.Namespace) -> None:
    tag_info, packages = list_source_packages(session, args.tag)

    if not packages:
        print(
            f"No source packages found in tag '{args.tag}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    lines = []
    lines.append(f"Tag: {tag_info['name']}")
    lines.append(f"Total source packages: {len(packages)}")
    lines.append("-" * 60)

    for name, info in sorted(packages.items()):
        lines.append(f"{info['nvr']}")

    output_text = "\n".join(lines) + "\n"

    print(output_text)


def do_list_update(
    session: koji.ClientSession, args: argparse.Namespace
) -> None:
    tag_info, packages = list_update_source_packages(
        session, args.tag, from_tags=args.base_tags
    )

    if not packages:
        print("No updated source packages found.", file=sys.stderr)
        sys.exit(1)

    lines = []
    base_tags_str = ", ".join(args.base_tags) if args.base_tags else "any tag"
    lines.append(
        f"Updated packages from {base_tags_str} to {tag_info['name']}"
    )
    lines.append(f"Total updated source packages: {len(packages)}")
    lines.append("-" * 60)

    for name, info in sorted(packages.items()):
        new_vr = f"{info['version']}-{info['release']}"
        base_version = info.get("base_version")
        if base_version:
            old_vr = f"{base_version['version']}-{base_version['release']}"
            lines.append(f"{name}: {old_vr} -> {new_vr}")
        else:
            lines.append(f"{name}: UNKNOWN -> {new_vr}")

    output_text = "\n".join(lines) + "\n"

    print(output_text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Koji helper script.")
    parser.add_argument(
        "--server",
        default="https://kojihub.xcp-ng.org",
        help="Koji hub server URL (default: %(default)s)",
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Ignore SSL certificate verification errors",
    )

    subparsers = parser.add_subparsers(dest="command")

    # list command
    list_parser = subparsers.add_parser(
        "list", help="List all source packages from a tag"
    )
    list_parser.add_argument("tag", help="The Koji tag to query")

    # list-update command
    list_update_parser = subparsers.add_parser(
        "list-update", help="List updated source packages between tags"
    )
    list_update_parser.add_argument("tag", help="The target Koji tag")
    list_update_parser.add_argument(
        "base_tags", nargs="+", help="The source Koji tags to compare against"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    session = get_session(args)

    try:
        if args.command == "list":
            do_list(session, args)
        elif args.command == "list-update":
            do_list_update(session, args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
