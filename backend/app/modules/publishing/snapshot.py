"""The student-facing result snapshot (P10.2): exactly what a student sees, frozen at publication.

Pure functions, no database. The payload carries its own ``schema`` number so a reader can handle every
version it meets; numbers are canonical decimal strings (``72.5``, never ``72.500``), so the payload hash is
stable however the values were stored. Internal fields (hashes of inputs, run ids, user ids) never appear.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.modules.publishing.models import PAYLOAD_SCHEMA
from app.modules.results.compute import num


@dataclass(frozen=True, slots=True)
class Institution:
    name: str  # the official name, as on documents
    display_name: str  # as on the portal


@dataclass(frozen=True, slots=True)
class ExamInfo:
    name: str
    kind: str
    term: str
    session: str


@dataclass(frozen=True, slots=True)
class PaperInfo:
    paper_id: str
    course_code: str
    course_name: str
    credits: Decimal | None
    components: Sequence[Mapping[str, Any]]  # {code, label, max}


@dataclass(frozen=True, slots=True)
class StudentInfo:
    enrollment_no: str
    full_name: str
    cohort_code: str
    cohort_name: str
    program: str | None


@dataclass(frozen=True, slots=True)
class SchemeInfo:
    name: str
    strategy: str


def _n(v: Any) -> str | None:
    if v is None:
        return None
    return num(v if isinstance(v, Decimal) else Decimal(str(v)))


def build_payload(
    *,
    institution: Institution,
    exam: ExamInfo,
    scheme: SchemeInfo,
    student: StudentInfo,
    result: Mapping[str, Any],
    papers: Sequence[Mapping[str, Any]],
    paper_info: Mapping[str, PaperInfo],
) -> dict[str, Any]:
    """``result`` and ``papers`` are a stored exam result and its paper results (columns as a mapping);
    papers come out in ``paper_info`` order (the exam's paper order)."""
    by_paper = {str(p["exam_paper_id"]): p for p in papers}
    out_papers = []
    for pid, info in paper_info.items():
        p = by_paper.get(pid)
        if p is None:
            continue
        marks = p.get("components") or {}
        out_papers.append(
            {
                "course_code": info.course_code,
                "course_name": info.course_name,
                "credits": _n(info.credits),
                "attendance": p.get("attendance"),
                "outcome": p["outcome"],
                "total": _n(p.get("total")),
                "max_total": _n(p.get("max_total")),
                "percentage": _n(p.get("percentage")),
                "grade": p.get("grade"),
                "grade_point": _n(p.get("grade_point")),
                "failed_components": list(p.get("failed_components") or []),
                "missing_components": list(p.get("missing_components") or []),
                "components": [
                    {
                        "code": c["code"],
                        "label": c.get("label") or c["code"],
                        "max": _n(c["max"]),
                        "marks": _n(marks.get(c["code"])),
                    }
                    for c in info.components
                ],
            }
        )
    return {
        "schema": PAYLOAD_SCHEMA,
        "institution": {"name": institution.name, "display_name": institution.display_name},
        "exam": {"name": exam.name, "kind": exam.kind, "term": exam.term, "session": exam.session},
        "scheme": {"name": scheme.name, "strategy": scheme.strategy},
        "student": {
            "enrollment_no": student.enrollment_no,
            "full_name": student.full_name,
            "cohort": {"code": student.cohort_code, "name": student.cohort_name},
            "program": student.program,
        },
        "result": {
            "outcome": result["outcome"],
            "total": _n(result.get("total")),
            "max_total": _n(result.get("max_total")),
            "percentage": _n(result.get("percentage")),
            "grade": result.get("grade"),
            "grade_point": _n(result.get("grade_point")),
            "sgpa": _n(result.get("sgpa")),
            "credits_attempted": _n(result.get("credits_attempted")),
            "credits_earned": _n(result.get("credits_earned")),
            "rank": result.get("rank"),
            "notes": list(result.get("notes") or []),
        },
        "papers": out_papers,
    }


def payload_hash(payload: Mapping[str, Any]) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode()).hexdigest()


# What students may see of the exam as a whole (tenant setting ``student_stats``).
def student_stats(stats: Mapping[str, Any], level: str) -> dict[str, Any] | None:
    if level == "none":
        return None
    papers = [
        {"course_code": p["course_code"], "average": p.get("average"), "max_total": p.get("max_total")}
        for p in stats.get("papers", [])
    ]
    out: dict[str, Any] = {"average_percentage": stats.get("average_percentage"), "papers": papers}
    if level == "full":
        out |= {
            "students": stats.get("students"),
            "pass_percentage": stats.get("pass_percentage"),
            "median_percentage": stats.get("median_percentage"),
            "stdev_percentage": stats.get("stdev_percentage"),
            "histogram": stats.get("histogram", []),
            "grades": stats.get("grades", []),
            "grades_basis": stats.get("grades_basis"),
            "papers": [
                p
                | {
                    "highest": q.get("highest"),
                    "median": q.get("median"),
                    "pass_percentage": q.get("pass_percentage"),
                }
                for p, q in zip(papers, stats.get("papers", []), strict=True)
            ],
        }
    return out
