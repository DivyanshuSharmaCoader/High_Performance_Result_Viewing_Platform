"""Data export (P18.5): the owner gets every record of the institution, and nothing of anyone else's."""

from __future__ import annotations

import csv
import io
import uuid
import zipfile

import pytest
from sqlalchemy import select, text

from app.modules.exports.models import DataExport
from app.modules.exports.service import FILES, purge_expired_exports
from app.modules.files.service import FileService
from tests.helpers import Client, client_as, drain_jobs
from tests.integration.test_publishing import _approved, _publish
from tests.integration.test_results import _reauth

pytestmark = pytest.mark.integration

URL = "/api/v1/admin/exports"


async def _zip(infra, tenant_id: uuid.UUID, export_id: str) -> zipfile.ZipFile:
    async with infra.db.uow(tenant_id) as uow:
        export = (
            await uow.session.scalars(select(DataExport).where(DataExport.id == uuid.UUID(export_id)))
        ).one()
        assert export.file_id is not None
        data = await FileService(infra).read_bytes(uow, export.file_id)
    return zipfile.ZipFile(io.BytesIO(data))


def _rows(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(zf.read(name).decode("utf-8-sig"))))


async def test_the_owner_exports_everything_and_only_their_institution(app, infra) -> None:
    e = await _approved(app, infra)
    other = await _approved(app, infra)  # another institution with the same kind of data
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        await _publish(c, e)
        r = await c.post(URL)
        assert r.status_code == 202, r.text
        export = r.json()
        assert export["status"] == "queued"
        assert (await c.post(URL)).status_code == 409  # one at a time
        assert (await c.post(f"{URL}/{export['id']}/link")).status_code == 409  # not ready yet

    assert await drain_jobs(infra, ["maintenance"]) >= 1
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        (listed,) = (await c.get(URL)).json()
        assert listed["status"] == "ready" and listed["expires_at"] and listed["size_bytes"] > 0
        assert listed["counts"]["students.csv"] >= 4
        link = await c.post(f"{URL}/{export['id']}/link")
        assert link.status_code == 200, link.text
        assert (
            link.json()["filename"].startswith("scorecode-export-")
            and link.headers["cache-control"] == "private, no-store"
        )
        audit = (await c.get("/api/v1/admin/audit-logs", params={"entity_id": export["id"]})).json()["items"]
        assert {a["action"] for a in audit} >= {
            "data.export_requested",
            "data.export_ready",
            "data.export_downloaded",
        }

    zf = await _zip(infra, e.x.t.id, export["id"])
    assert set(zf.namelist()) == {*FILES, "README.txt"}
    assert zf.read("students.csv").startswith(b"\xef\xbb\xbf")  # Excel reads UTF-8 with a BOM
    students = {r["enrollment_no"] for r in _rows(zf, "students.csv")}
    assert {"A001", "A002", "A003"} <= students
    (inst,) = _rows(zf, "institution.csv")
    assert inst["official_name"] == e.x.t.name
    results = _rows(zf, "results.csv")
    assert {(r["enrollment_no"], r["percentage"]) for r in results} >= {("A001", "85"), ("A002", "50")}
    assert _rows(zf, "marks.csv") and _rows(zf, "verification_codes.csv") and _rows(zf, "audit_log.csv")

    everything = b"".join(zf.read(n) for n in zf.namelist())
    assert other.x.t.name.encode() not in everything and other.x.t.slug.encode() not in everything
    for secret in (b"$argon2", b"password_hash", b"totp_secret", b"token_hash"):
        assert secret not in everything, secret
    staff = _rows(zf, "staff.csv")
    assert e.x.t.owner_email in {s["email"] for s in staff}
    assert set(staff[0]) == {
        "full_name",
        "email",
        "login_id",
        "roles",
        "status",
        "last_login_at",
        "employee_code",
        "designation",
        "phone",
        "created_at",
    }


async def test_only_the_owner_exports_and_only_after_reauthentication(app, infra) -> None:
    e = await _approved(app, infra)
    async with await client_as(app, infra, e.x.t, "institution_admin") as admin:
        assert (await admin.post(URL)).status_code == 403
        assert (await admin.get(URL)).status_code == 403
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        async with infra.db.uow(e.x.t.id) as uow:
            await uow.session.execute(
                text("UPDATE sessions SET reauthenticated_at = now() - interval '1 hour'")
            )
        r = await c.post(URL)
        assert r.status_code == 401 and r.json()["code"] == "reauth-required"
        await _reauth(c)
        assert (await c.post(URL)).status_code == 202


async def test_exports_expire_after_seven_days(app, infra) -> None:
    e = await _approved(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        export = (await c.post(URL)).json()
    await drain_jobs(infra, ["maintenance"])
    async with infra.db.uow(e.x.t.id) as uow:
        await uow.session.execute(text("UPDATE data_exports SET expires_at = now() - interval '1 minute'"))
    assert (await purge_expired_exports(infra))["exports"] >= 1
    async with infra.db.uow(e.x.t.id) as uow:
        purged = (
            await uow.session.execute(
                text("SELECT f.purged_at FROM data_exports x JOIN files f ON f.id = x.file_id")
            )
        ).scalar_one()
        assert purged is not None
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        assert (await c.get(URL)).json()[0]["status"] == "expired"
        r = await c.post(f"{URL}/{export['id']}/link")
        assert r.status_code == 409 and "expired" in r.json()["detail"]
