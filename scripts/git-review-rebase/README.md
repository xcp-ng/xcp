# git-review-rebase

An interactive TUI (Terminal User Interface) tool for reviewing rebased git branches side-by-side.

## Features

- Side-by-side diff viewing for rebased commits
- Interactive commit matching between branches
- Syntax highlighting with token-level diff highlighting
- Git blame integration for tracking commit origins
- Fuzzy search across commits
- Flexible filtering by commit match types
- Possibility to add notes to dropped commits

## Installation

### From source

```bash
git clone https://github.com/yourusername/git-review-rebase
cd git-review-rebase
pip install -e .
```

## Usage

```bash
git-review-rebase <base>..<left-branch> <onto_base>..<right-branch>
```

### Options

- `--repository PATH`: Path to git repository (default: current directory)
- `--no-cache`: Disable patchid caching

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/xcp-ng/xcp
cd xcp/scripts/git-review-rebase

# Install in development mode with dev dependencies
pip install -e ".[dev]"
```

### Code formatting and linting

```bash
black src/
ruff check src/
flake8 src/
```

### Type checking

```bash
mypy src/
pyright ./
```

## License

GPL-v2

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
