"""Blame functionality for commit tracking."""

import asyncio

import pygit2


class BlameInfo:
    def __init__(self, repo: pygit2.Repository, commit: pygit2.Commit, file_path: str):
        self.repo = repo
        self.commit = commit
        self.file_path = file_path
        self._blame_info: list[pygit2.Commit] = []
        self._loader = asyncio.create_task(self._load_blame_info())

    async def _load_blame_info(self):
        blame_process = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            self.repo.workdir,
            "blame",
            str(self.commit.id),
            self.file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await blame_process.communicate()

        for idx, line in enumerate(stdout.decode("utf-8").splitlines()):
            rev = line.split(" ")[0]
            if rev.startswith("^"):
                rev = rev[1:]
            commit = await asyncio.to_thread(self.repo.revparse_single, rev)
            assert isinstance(commit, pygit2.Commit)
            self._blame_info.append(commit)
            if idx % 100:
                await asyncio.sleep(0)

    async def commit_at(self, line_number: int) -> pygit2.Commit:
        await self._loader
        return self._blame_info[line_number]


class BlameCache:
    def __init__(self, repo: pygit2.Repository):
        self.repo = repo
        self.blame_infos: dict[tuple[pygit2.Oid, str], BlameInfo] = {}

    def preload_commit(self, commit: pygit2.Commit) -> None:
        diff_tree = commit.tree.diff_to_tree(commit.parents[0].tree)
        for delta in diff_tree.deltas:
            self.get_blame_info(commit.parents[0], delta.old_file.path)

    def get_blame_info(self, commit: pygit2.Commit, file_path: str) -> BlameInfo:
        key = (commit.id, file_path)
        if key in self.blame_infos:
            return self.blame_infos[key]

        self.blame_infos[key] = BlameInfo(self.repo, commit, file_path)
        return self.blame_infos[key]
