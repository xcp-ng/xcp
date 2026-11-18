# Milestone card links

`plane_milestone_links.py` lists the cards of a given plane milestone, and the interesting links found in
their description: links to help.vates.tech, github issues and xcp-ng.org forum posts. Only the cards with at
least one such link are printed.

It needs a plane token, through the `PLANE_TOKEN` environment variable or the `--plane-token` option,
and the `requests` python module.

```sh
./plane_milestone_links.py '<milestone title>'
```

# Milestone validation checklist

`plane_milestone_checklist.py` sets the release validation checklist used by XCPNG-3350 (a
`CI` / `Forum` / `QA` / `Blog` task list) on the cards of a milestone. CI, Forum and Blog are the same
for every card of a release, so they can be passed on the command line; QA is filled in by whoever
validates the card, so it is left alone unless `--qa` is given. An item is ticked when a value is
given for it.

A card that does not have the checklist yet gets it appended, and a card that already has one has the
given values refreshed in place, so the checklist of a whole milestone can be updated by running the
same command again with the new values. Only the items given on the command line are touched.

Nothing is written without `--apply`, and the original descriptions are saved to a json file first, so
a run can be undone:

```sh
# show what would change
./plane_milestone_checklist.py '<milestone title>' --forum 'https://xcp-ng.org/forum/topic/.../'

# write it, keeping a backup to undo with
./plane_milestone_checklist.py '<milestone title>' --forum 'https://...' --apply

# undo it
./plane_milestone_checklist.py --restore checklist_backup.json --apply
```

A single card can be updated with `--card XCPNG-1234` instead of a whole milestone. Each card is read
back after being written, because plane reformats the description on save, and the run stops at the
first card that did not take the change.

# Packages in pipe report generator

Generates an html report with the packages in the current tags.

# Requirements

You'll need a few extra python modules:
* koji
* requests
* specfile
* pygithub

The user running the generator must have a working configuration for koji (in `~/.koji`).
A plane token with enough rights to list the cards in the XCPNG project must be passed either through the `PLANE_TOKEN` 
environment variable or the `--plane-token` command line option.

An extra `--generated-info` command line option may be used to add some info about the report generation process.

The `--debug` option logs more details about the generation on stderr.

A machine readable version of the report can also be generated with the `--json-output` option:

```sh
pkg_in_pipe --json-output report.json report.html
```

The json report can be validated against its schema with:

```sh
python -m jsonschema -i report.json pkg_in_pipe.schema.json
```

# Release post generator

The `release_post.py` script generates the whole XCP-ng release post
from the json report. For each package of a given koji tag, it fetches the descriptions of the
related pull requests from github and prints the `Explain the change to users` section of those
descriptions.

It needs the `pydantic`, `requests` and `tqdm` python modules.
An optional `--github-token` option (or `GITHUB_TOKEN` environment variable) is used to
avoid the github api rate limits.

```sh
pkg_in_pipe --json-output report.json
release_post.py --report report.json
```

The release post is written on the standard output, as a full post template: the "What changed"
section contains one item per package with the `Explain the change to users` section of the pull
request descriptions, printed verbatim. The post writer can then
reorganize the items into the usual categories. The "Versions"
section lists every package of the tag with its version, showing the previously released
version as well when the report knows it (the `previous_nvr` field, the newest build of the
package in the updates or base tag). The `--version` option overrides the version number of
the post, otherwise it is derived from the tag (e.g. `v8.3-ci` gives 8.3).

The verbatim version is printed as a single list item: a one line section is written right
after the package name, a multiline section is written entirely on the following lines,
indented under the package name (blank lines are preserved). The HTML comments left in the
template of the pull request descriptions, and the blank lines around them, are removed.
A package without that section still gets an entry, with an empty description, and a
warning is printed on the standard error. For example:

```markdown
- `xo-lite`: * Update the UiTitle component to use the one from web-core (PR #9869)

- `amd-microcode`:
    Update to 2026-05-19 drop as redistributed by XenServer
    Updated CPUs:
     BRH-C1 00b00f21: 2025-10-17, rev 0b002161 -> 2025-10-17, rev 0b002162
```

The pull request descriptions are cached (same cache as the report
generator, in `/tmp/pkg_in_pipe.cache`, 24 hours retention). Use `--cache` to use another cache
path and `--re-cache` to refresh the cache.

# Run in docker

Before running in docker, the docker image must be built with:

```sh
docker build -t pkg_in_pipe .
```

A volume needs to be available to store the cache:

```sh
docker volume create pkg_in_pipe_cache
```

Several options are required to run the generator in docker:

* a `PLANE_TOKEN` environment variable with the rights required to request all the cards in the XCPNG project;
* a `GITHUB_TOKEN` environment variable with (at least) the `public_repo` scope;
* a (read only) mount of a directory containing the requeried certificates to connect to koji in `/root/.koji`
* a mount of the output directory in `/output`
* the path of the generated report

```sh
docker run \
    -v ~/.koji:/root/.koji:z \
    -e PLANE_TOKEN=<plane token> \
    -e GITHUB_TOKEN=<github token> \
    -v /out/dir:/output:z \
    -v pkg_in_pipe_cache:/tmp/pkg_in_pipe.cache \
    pkg_in_pipe /output/index.html
```
