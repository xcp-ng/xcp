"""Rebase table widget for viewing commit matches."""

import argparse
import subprocess

import pygit2
from rich.text import Text
from textual.widgets import DataTable

from ..commit_matching import RebasedCommitsMatches
from ..constants import CommitMatchInfoFlag, FilterType, commit_match_info_repr
from .search_bar import SearchBar
from .utils import cell_from_commit


class RebaseTable(DataTable):

    BINDINGS = [
        ("enter", "show_diff", "Show side-by-side diff"),
        ("c", "comment", "Comment commit"),
    ]

    def __init__(
        self,
        args: argparse.Namespace,
        repo: pygit2.Repository,
        filters: dict[CommitMatchInfoFlag, FilterType],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.args = args
        self.repo = repo
        self.rebased_commit_matches: None | RebasedCommitsMatches = None
        self.filters = filters
        self.fuzzy_terms: None | list[str] = None
        self.search_bar = SearchBar(fuzzy=True)
        self.column_keys = [
            self.add_column(self.args.left_range.split("..")[1], width=80),
            self.add_column(Text("Match type")),
            self.add_column(self.args.right_range.split("..")[1], width=80),
        ]

    def action_comment(self) -> None:
        with self.app.suspend():
            subprocess.run(
                ["git", "-C", self.repo.workdir, "notes", "add", str(self.row_key.value)]
            )

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
                        if match_type not in rebased_commit_match.match_info:
                            return True
                    case FilterType.Without:
                        if match_type in rebased_commit_match.match_info:
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

        assert self.rebased_commit_matches is not None
        for commit_oid, rebased_commit_match in self.rebased_commit_matches.commit_matches.items():
            left_cell = cell_from_commit(rebased_commit_match.left_commit)
            right_cell = cell_from_commit(rebased_commit_match.right_commit)

            if commit_filtered_out():
                continue

            # assert isinstance(commit_oid, str), f"{commit_oid} type ({type(commit_oid)}) != str"
            self.add_row(
                left_cell,
                markers_from_match_type(rebased_commit_match.match_info),
                right_cell,
                key=commit_oid,  # type: ignore
            )
