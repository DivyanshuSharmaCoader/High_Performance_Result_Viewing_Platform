"""``scorecode`` command line: run the API/worker, migrate, seed, and operator tasks."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _alembic_upgrade() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")


async def _post_migrate() -> None:
    from app.core.container import Infra
    from app.modules.entitlements.sync import sync_catalogue

    settings = get_settings()
    infra = Infra.build(settings, app_name="scorecode-migrate")
    try:
        result = await sync_catalogue(infra.db)
        print(f"catalogue synced: {result}")
        ensure = getattr(infra.storage, "ensure_bucket", None)
        if ensure is not None:
            try:
                await ensure()
                print(f"object storage bucket ready: {settings.s3_bucket}")
            except Exception as exc:  # storage may be provisioned separately in production
                print(f"warning: could not verify bucket {settings.s3_bucket}: {type(exc).__name__}")
    finally:
        await infra.close()


def cmd_migrate(_: argparse.Namespace) -> None:
    sys.path.insert(0, str(BACKEND_DIR))
    _alembic_upgrade()
    asyncio.run(_post_migrate())


def cmd_api(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        workers=args.workers,
        reload=args.reload,
        proxy_headers=False,  # client IP handling is done by our middleware (trust_proxy_headers)
        server_header=False,
        date_header=False,
        log_level="warning",
    )


def cmd_worker(_: argparse.Namespace) -> None:
    from app.worker import main as worker_main

    asyncio.run(worker_main())


def cmd_seed(args: argparse.Namespace) -> None:
    from app.seed import run_seed

    asyncio.run(run_seed(students_per_tenant=args.students))


def cmd_create_platform_user(args: argparse.Namespace) -> None:
    from app.modules.platform.bootstrap import create_platform_user_cli

    password = args.password or os.environ.get("SCORECODE_PLATFORM_PASSWORD_INIT")
    if not password:
        import getpass

        password = getpass.getpass("Password (min 12 chars): ")
    asyncio.run(create_platform_user_cli(args.email, args.name, password, args.role))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="scorecode")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="apply migrations and sync the plan catalogue").set_defaults(
        fn=cmd_migrate
    )

    api = sub.add_parser("api", help="run the HTTP API")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--workers", type=int, default=1)
    api.add_argument("--reload", action="store_true")
    api.set_defaults(fn=cmd_api)

    sub.add_parser("worker", help="run the background job worker").set_defaults(fn=cmd_worker)

    seed = sub.add_parser(
        "seed", help="create demo tenants (Thapar, Demo School, Demo Coaching) with synthetic data"
    )
    seed.add_argument("--students", type=int, default=120)
    seed.set_defaults(fn=cmd_seed)

    cpu = sub.add_parser(
        "create-platform-user", help="create a ScoreCode staff account (prints TOTP enrolment)"
    )
    cpu.add_argument("--email", required=True)
    cpu.add_argument("--name", required=True)
    cpu.add_argument("--role", default="platform_admin", choices=["platform_admin", "support", "readonly"])
    cpu.add_argument("--password")
    cpu.set_defaults(fn=cmd_create_platform_user)

    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
