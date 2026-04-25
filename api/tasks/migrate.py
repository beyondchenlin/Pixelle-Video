"""Task database migration CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


def build_alembic_config() -> Config:
    config_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(config_path))
    postgres_dsn = os.getenv("PIXELLE_POSTGRES_DSN")
    if postgres_dsn:
        config.set_main_option("sqlalchemy.url", postgres_dsn)
    return config


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    action = args[0] if args else "upgrade"
    revision = args[1] if len(args) > 1 else "head"
    config = build_alembic_config()

    if action == "upgrade":
        command.upgrade(config, revision)
        return
    if action == "downgrade":
        command.downgrade(config, revision)
        return
    if action == "current":
        command.current(config)
        return

    raise SystemExit(f"Unsupported migration action: {action}")


if __name__ == "__main__":
    main()
