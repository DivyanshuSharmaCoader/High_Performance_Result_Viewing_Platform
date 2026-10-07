"""Transactional email templates and the durable send job.

Emails are enqueued in the business transaction and sent by a worker with retries (docs/03 W11).
Links point to the tenant host; emails never contain marks. Payloads that carry one-time links are
scrubbed from the job row after a successful send.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jinja2 import Environment, StrictUndefined, select_autoescape
from sqlalchemy import text

from app.core.db import UnitOfWork
from app.core.jobs import JobContext, enqueue, registry
from app.core.logging import get_logger
from app.core.mailer import OutgoingEmail

log = get_logger(__name__)

_env = Environment(autoescape=select_autoescape(default=True), undefined=StrictUndefined, trim_blocks=True)

_LAYOUT = """\
<!doctype html><html><body style="margin:0;background:#f5f6f8;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1d2433">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 12px"><tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border:1px solid #e4e7ec;border-radius:12px">
<tr><td style="padding:28px 32px 8px;font-size:13px;letter-spacing:.02em;color:#5b6475;font-weight:600">{{ institution }}</td></tr>
<tr><td style="padding:0 32px 8px;font-size:20px;font-weight:650;line-height:1.35">{{ heading }}</td></tr>
<tr><td style="padding:8px 32px 0;font-size:15px;line-height:1.6;color:#344054">{{ body_html }}</td></tr>
{% if action_url %}<tr><td style="padding:24px 32px 8px"><a href="{{ action_url }}" style="display:inline-block;background:{{ brand_color }};color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;padding:12px 20px;border-radius:8px">{{ action_label }}</a></td></tr>
<tr><td style="padding:4px 32px 0;font-size:12px;color:#667085;word-break:break-all">Or paste this link into your browser: {{ action_url }}</td></tr>{% endif %}
<tr><td style="padding:24px 32px 28px;font-size:12px;color:#667085;line-height:1.5">{{ footer }}</td></tr>
</table>
<p style="font-size:11px;color:#98a2b3;margin-top:16px">Sent by ScoreCode on behalf of {{ institution }}.</p>
</td></tr></table></body></html>
"""


@dataclass(frozen=True)
class Template:
    subject: str
    heading: str
    body: str  # plain text paragraphs; rendered escaped into HTML
    action_label: str | None = None
    footer: str = "If you weren't expecting this email, you can safely ignore it."
    sensitive: bool = True  # contains a one-time link → scrub job payload after sending


TEMPLATES: dict[str, Template] = {
    "staff_invite": Template(
        subject="You're invited to {{ institution }} on ScoreCode",
        heading="Join {{ institution }} on ScoreCode",
        body="{{ inviter }} invited you to join as {{ role_label }}. Set your password to get started. "
        "This invitation expires in 7 days.",
        action_label="Accept invitation",
    ),
    "password_reset": Template(
        subject="Reset your {{ institution }} password",
        heading="Reset your password",
        body="We received a request to reset the password for your account. This link works once and "
        "expires in 60 minutes.",
        action_label="Choose a new password",
        footer="If you didn't ask to reset your password, ignore this email — your password won't change.",
    ),
    "student_activation": Template(
        subject="Activate your {{ institution }} results account",
        heading="Activate your results account",
        body="Your institution uses ScoreCode to publish results. Activate your account now so you can "
        "see your results as soon as they're published.",
        action_label="Activate account",
    ),
    "signup_verify": Template(
        subject="Confirm your email to create {{ institution }} on ScoreCode",
        heading="Confirm your email address",
        body="Confirm your email to finish creating your institution's ScoreCode portal at {{ portal_host }}. "
        "This link expires in 30 minutes.",
        action_label="Confirm and create portal",
    ),
    "trial_started": Template(
        subject="Your {{ plan_name }} is on — 30 days to try everything",
        heading="Your 30-day {{ plan_name }} has started",
        body="{{ institution }} now has every Pro feature: your own colours and login page, scheduled "
        "publication, two-person approval, departments and advanced analytics. The trial runs until "
        "{{ ends_on }}. Afterwards you're back on Free automatically — nothing is deleted and nothing is "
        "charged.",
        action_label="See what's included",
        footer="You're receiving this because you started a trial for {{ institution }} on ScoreCode.",
        sensitive=False,
    ),
    "trial_ending": Template(
        subject="Your ScoreCode trial ends in {{ days }} day{{ 's' if days != 1 else '' }}",
        heading="{{ days }} day{{ 's' if days != 1 else '' }} left in your trial",
        body="The trial for {{ institution }} ends on {{ ends_on }}. To keep Pro features, write to "
        "sales@scorecode.in or reply to this email. If you do nothing, you'll move to the Free plan: your "
        "students, marks and published results all stay.",
        action_label="Review your plan",
        footer="You're receiving this because you started a trial for {{ institution }} on ScoreCode.",
        sensitive=False,
    ),
    "trial_ended": Template(
        subject="Your ScoreCode trial has ended",
        heading="You're on the Free plan now",
        body="The trial for {{ institution }} has ended. Everything you created is still there. Over the "
        "Free plan's limits, you can view and export as before but not add more until you upgrade. Write "
        "to sales@scorecode.in to keep Pro.",
        action_label="See your plan",
        footer="You're receiving this because you had a trial for {{ institution }} on ScoreCode.",
        sensitive=False,
    ),
    "result_published": Template(
        subject="{{ exam_name }} results are available",
        heading="Your {{ exam_name }} results are available",
        body="{{ institution }} has published results for {{ exam_name }}. Sign in to view them and "
        "download your marksheet.",
        action_label="View my result",
        footer="You're receiving this because you have a results account with {{ institution }}.",
        sensitive=False,
    ),
    "result_revised": Template(
        subject="Your {{ exam_name }} result was revised",
        heading="Your {{ exam_name }} result was revised",
        body="{{ institution }} issued a revised result for {{ exam_name }}. Sign in to see the latest version.",
        action_label="View my result",
        footer="You're receiving this because you have a results account with {{ institution }}.",
        sensitive=False,
    ),
}


def render(template: str, params: dict[str, Any]) -> OutgoingEmail:
    tpl = TEMPLATES[template]
    ctx = {"brand_color": "#2952cc", **params}
    subject = _env.from_string(tpl.subject).render(ctx)
    heading = _env.from_string(tpl.heading).render(ctx)
    body_text = _env.from_string(tpl.body).render(ctx)
    footer = _env.from_string(tpl.footer).render(ctx)
    action_url = params.get("action_url")
    html = _env.from_string(_LAYOUT).render(
        institution=ctx.get("institution", "ScoreCode"),
        heading=heading,
        body_html=body_text,
        action_url=action_url,
        action_label=tpl.action_label,
        footer=footer,
        brand_color=ctx["brand_color"],
    )
    text_parts = [heading, "", body_text]
    if action_url:
        text_parts += ["", f"{tpl.action_label}: {action_url}"]
    text_parts += ["", footer]
    return OutgoingEmail(to=params["to"], subject=subject, text="\n".join(text_parts), html=html)


async def queue_email(
    uow: UnitOfWork, template: str, to: str, params: dict[str, Any], *, tenant_scoped: bool = True
) -> None:
    if template not in TEMPLATES:
        raise KeyError(template)
    await enqueue(
        uow,
        "notifications.send_email",
        {"template": template, "params": {**params, "to": to}},
        tenant_scoped=tenant_scoped,
    )


@registry.register("notifications.send_email", queue="notifications", max_attempts=6)
async def send_email_job(ctx: JobContext) -> dict[str, Any]:
    template = ctx.job.payload["template"]
    email = render(template, ctx.job.payload["params"])
    message_id = await ctx.infra.mailer.send(email)
    if TEMPLATES[template].sensitive:
        async with ctx.infra.db.uow(ctx.job.tenant_id) as uow:
            await uow.session.execute(
                text(
                    "UPDATE jobs SET payload = jsonb_build_object('template', CAST(:t AS text)) WHERE id = :id"
                ),
                {"t": template, "id": ctx.job.id},
            )
    return {"message_id": message_id}
