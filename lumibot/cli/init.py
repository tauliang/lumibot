"""Implementation of ``lumibot init``."""

from __future__ import annotations

from pathlib import Path

from lumibot.studio.templates import get_template

from .config import config_for_init, normalize_data_source_type, write_lumibot_config


def init_command(args) -> int:
    root = Path(args.path).expanduser().resolve()
    data_type = normalize_data_source_type(args.data_source or ("pandas_csv" if args.csv_path else "yahoo"))
    template_id = args.template or ("csv_single_symbol" if data_type == "pandas_csv" else "buy_and_hold")
    try:
        template = get_template(template_id)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 2

    csv_path = args.csv_path or "data/sample.csv"
    if root.exists() and any(root.iterdir()) and not args.force:
        print(f"Error: {root} is not empty. Use --force to write scaffold files anyway.")
        return 2

    try:
        root.mkdir(parents=True, exist_ok=True)
        for directory in ["strategies", "data", "runs"]:
            (root / directory).mkdir(parents=True, exist_ok=True)

        _write_file(root / "strategies" / "strategy.py", template.code, force=args.force)
        _write_file(root / ".env.example", _env_example(), force=args.force)
        if data_type == "pandas_csv" and not Path(csv_path).is_absolute():
            _write_file(root / csv_path, _sample_csv(args.symbol), force=args.force)
        elif data_type == "pandas_csv" and not Path(csv_path).exists():
            Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
            _write_file(Path(csv_path), _sample_csv(args.symbol), force=args.force)

        config = config_for_init(
            project_name=root.name or "lumibot-project",
            template_id=template_id,
            symbol=args.symbol.upper(),
            benchmark=args.benchmark.upper(),
            data_source_type=data_type,
            csv_path=csv_path,
            budget=args.budget,
            start=args.start,
            end=args.end,
        )
        write_lumibot_config(root / "lumibot.toml", config)
        _write_file(root / "README.md", _project_readme(root.name, data_type), force=args.force)
    except OSError as exc:
        print(f"Error: {exc}")
        return 2

    print(f"Created Lumibot project at {root}")
    print("Next: cd into the project, then run `lumibot doctor` and `lumibot run`.")
    return 0


def _write_file(path: Path, text: str, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise OSError(f"{path} already exists. Use --force to overwrite it.")
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _env_example() -> str:
    return """# The default local backtest workflow does not require API keys.
# Add broker or paid data credentials here later if you choose to use them.
"""


def _sample_csv(symbol: str) -> str:
    return """datetime,open,high,low,close,volume
2024-01-02,100,101,99,100,1000
2024-01-03,100,103,99,102,1000
2024-01-04,102,104,101,103,1000
2024-01-05,103,105,102,104,1000
2024-01-08,104,106,103,105,1000
2024-01-09,105,107,104,106,1000
2024-01-10,106,108,105,107,1000
"""


def _project_readme(project_name: str, data_type: str) -> str:
    data_note = (
        "This starter uses a local OHLCV CSV in `data/sample.csv`, so it can run without network access."
        if data_type == "pandas_csv"
        else "This starter uses Yahoo daily stock/ETF data. No broker or paid data credentials are required."
    )
    return f"""# {project_name or "Lumibot Project"}

{data_note}

## Quickstart

```bash
lumibot doctor
lumibot run
```

Backtest outputs are written to `runs/<run_id>/`.

## Files

- `lumibot.toml` stores the strategy, data source, backtest window, budget, and output settings.
- `strategies/strategy.py` contains the starter strategy.
- `data/` stores local CSV data when using the CSV data source.
- `runs/` stores persisted specs, logs, status files, and artifacts.
"""
