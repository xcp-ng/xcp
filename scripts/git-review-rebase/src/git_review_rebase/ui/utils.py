"""Utility functions for UI components."""

from rich.text import Text

from ..constants import SolarizedColors
from ..git_utils import abbrev, commit_title


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
