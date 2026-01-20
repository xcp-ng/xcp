#!/usr/bin/env python

import argparse
import asyncio
import multiprocessing
import os
import pygit2
import re
import subprocess

from collections import OrderedDict

from difflib import SequenceMatcher

from enum import Enum, StrEnum, Flag, auto

from pathlib import Path

from pygit2.enums import SortMode
from pygit2 import Walker

from pygments.lexers import get_lexer_for_filename

from rich.text import Text
from rich.style import Style

from tempfile import NamedTemporaryFile

from textual import work, log
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RadioButton,
    RadioSet,
)
from textual.widgets.data_table import ColumnKey


class SolarizedColors(StrEnum):
    # Darker to Lighter
    Base03 = "#002b36"
    Base02 = "#073642"
    Base01 = "#586e75"
    Base00 = "#657b83"
    Base0 = "#839496"
    Base1 = "#93a1a1"
    Base2 = "#eee8d5"
    Base3 = "#fdf6e3"
    Yellow = "#b58900"
    Orange = "#cb4b16"
    Red = "#dc322f"
    Magenta = "#d33682"
    Violet = "#6c71c4"
    Blue = "#268bd2"
    Cyan = "#2aa198"
    Green = "#859900"


class CommitMatchInfoFlag(Flag):
    LooseMatch = auto()
    PresentInRebaseOnto = auto()
    Dropped = auto()
    Added = auto()


class CommitMatchInfo(object):
    def __init__(self, flag, character, definition):
        self.flag = flag
        self.character = character
        self.definition = definition


commit_match_info_repr = {
    CommitMatchInfoFlag.LooseMatch: CommitMatchInfo(
        CommitMatchInfoFlag.LooseMatch,
        Text("≈", SolarizedColors.Yellow),
        "Commit patchid has changed"
    ),
    CommitMatchInfoFlag.PresentInRebaseOnto: CommitMatchInfo(
        CommitMatchInfoFlag.PresentInRebaseOnto,
        Text("⤶", SolarizedColors.Blue),
        "Commit present in new upstream"
    ),
    CommitMatchInfoFlag.Dropped:  CommitMatchInfo(
        CommitMatchInfoFlag.Dropped,
        Text("✗", SolarizedColors.Red),
        "Commit dropped in rebase"
    ),
    CommitMatchInfoFlag.Added: CommitMatchInfo(
        CommitMatchInfoFlag.Added,
        Text("✚", SolarizedColors.Green),
        "Commit added in rebase"
    ),
}


class FilterType(Enum):
    NoFilter = auto()
    With = auto()
    Without = auto()


def oid(
        repo: pygit2.Repository,
        revision: str
) -> pygit2.Oid:
    """Return oid from human parsable revision: HEAD, <sha1>, <branch_name>."""
    return repo.revparse_single(revision).id


def range_log(
        repo: pygit2.Repository,
        start: pygit2.Oid,
        end: pygit2.Oid,
        sort_mode: SortMode = SortMode.TOPOLOGICAL | SortMode.REVERSE
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
    return (
        f"refs/patchids/from_revision/"
        f"{revision[:2]}/{revision[2:4]}/{revision[4:]}"
    )


class CacheFlags(Flag):
    READ_FROM_CACHE = auto()
    WRITE_TO_CACHE = auto()


def patchid(
        repo: pygit2.Repository,
        commit: pygit2.Commit,
        cache_flags: CacheFlags
):
    if cache_flags:
        cached_ref = cached_patchid_ref(str(commit.id))
    try:
        if CacheFlags.READ_FROM_CACHE not in cache_flags:
            raise KeyError("Do not use the cache")
        o = pygit2.Oid(repo.revparse_single(cached_ref).data)
    except KeyError:
        diff = _repo.diff(commit.tree, commit.parents[0].tree)
        o = diff.patchid
        if CacheFlags.WRITE_TO_CACHE in cache_flags:
            blob = _repo.create_blob(diff.patchid.raw)
            repo.references.create(
                cached_ref,
                blob,
                force=True
            )
    return o


_repo = None
_commit_by_patchid_str = None


def patchid_map_fn(
        revision: str,
        cache_flags: CacheFlags =
        CacheFlags.READ_FROM_CACHE | CacheFlags.WRITE_TO_CACHE
):
    """Given a revision stuff the commits_patchid dict with its patchid."""
    commit = _repo.get(pygit2.Oid(hex=revision))
    _commit_by_patchid_str[str(patchid(_repo, commit, cache_flags))] = revision


def patchids(
        repo: pygit2.Repository,
        commits_oids: list[pygit2.Commit],
        cache_flags: CacheFlags,
) -> dict[str]:
    """Return a dict[Commit] -> Patchid."""
    global _repo, _commit_by_patchid_str
    _repo = repo
    with multiprocessing.Manager() as manager:
        _commit_by_patchid_str = manager.dict()
        with multiprocessing.Pool(multiprocessing.cpu_count()) as p:
            p.starmap(
                patchid_map_fn,
                # Oids objects cannot be pickled so use string representation
                [(str(oid), cache_flags) for oid in commits_oids]
            )
        return dict(_commit_by_patchid_str)


class BlameInfo(object):
    def __init__(self, repo: pygit2.Repository, commit: pygit2.Commit, file_path: str):
        self.repo = repo
        self.commit = commit
        self.file_path = file_path
        self._blame_info: list[pygit2.Commit] = list()
        log("start task")
        self._loader = asyncio.create_task(self._load_blame_info())
        log("end task")

    async def _load_blame_info(self):
        blame_process = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            self.repo.workdir,
            "blame",
            str(self.commit.id),
            self.file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await blame_process.communicate()

        for idx, line in enumerate(stdout.decode("utf-8").splitlines()):
            rev = line.split(" ")[0]
            if rev.startswith("^"):
                rev = rev[1:]
            commit = await asyncio.to_thread(self.repo.revparse_single, rev)
            self._blame_info.append(commit)
            if idx % 100:
                await asyncio.sleep(0)

    async def get_blame_info(self):
        await self._loader
        return self._blame_info


class BlameCache(object):
    def __init__(self, repo: pygit2.Repository):
        self.repo = repo
        self.blame_infos: dict[(pygit2.Oid, str), BlameInfo] = dict()

    def get_blame_info(self, commit: pygit2.Commit, file_path: str) -> BlameInfo:
        key = (commit.id, file_path)
        if key in self.blame_infos:
            return self.blame_infos[key]

        self.blame_infos[key] = BlameInfo(self.repo, commit, file_path)
        return self.blame_infos[key]


class Branch(Path):
    def to(self, suffix: str):
        return self.parent / suffix


class BranchRange(object):
    """Representation of a range, allows to index commits by title or sha1."""

    def __init__(
            self,
            repo: pygit2.Repository,
            start_range: str,
            end_range: str,
            cache_flags: CacheFlags
    ) -> None:
        """Initialize a BranchRange."""
        self.start_range = start_range
        self.end_range = end_range

        if end_range.endswith("base"):
            self.upstream_oid = oid(
                repo,
                str(Branch(end_range).to("upstream")) + "^{commit}"
            )
        else:
            self.upstream_oid = oid(
                repo,
                start_range + "^{commit}"
            )

        self._repo = repo

        self._commit_by_title = dict()
        self._commit_by_oid = OrderedDict()
        self._rebased_commits = OrderedDict()

        passed_upstream = False
        for commit in range_log(
                self._repo,
                oid(self._repo, self.start_range),
                oid(self._repo, self.end_range)
        ):
            self._commit_by_title[commit_title(commit)] = commit
            self._commit_by_oid[commit.id] = commit
            if commit.id == self.upstream_oid:
                passed_upstream = True
            if not passed_upstream:
                self._rebased_commits[commit.id] = commit

        self._commit_by_patchid = {
            pygit2.Oid(hex=k): self._repo.get(v)
            for k, v in patchids(
                self._repo,
                [str(oid) for oid in self._commit_by_oid.keys()],
                cache_flags
            ).items()
        }
        self._patchid_by_commitid = dict()
        for k, v in self._commit_by_patchid.items():
            self._patchid_by_commitid[v.id] = k


class RebasedCommitMatch(object):
    def __init__(
            self,
            left_commit: pygit2.Commit,
            right_commit: pygit2.Commit,
            match_type: CommitMatchInfoFlag
    ):
        self.left_commit = left_commit
        self.right_commit = right_commit
        self.match_type = match_type


class RebasedCommitsMatches(object):
    def __init__(
            self,
            args,
            repo: pygit2.Repository,
            left_range: BranchRange,
            right_range: BranchRange
    ):
        self.args = args
        self.repo = repo
        self.left_range = left_range
        self.right_range = right_range
        self.commit_matches = OrderedDict()
        self.init_matches()

    def init_matches(self) -> None:

        right_commit_keys = OrderedDict((k, None) for k in self.right_range._rebased_commits)
        left_commit_matches = OrderedDict()
        for left_commit_oid in self.left_range._commit_by_oid:
            left_commit = self.repo.get(left_commit_oid)
            match_info = CommitMatchInfoFlag(0)

            right_commit = self.right_range._commit_by_patchid.get(
                self.left_range._patchid_by_commitid[left_commit.id]
            )

            if right_commit is None:
                right_commit = self.right_range._commit_by_title.get(
                    commit_title(left_commit)
                )
                if right_commit is not None:
                    match_info = CommitMatchInfoFlag.LooseMatch

            if right_commit is not None and right_commit.id not in self.right_range._rebased_commits:
                match_info |= CommitMatchInfoFlag.PresentInRebaseOnto

            if right_commit is None:
                match_info |= CommitMatchInfoFlag.Dropped

            left_commit_matches[left_commit_oid] = RebasedCommitMatch(
                left_commit,
                right_commit,
                match_info
            )

            if right_commit is not None and right_commit.id in right_commit_keys:
                del right_commit_keys[right_commit.id]

        for right_commit_id in right_commit_keys:
            self.commit_matches[right_commit_id] = RebasedCommitMatch(
                None,
                self.repo.get(right_commit_id),
                CommitMatchInfoFlag.Added
            )
        self.commit_matches.update(left_commit_matches)


def abbrev(oid: pygit2.Oid):
    return str(oid)[:12]


class DiffBlameParser(object):
    hunk_pattern = re.compile(r"@@ -(?P<old_start>\d+),.*")

    def __init__(self, blame_cache: BlameCache, enabled: bool, commit: pygit2.Commit):
        self.commit: pygit2.Commit = commit
        self.current_file: None | str = None
        self.current_hunk_start: None | int = None
        self.current_hunk_line_index: int = 0
        self.blame_cache: BlameCache = blame_cache
        self.enabled: bool = enabled
        self.preload_cache()

    def preload_cache(self) -> None:
        if self.commit is None:
            return
        diff_tree = self.commit.tree.diff_to_tree(
            self.commit.parents[0].tree
        )
        for delta in diff_tree.deltas:
            self.blame_cache.get_blame_info(self.commit.parents[0], delta.old_file.path)

    def within_hunk(self, line: Text) -> bool:
        return (
            self.current_hunk_start is not None
            and not line.plain.startswith('diff')
            and not line.plain.startswith('index')
            and not line.plain.startswith('---')
            and not line.plain.startswith('+++')
            and not line.plain.startswith('@@')
            and not line.plain.startswith('new file mode')
        )

    async def get_blame_line(self, line: Text) -> Text:
        plain_line = line.plain
        if plain_line.startswith("diff"):
            return line
        if plain_line.startswith("index"):
            return line
        if plain_line.startswith("---"):
            self.current_file = plain_line[6:].strip()
            return line
        if plain_line.startswith("+++"):
            return line
        if plain_line.startswith("new file mode"):
            return line
        if plain_line.startswith("@@"):
            self.current_hunk_start = int(self.hunk_pattern.match(plain_line).group("old_start")) - 1
            self.current_hunk_line_index = 0
            return line
        if self.current_file is None or self.current_hunk_start is None or not self.enabled:
            return line

        new_line = Text("")

        if plain_line.startswith("+"):
            new_line.append(
                Text(
                    abbrev(self.commit.id) + " ",
                    SolarizedColors.Yellow
                )
            )
        else:
            blame = await self.blame_cache.get_blame_info(
                self.commit.parents[0], self.current_file
            ).get_blame_info()
            new_line.append(
                Text(
                    abbrev(blame[self.current_hunk_start + self.current_hunk_line_index].id) + " ",
                    SolarizedColors.Yellow
                )
            )
            self.current_hunk_line_index += 1

        new_line.append(line)
        return new_line


class CloseDiffTable(Message):
    pass


class DiffTable(DataTable):

    BINDINGS = [
        ("b", "toggle_blame", "Toggle blame info"),
        ("q", "quit_diff", "Close side-by-side diff"),
        ("W", "toggle_function_context", "Toggle function context"),
    ]

    CSS = """
    DataTable {
        scrollbar-gutter: stable;
        overflow-x: hidden;
    }
    """

    def __init__(self, repo: pygit2.Repository, **kwargs):
        super().__init__(**kwargs)
        self.repo: pygit2.Repository = repo
        self.left_commit: pygit2.Commit | None = None
        self.right_commit: pygit2.Commit | None = None
        self.search_term: str | None = None
        self.current_row_index: int = 0
        self.search_bar = SearchBar()
        self.diff = []
        self.show_function_context: bool = True
        self.show_blame: bool = False
        self.blame_cache: BlameCache = BlameCache(self.repo)
        self.show_diff_lock: asyncio.Lock = asyncio.Lock()
        self.reload_lock: asyncio.Lock = asyncio.Lock()

    async def action_toggle_blame(self) -> None:
        self.show_blame = not self.show_blame
        await self.show_diff()

    async def action_toggle_function_context(self) -> None:
        self.show_function_context = not self.show_function_context
        async with self.reload_lock:
            self.current_row_index = 0
            self.load_commit_diff(self.left_commit, self.right_commit)
            await self.show_diff()

    async def set_fuzzy_search(self, search_term: str) -> None:
        move_first_match = self.search_term != search_term

        self.search_term = search_term

        await self.show_diff()

        if not self.search_term:
            return

        matches = []
        for row_index, row_key in enumerate(self.rows.keys()):
            for cell_index, cell in enumerate(self.get_row(row_key)):
                if self.search_term in cell.plain:
                    matches.append(row_index)
                    break

        if not matches:
            self.move_cursor(row=0)
            return

        if move_first_match or max(matches) <= self.current_row_index:
            self.move_cursor(row=matches[0])
        else:
            for row_index in matches:
                if (row_index > self.current_row_index):
                    self.move_cursor(row=row_index)
                    break

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.current_row_index = event.cursor_row

    def on_mount(self):
        self.cursor_type = "row"
        self.wrap = False

    def action_quit_diff(self) -> None:
        self.load_commit_diff(None, None)
        self.post_message(CloseDiffTable())

    def check_action(self, action: str, parameters) -> bool:
        return self.scrollable_content_region.height > 0

    def available_width(self):
        return self.scrollable_content_region.width - 6

    async def on_resize(self) -> None:
        self.refresh_bindings()
        if self.left_commit is None and self.right_commit is None:
            return
        async with self.reload_lock:
            if self.width != self.available_width():
                self.load_commit_diff(self.left_commit, self.right_commit)
                await self.show_diff()

    def load_commit_diff(
            self,
            left_commit: None | pygit2.Commit,
            right_commit: None | pygit2.Commit
    ) -> None:
        self.left_commit = left_commit
        self.right_commit = right_commit

        if self.right_commit is None and self.left_commit is None:
            self.clear(columns=True)
            self.diff = []
            self.current_row_index = 0
            return

        def build_show_cmd(commit):
            show_cmd = [
                "git", "-C", self.repo.workdir, "show"
            ]
            if self.show_function_context:
                show_cmd.append("-W")
            show_cmd.append(abbrev(commit.id))
            return show_cmd

        log("load_commit_diff called")

        self.width = self.available_width()

        with NamedTemporaryFile(mode="w+t") as left_diff_path, \
             NamedTemporaryFile(mode="w+t") as right_diff_path:
            if self.left_commit:
                subprocess.run(
                    build_show_cmd(left_commit),
                    stdout=left_diff_path,
                )

            if self.right_commit:
                subprocess.run(
                    build_show_cmd(self.right_commit),
                    stdout=right_diff_path,
                )

            cmd = [
                "diff", "-y", f"-W{self.width}", "-t",
                left_diff_path.name,
                right_diff_path.name
            ]

            self.diff = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            ).stdout.splitlines()

    async def show_diff(self) -> None:
        async with self.show_diff_lock:
            await self._show_diff()

    async def _show_diff(self) -> None:
        def expected_change(line):
            line = str(line)
            return (
                line.startswith("commit") or
                line.startswith("index") or
                line.startswith("@@") or
                line.startswith("diff")
            )

        def colorize_diffs(left_column, middle_column, right_column):
            two_commits = self.right_commit is not None and self.left_commit is not None
            def colorize_column(column):
                if len(column):
                    match column.plain[0]:
                        case "+":
                            column.stylize(SolarizedColors.Green)
                        case "-":
                            column.stylize(SolarizedColors.Red)
                        case _:
                            if middle_column.plain in ["|", ">", "<"] and two_commits:
                                column.stylize(SolarizedColors.Violet)
            colorize_column(right_column)
            colorize_column(left_column)

            if middle_column.plain in [">", "<", "|"] and two_commits:
                left_column.stylize("bold")
                middle_column.stylize(f"bold {SolarizedColors.Violet}")
                right_column.stylize("bold")

        def highlight_diff_tokens(left_column, middle_column, right_column):
            highlight_token_diffs = (
                middle_column.plain == "|"
                and left_diff_blame_parser.within_hunk(left_column)
                and right_diff_blame_parser.within_hunk(right_column)
            )

            if not highlight_token_diffs:
                return

            lexer = get_lexer_for_filename(left_diff_blame_parser.current_file)
            left_tokens = [v for _, v in lexer.get_tokens(left_column.plain[1:])]
            right_tokens = [v for _, v in lexer.get_tokens(right_column.plain[1:])]

            matcher = SequenceMatcher(None, left_tokens, right_tokens)

            left_idx, right_idx = 0, 0

            #bg = Style(bgcolor=SolarizedColors.Base02)
            bg = "reverse"

            for opcode, l1, l2, r1, r2 in matcher.get_opcodes():
                log(opcode, l1, l2, r1, r2, left_tokens[l1:l2], right_tokens[r1:r2])
                if opcode == 'equal':
                    left_idx += sum([len(t) for t in left_tokens[l1:l2]])
                    right_idx += sum([len(t) for t in right_tokens[r1:r2]])
                    continue

                for i in range(l1, l2):
                    if i == len(left_tokens) - 1 or i == len(left_tokens) - 2:
                        break
                    left_column.stylize(bg, left_idx + 1, left_idx + len(left_tokens[i]) + 1)
                    left_idx += len(left_tokens[i])
                for i in range(r1, r2):
                    if i == len(right_tokens) - 1:
                        break
                    right_column.stylize(bg, right_idx + 1, right_idx + len(right_tokens[i]) + 1)
                    right_idx += len(right_tokens[i])


        def highlight_matched_terms(left_column: Text, right_column: Text) -> None:
            if self.search_term:
                left_column.highlight_words([self.search_term], "reverse")
                right_column.highlight_words([self.search_term], "reverse")

        async def prefix_blame_info(l: Text, c: Text, r: Text) -> None:
            match c.plain[0]:
                case ">":
                    r = await right_diff_blame_parser.get_blame_line(r)
                case "<":
                    l = await left_diff_blame_parser.get_blame_line(l)
                case _:
                    l = await left_diff_blame_parser.get_blame_line(l)
                    r = await right_diff_blame_parser.get_blame_line(r)

            return l, r

        log("show_diff called")
        self.clear(columns=True)

        self.add_column(cell_from_commit(self.left_commit), width=self.width // 2 - 2)
        self.add_column(Text(" "), width=1)
        self.add_column(cell_from_commit(self.right_commit), width=self.width // 2 - 2)

        right_diff_blame_parser = DiffBlameParser(self.blame_cache, self.show_blame, self.right_commit)
        left_diff_blame_parser = DiffBlameParser(self.blame_cache, self.show_blame, self.left_commit)

        for line_idx, line in enumerate(self.diff):

            if not line:
                self.add_row(Text(""), Text(""), Text(""))
                continue

            richline = Text(line)
            middle_point = (self.width + 1) // 2 - 1
            right_first_char_index = 2 if self.width % 2 != 0 else 3
            l, c, r = (
                richline[:middle_point],
                richline[middle_point],
                richline[middle_point+right_first_char_index:]
            )

            colorize_diffs(l, c, r)
            l, r = await prefix_blame_info(l, c, r)
            highlight_diff_tokens(l, c, r)
            highlight_matched_terms(l, r)

            self.add_row(cell(l), c, cell(r))
            if line_idx % 100:
                await asyncio.sleep(0)

        self.move_cursor(row=self.current_row_index)


def cell(t: Text) -> Text:
    t.overflow = "ellipsis"
    t.no_wrap = True
    return t


def cell_from_commit(commit) -> Text:
    c = cell(Text(""))
    if commit is None:
        return c

    c.append(Text(abbrev(commit.id), SolarizedColors.Yellow))
    c.append(Text(" " + commit_title(commit)))
    return c


class RebaseTable(DataTable):

    BINDINGS = [
        ("enter", "show_diff", "Show side-by-side diff"),
        ("c", "comment", "Comment commit"),
    ]


    def __init__(
            self, args: argparse.Namespace,
            repo: pygit2.Repository,
            filters: dict[CommitMatchInfoFlag, FilterType],
            **kwargs):
        super().__init__(**kwargs)
        self.args = args
        self.repo = repo
        self.rebased_commit_matches: None | RebasedCommitsMatches = None
        self.filters = filters
        self.fuzzy_terms: None | list[str] = None
        self.search_bar = SearchBar(fuzzy=True)
        self.column_keys: list[ColumnKey] = [
            self.add_column(self.args.left_range.split("..")[1], width=80),
            self.add_column(Text("Match type")),
            self.add_column(self.args.right_range.split("..")[1], width=80),
        ]

    def action_comment(self) -> None:
        with self.app.suspend():
            subprocess.run([
                "git",
                "-C", self.repo.workdir,
                "notes",
                "add",
                str(self.row_key.value)])

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        self.row_key = event.row_key

    def action_show_diff(self) -> None:
        self.action_select_cursor()

    def on_mount(self) -> None:
        self.loading = True
        self.cursor_type = "row"
        self.wrap = False
        self.zebra_stripes = True
        self.styles.height = "100%"

    def on_resize(self) -> None:
        self.update_column_widths()

    def update_column_widths(self) -> None:
        total_width = self.scrollable_content_region.width - 4
        middle_width = 16
        side_width = (total_width - middle_width) // 2
        self.columns[self.column_keys[0]].width = side_width
        self.columns[self.column_keys[1]].width = middle_width
        self.columns[self.column_keys[2]].width = side_width
        self.refresh()

    def set_filters(self, filters: dict[CommitMatchInfoFlag, FilterType]):
        if filters == self.filters:
            return
        self.filters = filters
        self.reload_table()

    async def set_fuzzy_search(self, fuzzy_search: str) -> None:
        def split_terms():
            return [t for t in fuzzy_search.split(" ") if t]

        fuzzy_terms = split_terms()
        if self.fuzzy_terms == fuzzy_terms:
            return
        self.fuzzy_terms = fuzzy_terms
        self.reload_table()

    def load_ranges(self, rebased_commit_matches: RebasedCommitsMatches) -> None:
        self.rebased_commit_matches = rebased_commit_matches
        self.reload_table()
        self.update_column_widths()
        self.loading = False

    def reload_table(self):
        def markers_from_match_type(match_type):
            match_markers = Text("")
            for match_info in CommitMatchInfoFlag:
                if match_info in match_type:
                    match_markers += commit_match_info_repr[match_info].character
            match_markers.align("center", width=self.columns[self.column_keys[1]].width)
            return match_markers

        def commit_filtered_out():
            for match_type, filter_type in self.filters.items():
                match filter_type:
                    case FilterType.NoFilter:
                        continue
                    case FilterType.With:
                        if match_type not in rebased_commit_match.match_type:
                            return True
                    case FilterType.Without:
                        if match_type in rebased_commit_match.match_type:
                            return True
            if self.fuzzy_terms is not None and self.fuzzy_terms:
                all_matched = True
                for term in self.fuzzy_terms:
                    if term not in left_cell and term not in right_cell:
                        all_matched = False
                        break
                    left_cell.highlight_words([term], style="reverse")
                    right_cell.highlight_words([term], style="reverse")
                return not all_matched
            return False

        self.clear(columns=False)

        for commit_oid, rebased_commit_match in (
                self.rebased_commit_matches.commit_matches.items()
        ):
            left_cell = cell_from_commit(rebased_commit_match.left_commit)
            right_cell = cell_from_commit(rebased_commit_match.right_commit)

            if commit_filtered_out():
                continue

            self.add_row(
                left_cell,
                markers_from_match_type(
                    rebased_commit_match.match_type
                ),
                right_cell,
                key=commit_oid
            )


class FilterRadioButton(RadioButton):
    def __init__(self, filter_type: FilterType, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filter_type = filter_type


class FilterScreen(ModalScreen):
    CSS = """
    FilterScreen {
        align: center middle;
    }

    Button {
        margin: 1 2
    }

    #filter_dialog {
        background: $panel;
        border: thick $primary;
        width: 90;
        height: auto;
        padding: 1 2;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel")
    ]

    def __init__(self, filters: dict[CommitMatchInfoFlag, FilterType], **kwargs):
        super().__init__(**kwargs)
        self.filters = filters

    def compose(self) -> ComposeResult:
        with Vertical(id="filter_dialog"):
            for flag in CommitMatchInfoFlag:
                with RadioSet(id=flag.name):
                    yield Label(
                        commit_match_info_repr[flag].character +
                        " " +
                        commit_match_info_repr[flag].definition
                    )
                    yield RadioButton(
                        FilterType.With.name,
                        value=self.filters[flag] == FilterType.With
                    )
                    yield RadioButton(
                        FilterType.Without.name,
                        value=self.filters[flag] == FilterType.Without
                    )
                    yield RadioButton(
                        FilterType.NoFilter.name,
                        value=self.filters[flag] == FilterType.NoFilter
                    )
            yield Button("Apply filters", variant="primary")
            yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.label == "Apply filters":
            radio_sets = self.query(RadioSet)
            filters = {}
            for radio_set in radio_sets:
                log(radio_set.pressed_button)
                filters[CommitMatchInfoFlag[radio_set.id]] = FilterType[radio_set.pressed_button.label]
            self.dismiss(filters)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SearchBar(Input):

    BINDINGS = [
        ("enter", "done", "Done searching"),
        ("escape", "cancel", "Clear search and close"),
        ("f3", "next", "Next match"),
    ]

    def __init__(self, *args, fuzzy: bool = False, **kwargs):
        kwargs["compact"] = True
        super().__init__(*args, **kwargs)
        self.placeholder = "Search"
        self.select_on_focus = False
        self.styles.display = "none"
        self.fuzzy = fuzzy
        self.refresh_bindings()

    def action_next(self) -> None:
        # Will send an event
        self.post_message(self.Changed(self, self.value))

    def action_cancel(self) -> None:
        self.value = ""
        self.post_message(self.Submitted(self, self.value))

    def action_done(self) -> None:
        self.post_message(self.Submitted(self, self.value))

    def check_action(self, action, parameters):
        if action != "next":
            return True
        else:
            return not self.fuzzy




class GitReviewRebase(App):
    """Entry-point."""

    CSS = """
    DataTable > .datatable--header {
        color: $primary;
    }
    """

    BINDINGS = [
        ("/", "search", "Search"),
        ("d", "toggle_theme", "Toggle light/dark theme"),
        ("f", "show_filters", "Filter by match type"),
        ("q", "quit", "Quit")
    ]

    def check_action(self, action, parameters):
        if action in ["quit", "toggle_theme"]:
            return True
        return not self.rebase_table.loading

    def __init__(self, args, **kwargs):
        super().__init__(**kwargs)
        self.args = args
        self.repo = pygit2.Repository(args.repository)
        self.filters: dict[CommitMatchInfoFlag, FilterType] = {
            match_info: FilterType.NoFilter for match_info in CommitMatchInfoFlag
        }
        self.rebase_table: None | RebaseTable = None
        self.diff_table: None | DiffTable = None
        self.diff_search_bar: None | SearchBar = None
        self.rebase_search_bar: None | SearchBar = None
        self.left_range: None | BranchRange = None
        self.right_range: None | BranchRange = None
        self.rebased_commits_matches: None | RebasedCommitsMatches = None
        self.active_table: None | DataTable = None

    def action_toggle_theme(self) -> None:
        if self.theme == "solarized-dark":
            self.theme = "solarized-light"
        else:
            self.theme = "solarized-dark"

    def action_search(self) -> None:
        self.active_table.search_bar.styles.display = "block"
        self.active_table.search_bar.styles.dock = "bottom"
        self.active_table.search_bar.styles.height = "1"
        self.active_table.search_bar.focus()

    async def on_input_changed(self, event: Input.Changed) -> None:
        await self.active_table.set_fuzzy_search(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.active_table.search_bar.styles.display = "none"
        self.active_table.focus()

    def compose(self) -> ComposeResult:
        self.rebase_table = RebaseTable(self.args, self.repo, self.filters)
        self.diff_table = DiffTable(self.repo)
        self.active_table = self.rebase_table

        yield Header()
        container = Vertical(
            self.rebase_table,
            self.diff_table,
            self.rebase_table.search_bar,
            self.diff_table.search_bar,
        )
        container.styles.height = "1fr"
        yield container
        yield Footer()
        self.refresh_bindings()

    def action_show_filters(self) -> None:
        self.push_screen(FilterScreen(self.filters, name="Filters"), self.apply_filters)

    def apply_filters(
            self,
            filters: dict[CommitMatchInfoFlag, FilterType] | None
    ) -> None:
        if not filters:
            return
        self.filters = filters
        self.rebase_table.set_filters(filters)

    def on_mount(self) -> None:
        self.theme = "solarized-dark"
        self.load_ranges()

    @work
    async def load_ranges(self) -> None:
        self.left_range = await asyncio.to_thread(
            BranchRange,
            self.repo,
            self.args.left_range.split("..")[0],
            self.args.left_range.split("..")[1],
            self.args.cache_flags
        )
        self.right_range = await asyncio.to_thread(
            BranchRange,
            self.repo,
            self.args.right_range.split("..")[0],
            self.args.right_range.split("..")[1],
            self.args.cache_flags
        )
        self.rebased_commits_matches = RebasedCommitsMatches(
            self.args,
            self.repo,
            self.left_range,
            self.right_range
        )
        self.rebase_table.load_ranges(self.rebased_commits_matches)
        self.rebase_table.focus()
        self.refresh_bindings()

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table == self.rebase_table:
            self.rebase_table.styles.height = "20%"
            self.diff_table.styles.height = "80%"
            async with self.diff_table.reload_lock:
                self.diff_table.load_commit_diff(
                    self.rebased_commits_matches.commit_matches[event.row_key.value].left_commit,
                    self.rebased_commits_matches.commit_matches[event.row_key.value].right_commit
                )
                await self.diff_table.show_diff()
            self.diff_table.focus()
            self.active_table = self.diff_table
            self.refresh()


    def on_close_diff_table(self, message: CloseDiffTable):
        self.diff_table.styles.height = 0
        self.rebase_table.styles.height = "100%"
        self.rebase_table.focus()
        self.refresh()
        self.active_table = self.rebase_table


def parse_args() -> tuple:
    """Parse the arguments and return them."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=str, default=".")
    parser.add_argument(
        "--no-cache",
        action="store_false",
        default=True,
        dest="cache"
    )
    parser.add_argument("left_range")
    parser.add_argument("right_range")
    args = parser.parse_args()

    args.repository = os.path.expanduser(args.repository)

    args.cache_flags = CacheFlags(0)
    if args.cache:
        args.cache_flags = CacheFlags.READ_FROM_CACHE | CacheFlags.WRITE_TO_CACHE

    return args


def main():
    args = parse_args()
    app = GitReviewRebase(args)
    app.run()


if __name__ == "__main__":
    main()
