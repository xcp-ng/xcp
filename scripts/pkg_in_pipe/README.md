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
