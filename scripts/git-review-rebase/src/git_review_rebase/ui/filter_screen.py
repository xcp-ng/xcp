"""Filter screen for commit match types."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Label, RadioButton, RadioSet

from ..constants import CommitMatchInfoFlag, FilterType, commit_match_info_repr


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

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, filters: dict[CommitMatchInfoFlag, FilterType], **kwargs):
        super().__init__(**kwargs)
        self.filters = filters

    def compose(self) -> ComposeResult:
        with Vertical(id="filter_dialog"):
            for flag in CommitMatchInfoFlag:
                with RadioSet(id=flag.name):
                    yield Label(
                        commit_match_info_repr[flag].character
                        + " "
                        + commit_match_info_repr[flag].definition
                    )
                    yield RadioButton(
                        FilterType.With.name, value=self.filters[flag] == FilterType.With
                    )
                    yield RadioButton(
                        FilterType.Without.name, value=self.filters[flag] == FilterType.Without
                    )
                    yield RadioButton(
                        FilterType.NoFilter.name, value=self.filters[flag] == FilterType.NoFilter
                    )
            yield Button("Apply filters", variant="primary")
            yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.label == "Apply filters":
            radio_sets = self.query(RadioSet)
            filters: dict[CommitMatchInfoFlag, FilterType] = {}
            for radio_set in radio_sets:
                assert isinstance(radio_set.id, str)
                assert isinstance(radio_set.pressed_button, RadioButton)
                assert isinstance(radio_set.pressed_button.label, str)
                filters[CommitMatchInfoFlag[radio_set.id]] = FilterType[
                    radio_set.pressed_button.label
                ]
            self.dismiss(filters)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
