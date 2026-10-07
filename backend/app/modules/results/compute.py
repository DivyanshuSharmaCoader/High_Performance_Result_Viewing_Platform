"""Result computation without the database (docs/03 W8): inputs → engine → outputs, hashes, statistics and
anomalies. Everything here is deterministic: the same inputs, in any order, give the same results and the
same hashes, which is what makes "run twice → identical" and "approved = published" provable.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from app.modules.grading.engine import (
    Attendance,
    ExamOutcome,
    ExamResult,
    GradingInputError,
    MarkInput,
    PaperOutcome,
    PaperSpec,
    assign_ranks,
    grade_exam,
    parse_config,
)

DECIDED = (ExamOutcome.PASS, ExamOutcome.FAIL)
ANOMALY_LIST_CAP = 100  # students listed per anomaly; the count is always exact


class ProcessingError(ValueError):
    """Inputs that can't be graded. The run fails with this message; nothing is written."""


@dataclass(frozen=True, slots=True)
class Paper:
    spec: PaperSpec
    course_code: str
    course_name: str


@dataclass(frozen=True, slots=True)
class Student:
    student_id: str
    enrollment_no: str
    full_name: str
    cohort_id: str


@dataclass(frozen=True, slots=True)
class Mark:
    components: Mapping[str, str]  # canonical decimal strings, as stored
    attendance: str


@dataclass(frozen=True, slots=True)
class Inputs:
    scheme_version_id: str
    config: Mapping[str, Any]
    papers: tuple[Paper, ...]
    students: tuple[Student, ...]
    marks: Mapping[tuple[str, str], Mark]  # (paper_id, student_id)


@dataclass(frozen=True, slots=True)
class Outcome:
    student: Student
    result: ExamResult
    rank: int | None
    marks: Mapping[str, Mark | None]  # paper_id → the marks graded (None: nothing entered)


@dataclass(frozen=True, slots=True)
class Computed:
    outcomes: tuple[Outcome, ...]  # by enrollment number
    content_hash: str


def num(d: Decimal | None) -> str | None:
    """Canonical text for a decimal: no exponent, no trailing zeros (so 72.50 and 72.5 hash the same)."""
    if d is None:
        return None
    text = format(d.normalize(), "f")
    return "0" if text == "-0" else text


def _digest(doc: Any) -> str:
    data = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(data.encode()).hexdigest()


def input_hash(inp: Inputs) -> str:
    """Everything the results depend on. Approval re-computes this to prove nothing changed since."""
    roster = {s.student_id for s in inp.students}
    return _digest(
        {
            "scheme_version": inp.scheme_version_id,
            "config": inp.config,
            "papers": sorted(
                (
                    {
                        "id": p.spec.paper_id,
                        "credits": num(p.spec.credits),
                        "pass_total": num(p.spec.pass_total),
                        "components": [[c.code, num(c.max), num(c.min_pass)] for c in p.spec.components],
                    }
                    for p in inp.papers
                ),
                key=lambda d: str(d["id"]),
            ),
            "students": sorted([s.student_id, s.cohort_id] for s in inp.students),
            "marks": sorted(
                [pid, sid, m.attendance, sorted(m.components.items())]
                for (pid, sid), m in inp.marks.items()
                if sid in roster
            ),
        }
    )


def _mark_input(mark: Mark) -> MarkInput:
    return MarkInput(
        components={k: Decimal(v) for k, v in mark.components.items()},
        attendance=Attendance(mark.attendance),
    )


def compute(inp: Inputs) -> Computed:
    cfg = parse_config(inp.config)
    specs = [p.spec for p in inp.papers]
    ordered = sorted(inp.students, key=lambda s: (s.enrollment_no, s.student_id))
    results: dict[str, ExamResult] = {}
    graded_marks: dict[str, dict[str, Mark | None]] = {}
    for s in ordered:
        marks = {p.spec.paper_id: inp.marks.get((p.spec.paper_id, s.student_id)) for p in inp.papers}
        try:
            results[s.student_id] = grade_exam(
                specs, {pid: _mark_input(m) for pid, m in marks.items() if m is not None}, cfg
            )
        except GradingInputError as exc:
            raise ProcessingError(f"{s.enrollment_no}: {exc}") from exc
        graded_marks[s.student_id] = marks
    ranking: Literal["competition", "dense", "none"] = getattr(cfg, "ranking", "none")
    ranks = assign_ranks(results, ranking)
    outcomes = tuple(
        Outcome(s, results[s.student_id], ranks[s.student_id], graded_marks[s.student_id]) for s in ordered
    )
    return Computed(outcomes, content_hash(outcomes))


def result_doc(o: Outcome) -> dict[str, Any]:
    """One student's result as canonical data: what is hashed, compared between runs and stored."""
    r = o.result
    return {
        "student_id": o.student.student_id,
        "cohort_id": o.student.cohort_id,
        "outcome": r.outcome.value,
        "total": num(r.total),
        "max_total": num(r.max_total),
        "percentage": num(r.percentage),
        "grade": r.grade,
        "grade_point": num(r.grade_point),
        "sgpa": num(r.sgpa),
        "credits_attempted": num(r.credits_attempted),
        "credits_earned": num(r.credits_earned),
        "rank": o.rank,
        "notes": list(r.notes),
        "papers": [
            {
                "paper_id": p.paper_id,
                "outcome": p.outcome.value,
                "attendance": m.attendance if (m := o.marks.get(p.paper_id)) else None,
                "components": dict(sorted(m.components.items())) if m else {},
                "total": num(p.total),
                "max_total": num(p.max_total),
                "percentage": num(p.percentage),
                "grade": p.grade,
                "grade_point": num(p.grade_point),
                "credits": num(p.credits),
                "failed_components": list(p.failed_components),
                "missing_components": list(p.missing_components),
            }
            for p in r.papers
        ],
    }


def content_hash(outcomes: Iterable[Outcome]) -> str:
    return _digest(sorted((result_doc(o) for o in outcomes), key=lambda d: str(d["student_id"])))


# ---- preview ----------------------------------------------------------------------------------------


def _pct(part: int, whole: int) -> str | None:
    return num((Decimal(part) * 100 / whole).quantize(Decimal("0.1"))) if whole else None


def _mean(values: list[Decimal]) -> Decimal | None:
    return sum(values, Decimal(0)) / len(values) if values else None


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    v, mid = sorted(values), len(values) // 2
    return v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2


def _r2(d: Decimal | None) -> str | None:
    return num(d.quantize(Decimal("0.01"))) if d is not None else None


def statistics(c: Computed, papers: Iterable[Paper]) -> dict[str, Any]:
    """Distribution, pass rate and per-paper figures for the preview. Pass % counts students with a result
    (pass or fail); absent, withheld and incomplete students are reported separately."""
    outcomes = Counter(o.result.outcome.value for o in c.outcomes)
    decided = [o for o in c.outcomes if o.result.outcome in DECIDED]
    pcts = [o.result.percentage for o in decided if o.result.percentage is not None]
    bins = [0] * 10
    for p in pcts:
        bins[min(int(p // 10), 9)] += 1
    by_grade: dict[str, list[Decimal]] = defaultdict(list)
    for o in decided:
        if o.result.grade:
            by_grade[o.result.grade].append(o.result.percentage or Decimal(0))
    basis = "exam"
    if not by_grade:  # the scheme grades papers only (a credit scheme gives the exam an SGPA instead)
        basis = "paper"
        for o in c.outcomes:
            for pr in o.result.papers:
                if pr.outcome in (PaperOutcome.PASS, PaperOutcome.FAIL) and pr.grade:
                    by_grade[pr.grade].append(pr.percentage or Decimal(0))
    grades = sorted(by_grade.items(), key=lambda kv: (-(_mean(kv[1]) or Decimal(0)), kv[0]))
    per_paper = []
    for paper in papers:
        pid = paper.spec.paper_id
        rows = [pr for o in c.outcomes for pr in o.result.papers if pr.paper_id == pid]
        sat = [pr for pr in rows if pr.outcome in (PaperOutcome.PASS, PaperOutcome.FAIL)]
        totals = [pr.total for pr in sat if pr.total is not None]
        per_paper.append(
            {
                "paper_id": pid,
                "course_code": paper.course_code,
                "course_name": paper.course_name,
                "max_total": num(paper.spec.max_total),
                "appeared": len(sat),
                "passed": sum(1 for pr in sat if pr.passed),
                "pass_percentage": _pct(sum(1 for pr in sat if pr.passed), len(sat)),
                "absent": sum(1 for pr in rows if pr.outcome is PaperOutcome.ABSENT),
                "incomplete": sum(1 for pr in rows if pr.outcome is PaperOutcome.INCOMPLETE),
                "average": _r2(_mean(totals)),
                "highest": num(max(totals)) if totals else None,
                "lowest": num(min(totals)) if totals else None,
            }
        )
    return {
        "students": len(c.outcomes),
        "outcomes": {k.value: outcomes.get(k.value, 0) for k in ExamOutcome},
        "pass_percentage": _pct(outcomes.get("pass", 0), len(decided)),
        "average_percentage": _r2(_mean(pcts)),
        "median_percentage": _r2(_median(pcts)),
        "histogram": [{"from": i * 10, "to": i * 10 + 10, "count": n} for i, n in enumerate(bins)],
        "grades": [{"grade": g, "count": len(v)} for g, v in grades],
        "grades_basis": basis,
        "papers": per_paper,
    }


def _who(o: Outcome, detail: str) -> dict[str, Any]:
    s = o.student
    return {
        "student_id": s.student_id,
        "enrollment_no": s.enrollment_no,
        "full_name": s.full_name,
        "detail": detail,
    }


def _anomaly(code: str, severity: str, title: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "count": len(items),
        "items": items[:ANOMALY_LIST_CAP],
    }


def anomalies(
    c: Computed,
    papers: Iterable[Paper],
    *,
    previous: Mapping[str, Mapping[str, Any]] | None = None,
    unsubmitted: Iterable[Mapping[str, str]] = (),
) -> list[dict[str, Any]]:
    """Things worth a second look before approving (docs/03 W8 step 4). ``previous`` maps student ids to
    the last run's ``result_doc``; only students whose total, outcome or grade moved are reported."""
    codes = {p.spec.paper_id: p.course_code for p in papers}
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for o in c.outcomes:
        r = o.result
        marks = list(o.marks.values())
        if marks and all(m is None for m in marks):
            found["NO_MARKS"].append(_who(o, "No marks entered for any paper."))
        elif r.outcome is ExamOutcome.INCOMPLETE:
            missing = [
                codes[p.paper_id] + (f" ({', '.join(p.missing_components)})" if p.missing_components else "")
                for p in r.papers
                if p.outcome is PaperOutcome.INCOMPLETE
            ]
            found["INCOMPLETE"].append(_who(o, "Missing: " + ", ".join(missing)))
        if marks and all(m is not None and m.attendance == "absent" for m in marks):
            found["ABSENT_ALL"].append(_who(o, "Absent from every paper."))
        sat = [p for p in r.papers if p.outcome in (PaperOutcome.PASS, PaperOutcome.FAIL)]
        if sat and len(sat) == len(r.papers) and all(p.total == p.max_total for p in sat):
            found["ALL_MAX"].append(_who(o, "Full marks in every paper."))
        if r.outcome is ExamOutcome.WITHHELD:
            found["WITHHELD"].append(_who(o, "Withheld or malpractice in at least one paper."))
        if previous is not None and (before := previous.get(o.student.student_id)) is not None:
            now = result_doc(o)
            changes = [
                f"{label} {before.get(key) or '—'} → {now[key] or '—'}"
                for key, label in (("total", "total"), ("grade", "grade"), ("outcome", "result"))
                if before.get(key) != now[key]
            ]
            if changes:
                text = "; ".join(changes)
                found["CHANGED"].append(_who(o, text[0].upper() + text[1:]))
    pending = [{"detail": f"{x['course_code']} · {x['cohort_code']} ({x['status']})"} for x in unsubmitted]
    out = [_anomaly("UNSUBMITTED", "warning", "Processed before every paper was submitted", pending)]
    titles = {
        "NO_MARKS": ("warning", "No marks at all"),
        "INCOMPLETE": ("warning", "Marks missing"),
        "ALL_MAX": ("warning", "Full marks in every paper"),
        "ABSENT_ALL": ("info", "Absent from every paper"),
        "WITHHELD": ("info", "Result withheld"),
        "CHANGED": ("info", "Changed since the last processing"),
    }
    out += [_anomaly(code, *titles[code], found[code]) for code in titles if found.get(code)]
    return [a for a in out if a["count"]]
