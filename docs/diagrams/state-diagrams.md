# State Machine Diagrams

> State machines are implemented as explicit transition tables in each module's `domain.py` and tested exhaustively (every legal transition allowed, every other rejected). Every transition writes an audit event.

## 1. Examination lifecycle

```mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> MarksEntryOpen: open entry (papers + cohorts configured)
    MarksEntryOpen --> MarksEntryClosed: close entry / deadline
    MarksEntryClosed --> MarksEntryOpen: reopen (reason)
    MarksEntryClosed --> Processed: process results
    Processed --> MarksEntryClosed: marks changed (results stale)
    Processed --> Processed: re-process
    Processed --> Approved: approve (content hash frozen)
    Approved --> Processed: reject / revoke approval (reason)
    Approved --> Scheduled: schedule publication
    Approved --> Published: publish now
    Scheduled --> Approved: cancel schedule
    Scheduled --> Published: scheduled time reached
    Published --> CorrectionDraft: start correction (reason)
    CorrectionDraft --> Processed: re-process changed marks
    Published --> Withdrawn: withdraw (reason)
    Withdrawn --> Approved: re-approve for publication
    Published --> Archived: session archived
    Draft --> [*]: delete (only if no marks)
```

## 2. Paper submission (per paper x cohort)

```mermaid
stateDiagram-v2
    [*] --> Open
    Open --> Submitted: faculty submits
    Submitted --> Returned: admin returns (comment)
    Returned --> Submitted: faculty resubmits
    Submitted --> Locked: exam approved
    Open --> Locked: admin force-locks (reason)
    Locked --> Open: correction started (affected papers only)
```

## 3. Result run

```mermaid
stateDiagram-v2
    [*] --> Running
    Running --> Completed: computation succeeded
    Running --> Failed: error (retryable)
    Failed --> Running: retry
    Completed --> Stale: input marks changed
    Completed --> Approved: approval recorded
    Approved --> Published: publication goes live
    Stale --> [*]: superseded by new revision
```

## 4. Import job

```mermaid
stateDiagram-v2
    [*] --> Uploaded
    Uploaded --> Parsing: worker picks up
    Parsing --> Failed: unreadable file (wrong format, macros, too large, too many rows)
    Parsing --> NeedsMapping: a required field has no column
    Parsing --> Validated: rows staged with issues
    NeedsMapping --> Validating: admin maps columns
    Validated --> Validating: mapping changed / re-check
    Validating --> Validated
    Validating --> NeedsMapping
    Validated --> Committing: admin commits (no errors, or "skip rows with errors")
    NeedsMapping --> Cancelled: admin cancels / superseded by re-upload
    Validated --> Cancelled: admin cancels / superseded by re-upload
    Committing --> Committed: single transaction succeeded
    Committing --> Validated: refused by a business rule (e.g. seat limit) — nothing written, reason shown
    Committed --> [*]
    Cancelled --> [*]
    Failed --> [*]
```

## 5. Publication

```mermaid
stateDiagram-v2
    [*] --> Scheduled: created with future time
    [*] --> Published: created with now
    Scheduled --> Published: job fires at scheduled time
    Scheduled --> Cancelled: admin cancels
    Published --> Superseded: newer version published
    Published --> Withdrawn: admin withdraws (reason)
    Superseded --> [*]
    Withdrawn --> [*]
    Cancelled --> [*]
```

## 6. Verification record

```mermaid
stateDiagram-v2
    [*] --> Pending: code generated at approval
    Pending --> Active: publication published
    Pending --> Void: approval revoked before publication
    Active --> Superseded: corrected version published
    Active --> Withdrawn: publication withdrawn
    Active --> Revoked: fraud or error (reason)
    Superseded --> [*]
    Withdrawn --> Active: re-published unchanged
    Revoked --> [*]
```

## 7. Tenant

```mermaid
stateDiagram-v2
    [*] --> PendingVerification: sign-up submitted
    PendingVerification --> Active: email verified
    PendingVerification --> [*]: expired
    Active --> Suspended: platform admin (abuse, non-payment)
    Suspended --> Active: reactivated
    Active --> Closing: owner requests closure
    Closing --> Active: closure cancelled within grace
    Closing --> Closed: grace period ends, data deleted
    Closed --> [*]
```

## 8. Subscription

```mermaid
stateDiagram-v2
    [*] --> Trialing
    [*] --> Active
    Trialing --> Active: payment received
    Trialing --> Expired: trial ends
    Active --> PastDue: period ended unpaid
    PastDue --> Active: payment received
    PastDue --> Expired: grace ends (falls back to Free entitlements)
    Active --> Cancelled: owner cancels (effective at period end)
    Expired --> [*]
    Cancelled --> [*]
```
