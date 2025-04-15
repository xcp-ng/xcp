#!/usr/bin/env python

import argparse
import os
from datetime import datetime
from textwrap import dedent

import koji
import requests


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

def print_table_line(out, build, link, issues, by):
    issues_content = '\n'.join([
        f'''<li>
                <a class="font-medium text-blue-600 dark:text-blue-500 hover:underline"
                   href="https://project.vates.tech/vates-global/browse/XCPNG-{i['sequence_id']}/">XCPNG-{i['sequence_id']}
                </a>
            </li>'''
        for i in issues
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
                {by}
            </td>
        </tr>
        ''', file=out)  # nopep8

parser = argparse.ArgumentParser(description='Generate a report of the packages in the pipe')
parser.add_argument('output', nargs='?', help='Report output path', default='report.html')
parser.add_argument('--generated-info', help="Add this message about the generation in the report")
parser.add_argument('--plane-token', help="The token used to access the plane api", default=os.environ['PLANE_TOKEN'])
args = parser.parse_args()

# open koji session
config = koji.read_config("koji")
session = koji.ClientSession('https://kojihub.xcp-ng.org', config)
session.ssl_login(config['cert'], None, config['serverca'])

# load the issues from plane, so we can search for the plane card related to a build
resp = requests.get(
    'https://project.vates.tech/api/v1/workspaces/vates-global/projects/43438eec-1335-4fc2-8804-5a4c32f4932d/issues/',
    headers={'x-api-key': args.plane_token},
)
project_issues = resp.json()

with open(args.output, 'w') as out:
    print_header(out)
    tags = [f'v{v}-{p}' for v in ['8.2', '8.3'] for p in ['incoming', 'ci', 'testing', 'candidates', 'lab']]
    for tag in tags:
        print_table_header(out, tag)
        for build in session.listTagged(tag):
            build_url = f'https://koji.xcp-ng.org/buildinfo?buildID={build['build_id']}'
            build_issues = [i for i in project_issues['results'] if f'href="{build_url}"' in i['description_html']]
            print_table_line(out, build['nvr'], build_url, build_issues, build['owner_name'])
        print_table_footer(out)
    print_footer(out, args.generated_info)
