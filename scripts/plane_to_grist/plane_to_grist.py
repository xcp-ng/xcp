#!/usr/bin/env python3

import argparse
import contextlib
import os
import re
from datetime import datetime
from itertools import islice

import requests

parser = argparse.ArgumentParser(description='Convert plane to grist')
parser.add_argument(
    '--plane-token', help="The token used to access the plane api", default=os.environ.get('PLANE_TOKEN')
)
parser.add_argument(
    '--grist-token', help="The token used to access the grist api", default=os.environ.get('GRIST_TOKEN')
)
args = parser.parse_args()

PLANE_URL = 'https://project.vates.tech/api/v1/workspaces/vates-global/projects/43438eec-1335-4fc2-8804-5a4c32f4932d'
def get_plane_data(path):
    resp = requests.get(f'{PLANE_URL}/{path}', headers={'x-api-key': args.plane_token})
    resp.raise_for_status()
    data = resp.json()
    if 'results' in data:
        return data['results']
    else:
        return data

GRIST_URL = 'https://grist.vates.tech/api/docs/p1ReergFeb75t9oEJQ2XTp'
def grist_get(path):
    resp = requests.get(f'{GRIST_URL}/{path}', headers={'Authorization': f'Bearer {args.grist_token}'})
    try:
        resp.raise_for_status()
    except Exception as e:
        print(resp.json())
        raise e
    return resp.json()[path]

def grist_post(path, data):
    resp = requests.post(f'{GRIST_URL}/{path}', headers={'Authorization': f'Bearer {args.grist_token}'}, json=data)
    try:
        resp.raise_for_status()
    except Exception as e:
        print(resp.json())
        raise e

GRIST_TYPES = {
    str: 'Text',
    int: 'Int',
    float: 'Numeric',
    bool: 'Bool',
    datetime: 'DateTime:Europe/Paris',
}

def convert_type(v):
    if isinstance(v, str):
        with contextlib.suppress(ValueError):
            v = datetime.strptime(v, "%Y-%m-%dT%H:%M:%S.%f%z")
    return v

def get_table_columns(data: list[dict]):
    res = []
    for d in data:
        for name, value in d.items():
            name = 'id2' if name == 'id' else name
            value_type = type(convert_type(value))
            if value_type in GRIST_TYPES:
                column = {
                    "id": name,
                    "fields": {
                        "type": GRIST_TYPES[value_type],
                        "label": name,
                    }
                }
                if column not in res:
                    res.append(column)
    return res

def filter_columns(d: dict):
    res = {}
    for name, value in d.items():
        name = 'id2' if name == 'id' else name
        value_type = type(convert_type(value))
        if value_type in GRIST_TYPES:
            res[name] = value
    return res

def make_chunks(data, size):
    it = iter(data)
    # use `xragne` if you are in python 2.7:
    for i in range(0, len(data), size):
        yield [k for k in islice(it, size)]

def table_to_var(table):
    return re.sub('([a-z])([A-Z])', r'\1_\2', table).lower()

issues = get_plane_data('issues')
labels = get_plane_data('labels')
modules = get_plane_data('modules')
states = get_plane_data('states')
types = get_plane_data('issue-types')
module_issues = [{
    'module': module['id'],
    'issue': issue['id']
} for module in modules for issue in get_plane_data(f'modules/{module["id"]}/module-issues')]
members = get_plane_data('members')

# create the tables
tables = grist_get('tables')
existing_tables = set(table['id'] for table in tables)
missing_tables = {'Issues', 'Labels', 'Modules', 'States', 'Types', 'Members'} - existing_tables
for table in missing_tables:
    grist_post('tables', {'tables': [{
        'id': table,
        'columns': get_table_columns(globals()[table_to_var(table)])
    }]})
if 'IssueLabels' not in existing_tables:
    grist_post('tables', {'tables': [{
        'id': 'IssueLabels',
        'columns': [
            {
                "id": 'issue',
                "fields": {
                    "type": 'Ref:Issues',
                    "label": 'issue',
                },
            },
            {
                "id": 'label',
                "fields": {
                    "type": 'Ref:Labels',
                    "label": 'label',
                },
            },
        ]
    }]})
if 'IssueAssignees' not in existing_tables:
    grist_post('tables', {'tables': [{
        'id': 'IssueAssignees',
        'columns': [
            {
                "id": 'issue',
                "fields": {
                    "type": 'Ref:Issues',
                    "label": 'issue',
                },
            },
            {
                "id": 'member',
                "fields": {
                    "type": 'Ref:Members',
                    "label": 'member',
                },
            },
        ]
    }]})
if 'ModuleIssues' not in existing_tables:
    grist_post('tables', {'tables': [{
        'id': 'ModuleIssues',
        'columns': [
            {
                "id": 'module',
                "fields": {
                    "type": 'Ref:Modules',
                    "label": 'module',
                },
            },
            {
                "id": 'issue',
                "fields": {
                    "type": 'Ref:Issues',
                    "label": 'issue',
                },
            },
        ]
    }]})

grist_post('tables/Labels/records', {'records': [{'fields': filter_columns(label)} for label in labels]})
grist_post('tables/Modules/records', {'records': [{'fields': filter_columns(module)} for module in modules]})
grist_post('tables/Types/records', {'records': [{'fields': filter_columns(type)} for type in types]})
grist_post('tables/States/records', {'records': [{'fields': filter_columns(state)} for state in states]})
grist_post('tables/Members/records', {'records': [{'fields': filter_columns(member)} for member in members]})
for subissues in make_chunks(issues, 10):
    grist_post('tables/Issues/records', {'records': [{'fields': filter_columns(issue)} for issue in subissues]})
    issue_label_records = [
        {'fields': {'issue': issue['id'], 'label': label}} for issue in subissues for label in issue['labels']
    ]
    if issue_label_records:
        grist_post(
            'tables/IssueLabels/records',
            {
                'records': issue_label_records
            },
        )
    issue_assignee_records = [
        {'fields': {'issue': issue['id'], 'member': member}} for issue in subissues for member in issue['assignees']
    ]
    if issue_assignee_records:
        grist_post(
            'tables/IssueAssignees/records',
            {
                'records': issue_assignee_records
            },
        )
grist_post(
    'tables/ModuleIssues/records',
    {'records': [{'fields': filter_columns(module_issue)} for module_issue in module_issues]},
)
