"""Diff parsing utilities."""

import re


class DiffPosition:
    def __init__(self, new_file, new_line_number, old_file, old_line_number):
        self.new_file = new_file
        self.new_line_number = new_line_number
        self.old_file = old_file
        self.old_line_number = old_line_number

    def __repr__(self) -> str:
        return (
            f"new={self.new_file}+{self.new_line_number} "
            f"old={self.old_file}+{self.old_line_number}"
        )


class DiffParser:
    hunk_pattern = re.compile(r"@@ -(?P<old_start>\d+),\d+ \+(?P<new_start>\d+),\d+ @@.*")

    def __init__(self):
        self.last_line: None | str = None
        self.old_file: None | str = None
        self.old_start: None | int = None
        self.old_index: int = 0
        self.new_file: None | str = None
        self.new_start: None | int = None
        self.new_index: int = 0

    @staticmethod
    def is_diff_header(line: str) -> bool:
        return (
            line.startswith("diff")
            or line.startswith("index")
            or line.startswith("---")
            or line.startswith("+++")
            or line.startswith("@@")
            or line.startswith("new file mode")
        )

    @staticmethod
    def is_hunk_header(line: str) -> bool:
        return line.startswith("@@")

    @staticmethod
    def is_old_file_header(line: str) -> bool:
        return line.startswith("---")

    @staticmethod
    def is_new_file_header(line: str) -> bool:
        return line.startswith("+++")

    def within_hunk(self) -> bool:
        return (
            self.old_start is not None
            and self.last_line is not None
            and not self.is_diff_header(self.last_line)
        )

    def record_header_information(self, line: str) -> None:
        if self.is_old_file_header(line):
            self.old_file = line[6:].strip()
        elif self.is_new_file_header(line):
            self.new_file = line[6:].strip()
        elif self.is_hunk_header(line):
            m = self.hunk_pattern.match(line)
            if m is None:
                raise RuntimeError(f'"{line}" does not match hunk header regexp')
            self.old_start = int(m.group("old_start")) - 1
            self.old_index = 0
            self.new_start = int(m.group("new_start")) - 1
            self.new_index = 0

    def parse_line(self, line: str) -> None:
        self.last_line = line

        if self.is_diff_header(line):
            self.old_start = None
            self.new_start = None
            self.record_header_information(line)
            return

        if not line:
            return

        match line[0]:
            case "+":
                self.new_index += 1
            case "-":
                self.old_index += 1
            case _:
                self.old_index += 1
                self.new_index += 1

    def get_current_position(self) -> DiffPosition:
        if self.new_start is None or self.old_start is None:
            raise RuntimeError("Cannot get current position at this stage")
        return DiffPosition(
            self.new_file,
            self.new_start + self.new_index,
            self.old_file,
            self.old_start + self.old_index,
        )
