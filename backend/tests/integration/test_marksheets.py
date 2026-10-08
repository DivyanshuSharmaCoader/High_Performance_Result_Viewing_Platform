"""Marksheets and public verification (P11.2–P11.5).

The layout itself (WeasyPrint) is tested in tests/unit/test_marksheet_pdf.py, which needs Pango. Here the
renderer is replaced by a stand-in so the whole flow runs anywhere:
publish → render jobs → stored files → downloads → verification.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text, update

from app.core.clock import utcnow
from app.modules.documents.models import MarksheetDocument
from app.modules.documents.render import RenderResult
from app.modules.documents.service import MarksheetService
from app.modules.publishing.models import Publication
from app.modules.verification.codes import grouped
from app.modules.verification.models import VerificationRecord
from app.modules.verification.service import VerificationService
from tests.helpers import Client, drain_jobs
from tests.integration.test_publishing import _approved, _as_student, _logins, _publish, _pubs
from tests.integration.test_results import Exam, _reauth

pytestmark = pytest.mark.integration

VERIFY_HOST = "verify.localhost"


@pytest.fixture
def fake_pdf(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Stands in for WeasyPrint: a small "PDF" naming the student and the code it was given."""
    calls: list[dict[str, Any]] = []

    def render(payload: dict[str, Any], **ctx: Any) -> RenderResult:
        calls.append({"enrollment": payload["student"]["enrollment_no"], **ctx})
        body = f"%PDF-1.7 marksheet {payload['student']['enrollment_no']} {ctx['code_display']}"
        return RenderResult(pdf=body.encode())

    monkeypatch.setattr("app.modules.documents.service.render_marksheet", render)
    return calls


async def _published(app, infra, *students: str) -> tuple[Exam, dict[str, Any]]:
    e = await _approved(app, infra)
    if students:
        await _logins(app, e, *students)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        r = await _publish(c, e)
        assert r.status_code == 201, r.text
    return e, r.json()


def _mine(calls: list[dict[str, Any]], codes: dict[str, str]) -> list[dict[str, Any]]:
    """Render calls for this test's tenant (the queue is shared with every other test)."""
    return [c for c in calls if c["verify_url"].rsplit("/", 1)[1] in codes.values()]


async def _codes(infra, e: Exam) -> dict[str, str]:
    async with infra.db.uow(e.x.t.id) as uow:
        rows = await uow.session.execute(
            text(
                "SELECT s.enrollment_no, v.code FROM verification_records v "
                "JOIN students s ON s.id = v.student_id ORDER BY v.created_at"
            )
        )
        return dict(rows.all())  # type: ignore[arg-type]


async def _usage(infra, tenant_id: uuid.UUID) -> int:
    async with infra.db.uow(tenant_id) as uow:
        return (
            await uow.session.execute(
                text("SELECT value FROM tenant_usage_counters WHERE metric = 'storage_bytes'")
            )
        ).scalar_one()


async def test_publishing_prepares_and_renders_a_marksheet_and_a_code_per_student(
    app, infra, fake_pdf
) -> None:
    e, pub = await _published(app, infra)
    codes = await _codes(infra, e)
    assert sorted(codes) == ["A001", "A002", "A003", "B001"]
    assert all(re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", c) for c in codes.values())
    assert len(set(codes.values())) == 4
    async with infra.db.uow(e.x.t.id) as uow:
        jobs = (
            await uow.session.execute(
                text("SELECT count(*) FROM jobs WHERE kind = 'documents.render' AND queue = 'pdf'")
            )
        ).scalar_one()
        assert jobs == 1  # four students: one chunk
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        listed = (await c.get(_pubs(e))).json()
        assert listed[0]["marksheets"] == {"total": 4, "rendered": 0, "pending": 4, "failed": 0}

    usage_before = await _usage(infra, e.x.t.id)
    await drain_jobs(infra, ["pdf"])
    assert sorted(call["enrollment"] for call in _mine(fake_pdf, codes)) == ["A001", "A002", "A003", "B001"]
    for call in _mine(fake_pdf, codes):
        code = codes[call["enrollment"]]
        assert call["verify_url"] == f"http://{VERIFY_HOST}:8080/v/{code}"
        assert call["code_display"] == grouped(code) and call["version"] == 1
    async with infra.db.uow(e.x.t.id) as uow:
        docs = (await uow.session.scalars(select(MarksheetDocument))).all()
        assert {d.status for d in docs} == {"rendered"}
        for d in docs:
            stored = await infra.storage.get(
                (
                    await uow.session.execute(
                        text("SELECT object_key FROM files WHERE id = :id AND kind = 'marksheet'"),
                        {"id": d.file_id},
                    )
                ).scalar_one()
            )
            assert d.sha256 == hashlib.sha256(stored).hexdigest()
    # Marksheets count towards storage, but never block rendering (docs/12 §4).
    assert await _usage(infra, e.x.t.id) > usage_before
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        assert (await c.get(_pubs(e))).json()[0]["marksheets"]["rendered"] == 4

    await drain_jobs(infra, ["pdf"])  # nothing left to do: rendering again changes nothing
    assert len(_mine(fake_pdf, codes)) == 4
    assert pub["status"] == "published"


async def test_students_download_only_their_own_marksheet_through_a_short_lived_link(
    app, infra, fake_pdf
) -> None:
    e, pub = await _published(app, infra, "A001", "A002")
    codes = await _codes(infra, e)
    url = f"/api/v1/me/results/{pub['id']}/marksheet"
    async with await _as_student(app, e, "A001") as a1:
        pending = await a1.get(url)
        assert pending.status_code == 200 and pending.headers["cache-control"] == "private, no-store"
        assert pending.json()["status"] == "pending" and pending.json()["url"] is None
        # The code is there from the start, so the student can share it as soon as results are out.
        assert pending.json()["verification"]["code"] == grouped(codes["A001"])
    await drain_jobs(infra, ["pdf"])
    async with await _as_student(app, e, "A001") as a1:
        body = (await a1.get(url)).json()
        assert body["status"] == "rendered" and body["expires_in"] == 120
        assert re.fullmatch(r"Marksheet-A001-Finals-Session-[A-Z0-9]+\.pdf", body["filename"])
        async with httpx.AsyncClient() as s3:
            pdf = await s3.get(body["url"])
        assert pdf.status_code == 200 and b"marksheet A001" in pdf.content
        assert f'filename="{body["filename"]}"' in pdf.headers["content-disposition"]
        assert body["verification"]["url"].endswith(f"/v/{codes['A001']}")
        assert (await a1.get(f"/api/v1/me/results/{uuid.uuid4()}/marksheet")).status_code == 404
    # The same publication id, from another student, is *their* marksheet.
    async with await _as_student(app, e, "A002") as a2:
        theirs = (await a2.get(url)).json()
        assert theirs["verification"]["code"] == grouped(codes["A002"])
        async with httpx.AsyncClient() as s3:
            assert b"marksheet A002" in (await s3.get(theirs["url"])).content
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        assert (await c.get(url)).status_code == 403  # staff use the admin route
        await _reauth(c)
        r = await c.post(f"{_pubs(e)}/{pub['id']}/withdraw", json={"reason": "Wrong exam picked"})
        assert r.status_code == 200
    async with await _as_student(app, e, "A001") as a1:
        assert (await a1.get(url)).status_code == 404  # withdrawn: no downloads


async def test_administrators_download_any_marksheet_of_their_publication(app, infra, fake_pdf) -> None:
    e, pub = await _published(app, infra)
    await drain_jobs(infra, ["pdf"])
    async with infra.db.uow(e.x.t.id) as uow:
        a001 = (
            await uow.session.execute(text("SELECT id FROM students WHERE enrollment_no = 'A001'"))
        ).scalar_one()
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        r = await c.get(f"{_pubs(e)}/{pub['id']}/marksheets/{a001}")
        assert r.status_code == 200 and r.json()["status"] == "rendered"
        async with httpx.AsyncClient() as s3:
            assert b"marksheet A001" in (await s3.get(r.json()["url"])).content
        assert (await c.get(f"{_pubs(e)}/{pub['id']}/marksheets/{uuid.uuid4()}")).status_code == 404
        other_exam = f"/api/v1/admin/exams/{uuid.uuid4()}/publications/{pub['id']}/marksheets/{a001}"
        assert (await c.get(other_exam)).status_code == 404


async def test_failed_renders_retry_then_stop_and_administrators_can_retry_them(
    app, infra, monkeypatch
) -> None:
    broken = {"A002"}

    def render(payload: dict[str, Any], **ctx: Any) -> RenderResult:
        if payload["student"]["enrollment_no"] in broken:
            raise RuntimeError("Pango crashed on A002 Pupil")  # the message must not be stored
        return RenderResult(pdf=b"%PDF-1.7 ok")

    monkeypatch.setattr("app.modules.documents.service.render_marksheet", render)
    e, pub = await _published(app, infra)
    pid = uuid.UUID(pub["id"])
    async with infra.db.uow(e.x.t.id) as uow:
        students = list((await uow.session.scalars(select(MarksheetDocument.student_id))).all())
    service = MarksheetService(infra)
    with pytest.raises(RuntimeError, match="1 of 4 marksheets failed"):
        await service.render(e.x.t.id, pid, students, final_attempt=False)
    assert await service.render(e.x.t.id, pid, students, final_attempt=True) == {"rendered": 0, "failed": 1}
    async with infra.db.uow(e.x.t.id) as uow:
        rows = (
            await uow.session.execute(
                text(
                    "SELECT s.enrollment_no, d.status, d.attempts, d.last_error FROM marksheet_documents d "
                    "JOIN students s ON s.id = d.student_id ORDER BY s.enrollment_no"
                )
            )
        ).all()
    assert [tuple(r) for r in rows] == [
        ("A001", "rendered", 1, None),
        ("A002", "failed", 2, "RuntimeError"),  # the type only: messages can quote student data
        ("A003", "rendered", 1, None),
        ("B001", "rendered", 1, None),
    ]
    broken.clear()
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        assert (await c.get(_pubs(e))).json()[0]["marksheets"]["failed"] == 1
        r = await c.post(f"{_pubs(e)}/{pub['id']}/marksheets/retry")
        assert r.status_code == 200 and r.json() == {"queued": 1}
        assert (await c.post(f"{_pubs(e)}/{pub['id']}/marksheets/retry")).json() == {"queued": 0}
    await drain_jobs(infra, ["pdf"])
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        assert (await c.get(_pubs(e))).json()[0]["marksheets"] == {
            "total": 4,
            "rendered": 4,
            "pending": 0,
            "failed": 0,
        }


async def _supersede(infra, e: Exam, v1: uuid.UUID) -> uuid.UUID:
    """A revised version going live over v1 (the state the correction flow leaves behind)."""
    async with infra.db.uow(e.x.t.id) as uow:
        old = (await uow.session.scalars(select(Publication).where(Publication.id == v1))).one()
        old.status = "superseded"
        await uow.flush()
        new = Publication(
            tenant_id=e.x.t.id,
            exam_id=old.exam_id,
            result_run_id=old.result_run_id,
            version=2,
            status="published",
            published_at=utcnow(),
            supersedes_id=v1,
            content_hash=old.content_hash,
        )
        uow.session.add(new)
        await uow.flush()
        return new.id


async def test_verification_follows_the_publication_and_revocation(app, infra, fake_pdf) -> None:
    e, pub = await _published(app, infra)
    await drain_jobs(infra, ["pdf"])
    codes = await _codes(infra, e)
    verify = VerificationService(infra)

    v = await verify.lookup(codes["A001"].lower())  # what people type works too
    assert v is not None and v.status == "valid" and v.version == 1
    assert v.code == grouped(codes["A001"]) and v.exam == "Finals"
    assert v.student_name.endswith("***") and "*" in v.enrollment_no and v.enrollment_no != "A001"
    async with infra.db.uow(e.x.t.id) as uow:
        doc_sha = (
            await uow.session.execute(
                text(
                    "SELECT d.sha256 FROM marksheet_documents d JOIN students s ON s.id = d.student_id "
                    "WHERE s.enrollment_no = 'A001'"
                )
            )
        ).scalar_one()
    assert v.document_sha256 == doc_sha
    await verify.lookup(grouped(codes["A001"]))
    async with infra.db.uow(e.x.t.id) as uow:
        rec = (
            await uow.session.scalars(
                select(VerificationRecord).where(VerificationRecord.code == codes["A001"])
            )
        ).one()
        assert rec.verify_count == 2 and rec.last_verified_at is not None

    assert await verify.lookup("0" * 26) is None
    assert await verify.lookup("not a code") is None

    # One student's marksheet revoked: only that one changes.
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        url = f"{_pubs(e)}/{pub['id']}/verification/{rec.student_id}/revoke"
        assert (await c.post(url, json={"reason": "Issued to the wrong person"})).status_code == 200
        assert (await c.post(url, json={"reason": "again"})).status_code == 409
        audit = (await c.get("/api/v1/admin/audit-logs", params={"action": "verification.revoked"})).json()
        assert audit["items"][0]["reason"] == "Issued to the wrong person"
    assert (await verify.lookup(codes["A001"])).status == "revoked"  # type: ignore[union-attr]
    assert (await verify.lookup(codes["A002"])).status == "valid"  # type: ignore[union-attr]

    # A revised version: the old statement says so, with the date of the revision.
    v2 = await _supersede(infra, e, uuid.UUID(pub["id"]))
    superseded = await verify.lookup(codes["A002"])
    assert superseded is not None and superseded.status == "superseded" and superseded.status_at is not None
    async with infra.db.uow(e.x.t.id) as uow:
        await uow.session.execute(
            update(Publication)
            .where(Publication.id == v2)
            .values(status="withdrawn", withdrawn_at=utcnow(), withdraw_reason="x")
        )
    # Withdrawn results.
    e2, pub2 = await _published(app, infra)
    codes2 = await _codes(infra, e2)
    async with Client(app, e2.x.t.host) as c:
        await c.login(e2.x.t.owner_email)
        await _reauth(c)
        await c.post(f"{_pubs(e2)}/{pub2['id']}/withdraw", json={"reason": "Wrong exam picked"})
    withdrawn = await verify.lookup(codes2["A001"])
    assert withdrawn is not None and withdrawn.status == "withdrawn" and withdrawn.status_at is not None
    # An institution that has left shows nothing about the student.
    async with infra.db.platform_uow() as uow:
        await uow.session.execute(
            text("UPDATE tenants SET status = 'closed' WHERE id = :t"), {"t": e2.x.t.id}
        )
    gone = await verify.lookup(codes2["A001"])
    assert gone is not None and gone.status == "institution_left" and gone.student_name == ""


async def test_a_scheduled_publication_cannot_be_verified_until_it_goes_live(app, infra, fake_pdf) -> None:
    from app.modules.publishing.service import PublishingService

    e = await _approved(app, infra)
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        r = await _publish(c, e, at=(utcnow() + timedelta(hours=2)).isoformat())
        assert r.status_code == 201, r.text
    pub = r.json()
    await drain_jobs(infra, ["pdf"])  # rendered ahead of go-live
    codes = await _codes(infra, e)
    assert len(_mine(fake_pdf, codes)) == 4
    code = codes["A001"]
    verify = VerificationService(infra)
    assert await verify.lookup(code) is None  # looks exactly like an unknown code
    await PublishingService(infra).go_live(e.x.t.id, uuid.UUID(pub["id"]))
    live = await verify.lookup(code)
    assert live is not None and live.status == "valid"


async def test_the_public_verify_page(app, infra, fake_pdf) -> None:
    e = await _approved(app, infra)
    # Tenant-controlled text on a public page: the institution's name goes into the snapshot at publication.
    async with infra.db.uow(e.x.t.id) as uow:
        await uow.session.execute(
            text("UPDATE tenant_branding SET display_name = '<script>alert(1)</script> Academy'")
        )
    async with Client(app, e.x.t.host) as c:
        await c.login(e.x.t.owner_email)
        assert (await _publish(c, e)).status_code == 201
    await drain_jobs(infra, ["pdf"])
    code = (await _codes(infra, e))["A001"]
    async with infra.db.uow(e.x.t.id) as uow:
        full_name = (
            await uow.session.execute(text("SELECT full_name FROM students WHERE enrollment_no = 'A001'"))
        ).scalar_one()
    async with Client(app, VERIFY_HOST, ip="198.51.100.40") as v:
        r = await v.get(f"/v/{code}")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
        assert r.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert "default-src 'none'" in r.headers["content-security-policy"]
        assert "script-src" not in r.headers["content-security-policy"]  # no scripts at all
        page = r.text
        assert ">Valid<" in page and grouped(code) in page and "Finals" in page
        assert full_name not in page and "A001" not in page  # masked
        assert "<script" not in page and "&lt;script&gt;alert(1)&lt;/script&gt; Academy" in page

        lower = grouped(code).lower()
        assert (await v.get(f"/v/{lower}")).status_code == 200
        r = await v.get("/v", params={"code": lower}, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == f"/v/{code}"
        bad = await v.get("/v", params={"code": "hello"})
        assert bad.status_code == 422 and "isn&#39;t a verification code" in bad.text
        assert (await v.get("/v")).status_code == 200
        r = await v.get("/", follow_redirects=False)
        assert r.status_code == 308 and r.headers["location"] == "/v"

        unknown = await v.get(f"/v/{'7' * 26}")
        assert unknown.status_code == 404 and "No statement found" in unknown.text
        assert unknown.headers["cache-control"] == "public, max-age=60"

    # The page exists only on the verify host.
    async with Client(app, e.x.t.host) as c:
        assert (await c.get(f"/v/{code}")).status_code == 404


async def test_verify_lookups_are_rate_limited_per_address(app, infra, fake_pdf) -> None:
    e, _ = await _published(app, infra)
    code = (await _codes(infra, e))["A001"]
    async with Client(app, VERIFY_HOST, ip="198.51.100.77") as v:
        statuses = [(await v.get(f"/v/{code}")).status_code for _ in range(35)]
        assert 429 in statuses
        limited = await v.get(f"/v/{code}")
        assert limited.status_code == 429 and int(limited.headers["retry-after"]) >= 1
        assert "Too many lookups" in limited.text
    async with Client(app, VERIFY_HOST, ip="198.51.100.78") as other:
        assert (await other.get(f"/v/{code}")).status_code == 200


async def test_the_code_lookup_reveals_nothing_but_the_tenant(app, infra, fake_pdf) -> None:
    e, _ = await _published(app, infra)
    code = (await _codes(infra, e))["A001"]
    async with infra.db.uow() as uow:  # the runtime role with no tenant context, like the verify host
        row = (await uow.session.execute(text("SELECT * FROM verification_lookup(:c)"), {"c": code})).one()
        assert set(row._mapping.keys()) == {"tenant_id", "tenant_status"}
        assert row.tenant_id == e.x.t.id
    with pytest.raises(Exception, match=r"app\.tenant_id|invalid input syntax for type uuid"):
        async with infra.db.uow() as uow:
            await uow.session.execute(text("SELECT count(*) FROM verification_records"))
