/**
 * The student and parent screens in English: the catalogue every other language must match (decision
 * D29). Placeholders are `{name}`; keys ending `_one` / `_other` are counts. Staff screens are English
 * and don't use this.
 */
const en = {
  // shell
  "shell.account_menu": "Account menu",
  "shell.home": "Home",
  "shell.password_sessions": "Password & sessions",
  "shell.sign_out": "Sign out",
  "shell.language": "Language",
  "shell.powered_by": "Powered by ScoreCode",
  // home
  "home.hello": "Hello, {name}",
  "home.enrollment_no": "Enrollment no.",
  "home.no_results": "No results yet",
  "home.no_results_desc": "Your results will appear here as soon as {institution} publishes them.",
  "home.latest": "Latest result",
  "home.published": "published {when}",
  "home.revised": "revised",
  "home.see_full": "See full result",
  "home.earlier": "Earlier results",
  // result page
  "result.my_results": "My results",
  "result.print": "Print",
  "result.not_available": "This result isn't available. It may have been withdrawn by your institution.",
  "result.load_failed": "Your result couldn't be loaded. Check your connection and try again.",
  "result.revised_notice": "This is a revised result, published {date}. It replaces the earlier version.",
  "result.published_by": "Published by {institution} on {date}",
  "result.class_average_pct": "class average {value}%",
  // result card
  "view.result_of": "Result of {name}",
  "view.sgpa": "SGPA",
  "view.percentage": "Percentage",
  "view.grade": "Grade",
  "view.total": "Total",
  "view.rank": "Rank",
  "view.credits_earned": "Credits earned {earned} of {attempted}",
  "view.marks_by_paper": "Marks by paper",
  "view.credits": "{n} credits",
  "view.below_minimum": "below the minimum",
  "view.no_marks": "No marks entered",
  "view.class_average": "class average {value}",
  "outcome.pass": "Passed",
  "outcome.fail": "Not passed",
  "outcome.fail_note": "Talk to your institution about re-evaluation or a supplementary exam.",
  "outcome.absent": "Absent",
  "outcome.withheld": "Result withheld",
  "outcome.withheld_note": "Your institution will tell you why and what happens next.",
  "outcome.incomplete": "Incomplete",
  "outcome.incomplete_note": "Some marks weren't entered. Contact your institution.",
  "paper.pass": "Pass",
  "paper.fail": "Fail",
  "paper.absent": "Absent",
  "paper.exempt": "Exempt",
  "paper.withheld": "Withheld",
  "paper.incomplete": "Incomplete",
  // marksheet
  "ms.title": "Marksheet (PDF)",
  "ms.ready": "Your official statement of marks, with a QR code anyone can scan to check it.",
  "ms.pending": "Being prepared — it'll be ready in a moment.",
  "ms.failed": "Not ready yet. Your institution can see this and will fix it.",
  "ms.download": "Download",
  "ms.preparing": "Preparing…",
  "ms.still_preparing": "Your marksheet is still being prepared. Try again in a minute.",
  "ms.gone": "This marksheet is no longer available.",
  "ms.download_failed": "The download didn't start. Check your connection and try again.",
  "ms.share_title": "Share a verifiable result",
  "ms.share_desc":
    "Employers and universities can confirm it's genuine at this address. They see your institution, the exam and whether the result is current — not your marks.",
  "ms.copy": "Copy link",
  "ms.copied": "Copied",
  "ms.copy_failed": "Couldn't copy the link. Select it and copy it yourself.",
  "ms.code": "Verification code",
  // class statistics
  "stats.title": "How the class did",
  "stats.students_one": "{n} student",
  "stats.students_other": "{n} students",
  "stats.passed": "{value}% passed",
  "stats.average": "average {value}%",
  "stats.median": "median {value}%",
  "stats.by_percentage": "Students by percentage",
  "stats.band": "{from}–{to}%: {count}",
  "stats.you": "(you)",
  "stats.your_band": "Your band is highlighted",
} as const;

export type MessageKey = keyof typeof en;
export type Catalogue = Record<MessageKey, string>;
export default en satisfies Catalogue;
