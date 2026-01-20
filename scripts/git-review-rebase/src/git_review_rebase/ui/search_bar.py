"""Search bar widget."""

from textual.widgets import Input


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
