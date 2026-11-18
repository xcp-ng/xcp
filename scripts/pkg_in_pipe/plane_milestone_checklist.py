#!/usr/bin/env python3
# Append a release checklist to the cards of a plane milestone, following the format of
# XCPNG-3350. Dry run by default: pass --apply to write.
"""Append a validation checklist to the cards of a plane milestone."""
import argparse
import html
import json
import os
import re
import sys
import uuid

import requests

PLANE_PROJECT_URL = (
    'https://project.vates.tech/api/v1/workspaces/vates-global/projects/'
    '43438eec-1335-4fc2-8804-5a4c32f4932d'
)
CARD_URL = 'https://project.vates.tech/vates-global/browse/XCPNG-{sequence_id}/'

# The checklist of XCPNG-3350. CI, Forum and Blog are the same for every card of a release,
# while QA is filled in by whoever validates the card, so it is left empty unless asked.
DEFAULT_ITEMS = ('CI', 'Forum', 'QA', 'Blog')

LINK_CLASSES = (
    'text-link-primary underline underline-offset-[3px] hover:text-link-primary-hover'
    ' transition-colors cursor-pointer'
)
URL_RE = re.compile(r'^https?://\S+$')
TASK_LIST_RE = re.compile(r'<ul[^>]*data-type="taskList".*?</ul>', re.S)
TASK_ITEM_RE = re.compile(r'<li\b[^>]*data-type="taskItem".*?</li>', re.S)


def new_id():
    """Plane tags every editor block with a uuid, so the appended checklist needs its own."""
    return str(uuid.uuid4())


def check_status(resp, url):
    """Report a plane api failure with something actionable instead of a bare traceback."""
    if resp.ok:
        return
    hints = {
        401: 'no credentials sent, PLANE_TOKEN was probably empty',
        403: 'the token was rejected, or it lacks the rights to write this project',
        404: f'{url} does not exist, check the workspace/project id in {__file__}',
        429: 'rate limited by the plane api, retry in a moment',
    }
    detail = hints.get(resp.status_code, 'unexpected plane api error')
    body = resp.text.strip().replace('\n', ' ')[:200]
    sys.exit(f'plane api returned {resp.status_code} for {url}: {detail}\n{body}')


def request(method, url, token, json_body=None, params=None):
    """Do a plane api call and report a failure instead of raising."""
    resp = requests.request(method, url, headers={'x-api-key': token}, json=json_body, params=params)
    check_status(resp, url)
    return resp.json() if resp.content else {}


def paginate(path, token):
    """Fetch all the pages of a plane list endpoint."""
    url = f'{PLANE_PROJECT_URL}/{path}/'
    results = []
    cursor = None
    while True:
        data = request('GET', url, token, params={'cursor': cursor} if cursor else {})
        results.extend(data.get('results', []))
        cursor = data.get('next_cursor')
        if not data.get('next_page_results', False) or not cursor:
            return results


def find_milestone(milestones, name):
    """Find the milestone whose title matches name, ignoring the case."""
    matches = [m for m in milestones if m['title'].casefold() == name.casefold()]
    if not matches:
        available = ', '.join(sorted(m['title'] for m in milestones))
        sys.exit(f'no milestone named "{name}" in this project. Available milestones: {available}')
    if len(matches) > 1:
        sys.exit(f'more than one milestone named "{name}" in this project, please be more specific')
    return matches[0]


def render_item(label, value, checked):
    """Build one checklist item, with a link when the value is a bare url."""
    if not value:
        content = html.escape(f'{label}:')
    elif URL_RE.match(value):
        link = html.escape(value, quote=True)
        content = f'{html.escape(label)}: <a target="_blank" class="{LINK_CLASSES}" href="{link}" rel="noopener noreferrer">{link}</a>'  # noqa: E501
    else:
        content = html.escape(f'{label}: {value}')

    checkbox = '<input type="checkbox" checked="checked">' if checked else '<input type="checkbox">'
    checked_attr = 'true' if checked else 'false'
    return (
        f'<li data-id="{new_id()}" data-checked="{checked_attr}" data-type="taskItem">'
        f'<label>{checkbox}<span></span></label>'
        f'<div><p class="editor-paragraph-block" data-spacing-group="body" data-id="{new_id()}">'
        f'{content}</p></div></li>'
    )


def build_checklist(items):
    """Build the whole taskList, as the one closing XCPNG-3350."""
    body = ''.join(render_item(label, value, checked) for label, value, checked in items)
    return f'<ul data-spacing-group="list" data-id="{new_id()}" data-type="taskList">{body}</ul>'


def clean_value(value):
    """Drop the backslashes a shell leaves behind when a url is quoted."""
    if value and URL_RE.match(value) and '\\' in value:
        return value.replace('\\', '')
    return value


def item_label(item_html):
    """The 'CI' of a '<li>...CI: something...', or None when the item is not a checklist entry."""
    match = re.match(r'\s*([A-Za-z][A-Za-z ]*?)\s*:', plain_text(item_html))
    return match.group(1).strip() if match else None


def item_is_checked(item_html):
    """Whether the checkbox of a checklist item is ticked."""
    # the data-checked of the <li> is what plane's editor reads back, the checked of the
    # <input> is only rendering and is not always there on a box ticked in the plane ui
    tag = re.match(r'\s*<li\b[^>]*>', item_html)
    attr = re.search(r'\bdata-checked="([^"]*)"', tag.group(0)) if tag else None
    if attr:
        return attr.group(1) in ('', 'true')
    return re.search(r'<input\b[^>]*\bchecked\b', item_html) is not None


def checklist_state(description):
    """The ticked state and value of each checklist item of a description, by label."""
    match = TASK_LIST_RE.search(description or '')
    if not match:
        return {}
    state = {}
    for item in TASK_ITEM_RE.finditer(match.group(0)):
        label = item_label(item.group(0))
        if label:
            value = plain_text(item.group(0)).split(':', 1)[1].strip()
            state[label] = (item_is_checked(item.group(0)), value)
    return state


def update_checklist(description, items):
    # only the items with a value are touched, so the QA entry filled in by a tester is kept,
    # and an item missing from the checklist is added at the end of it
    """Set the value of the checklist items given on the command line."""
    match = TASK_LIST_RE.search(description)
    if not match:
        return description, [], []

    task_list = match.group(0)
    body = task_list[: -len('</ul>')]
    changed, expected = [], []

    for label, value, checked in items:
        if value is None:
            # no value given: leave whatever a tester wrote there alone
            continue
        new_item = render_item(label, value, checked)
        expected.append(f'{label}: {value}')

        for item in TASK_ITEM_RE.finditer(body):
            if item_label(item.group(0)) == label:
                # compare the text and not the markup: plane gives each item its own uuid, so
                # the same value written twice never has the same html
                same = plain_text(item.group(0)) == plain_text(new_item)
                if same and item_is_checked(item.group(0)) == checked:
                    break  # already up to date
                start, end = item.start(), item.end()
                body = body[:start] + new_item + body[end:]
                changed.append(label)
                break
        else:
            body += new_item
            changed.append(label)

    new_task_list = body + '</ul>'
    return description[:match.start()] + new_task_list + description[match.end():], changed, expected


def append_checklist(description, checklist):
    # plane may wrap the whole description in a trailing </div>, in which case the checklist
    # has to go before it to stay inside the body
    """Put the checklist at the end of the description body."""
    match = re.search(r'((?:\s*</div>)+)\s*$', description)
    if match:
        cut = match.start()
        return description[:cut] + checklist + description[cut:]
    return description + checklist


def has_checklist(description):
    """Whether the card already has a taskList, so re-running does not add a second one."""
    return bool(TASK_LIST_RE.search(description or ''))


def plain_text(markup):
    """A tag free version of some html, to compare descriptions without the formatting."""
    text = re.sub(r'<[^>]+>', ' ', markup)
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def find_cards(milestone_name, sequence_ids, token):
    """Get the cards to update: a whole milestone, or the given sequence ids."""
    if sequence_ids:
        wanted = {int(re.search(r'\d+', str(s)).group()) for s in sequence_ids}
        found = [c for c in paginate('issues', token) if c.get('sequence_id') in wanted]
        missing = wanted - {c['sequence_id'] for c in found}
        if missing:
            sys.exit(f'no card with sequence id {sorted(missing)} in this project')
        return sorted(found, key=lambda c: c['sequence_id']), None

    if not milestone_name:
        sys.exit('give a milestone title or at least one --card')

    milestone = find_milestone(paginate('milestones', token), milestone_name)
    work_items = paginate(f"milestones/{milestone['id']}/work-items", token)
    cards = {card['id']: card for card in paginate('issues', token)}
    ids = list(dict.fromkeys(w['issue'] for w in work_items if w.get('issue') in cards))
    return [cards[i] for i in ids], milestone


def build_items(args):
    """The checklist items to write: shared values from the cli, QA left to the tester."""
    values = {'CI': args.ci, 'Forum': args.forum, 'QA': args.qa, 'Blog': args.blog}
    return [
        (label, clean_value(values.get(label)), values.get(label) is not None)
        for label in DEFAULT_ITEMS
    ]


def restore_backup(path, token):
    """Put back the descriptions saved by a previous run."""
    with open(path) as f:
        backup = json.load(f)

    print(f'{len(backup)} descriptions in {path}')
    for entry in backup:
        print(f"  XCPNG-{entry['sequence_id']}  {entry['name']}")
    print()

    restored, failed = 0, []
    for entry in backup:
        url = f"{PLANE_PROJECT_URL}/issues/{entry['id']}/"
        request('PATCH', url, token, json_body={'description_html': entry['description_html']})
        after = plain_text(request('GET', url, token).get('description_html') or '')
        # plane reformats the html on save, so compare the text and not the raw markup
        if plain_text(entry['description_html'])[-200:] in after[-400:]:
            print(f'  XCPNG-{entry["sequence_id"]} restored')
            restored += 1
        else:
            print(f'  XCPNG-{entry["sequence_id"]} NOT RESTORED')
            failed.append(entry['sequence_id'])
            break
    return restored, failed


def save_backup(path, plan):
    """Save the original description of every card about to change."""
    backup = [
        {
            'id': card['id'],
            'sequence_id': card['sequence_id'],
            'name': card['name'],
            'description_html': card['description_html'],
            'description_stripped': card.get('description_stripped'),
        }
        for card, _, _ in plan
    ]
    with open(path, 'w') as f:
        json.dump(backup, f, indent=2)
    return len(backup)


def apply_plan(plan, token):
    """Write the checklist to every card, then read each one back to confirm it landed."""
    ok, failed = 0, []
    for card, description, expected in plan:
        sequence_id = card['sequence_id']
        url = f"{PLANE_PROJECT_URL}/issues/{card['id']}/"
        request('PATCH', url, token, json_body={'description_html': description})
        after = plain_text(request('GET', url, token).get('description_html') or '')
        # plane rewrites the html on save, so compare the text and not the raw markup
        missing = [text for text in expected if text not in after]
        if not missing:
            print(f'  XCPNG-{sequence_id} ok')
            ok += 1
        else:
            print(f'  XCPNG-{sequence_id} NOT APPLIED ({missing[0]!r} missing), stopping')
            failed.append(sequence_id)
            break
    return ok, failed


def main():
    parser = argparse.ArgumentParser(
        description="Append a validation checklist to the cards of a plane milestone"
    )
    parser.add_argument('milestone', nargs='?', help='The title of the milestone to update')
    parser.add_argument(
        '--card', '-c', dest='cards', action='append', help='Update this card instead of a milestone',
        default=[],
    )
    parser.add_argument('--apply', help='Actually write to plane', action='store_true')
    parser.add_argument(
        '--backup', help='Where to save the original descriptions', default='checklist_backup.json'
    )
    parser.add_argument('--restore', help='Restore the descriptions saved in a backup file instead')
    parser.add_argument('--ci', help='Value of the CI checklist item, also ticks it')
    parser.add_argument('--forum', help='Value of the Forum checklist item, also ticks it')
    parser.add_argument('--qa', help='Value of the QA checklist item, also ticks it')
    parser.add_argument('--blog', help='Value of the Blog checklist item, also ticks it')
    parser.add_argument(
        '--plane-token', help="The token used to access the plane api", default=os.environ.get('PLANE_TOKEN')
    )
    args = parser.parse_args()

    if not args.plane_token:
        sys.exit('no plane token, pass --plane-token or set the PLANE_TOKEN environment variable')

    if args.restore:
        if not os.path.exists(args.restore):
            sys.exit(f'no backup file at {args.restore}')
        if not args.apply:
            sys.exit('refusing to restore without --apply')
        restored, failed = restore_backup(args.restore, args.plane_token)
        print(f'\n{restored} card(s) restored')
        if failed:
            sys.exit(f'XCPNG-{failed[0]} was not restored, stopped')
        return

    if not args.milestone and not args.cards:
        sys.exit('give a milestone title or at least one --card')

    items = build_items(args)
    if not any(value for _, value, _ in items):
        sys.exit('nothing to set: give at least one of --ci, --forum, --qa or --blog')

    cards, milestone = find_cards(args.milestone, args.cards, args.plane_token)
    where = f'milestone "{milestone["title"]}"' if milestone else f'{len(cards)} card(s)'

    # a card that already has a checklist gets the given values refreshed instead of a second
    # checklist; the checklist is built per card as plane gives every editor block a uuid, and
    # reusing one across cards would paste identical block ids into unrelated descriptions
    todo = []
    unchanged = 0
    actions = {}
    for card in cards:
        description = card.get('description_html') or ''
        if has_checklist(description):
            new_description, changed, expected = update_checklist(description, items)
            if not changed:
                unchanged += 1
                continue
            action = f'would update {", ".join(changed)}'
        else:
            checklist = build_checklist(items)
            new_description = append_checklist(description, checklist)
            changed = [label for label, _, _ in items]
            expected = [f'{label}: {value}' for label, value, _ in items if value]
            action = f'would append a checklist with {", ".join(changed)}'
        todo.append((card, new_description, expected))
        actions[card['sequence_id']] = action

    print(
        f'{where}: {len(cards)} cards, {len(todo)} to update, {unchanged} already up to date\n'
    )
    for card, description, _ in todo:
        print(f"XCPNG-{card['sequence_id']}  {card['name']}")
        print(f'  {CARD_URL.format(sequence_id=card["sequence_id"])}')
        print(f'  {actions[card["sequence_id"]]}')
        final = checklist_state(description)
        for label, value, checked in items:
            if value is None:
                # not given on the command line: show what the card keeps, not an empty box
                checked, current = final.get(label, (False, ''))
                value = f'{current} (left as is)' if current else '(left as is)'
            state = 'x' if checked else ' '
            print(f'    [{state}] {label}: {value}')
        print()

    if not todo:
        print('nothing to do')
        return
    if not args.apply:
        print('dry run, pass --apply to write')
        return

    count = save_backup(args.backup, todo)
    print(f'backed up {count} descriptions to {args.backup}')
    ok, failed = apply_plan(todo, args.plane_token)
    print(f'\n{ok}/{len(todo)} cards updated')
    if failed:
        sys.exit(f'XCPNG-{failed[0]} was not updated, stopped. Restore with the {args.backup} backup.')


if __name__ == '__main__':
    main()
