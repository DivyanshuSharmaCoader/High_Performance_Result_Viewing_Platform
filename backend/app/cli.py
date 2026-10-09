"""``scorecode`` command line: run the API/worker, migrate, seed, and operator tasks."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from app.core.config import get_settings
from app.models_registry import metadata as _all_models  # noqa: F401  (every table, so FKs resolve)

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
    import tempfile

    import uvicorn

    from app.core.metrics import MULTIPROC_ENV, prepare_multiprocess

    if args.workers > 1:  # one /metrics for all workers (core/metrics.py)
        default = str(Path(tempfile.gettempdir()) / "scorecode-metrics")
        prepare_multiprocess(os.environ.get(MULTIPROC_ENV) or default)
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


async def _jobs(args: argparse.Namespace) -> None:
    """Uses the platform role: these functions span tenants and are granted to it alone (0015)."""
    import uuid

    from sqlalchemy import text

    from app.core.container import Infra

    infra = Infra.build(get_settings(), app_name="scorecode-cli")
    try:
        async with infra.db.platform_uow() as uow:
            if args.jobs_command == "stats":
                rows = (await uow.session.execute(text("SELECT * FROM jobs_stats() ORDER BY 1, 2"))).all()
                print(f"{'queue':15} {'status':8} {'jobs':>7} {'oldest':>10}")
                for r in rows:
                    print(f"{r.queue:15} {r.status:8} {r.jobs:7d} {r.oldest_s:9.0f}s")
                if not rows:
                    print("no due, running or dead jobs")
            elif args.jobs_command == "dead":
                rows = (
                    await uow.session.execute(text("SELECT * FROM jobs_dead(:n)"), {"n": args.limit})
                ).all()
                for r in rows:
                    print(f"{r.id}  {r.queue}/{r.kind}  tenant={r.tenant_id}  attempts={r.attempts}")
                    when = f"{r.finished_at:%Y-%m-%d %H:%M} UTC" if r.finished_at else "-"
                    print(f"    {when}  {r.last_error or ''}")
                if not rows:
                    print("no dead jobs")
            else:
                for job_id in args.job_ids:
                    ok = (
                        await uow.session.execute(text("SELECT jobs_retry(:id)"), {"id": uuid.UUID(job_id)})
                    ).scalar_one()
                    print(
                        f"{job_id}: {'queued again' if ok else 'not dead, or an equivalent job is already queued'}"
                    )
    finally:
        await infra.close()


def cmd_jobs(args: argparse.Namespace) -> None:
    asyncio.run(_jobs(args))


async def _reencrypt(dry_run: bool) -> int:
    from app.core.container import Infra
    from app.modules.identity.key_rotation import reencrypt_secrets

    old = os.environ.get("SCORECODE_OLD_SECRET_KEY", "")
    if len(old) < 32:
        print("set SCORECODE_OLD_SECRET_KEY to the previous secret key (SCORECODE_SECRET_KEY is the new one)")
        return 2
    infra = Infra.build(get_settings(), app_name="scorecode-cli")
    try:
        report = await reencrypt_secrets(infra, old, dry_run=dry_run)
    finally:
        await infra.close()
    verb = "would re-encrypt" if dry_run else "re-encrypted"
    print(f"{verb} {report.reencrypted}; already on the new key {report.already_new}")
    for item in report.unreadable:
        print(f"unreadable with either key (left as is): {item}")
    return 1 if report.unreadable else 0


def cmd_reencrypt_secrets(args: argparse.Namespace) -> None:
    sys.exit(asyncio.run(_reencrypt(args.dry_run)))


def cmd_worker(_: argparse.Namespace) -> None:
    from app.worker import main as worker_main

    asyncio.run(worker_main())


def cmd_seed(args: argparse.Namespace) -> None:
    from app.seed import run_seed

    asyncio.run(run_seed(students_per_tenant=args.students, with_history=args.with_history))


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
    seed.add_argument(
        "--with-history", action="store_true", help="also exams and publications for the demo (docs/demo/)"
    )
    seed.set_defaults(fn=cmd_seed)

    cpu = sub.add_parser(
        "create-platform-user", help="create a ScoreCode staff account (prints TOTP enrolment)"
    )
    cpu.add_argument("--email", required=True)
    cpu.add_argument("--name", required=True)
    cpu.add_argument("--role", default="platform_admin", choices=["platform_admin", "support", "readonly"])
    cpu.add_argument("--password")
    cpu.set_defaults(fn=cmd_create_platform_user)

    jobs = sub.add_parser(
        "jobs", help="operator view of background jobs (docs/runbooks/stuck-publication.md)"
    )
    jobs_sub = jobs.add_subparsers(dest="jobs_command", required=True)
    jobs_sub.add_parser("stats", help="due, running and dead jobs per queue, with the oldest's age")
    dead = jobs_sub.add_parser("dead", help="jobs that failed every attempt, newest first")
    dead.add_argument("--limit", type=int, default=50)
    retry = jobs_sub.add_parser("retry", help="run dead jobs again from attempt 0")
    retry.add_argument("job_ids", nargs="+")
    jobs.set_defaults(fn=cmd_jobs)

    rotate = sub.add_parser(
        "reencrypt-secrets",
        help="after changing SCORECODE_SECRET_KEY: re-encrypt two-step secrets from SCORECODE_OLD_SECRET_KEY",
    )
    rotate.add_argument("--dry-run", action="store_true")
    rotate.set_defaults(fn=cmd_reencrypt_secrets)

    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
