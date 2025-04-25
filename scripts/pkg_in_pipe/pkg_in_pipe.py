#!/usr/bin/env python

import argparse
import io
import os
import re
from datetime import datetime
from textwrap import dedent

import github
import koji
import requests
from github.PullRequest import PullRequest


def print_header(out):
    print(dedent('''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>XCP-ng Package Update</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="bg-gray-400 text-center">
        '''), file=out)

def print_plane_warning(out):
    print(dedent('''
        <div class="px-3 py-3">
        <div class="bg-orange-100 border-l-4 border-orange-500 text-orange-700 p-4" role="alert">
            <p class="font-bold">Plane malfunction</p>
            <p>The issues could not be retrieved from plane.</p>
        </div>
        </div>'''), file=out)

def print_koji_error(out):
    print(dedent('''
        <div class="px-3 py-3">
        <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
            <strong class="font-bold">Koji error!</strong>
            <span class="block sm:inline">The report can't be generated.</span>
        </div>
        </div>'''), file=out)

def print_generic_error(out):
    print(dedent('''
        <div class="px-3 py-3">
        <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
            <strong class="font-bold">Unknown error!</strong>
            <span class="block sm:inline">The report can't be generated.</span>
        </div>
        </div>'''), file=out)

def print_footer(out, generated_info):
    now = datetime.now()
    print(dedent(f'''
        Last generated at {now}. {generated_info or ''}
        </body>
        </html>
        '''), file=out)

def print_table_header(out, tag):
    print(dedent(f'''
        <div class="px-3 py-3">
        <div class="relative overflow-x-auto shadow-md sm:rounded-lg">
            <table class="table-fixed w-full text-sm text-left rtl:text-right text-gray-500 dark:text-gray-400">
                <caption class="p-5 text-lg font-semibold text-left rtl:text-right text-gray-900 bg-white dark:text-white dark:bg-gray-800">
                    {tag}
                </caption>
                <thead class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                    <tr>
                        <th scope="col" class="px-6 py-3">
                            Build
                        </th>
                        <th scope="col" class="px-6 py-3">
                            Cards
                        </th>
                        <th scope="col" class="px-6 py-3">
                            Pull Requests
                        </th>
                        <th scope="col" class="px-6 py-3">
                            By
                        </th>
                    </tr>
                </thead>
                <tbody>
        '''), file=out)  # nopep8

def print_table_footer(out):
    print(dedent('''
                </tbody>
            </table>
        </div>
        </div>
        '''), file=out)

def print_table_line(out, build, link, issues, by, prs: list[PullRequest]):
    issues_content = '\n'.join([
        f'''<li>
                <a class="font-medium text-blue-600 dark:text-blue-500 hover:underline"
                   href="https://project.vates.tech/vates-global/browse/XCPNG-{i['sequence_id']}/">XCPNG-{i['sequence_id']}
                </a>
            </li>'''
        for i in issues
    ])
    prs_content = '\n'.join([
        f'''<li>
                <a class="font-medium text-blue-600 dark:text-blue-500 hover:underline"
                   href="{pr.html_url}">{pr.title} #{pr.number}
                </a>
            </li>'''
        for pr in prs
    ])
    print(f'''    
        <tr class="odd:bg-white odd:dark:bg-gray-900 even:bg-gray-50 even:dark:bg-gray-800 border-b dark:border-gray-700 border-gray-200">
            <th scope="row" class="px-6 py-4 font-medium text-gray-900 whitespace-nowrap dark:text-white">
                <a class="font-medium text-blue-600 dark:text-blue-500 hover:underline" href="{link}">{build}</a>
            </th>
            <td class="px-6 py-4">
                <ul>
                {issues_content}
                </ul>
            </td>
            <td class="px-6 py-4">
                <ul>
                {prs_content}
                </ul>
            </td>
            <td class="px-6 py-4">
                {by}
            </td>
        </tr>
        ''', file=out)  # nopep8

def parse_source(source: str) -> tuple[str, str]:
    groups = re.match(r'git\+https://github\.com/([\w-]+/[\w-]+)(|\.git)#([0-9a-f]{40})', source)
    assert groups is not None, "can't match the source to the expected github url"
    return (groups[1], groups[3])

parser = argparse.ArgumentParser(description='Generate a report of the packages in the pipe')
parser.add_argument('output', nargs='?', help='Report output path', default='report.html')
parser.add_argument('--generated-info', help="Add this message about the generation in the report")
parser.add_argument(
    '--plane-token', help="The token used to access the plane api", default=os.environ.get('PLANE_TOKEN')
)
args = parser.parse_args()

# load the issues from plane, so we can search for the plane card related to a build
resp = requests.get(
    'https://project.vates.tech/api/v1/workspaces/vates-global/projects/43438eec-1335-4fc2-8804-5a4c32f4932d/issues/',
    headers={'x-api-key': args.plane_token},
)
issues = resp.json().get('results', [])

# connect to github
gh = github.Github(auth=github.Auth.Token(os.environ['GITHUB_TOKEN']))

ok = True
with open(args.output, 'w') as out:
    print_header(out)
    if not issues:
        print_plane_warning(out)
    tags = [f'v{v}-{p}' for v in ['8.2', '8.3'] for p in ['incoming', 'ci', 'testing', 'candidates', 'lab']]
    temp_out = io.StringIO()
    try:
        # open koji session
        config = koji.read_config("koji")
        session = koji.ClientSession('https://kojihub.xcp-ng.org', config)
        session.ssl_login(config['cert'], None, config['serverca'])
        for tag in tags:
            print_table_header(temp_out, tag)
            for tagged in sorted(session.listTagged(tag), key=lambda build: int(build['build_id']), reverse=True):
                build = session.getBuild(tagged['build_id'])
                prs: list[PullRequest] = []
                if build['source'] is not None:
                    (repo, sha) = parse_source(build['source'])
                    prs = list(gh.get_repo(repo).get_commit(sha).get_pulls())
                build_url = f'https://koji.xcp-ng.org/buildinfo?buildID={tagged["build_id"]}'
                build_issues = [i for i in issues if f'href="{build_url}"' in i['description_html']]
                print_table_line(temp_out, tagged['nvr'], build_url, build_issues, tagged['owner_name'], prs)
            print_table_footer(temp_out)
        out.write(temp_out.getvalue())
    except koji.GenericError:
        print_koji_error(out)
        raise
    except Exception:
        print_generic_error(out)
        raise
    finally:
        print_footer(out, args.generated_info)
