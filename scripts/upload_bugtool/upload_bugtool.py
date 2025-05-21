#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Upload a bugtool archive to Nextcloud.
# This script should run on both Python 2 and 3.

from __future__ import print_function

import argparse
import getpass
import os
import subprocess
import sys

try:
    from itertools import zip_longest
except ImportError:
    from itertools import izip_longest as zip_longest

try:
    import urllib.parse as urlparse
    from urllib.parse import quote as urlquote
except ImportError:
    import urlparse
    from urllib import quote as urlquote

try:
    from xcp.branding import PLATFORM_VERSION
except ImportError:
    PLATFORM_VERSION = "9999"  # failsafe value, assume dev build


def version_lt(a, b):
    for ai, bi in zip_longest(a, b, fillvalue=0):
        if ai < bi:
            return True
        elif ai > bi:
            return False
    return False


def parse_share_link(share_link):
    """
    Parses the Nextcloud/Owncloud share link to extract the base URL and token.
    Args:
        share_link (str): The share link URL.
    Returns:
        tuple: A tuple containing (base_url, token).
    """
    parsed_url = urlparse.urlparse(share_link)._replace(query="", fragment="")
    path_segments = parsed_url.path.split("/")

    if path_segments[-3:-1] == ["index.php", "s"]:
        base_url = urlparse.urljoin(share_link, "../..")
        token = path_segments[-1]
    elif path_segments[-2] == "s":
        base_url = urlparse.urljoin(share_link, "..")
        token = path_segments[-1]
    else:
        raise ValueError(
            "Invalid share link format. Could not determine base URL from: %s"
            % share_link
        )

    return base_url, token


def upload(base_url, folder_token, password, file):
    print("Uploading %s" % file, file=sys.stderr)

    upload_filename = urlquote(os.path.basename(file))
    target_url = urlparse.urljoin(base_url, "public.php/webdav/%s" % upload_filename)
    cred = "%s:%s" % (folder_token, password)

    # fmt: off
    curl_args = [
        "curl",
        "--show-error",
        "--fail",
        "--upload-file", file,
        "--user", cred,
        "--header", "X-Requested-With: XMLHttpRequest",
        target_url,
    ]
    # fmt: on
    platform_version = tuple(int(x) for x in PLATFORM_VERSION.split("."))
    if version_lt(platform_version, (3, 3, 0)):
        # On 8.2, the default curl ciphersuite setting isn't compatible with most servers.
        # Use the same default ciphersuites as 8.3 /root/.curlrc.
        curl_args += [
            "--ciphers",
            "ECDHE-RSA-AES256-SHA384,ECDHE-RSA-AES256-GCM-SHA384,AES256-SHA256,AES128-SHA256,ECDHE-ECDSA-AES128-GCM-SHA256",
        ]

    subprocess.check_call(curl_args, stdout=sys.stdout, stderr=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Uploads a file to a Nextcloud/Owncloud shared drop folder."
    )
    parser.add_argument(
        "-p", action="store_true", help="Prompt for password for the share link."
    )
    parser.add_argument("share_link", help="The Nextcloud/Owncloud share link URL.")
    parser.add_argument("files", nargs="+", help="Files to upload.")

    args = parser.parse_args()

    if any(not os.path.exists(file) in file for file in args.files):
        print("Error: Given file path does not exist", file=sys.stderr)
        sys.exit(1)

    password = ""
    if args.p:
        if sys.stdin.isatty():
            password = getpass.getpass("Enter password for share link: ")
        else:
            print(
                "Error: Cannot prompt for password when not on a TTY.", file=sys.stderr
            )
            sys.exit(1)

    base_url, folder_token = parse_share_link(args.share_link)

    for file in args.files:
        upload(base_url, folder_token, password, file)


if __name__ == "__main__":
    main()
