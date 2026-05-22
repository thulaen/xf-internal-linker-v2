# SonarQube To AutoIssues

[SPEC FRESHNESS: reviewed_at=2026-05-22 next_review=2026-06-22]

## Summary

SonarQube Community Build is a self-hosted code scanner. In this project it is
read-only: it finds code-quality problems, and AutoIssues remains the fixing
queue. SonarQube findings import into first-class `source="sonarqube"`
AutoIssue rows. The session-start quota now keeps the existing 30 cross-source
fixes and adds 10 SonarQube fixes.

## Source-Backed Notes

- SonarSource documents SonarQube Community Build as a self-managed automated
  code review and static-analysis tool for supported languages.
- SonarSource documents a Web API for SonarQube Community Build and recommends
  bearer-token authentication for secured calls.
- SonarSource documents the SonarScanner command-line tool and its Docker image
  as the scanner path for projects configured by `sonar-project.properties`.
- SonarSource documents the Community Build Docker image and default localhost
  setup path for local evaluation.

## Behavior

Given SonarQube has scanned this repository, when an agent runs
`manage.py ingest_sonarqube_issues`, then open SonarQube findings become
deduped AutoIssues with repo-relative affected files.

Given the same SonarQube finding appears in a later scan, when the importer runs
again, then the existing AutoIssue is updated rather than duplicating storage.

Given SonarQube is offline or not configured yet, when the importer runs, then
the command prints a clear message and exits without crashing.

## Design

- Docker Compose provides a local `sonarqube` service on `127.0.0.1:9000`.
- `sonar-project.properties` defines this repository's scanner scope.
- The importer calls SonarQube's `/api/issues/search` endpoint with
  `componentKeys=<project>` and `resolved=false`.
- Imported findings use `source="sonarqube"` and
  `external_id="sonarqube:<project>:<issue-key>"`.
- The session-start AutoIssue quota is 40 total picks: 30 from the existing
  source buckets and 10 from SonarQube findings.
- Severity and priority are mapped conservatively from SonarQube issue data.
- The existing `upsert_dedup` helper remains the only AutoIssue write path.

## Sources

- [SPEC CITED: feature=fr-sonarqube-autoissues kind=technical_doc id=sonarsource-web-api verified_at=2026-05-22] SonarSource, "SonarQube Community Build Web API,"
  https://docs.sonarsource.com/sonarqube-community-build/extension-guide/web-api/
- [SPEC CITED: feature=fr-sonarqube-autoissues kind=technical_doc id=sonarsource-scanner-cli verified_at=2026-05-22] SonarSource, "SonarScanner CLI,"
  https://docs.sonarsource.com/sonarqube-community-build/analyzing-source-code/scanners/sonarscanner/
- [SPEC CITED: feature=fr-sonarqube-autoissues kind=technical_doc id=sonarsource-docker-install verified_at=2026-05-22] SonarSource, "Installing SonarQube from Docker,"
  https://docs.sonarsource.com/sonarqube-community-build/setup-and-upgrade/installing-sonarqube-from-docker/
- [SPEC CITED: feature=fr-sonarqube-autoissues kind=academic_paper id=978-0321146533 verified_at=2026-05-22] Beck, K. 2002. Test-Driven Development by Example. Addison-Wesley. ISBN 978-0321146533.
