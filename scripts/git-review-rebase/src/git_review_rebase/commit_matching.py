"""Commit matching logic for rebased branches."""

from collections import OrderedDict

import pygit2

from .branch_range import BranchRange
from .constants import CommitMatchInfoFlag
from .git_utils import commit_title


class RebasedCommitMatch:
    def __init__(
        self,
        left_commit: None | pygit2.Commit,
        right_commit: None | pygit2.Commit,
        match_info: CommitMatchInfoFlag,
    ):
        self.left_commit = left_commit
        self.right_commit = right_commit
        self.match_info = match_info


class RebasedCommitsMatches:
    def __init__(
        self, args, repo: pygit2.Repository, left_range: BranchRange, right_range: BranchRange
    ):
        self.args = args
        self.repo = repo
        self.left_range: BranchRange = left_range
        self.right_range: BranchRange = right_range
        self.commit_matches: OrderedDict[pygit2.Oid, RebasedCommitMatch] = OrderedDict()
        self.init_matches()

    def init_matches(self) -> None:

        right_commit_keys = OrderedDict((k, None) for k in self.right_range._rebased_commits)
        left_commit_matches: OrderedDict[pygit2.Oid, RebasedCommitMatch] = OrderedDict()
        for left_commit_oid in self.left_range._commit_by_oid:
            left_commit = self.repo.get(left_commit_oid)
            assert isinstance(left_commit, pygit2.Commit)
            match_info = CommitMatchInfoFlag(0)

            right_commit = self.right_range._commit_by_oid.get(left_commit_oid)
            if right_commit is not None:
                match_info |= CommitMatchInfoFlag.SameCommit

            else:
                right_commit = self.right_range._commit_by_patchid.get(
                    self.left_range._patchid_by_commitid[left_commit.id]
                )

            if right_commit is None:
                right_commit = self.right_range._commit_by_title.get(commit_title(left_commit))
                if right_commit is not None:
                    match_info = CommitMatchInfoFlag.LooseMatch

            if (
                right_commit is not None
                and right_commit.id not in self.right_range._rebased_commits
            ):
                match_info |= CommitMatchInfoFlag.PresentInRebaseOnto

            if right_commit is None:
                match_info |= CommitMatchInfoFlag.Dropped
            # else if self.repo.lookup_note(rig)

            left_commit_matches[left_commit_oid] = RebasedCommitMatch(
                left_commit, right_commit, match_info
            )

            if right_commit is not None and right_commit.id in right_commit_keys:
                del right_commit_keys[right_commit.id]

        # Remainders commits on the right side
        for right_commit_id in right_commit_keys:
            right_commit = self.repo.get(right_commit_id)
            assert isinstance(right_commit, pygit2.Commit)
            self.commit_matches[right_commit_id] = RebasedCommitMatch(
                None, right_commit, CommitMatchInfoFlag.Added
            )
        self.commit_matches.update(left_commit_matches)
