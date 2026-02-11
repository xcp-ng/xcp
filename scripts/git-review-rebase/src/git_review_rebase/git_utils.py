"""Git utility functions for repository operations."""

import multiprocessing
from multiprocessing.managers import DictProxy

import pygit2
from pygit2 import Walker
from pygit2.enums import SortMode

from .constants import CacheFlags


def oid(repo: pygit2.Repository, revision: str) -> pygit2.Oid:
    """Return oid from human parsable revision: HEAD, <sha1>, <branch_name>."""
    return repo.revparse_single(revision).id


def is_ancestor(
    repo: pygit2.Repository, potential_ancestor: pygit2.Commit, of_commit: pygit2.Commit
) -> bool:
    return repo.merge_base(potential_ancestor.id, of_commit.id) == potential_ancestor.id


def range_log(
    repo: pygit2.Repository,
    start: pygit2.Oid,
    end: pygit2.Oid,
    sort_mode: SortMode = SortMode.TOPOLOGICAL | SortMode.REVERSE,
) -> Walker:
    """Return a walker for the range start..end."""
    walker = repo.walk(end)
    walker.hide(start)
    return walker


def commit_title(commit: pygit2.Commit) -> str:
    """Given a Commit object, return the commit title."""
    return commit.message.splitlines()[0]


def cached_patchid_ref(revision: str) -> str:
    """Poor man's cache in git refs directly using merkle trees."""
    return f"refs/patchids/from_revision/" f"{revision[:2]}/{revision[2:4]}/{revision[4:]}"


_repo: None | pygit2.Repository = None
_commit_by_patchid_str: None | DictProxy = None


def patchid(repo: pygit2.Repository, commit: pygit2.Commit, cache_flags: CacheFlags) -> pygit2.Oid:
    cached_ref = cached_patchid_ref(str(commit.id))
    try:
        if CacheFlags.READ_FROM_CACHE not in cache_flags:
            raise KeyError("Do not use the cache")
        blob = repo.revparse_single(cached_ref)
        assert isinstance(blob, pygit2.Blob)
        o = pygit2.Oid(blob.read_raw())
    except KeyError:
        diff = repo.diff(commit, commit.parents[0])
        o = diff.patchid
        if CacheFlags.WRITE_TO_CACHE in cache_flags:
            blob_oid = repo.create_blob(diff.patchid.raw)
            repo.references.create(cached_ref, blob_oid, force=True)
    return o


def patchid_map_fn(
    revision: str, cache_flags: CacheFlags = CacheFlags.READ_FROM_CACHE | CacheFlags.WRITE_TO_CACHE
) -> None:
    """Given a revision stuff the commits_patchid dict with its patchid."""
    if _repo is None:
        raise RuntimeError("_repo needs to be defined")
    if _commit_by_patchid_str is None:
        raise RuntimeError("_commit_by_patchid_str needs to be defined")
    commit = _repo.get(pygit2.Oid(hex=revision))
    assert isinstance(commit, pygit2.Commit)
    _commit_by_patchid_str[str(patchid(_repo, commit, cache_flags))] = revision


def patchids(
    repo: pygit2.Repository,
    commits_oids: list[pygit2.Oid],
    cache_flags: CacheFlags,
) -> dict[str, str]:
    """Return a dict[Commit] -> Patchid."""
    global _repo, _commit_by_patchid_str
    _repo = repo
    with multiprocessing.Manager() as manager:
        _commit_by_patchid_str = manager.dict()
        with multiprocessing.Pool(multiprocessing.cpu_count()) as p:
            p.starmap(
                patchid_map_fn,
                # Oids objects cannot be pickled so use string representation
                [(str(oid), cache_flags) for oid in commits_oids],
            )
        return dict(_commit_by_patchid_str)


def abbrev(oid: pygit2.Oid):
    return str(oid)[:12]
