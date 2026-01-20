"""Main application class."""

import asyncio

import pygit2
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Input

from .branch_range import BranchRange
from .commit_matching import RebasedCommitsMatches
from .constants import CommitMatchInfoFlag, FilterType
from .git_utils import oid
from .ui.diff_table import CloseDiffTable, DiffTable
from .ui.filter_screen import FilterScreen
from .ui.rebase_table import RebaseTable


class GitReviewRebase(App):
    """Entry-point."""

    CSS = """
    DataTable > .datatable--header {
        color: $primary;
    }
    """

    BINDINGS = [
        ("/", "search", "Search"),
        ("C", "clear_filters", "Clear filters"),
        ("d", "toggle_theme", "Toggle light/dark theme"),
        ("f", "show_filters", "Filter by match type"),
        ("q", "quit", "Quit"),
    ]

    def check_action(self, action, parameters):
        if action in ["quit", "toggle_theme"]:
            return True
        if action in ["show_filters", "clear_filters"]:
            return (
                self.rebase_table is not None
                and not self.rebase_table.loading
                and self.active_table == self.rebase_table
            )
        return True

    def no_filters(self) -> bool:
        for f in self.filters.values():
            if f != FilterType.NoFilter:
                return False
        return True

    def action_clear_filters(self) -> None:
        self.apply_filters(dict.fromkeys(CommitMatchInfoFlag, FilterType.NoFilter))

    def __init__(self, args, **kwargs):
        super().__init__(**kwargs)
        self.args = args
        self.repo = pygit2.Repository(args.repository)
        self.filters: dict[CommitMatchInfoFlag, FilterType] = dict.fromkeys(
            CommitMatchInfoFlag, FilterType.NoFilter
        )
        self.rebase_table: None | RebaseTable = None
        self.diff_table: None | DiffTable = None
        self.diff_search_bar: None | Input = None
        self.rebase_search_bar: None | Input = None
        self.left_range: None | BranchRange = None
        self.right_range: None | BranchRange = None
        self.rebased_commits_matches: None | RebasedCommitsMatches = None
        self.active_table: None | RebaseTable | DiffTable = None

    def action_toggle_theme(self) -> None:
        if self.theme == "solarized-dark":
            self.theme = "solarized-light"
        else:
            self.theme = "solarized-dark"

    def action_search(self) -> None:
        assert self.active_table is not None
        self.active_table.search_bar.styles.display = "block"
        self.active_table.search_bar.styles.dock = "bottom"
        self.active_table.search_bar.styles.height = "1"
        self.active_table.search_bar.focus()

    async def on_input_changed(self, event: Input.Changed) -> None:
        assert self.active_table is not None
        await self.active_table.set_fuzzy_search(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        assert self.active_table is not None
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

    def apply_filters(self, filters: dict[CommitMatchInfoFlag, FilterType] | None) -> None:
        if not filters:
            return
        self.filters = filters
        assert self.rebase_table is not None
        self.rebase_table.set_filters(filters)

    def on_mount(self) -> None:
        self.theme = "solarized-dark"
        self.load_ranges()

    @work
    async def load_ranges(self) -> None:
        assert self.rebase_table is not None
        merge_base = self.repo.merge_base(
            oid(self.repo, self.args.left_range.split("..")[1]),
            oid(self.repo, self.args.right_range.split("..")[1]),
        )
        self.left_range = await asyncio.to_thread(
            BranchRange,
            self.repo,
            self.args.left_range.split("..")[0],
            self.args.left_range.split("..")[1],
            self.args.cache_flags,
        )
        self.right_range = await asyncio.to_thread(
            BranchRange,
            self.repo,
            self.args.right_range.split("..")[0],
            self.args.right_range.split("..")[1],
            self.args.cache_flags,
            merge_base=merge_base,
        )
        self.rebased_commits_matches = RebasedCommitsMatches(
            self.args, self.repo, self.left_range, self.right_range
        )
        self.rebase_table.load_ranges(self.rebased_commits_matches)
        self.rebase_table.focus()
        self.refresh_bindings()

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        assert self.diff_table is not None
        assert self.rebase_table is not None

        if event.data_table == self.rebase_table:
            assert event.row_key.value is not None
            self.rebase_table.styles.height = "20%"
            self.diff_table.styles.height = "80%"
            async with self.diff_table.reload_lock:
                assert self.rebased_commits_matches is not None
                assert isinstance(event.row_key.value, pygit2.Oid)
                self.diff_table.load_commit_diff(
                    self.rebased_commits_matches.commit_matches[event.row_key.value].left_commit,
                    self.rebased_commits_matches.commit_matches[event.row_key.value].right_commit,
                )
                await self.diff_table.show_diff()
            self.diff_table.focus()
            self.active_table = self.diff_table
            self.refresh()

    def on_close_diff_table(self, message: CloseDiffTable):
        assert self.diff_table is not None
        assert self.rebase_table is not None
        self.diff_table.styles.height = 0
        self.rebase_table.styles.height = "100%"
        self.rebase_table.focus()
        self.refresh()
        self.active_table = self.rebase_table
