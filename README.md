# lol-damage-calcs

Understand items in league and damage calcs.

## Prerequisites

- **Python 3.11+** – the calculator and supporting tooling are written in modern Python.
- **Poetry** or **pip** for dependency management. Examples below use `pip` with a virtual environment.
- (Optional) **Node.js 18+** if you plan to work on the React-based UI dashboard.
- A Riot Games API key if you wish to fetch non-public static data (the default Data Dragon endpoints do not require one).

To get started, create and activate a virtual environment and install the project:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Data acquisition

Static champion and item definitions are cached in `data/static/` as JSON files. Refresh them periodically to match the current League patch:

1. Ensure your virtual environment is active.
2. Run the refresh script, specifying the patch (defaults to `latest`).

```bash
python scripts/refresh_static_data.py --patch 14.5.1
```

The script downloads champion, item, and rune data from Riot's [Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon) service and updates:

- `data/static/champions.json`
- `data/static/items.json`
- `data/static/runes.json`

If you have a Riot API key stored in `.env`, the script will also pull balance adjustments that have not yet shipped to Data Dragon.

## Project structure

```
.
├── data/
│   └── static/           # Cached champion, item, and rune JSON payloads
├── docs/                 # Additional documentation and design notes
├── lol_damage_calcs/     # Core damage calculation engine and shared utilities
├── scripts/              # Helper scripts (data refresh, benchmarking, etc.)
├── ui/                   # Optional React front-end for browsing builds
├── tests/                # Pytest suite covering the calculation engine
└── README.md
```

## Usage

The project provides both a command-line interface and a lightweight web UI.

### Command line

List the top burst and damage-over-time (DoT) builds for a given champion:

```bash
python -m lol_damage_calcs.cli top-builds --champion "LeBlanc" --mode burst
python -m lol_damage_calcs.cli top-builds --champion "Cassiopeia" --mode dot
```

Use `--vs-tank` or `--vs-squishy` to switch target profiles, and `--limit` to control how many builds are returned. Run `python -m lol_damage_calcs.cli --help` for the full CLI reference.

### Web UI

Start the development server to explore builds in a browser dashboard:

```bash
cd ui
npm install
npm run dev
```

The dashboard includes search, filtering by damage profile, and detail breakdowns for every recommended item set.

## Running tests

Run the automated checks before submitting changes:

```bash
pytest
```

To run a quick subset while iterating on a calculation module:

```bash
pytest tests/test_burst_calcs.py -k "test_leblanc"
```

Add `--cov=lol_damage_calcs` to track coverage locally.

## Contributing

1. Fork the repository and create a feature branch.
2. Keep changes focused and covered by tests (`pytest`).
3. Format Python code with `ruff format` and lint with `ruff check` before committing.
4. Update documentation (including this README) when behavior or data expectations change.
5. Submit a pull request with a clear summary of the changes and testing evidence.

By contributing you agree to follow the [Code of Conduct](docs/CODE_OF_CONDUCT.md) and the Riot Games [Developer Terms](https://developer.riotgames.com/).
