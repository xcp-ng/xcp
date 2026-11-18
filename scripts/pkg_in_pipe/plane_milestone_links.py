#!/usr/bin/env python3
"""List the cards of a plane milestone and the interesting links in their description."""
import argparse
import os
import re
import sys

import requests

PLANE_PROJECT_URL = (
    'https://project.vates.tech/api/v1/workspaces/vates-global/projects/'
    '43438eec-1335-4fc2-8804-5a4c32f4932d'
)
CARD_URL = 'https://project.vates.tech/vates-global/browse/XCPNG-{sequence_id}/'

# The forum moved from the xcp-ng.org/forum/ path to the forum.xcp-ng.org host, so match both.
LINK_PATTERNS = {
    'help': re.compile(r'https?://(?:[\w-]+\.)*help\.vates\.tech[^\s"\'<>)]*'),
    'gh': re.compile(r'https://github\.com/[\w.-]+/[\w.-]+/issues/\d+'),
    'forum': re.compile(
        r'(?:https?://)?(?:www\.)?xcp-ng\.org/forum/[^\s"\'<>)]*'
        r'|(?:https?://)?forum\.xcp-ng\.org/[^\s"\'<>)]*'
    ),
}

DESCRIPTION_FIELDS = ('description_html', 'description', 'description_stripped')


def check_status(resp, url):
    """Report a plane api failure with something actionable instead of a bare traceback."""
    if resp.ok:
        return
    hints = {
        401: 'no credentials sent, PLANE_TOKEN was probably empty',
        403: 'the token was rejected, or it lacks the rights to read this project',
        404: f'{url} does not exist, check the workspace/project id in {__file__}',
        429: 'rate limited by the plane api, retry in a moment',
    }
    detail = hints.get(resp.status_code, 'unexpected plane api error')
    body = resp.text.strip().replace('\n', ' ')[:200]
    sys.exit(f'plane api returned {resp.status_code} for {url}: {detail}\n{body}')


def paginate(path, token):
    """Fetch all the pages of a plane list endpoint."""
    url = f'{PLANE_PROJECT_URL}/{path}/'
    results = []
    cursor = None
    while True:
        resp = requests.get(
            url,
            headers={'x-api-key': token},
            params={'cursor': cursor} if cursor else {},
        )
        check_status(resp, url)
        data = resp.json()
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


def card_description(card):
    """Concatenate the fields of a card that may contain links."""
    return '\n'.join(card.get(field) or '' for field in DESCRIPTION_FIELDS)


def find_links(card):
    """Return the interesting links of a card, deduped and in a stable order."""
    description = card_description(card)
    links = {}
    for kind, pattern in LINK_PATTERNS.items():
        found = {match.group(0) for match in pattern.finditer(description)}
        if found:
            links[kind] = sorted(url if '://' in url else f'https://{url}' for url in found)
    return links


def card_state(card, states):
    """The name of the state of a card, as the api returns the state as a uuid."""
    state = card.get('state_detail') or card.get('state')
    if isinstance(state, dict):
        return state.get('name') or state.get('group') or '?'
    return states.get(state) or ('?' if state is None else state)


def print_card(card, links, states):
    sequence_id = card.get('sequence_id')
    identifier = f'XCPNG-{sequence_id}' if sequence_id is not None else card['id']
    print(f"{identifier}  {card.get('name') or ''}  [{card_state(card, states)}]")
    if sequence_id is not None:
        print(f"  {CARD_URL.format(sequence_id=sequence_id)}")
    for kind in LINK_PATTERNS:
        for link in links.get(kind, []):
            print(f'  {kind:<5}: {link}')
    print()


def main():
    parser = argparse.ArgumentParser(
        description="List the cards of a plane milestone and the interesting links in their description"
    )
    parser.add_argument('milestone', help='The title of the milestone to look at')
    parser.add_argument(
        '--plane-token', help="The token used to access the plane api", default=os.environ.get('PLANE_TOKEN')
    )
    args = parser.parse_args()

    if not args.plane_token:
        sys.exit('no plane token, pass --plane-token or set the PLANE_TOKEN environment variable')

    milestone = find_milestone(paginate('milestones', args.plane_token), args.milestone)
    # the work items don't contain the descriptions, so get the cards themselves
    work_items = paginate(f"milestones/{milestone['id']}/work-items", args.plane_token)
    cards = {card['id']: card for card in paginate('issues', args.plane_token)}
    card_ids = list(dict.fromkeys(w['issue'] for w in work_items if w.get('issue') in cards))
    states = {state['id']: state['name'] for state in paginate('states', args.plane_token)}

    # only the cards with at least one interesting link are worth reporting
    found = [(cards[card_id], find_links(cards[card_id])) for card_id in card_ids]
    found = [(card, links) for card, links in found if links]

    print(f'{len(found)} of the {len(card_ids)} cards in milestone "{milestone["title"]}" have a link\n')
    for card, links in found:
        print_card(card, links, states)


if __name__ == '__main__':
    main()
