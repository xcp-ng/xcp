rpmwatcher2 is the replacement of `scripts/rpmwatcher`, which still runs during the transition.

rpmwatcher analyzes the RPMs of an XCP-ng release and produces reports about them:
- role of each package: installed by default, extra installable package, build dependency, unused...
- provenance: who built it (XenServer, CentOS, EPEL, XCP-ng), who added it, who maintains it
  and why (from `scripts/rpm_owners/packages.json`)
- version comparison with CentOS 7 and EPEL 7

The repositories are not mirrored: the metadata (repodata) is read from updates.xcp-ng.org
and the dependencies are resolved with libsolv, the way yum would on an XCP-ng host.
CentOS 7 and EPEL 7 are EOL, so their latest versions are stored in `data/`.

koji is only queried for the `built-by-*` tags and the `installable_extras` group. These
read-only queries don't need any account nor client certificate, only the CA of the koji hub
certificate, stored in `data/koji-ca.crt` (self-signed `kojica`, valid until 2035).

# Usage

```
docker compose run --rm rpmwatcher          # XCP-ng 8.3, reports in ./out/8.3/reports
XCP_VERSION=8.2 docker compose run --rm rpmwatcher
```

The reports are uploaded to S3 when `S3_BUCKET` is set (and optionally `S3_PREFIX`,
`S3_ENDPOINT_URL` and the usual `AWS_*` variables). For the production upload, put them in a
`prod.env` file (ignored by git) and pass it explicitly:

```
docker compose --env-file prod.env run --rm rpmwatcher
```

Don't name it `.env`: docker compose would load it for every run, including tests.
See `compose.yaml` to test the upload with a local S3 server.

S3 static websites don't list directories, so an `index.html` that looks like an nginx
directory listing is written in every directory, and the list of versions at the top is
rebuilt after each upload.

Without docker, it needs python3-solv, python3-rpm, python3-markdown and koji:

```
./rpmwatcher.py 8.3 --output out --cache cache
```

Options for tests and debugging: `--repo-url` to use a mirror or a local copy (`file://`), `--packages-info` to use a local packages.json, `--koji-snapshot` to use
a JSON file instead of koji (`{"built_by": {"<srpm nvr>": "<builder>"}, "installable_extras": [...]}`),
`--verbose` to see why packages are not installable.
