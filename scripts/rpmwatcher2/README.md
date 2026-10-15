rpmwatcher2 is the replacement of `scripts/rpmwatcher`, which still runs during the transition.

rpmwatcher analyzes the RPMs of an XCP-ng release and produces reports about them:
- role of each package: installed by default, extra installable package, build dependency, unused...
- provenance: who built it (XenServer, CentOS, EPEL, XCP-ng), who added it, who maintains it
  and why (from `scripts/rpm_owners/packages.json`)
- version comparison with CentOS 7 and EPEL 7

It runs in two steps:
- `resolve.py` resolves the dependencies with yum, in a minimal XCP-ng 8.3 container
  (`Dockerfile.resolve`). It has the same yum as an XCP-ng host and as the centos:7.5.1804
  container used by `scripts/rpmwatcher`, and runs the same yum commands, on the XCP-ng
  repositories only. The repositories are not mirrored: yum reads their metadata from
  updates.xcp-ng.org, and the build dependencies come from the metadata of the Source
  repositories, so no RPM nor SRPM is downloaded. The container doesn't need to be privileged.
- `rpmwatcher.py` computes the roles and writes the reports, in a Fedora container
  (`Dockerfile`), then `entrypoint.sh` uploads them.

CentOS 7 and EPEL 7 are EOL, so their latest versions are stored in `data/`.

koji is only queried for the `built-by-*` tags and the `installable_extras` group. These
read-only queries don't need any account nor client certificate, only the CA of the koji hub
certificate, stored in `data/koji-ca.crt` (self-signed `kojica`, valid until 2035).

The XCP-ng image is bootstrapped from the XCP-ng repositories with the dnf of Fedora. The
packages it contains are checked against the XCP-ng signing key while it's built.

# Usage

```
docker compose run --rm rpmwatcher          # XCP-ng 8.3, reports in ./out/8.3/reports
```

docker compose runs `resolve` first. Its result goes in the `work` volume.

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

Without docker, `resolve.py` needs an XCP-ng 8.3 (or CentOS 7) system with yum-utils, and
`rpmwatcher.py` needs python3-rpm and python3-markdown:

```
./resolve.py 8.3 --output work
./rpmwatcher.py 8.3 --input work --output out
```

Options for tests and debugging:
- `resolve.py`: `--repo-url` to use a mirror or a local copy (`file://`, with `--no-gpgcheck`
  if the metadata is not signed), `--koji-snapshot` to use a JSON file instead of koji
  (`{"built_by": {"<srpm nvr>": "<builder>"}, "installable_extras": [...]}`), `--verbose` to see
  the yum commands.
- `rpmwatcher.py`: `--packages-info` to use a local packages.json.
