#!/usr/bin/env python3

"""
Write index.html files that look like the directory listings of nginx (autoindex),
since S3 static websites don't generate them.

usage: autoindex.py [--previous INDEX] [--updated ENTRY]... OUTPUT_FILE TITLE_PATH ENTRY...
  writes a listing of the given entries (sub-directories end with a /, no size).
  Their dates are the current time for the updated entries, else the ones found in
  the previous index (if any).
"""

import argparse
import calendar
import datetime
import html
import os
import re
import time


def write_index(path, title_path, entries):
    """ entries: list of (name, mtime or None, size or None), directories end with / """
    title = html.escape("Index of %s" % title_path)
    lines = ['<a href="../">../</a>']
    for name, mtime, size in sorted(entries, key=lambda e: (not e[0].endswith('/'), e[0])):
        date = datetime.datetime.fromtimestamp(mtime, datetime.timezone.utc).strftime('%d-%b-%Y %H:%M') if mtime else '-'
        label = html.escape(name if len(name) <= 50 else name[:47] + '..>')
        padding = ' ' * (51 - len(name[:50]))
        lines.append('<a href="%s">%s</a>%s%s %19s' % (html.escape(name), label, padding, date.ljust(17),
                                                        '-' if size is None else size))
    with open(path, 'w') as f:
        f.write('<html>\n<head><meta charset="utf-8"/><title>%s</title></head>\n<body>\n<h1>%s</h1><hr><pre>%s\n'
                '</pre><hr></body>\n</html>\n' % (title, title, '\n'.join(lines)))

def read_index_dates(path):
    """ Return {name: mtime} from an index written by write_index, or {} if there's none """
    try:
        with open(path) as f:
            content = f.read()
    except FileNotFoundError:
        return {}
    return {html.unescape(name): calendar.timegm(time.strptime(date, '%d-%b-%Y %H:%M'))
            for name, date in re.findall(r'<a href="([^"]+)">.*?</a> +(\d\d-\w{3}-\d{4} \d\d:\d\d) ', content)}

def write_dir_indexes(root, title_root='/'):
    """ Write an index.html in every directory under root, listing its files and sub-directories """
    for dirpath, dirnames, filenames in os.walk(root):
        entries = []
        for name in dirnames:
            entries.append((name + '/', os.path.getmtime(os.path.join(dirpath, name)), None))
        for name in filenames:
            if name != 'index.html':
                st = os.stat(os.path.join(dirpath, name))
                entries.append((name, st.st_mtime, st.st_size))
        rel = os.path.relpath(dirpath, root)
        title_path = title_root.rstrip('/') + '/' + ('' if rel == '.' else rel + '/')
        write_index(os.path.join(dirpath, 'index.html'), title_path, entries)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Write a directory listing of the given entries")
    parser.add_argument('--previous', help="previous index, to keep the dates of the entries")
    parser.add_argument('--updated', action='append', default=[], help="entry to date with the current time")
    parser.add_argument('output')
    parser.add_argument('title_path')
    parser.add_argument('entries', nargs='*')
    args = parser.parse_args()
    dates = read_index_dates(args.previous) if args.previous else {}
    now = time.time()
    write_index(args.output, args.title_path,
                [(name, now if name in args.updated else dates.get(name), None) for name in args.entries])
