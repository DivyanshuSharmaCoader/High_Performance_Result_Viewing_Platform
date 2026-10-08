# Incident templates

## Incident note (start when a page fires)
```
Incident: <short name>                         Severity: page / warn
Started (detected): <UTC> / <IST>               By: <alert name or reporter>
Impact: <who can't do what: students of X can't see results; all sign-ins fail; ...>
Timeline (UTC):
  hh:mm  alert fired / reported
  hh:mm  <each check and each change, one line each>
  hh:mm  service restored
Cause: <once known>
Follow-ups: <tests, alerts, runbook fixes, owners, dates>
```

## Status update (first within 15 min, then every 30 min, and when resolved)
> **ScoreCode: <investigating | identified | monitoring | resolved>** (<time IST>)
> <What users see, in one sentence, e.g. "Some students can't open their results.">
> <What we're doing, e.g. "We've found the cause and are restoring service.">
> Next update by <time IST>.

## To an institution: delayed scheduled publication
> Subject: Your results publication for <exam> is delayed
>
> The results for <exam>, scheduled for <time IST>, have not gone live yet because of a problem on our
> side. Nothing has been lost, and nothing has been shown to students early. We expect them to go live
> by <time IST>, and will tell you the moment they do. If you'd rather publish yourselves, you can cancel
> the schedule and publish now from the exam page. — ScoreCode support

## To an institution: data incident
> Subject: Security incident affecting <institution>: what happened and what we're doing
>
> On <date, time IST> we found <what happened, plainly>. It affected <which data: e.g. names and marks of
> N students in exam X>, between <from> and <to>. It did not affect <what's known to be unaffected>.
> We have <contained it: how>, and <what's next>. As the data fiduciary for your students, you may need
> to notify the Data Protection Board and affected students; we'll give you everything you need for
> that. Your contact for this incident is <name, phone, email>.

## Post-incident review (within 5 working days; blameless)
1. **Summary:** impact, duration, detection (alert or person), time to detect, time to recover.
2. **Timeline:** from the incident note.
3. **What went well, and what didn't.**
4. **Contributing causes.** Not "human error": what made the mistake easy?
5. **Actions,** each with an owner and a date. Tests that would have caught it, alerts that would have
   fired sooner, runbook changes.
