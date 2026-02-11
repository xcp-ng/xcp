"""Constants, enums, and color definitions for git-review-rebase."""

from enum import Enum, Flag, StrEnum, auto

from rich.text import Text


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
    SameCommit = auto()
    LooseMatch = auto()
    PresentInRebaseOnto = auto()
    Dropped = auto()
    Added = auto()
    Reviewed = auto()


class CommitMatchInfo:
    def __init__(self, flag, character, definition):
        self.flag = flag
        self.character = character
        self.definition = definition


commit_match_info_repr = {
    CommitMatchInfoFlag.SameCommit: CommitMatchInfo(
        CommitMatchInfoFlag.SameCommit, Text("=", SolarizedColors.Green), "Commits are the same"
    ),
    CommitMatchInfoFlag.LooseMatch: CommitMatchInfo(
        CommitMatchInfoFlag.LooseMatch,
        Text("≈", SolarizedColors.Yellow),
        "Commit patchid has changed",
    ),
    CommitMatchInfoFlag.PresentInRebaseOnto: CommitMatchInfo(
        CommitMatchInfoFlag.PresentInRebaseOnto,
        Text("⤶", SolarizedColors.Blue),
        "Commit present in new upstream",
    ),
    CommitMatchInfoFlag.Dropped: CommitMatchInfo(
        CommitMatchInfoFlag.Dropped, Text("✗", SolarizedColors.Red), "Commit dropped in rebase"
    ),
    CommitMatchInfoFlag.Reviewed: CommitMatchInfo(
        CommitMatchInfoFlag.Reviewed, Text("✔", SolarizedColors.Green), "Commit already reviewed"
    ),
    CommitMatchInfoFlag.Added: CommitMatchInfo(
        CommitMatchInfoFlag.Added, Text("✚", SolarizedColors.Green), "Commit added in rebase"
    ),
}


class FilterType(Enum):
    NoFilter = auto()
    With = auto()
    Without = auto()


class CacheFlags(Flag):
    READ_FROM_CACHE = auto()
    WRITE_TO_CACHE = auto()
