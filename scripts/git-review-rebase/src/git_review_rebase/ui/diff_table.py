"""Diff table widget for side-by-side diff viewing."""

import asyncio
import subprocess
from difflib import SequenceMatcher
from tempfile import NamedTemporaryFile

import pygit2
from pygments.lexers import get_lexer_for_filename
from rich.text import Text
from textual.message import Message
from textual.widgets import DataTable

from ..blame import BlameCache
from ..constants import SolarizedColors
from ..diff_parser import DiffParser
from ..git_utils import abbrev
from .search_bar import SearchBar
from .utils import cell, cell_from_commit


class CloseDiffTable(Message):
    pass


class DiffPrettyRowMaker:
    def __init__(
        self,
        right_commit: None | pygit2.Commit,
        left_commit: None | pygit2.Commit,
        blame_cache: None | BlameCache,
        search_term: None | str,
        width: int,
    ):
        self.right_commit = right_commit
        self.left_commit = left_commit

        self.middle_point = (width + 1) // 2 - 1
        self.right_first_char_index = 2 if width % 2 != 0 else 3

        self.right_diff: DiffParser = DiffParser()
        self.left_diff: DiffParser = DiffParser()

        self.blame_cache = blame_cache

        self.search_term = search_term

    def colorize_diffs(self, left_text: Text, middle_text: Text, right_text: Text) -> None:
        two_commits = self.right_commit is not None and self.left_commit is not None

        def colorize_column(column):
            if len(column):
                match column.plain[0]:
                    case "+":
                        column.stylize(SolarizedColors.Green)
                    case "-":
                        column.stylize(SolarizedColors.Red)
                    case _:
                        if middle_text.plain in ["|", ">", "<"] and two_commits:
                            column.stylize(SolarizedColors.Violet)

        colorize_column(right_text)
        colorize_column(left_text)

        if middle_text.plain in [">", "<", "|"] and two_commits:
            left_text.stylize("bold")
            middle_text.stylize(f"bold {SolarizedColors.Violet}")
            right_text.stylize("bold")

    def highlight_diff_tokens(self, left_text: Text, middle_text: Text, right_text: Text) -> None:
        should_highlight_tokens = (
            middle_text.plain == "|"
            and self.left_diff.within_hunk()
            and self.right_diff.within_hunk()
        )

        if not should_highlight_tokens:
            return

        assert self.left_diff.old_file is not None
        lexer = get_lexer_for_filename(self.left_diff.old_file)
        left_tokens = [v for _, v in lexer.get_tokens(left_text.plain[1:])]
        right_tokens = [v for _, v in lexer.get_tokens(right_text.plain[1:])]

        matcher = SequenceMatcher(None, left_tokens, right_tokens)

        left_idx, right_idx = 0, 0

        bg = "reverse"

        for opcode, l1, l2, r1, r2 in matcher.get_opcodes():
            if opcode == "equal":
                left_idx += sum([len(t) for t in left_tokens[l1:l2]])
                right_idx += sum([len(t) for t in right_tokens[r1:r2]])
                continue

            for i in range(l1, l2):
                if i == len(left_tokens) - 1 or (
                    i == len(left_tokens) - 2 and not left_tokens[i].strip()
                ):
                    break
                left_text.stylize(bg, left_idx + 1, left_idx + len(left_tokens[i]) + 1)
                left_idx += len(left_tokens[i])
            for i in range(r1, r2):
                if i == len(right_tokens) - 1:
                    break
                right_text.stylize(bg, right_idx + 1, right_idx + len(right_tokens[i]) + 1)
                right_idx += len(right_tokens[i])

    async def stylicize(
        self, left_diff_line: str, middle_char: str, right_diff_line: str
    ) -> tuple[Text, Text, Text]:
        left_text, middle_text, right_text = (
            Text(left_diff_line),
            Text(middle_char),
            Text(right_diff_line),
        )

        self.colorize_diffs(left_text, middle_text, right_text)
        self.highlight_diff_tokens(left_text, middle_text, right_text)
        if self.blame_cache is not None:
            left_text, right_text = await self.add_blame_info(left_text, middle_text, right_text)
        self.highlight_matched_terms(left_text, right_text)
        return left_text, middle_text, right_text

    def highlight_matched_terms(self, left_text: Text, right_text: Text) -> None:
        if self.search_term is not None:
            left_text.highlight_words([self.search_term], "reverse")
            right_text.highlight_words([self.search_term], "reverse")

    @staticmethod
    def prefix_blame_info(commit: pygit2.Commit, line_text: Text) -> Text:
        new_line = Text("")
        new_line.append_text(Text(abbrev(commit.id) + " ", SolarizedColors.Yellow))
        new_line.append_text(line_text)
        return new_line

    async def prefix(self, diff_parser: DiffParser, commit: pygit2.Commit, cur_line: Text) -> Text:
        if not diff_parser.within_hunk():
            return cur_line

        if not cur_line.plain.startswith("+"):
            position = diff_parser.get_current_position()
            assert self.blame_cache is not None
            blame_info = self.blame_cache.get_blame_info(commit.parents[0], position.old_file)
            commit = await blame_info.commit_at(position.old_line_number - 1)

        return self.prefix_blame_info(commit, cur_line)

    async def add_blame_info(
        self, left_text: Text, middle_text: Text, right_text: Text
    ) -> tuple[Text, Text]:

        match middle_text.plain[0]:
            case ">":
                assert self.right_commit is not None
                left = left_text
                right = await self.prefix(self.right_diff, self.right_commit, right_text)
            case "<":
                assert self.left_commit is not None
                right = right_text
                left = await self.prefix(self.left_diff, self.left_commit, left_text)
            case _:
                assert self.left_commit is not None
                assert self.right_commit is not None
                right = await self.prefix(self.right_diff, self.right_commit, right_text)
                left = await self.prefix(self.left_diff, self.left_commit, left_text)
        return left, right

    async def get_row_from_line(self, line: str) -> tuple[Text, Text, Text]:
        if not line:
            return (Text(""), Text(""), Text(""))

        left_diff_line, middle_char, right_diff_line = (
            line[: self.middle_point],
            line[self.middle_point],
            line[self.middle_point + self.right_first_char_index :],
        )

        self.right_diff.parse_line(right_diff_line)
        self.left_diff.parse_line(left_diff_line)

        left, middle, right = await self.stylicize(left_diff_line, middle_char, right_diff_line)
        return cell(left), middle, cell(right)


class DiffTable(DataTable):

    BINDINGS = [
        ("b", "toggle_blame", "Toggle blame info"),
        ("q", "quit_diff", "Close side-by-side diff"),
        ("W", "toggle_function_context", "Toggle function context"),
    ]

    DEFAULT_CSS = """
    DiffTable {
        scrollbar-gutter: stable;
        overflow-y: scroll;
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
        self.diff: list[str] = []
        self.show_function_context: bool = True
        self.show_blame: bool = False
        self.blame_cache: BlameCache = BlameCache(self.repo)
        self.show_diff_lock: asyncio.Lock = asyncio.Lock()
        self.reload_lock: asyncio.Lock = asyncio.Lock()

    async def action_toggle_blame(self) -> None:
        self.show_blame = not self.show_blame
        scroll_offset = self.scroll_offset
        await self.show_diff()
        self.call_after_refresh(self.scroll_to, y=scroll_offset.y, animate=False)

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
            for cell_content in self.get_row(row_key):
                if self.search_term in cell_content.plain:
                    matches.append(row_index)
                    break

        if not matches:
            self.move_cursor(row=0)
            return

        if move_first_match or max(matches) <= self.current_row_index:
            self.move_cursor(row=matches[0])
        else:
            for row_index in matches:
                if row_index > self.current_row_index:
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
        # We have one character padding on the left/right of each colum, 2
        # padding characters per column = 6, plus 2 bytes for the scollbar
        # = 8
        return self.scrollable_content_region.width - 8

    async def on_resize(self) -> None:
        self.refresh_bindings()
        if self.left_commit is None and self.right_commit is None:
            return
        async with self.reload_lock:
            if self.width != self.available_width():
                self.load_commit_diff(self.left_commit, self.right_commit)
                await self.show_diff()

    def load_commit_diff(
        self, left_commit: None | pygit2.Commit, right_commit: None | pygit2.Commit
    ) -> None:
        self.left_commit = left_commit
        self.right_commit = right_commit

        if self.right_commit is None and self.left_commit is None:
            self.clear(columns=True)
            self.diff = []
            self.current_row_index = 0
            return

        def build_show_cmd(commit):
            show_cmd = ["git", "-C", self.repo.workdir, "show"]
            if self.show_function_context:
                show_cmd.append("-W")
            show_cmd.append(abbrev(commit.id))
            return show_cmd

        if self.left_commit is not None:
            self.blame_cache.preload_commit(self.left_commit)
        if self.right_commit is not None:
            self.blame_cache.preload_commit(self.right_commit)

        self.width = self.available_width()

        with (
            NamedTemporaryFile(mode="w+t") as left_diff_path,
            NamedTemporaryFile(mode="w+t") as right_diff_path,
        ):
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

            cmd = ["diff", "-y", f"-W{self.width}", "-t", left_diff_path.name, right_diff_path.name]

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
        self.clear(columns=True)
        column_length = (self.width - 1) // 2

        self.add_column(cell_from_commit(self.left_commit), width=column_length)
        self.add_column(Text(" "), width=1)
        self.add_column(cell_from_commit(self.right_commit), width=column_length)

        diff_row_maker = DiffPrettyRowMaker(
            self.right_commit,
            self.left_commit,
            self.blame_cache if self.show_blame else None,
            self.search_term,
            self.width,
        )

        for line in self.diff:
            row = await diff_row_maker.get_row_from_line(line)
            self.add_row(*row)

        self.move_cursor(row=self.current_row_index, scroll=False)
