# skx

## Usage

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/) first.

```bash
# run with uv tool install
uv tool install git+https://github.com/Joilence/skx
skx --help

# run without install
uvx --from git+https://github.com/Joilence/skx skx --help
```

## Development

Use [`uv`](https://docs.astral.sh/uv/getting-started/installation/) for virtual environment and dependencies:

```bash
git clone git+https://github.com/Joilence/skx
cd skx
uv sync
pre-commit install
```
