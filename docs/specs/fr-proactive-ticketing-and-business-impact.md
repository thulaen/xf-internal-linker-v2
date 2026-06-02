# FR — Proactive Ticketing And Business Impact

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

Create draft tickets before a crash when early warnings are strong, summarize noisy logs, and translate background worker failures into plain business impact.

## Sources Of Truth

- Patent US20200034733A1, forecast confidence bands for anomaly detection, `https://patents.google.com/patent/US20200034733A1`.
- Holt, "Forecasting seasonals and trends by exponentially weighted moving averages", 1957; Winters, "Forecasting Sales by Exponentially Weighted Moving Averages", Management Science 1960, DOI `10.1287/mnsc.6.3.324`.
- Prometheus alerting practices, `https://prometheus.io/docs/practices/alerting/`.
- Celery official task and result documentation, `https://docs.celeryq.dev/`.

## Behavior

### Scenario: draft before crash

Given a metric trend predicts likely failure,  
When confidence passes the threshold,  
Then a draft AutoIssue appears before the crash and is labelled as a prediction.

### Scenario: worker failure impact

Given a Celery task fails,  
When the work queue projection runs,  
Then the row includes plain business impact such as links not generated, processing time wasted, or evidence that impact is unknown.

### Scenario: noisy logs

Given an agent generates thousands of repetitive logs,  
When summarization runs,  
Then old repeated logs are summarized and current signal stays visible.

## Defaults

- Draft tickets do not count as proven failures until a real alert or human approval confirms them.
- Log summaries keep source counts, first seen, last seen, and one example message.
- Business impact text must use plain English.


[SPEC CITED: feature=fr-proactive-ticketing-and-business-impact kind=technical_doc id=https://patents.google.com/patent/US20200034733A1 verified_at=2026-06-02]
