# Security Policy

## Supported versions

This project is under active development.

| Version                 | Supported                    |
| ----------------------- | ---------------------------- |
| main                    | Yes                          |
| latest released version | Yes                          |
| older versions          | No, unless explicitly stated |

Security fixes are applied to the latest supported code only.

## Reporting a vulnerability

Please do not open a public GitHub issue for security vulnerabilities.

Use GitHub private vulnerability reporting if it is enabled for this repository.

If private vulnerability reporting is not available, contact the maintainer through the security contact listed in the repository profile or project documentation.

## What to include

Please include as much of the following as possible.

* A clear description of the vulnerability
* Steps to reproduce
* Affected files, endpoints, pages, packages, or workflows
* Expected impact
* Screenshots, logs, proof of concept code, or request examples where useful
* Whether the issue affects authentication, authorization, secrets, user data, admin actions, CI, deployment, or dependencies

## Response timeline

I aim to acknowledge valid security reports within 72 hours.

After triage, I will try to provide one of the following.

* Confirmation that the issue is accepted
* A request for more information
* A reason why the report is not considered a vulnerability
* An estimated fix path when possible

Critical issues may be fixed privately before public disclosure.

## Scope

The following areas are in scope.

* Authentication and authorization
* API endpoints
* Python backend code
* TypeScript frontend code
* Database access and migrations
* Secrets, tokens, and credentials
* GitHub Actions and CI workflows
* Dependency vulnerabilities
* File upload or import behavior
* Admin, operator, or automation workflows
* AutoIssues security, validation, ranking, routing, and commit-blocking behavior

## Out of scope

The following are usually out of scope unless they cause a real security impact.

* Missing security headers without a practical exploit
* Reports from automated scanners with no proof of impact
* Denial of service caused only by extreme traffic or unrealistic local conditions
* Social engineering
* Physical attacks
* Attacks requiring access to a maintainer machine
* Issues in unsupported versions
* Vulnerabilities in third-party services that are not caused by this project

## Research rules

Please follow these rules when testing.

* Do not access, modify, delete, or exfiltrate other users' data
* Do not attempt persistence
* Do not run destructive tests
* Do not spam forms, APIs, queues, or workflows
* Do not publish the vulnerability before it has been reviewed and fixed
* Use the minimum proof of concept needed to demonstrate the issue

Good faith security research that follows this policy is welcome.

## Disclosure

Please allow time for the issue to be investigated and fixed before public disclosure.

Once the fix is available, a public security advisory or release note may be published when appropriate.

## Bug bounty

This project does not currently offer a paid bug bounty.

Reports are still appreciated and will be credited when appropriate, unless the reporter requests otherwise.

## Security practices

This project aims to use the following security controls.

* Least privilege for secrets, tokens, services, and CI permissions
* Dependency scanning
* Secret scanning
* Static analysis
* Tests for authorization and permission boundaries
* Review of security-sensitive changes before merge
* Blocking commits or pull requests when serious security checks fail
* No hardcoded production secrets
* No public disclosure of private vulnerability details before a fix is ready
