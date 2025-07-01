#!/usr/bin/env python

import argparse
import io
import json
import os
import re
from datetime import datetime
from textwrap import dedent
from typing import cast
from urllib.request import urlopen

import diskcache
import github
import koji
import requests
from github.Commit import Commit
from github.GithubException import BadCredentialsException
from github.PullRequest import PullRequest


def print_header(out):
    print(dedent('''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>XCP-ng Package Update</title>
            <style>
                .tooltip{
                  visibility: hidden;
                  position: absolute;
                }
                .has-tooltip:hover .tooltip {
                  visibility: visible;
                  z-index: 100;
                }
            </style>
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

def print_github_warning(out):
    print(dedent('''
        <div class="px-3 py-3">
        <div class="bg-orange-100 border-l-4 border-orange-500 text-orange-700 p-4" role="alert">
            <p class="font-bold">Github access problem</p>
            <p>The pull requests come from the cache and may not be up to date.</p>
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

def print_footer(out, started_at, generated_info):
    now = datetime.now()
    duration = now - started_at
    print(dedent(f'''
        Generated on {now.date()} at {now.time().strftime("%H:%M:%S")} (took {duration.seconds} seconds).
        {generated_info or ''}
        </body>
        </html>
        '''), file=out)

def print_table_header(out, tag):
    print(dedent(f'''
        <div class="px-3 py-2">
        <div class="relative overflow-x-auto shadow-md sm:rounded-lg">
            <table class="table-fixed w-full text-sm text-left rtl:text-right text-gray-500 dark:text-gray-400">
                <caption class="px-5 py-3 text-lg font-semibold text-left rtl:text-right text-gray-900 bg-white dark:text-white dark:bg-gray-800">
                    <a name="{tag}" href="#{tag}">{tag}</a>
                </caption>
                <thead class="text-xs text-gray-700 uppercase bg-gray-50 dark:bg-gray-700 dark:text-gray-400">
                    <tr>
                        <th scope="col" class="px-6 py-2 w-[25.5%]">
                            Build
                        </th>
                        <th scope="col" class="px-6 py-2 w-[37.5%]">
                            Pull Requests
                        </th>
                        <th scope="col" class="px-6 py-2 w-[12.5%]">
                            Cards
                        </th>
                        <th scope="col" class="px-6 py-2 w-[12.5%]">
                            Built by
                        </th>
                        <th scope="col" class="px-6 py-2 w-[12.5%]">
                            Maintained by
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

def issue_has_link(issue, url):
    url = url.strip('/')
    return f'href="{url}"' in issue['description_html'] or f'href="{url}/"' in issue['description_html']

def issues_have_link(issues, url):
    return any([issue_has_link(issue, url) for issue in issues])

def print_table_line(out, build, link, issues, built_by, prs: list[PullRequest], maintained_by):
    issues_content = '\n'.join([
        f'''<li>
                <a target="_blank" class="font-medium text-blue-600 dark:text-blue-500 hover:underline {'italic' if issue_has_link(i, link) else ''}"
                   href="https://project.vates.tech/vates-global/browse/XCPNG-{i['sequence_id']}/">XCPNG-{i['sequence_id']}
                </a>
            </li>'''  # noqa
        for i in issues
    ])
    warn_pr = "<span class='has-tooltip'><span class='tooltip p-1 rounded bg-blue-500 text-gray-900'>Pull request not listed in any of the related cards</span>⚠️</span>"  # noqa
    prs_content = '\n'.join([
        f'''<li>
                <a target="_blank" class="font-medium text-blue-600 dark:text-blue-500 hover:underline"
                   href="{pr.html_url}">{pr.title} #{pr.number}
                </a> {"" if issues_have_link(issues, pr.html_url) else warn_pr}
            </li>'''
        for pr in prs
    ])
    warn_build = "<span class='has-tooltip'><span class='tooltip p-1 rounded bg-blue-500 text-gray-900'>Build not listed in any of the related cards</span>⚠️</span>"  # noqa
    warn_maintainer = "<span class='has-tooltip'><span class='tooltip p-1 rounded bg-blue-500 text-gray-900'>Maintainer information missing</span>⚠️</span>"  # noqa
    print(f'''    
        <tr class="odd:bg-white odd:dark:bg-gray-900 even:bg-gray-50 even:dark:bg-gray-800 border-b dark:border-gray-700 border-gray-200">
            <th scope="row" class="px-6 py-2 font-medium text-gray-900 whitespace-nowrap dark:text-white truncate">
                <a target="_blank" class="font-medium text-blue-600 dark:text-blue-500 hover:underline" href="{link}">{build}</a> {"" if issues_have_link(issues, link) else warn_build}
            </th>
            <td class="px-6 py-2">
                <ul>
                {prs_content}
                </ul>
            </td>
            <td class="px-6 py-2">
                <ul>
                {issues_content}
                </ul>
            </td>
            <td class="px-6 py-2">
                {built_by}
            </td>
            <td class="px-6 py-2">
                {maintained_by if maintained_by is not None else warn_maintainer}
            </td>
        </tr>
        ''', file=out)  # nopep8

def parse_source(source: str) -> tuple[str, str]:
    groups = re.match(r'git\+https://github\.com/([\w-]+/[\w-]+)(|\.git)#([0-9a-f]{40})', source)
    assert groups is not None, "can't match the source to the expected github url"
    return (groups[1], groups[3])

def filter_issues(issues, urls):
    res = []
    for issue in issues:
        for url in urls:
            if issue_has_link(issue, url):
                res.append(issue)
                break
    return res


TAG_ORDER = ['incoming', 'ci', 'testing', 'candidates', 'updates', 'base', 'lab']

def tag_priority(tag):
    # drop the version in the tag — v8.3-incoming -> incoming
    tag = tag.split('-')[-1]
    return TAG_ORDER.index(tag)

def find_previous_build_commit(session, build_tag, build):
    """Find the previous build in an higher priority koji tag and return its commit."""
    tagged = session.listTagged(build_tag, package=build['package_name'], inherit=True)
    tagged = sorted(tagged, key=lambda t: (tag_priority(t['tag_name']), -t['build_id']))
    build_tag_priority = tag_priority(build_tag)
    tagged = [
        t for t in tagged if tag_priority(t['tag_name']) >= build_tag_priority and t['build_id'] < build['build_id']
    ]
    if not tagged:
        return None
    previous_build = session.getBuild(tagged[0]['build_id'])
    if not previous_build.get('source'):
        return None
    return parse_source(previous_build['source'])[1]

def find_commits(gh, repo, start_sha, end_sha) -> list[Commit]:
    """
    List the commits in the range [start_sha,end_sha[.

    Note: these are the commits listed by Github starting from start_sha up to end_sha excluded.
    A commit older that the end_sha commit and added by a merge commit won't appear in this list.
    """
    cache_key = f'commits-2-{start_sha}-{end_sha}'
    if not args.re_cache and cache_key in CACHE:
        return cast(list[Commit], CACHE[cache_key])
    commits = []
    if gh:
        for commit in gh.get_repo(repo).get_commits(start_sha):
            if commit.sha == end_sha:
                break
            commits.append(commit)
        CACHE.set(cache_key, commits, expire=RETENTION_TIME)
    return commits

def find_pull_requests(gh, repo, start_sha, end_sha):
    """Find the pull requests for the commits in the [start_sha,end_sha[ range."""
    prs = set()
    for commit in find_commits(gh, repo, start_sha, end_sha):
        cache_key = f'commit-prs-3-{commit.sha}'
        if not args.re_cache and cache_key in CACHE:
            prs.update(cast(list[PullRequest], CACHE[cache_key]))
        elif gh:
            commit_prs = list(commit.get_pulls())
            if not commit_prs:
                # github is not properly reporting some PRs. Try to workaround that problem by getting
                # the PR number from the commit message
                group = re.match(r'Merge pull request #(\d+) from ', commit.commit.message)
                if group:
                    pr = gh.get_repo(repo).get_pull(int(group[1]))
                    prs.add(pr)
            CACHE.set(cache_key, commit_prs, expire=RETENTION_TIME)
            prs.update(commit_prs)
    return sorted(prs, key=lambda p: p.number, reverse=True)


started_at = datetime.now()

parser = argparse.ArgumentParser(description='Generate a report of the packages in the pipe')
parser.add_argument('output', nargs='?', help='Report output path', default='report.html')
parser.add_argument('--generated-info', help="Add this message about the generation in the report")
parser.add_argument(
    '--plane-token', help="The token used to access the plane api", default=os.environ.get('PLANE_TOKEN')
)
parser.add_argument(
    '--github-token', help="The token used to access the Github api", default=os.environ.get('GITHUB_TOKEN')
)
parser.add_argument('--cache', help="The cache path", default="/tmp/pkg_in_pipe.cache")
parser.add_argument(
    '--tag', '-t', dest='tags', help="The koji tags to include in the report", action='append', default=[]
)
parser.add_argument(
    '--package', '-p', dest='packages', help="The packages to include in the report", action='append', default=[]
)
parser.add_argument('--re-cache', help="Refresh the cache", action='store_true')
args = parser.parse_args()

CACHE = diskcache.Cache(args.cache)
RETENTION_TIME = 24 * 60 * 60  # 24 hours

DEFAULT_TAGS = [f'v{v}-{p}' for v in ['8.2', '8.3'] for p in ['incoming', 'ci', 'testing', 'candidates', 'lab']]
tags = args.tags or DEFAULT_TAGS

# load the issues from plane, so we can search for the plane card related to a build
try:
    resp = requests.get(
        'https://project.vates.tech/api/v1/workspaces/vates-global/projects/'
        '43438eec-1335-4fc2-8804-5a4c32f4932d/issues/',
        headers={'x-api-key': args.plane_token},
    )
    issues = resp.json().get('results', [])
except Exception:
    issues = []

# connect to github
if args.github_token:
    gh = github.Github(auth=github.Auth.Token(args.github_token))
    try:
        gh.get_repo('xcp-ng/xcp')  # check that the token is valid
    except BadCredentialsException:
        gh = None
else:
    gh = None

# load the packages maintainers
with urlopen('https://github.com/xcp-ng/xcp/raw/refs/heads/master/scripts/rpm_owners/packages.json') as f:
    PACKAGES = json.load(f)

with io.StringIO() as out:
    print_header(out)
    if not issues:
        print_plane_warning(out)
    if not gh:
        print_github_warning(out)
    with io.StringIO() as temp_out:
        try:
            # open koji session
            config = koji.read_config("koji")
            session = koji.ClientSession('https://kojihub.xcp-ng.org', config)
            session.ssl_login(config['cert'], None, config['serverca'])
            for tag in tags:
                tag_history = dict(
                    (tl['build_id'], tl['create_ts'])
                    for tl in session.queryHistory(tag=tag, active=True)['tag_listing']
                )
                print_table_header(temp_out, tag)
                taggeds = session.listTagged(tag)
                taggeds = (t for t in taggeds if t['package_name'] in args.packages or args.packages == [])
                taggeds = sorted(taggeds, key=lambda t: (tag_history[t['build_id']], t['build_id']), reverse=True)
                for tagged in taggeds:
                    build = session.getBuild(tagged['build_id'])
                    prs: list[PullRequest] = []
                    maintained_by = None
                    previous_build_sha = find_previous_build_commit(session, tag, build)
                    if build['source'] is not None:
                        (repo, sha) = parse_source(build['source'])
                        prs = find_pull_requests(gh, repo, sha, previous_build_sha)
                    maintained_by = PACKAGES.get(tagged['package_name'], {}).get('maintainer')
                    build_url = f'https://koji.xcp-ng.org/buildinfo?buildID={tagged["build_id"]}'
                    build_issues = filter_issues(issues, [build_url] + [pr.html_url for pr in prs])
                    print_table_line(
                        temp_out, tagged['nvr'], build_url, build_issues, tagged['owner_name'], prs, maintained_by
                    )
                print_table_footer(temp_out)
            out.write(temp_out.getvalue())
        except koji.GenericError:
            print_koji_error(out)
            raise
        except Exception:
            print_generic_error(out)
            raise
        finally:
            print_footer(out, started_at, args.generated_info)

    # write the actual output at once, in order to avoid a blank page during the processing
    with open(args.output, 'w') as f:
        f.write(out.getvalue())
