"""Branch range representation for git operations."""

from collections import OrderedDict

import pygit2

from .constants import CacheFlags
from .git_utils import commit_title, is_ancestor, oid, patchids, range_log


class BranchRange:
    """Representation of a range, allows to index commits by title or sha1."""

    def __init__(
        self,
        repo: pygit2.Repository,
        start_range: str,
        end_range: str,
        cache_flags: CacheFlags,
        merge_base: None | pygit2.Oid = None,
    ) -> None:
        """Initialize a BranchRange."""
        self.start_range = start_range
        self.start_range_oid = oid(repo, self.start_range)
        self.end_range = end_range

        self._repo = repo
        self._commit_by_title: dict[str, pygit2.Commit] = {}
        self._commit_by_oid: OrderedDict[pygit2.Oid, pygit2.Commit] = OrderedDict()
        self._rebased_commits: OrderedDict[pygit2.Oid, pygit2.Commit] = OrderedDict()
        self._patchid_by_commitid: OrderedDict[pygit2.Oid, pygit2.Oid] = OrderedDict()
        self._commit_by_patchid: OrderedDict[pygit2.Oid, pygit2.Commit] = OrderedDict()
        self._cache_flags = cache_flags
        self.merge_base: None | pygit2.Oid = None

        if merge_base is not None:
            start_commit = repo.get(self.start_range_oid)
            merge_commit = repo.get(merge_base)
            assert isinstance(start_commit, pygit2.Commit)
            assert isinstance(merge_commit, pygit2.Commit)
            if not is_ancestor(repo, start_commit, merge_commit):
                self.merge_base = merge_base
        self.init_range()

    def _get_commit(self, commit_id: str) -> pygit2.Commit:
        commit = self._repo.get(commit_id)
        assert isinstance(commit, pygit2.Commit)
        return commit

    def init_range(self) -> None:
        passed_upstream = False
        for commit in range_log(
            self._repo, self.merge_base or self.start_range_oid, oid(self._repo, self.end_range)
        ):
            self._commit_by_title[commit_title(commit)] = commit
            self._commit_by_oid[commit.id] = commit
            if self.merge_base is not None and commit.id == self.start_range_oid:
                passed_upstream = True
            if not passed_upstream:
                self._rebased_commits[commit.id] = commit

        self._commit_by_patchid.update(
            {
                pygit2.Oid(hex=k): self._get_commit(v)
                for k, v in patchids(
                    self._repo, list(self._commit_by_oid.keys()), self._cache_flags
                ).items()
            }
        )
        for k, v in self._commit_by_patchid.items():
            assert isinstance(k, pygit2.Oid), f"{k} type ({type(k)}) != pygit2.Oid"
            assert isinstance(v, pygit2.Commit), f"{v} type ({type(v)}) != pygit2.Commit"
            self._patchid_by_commitid[v.id] = k
