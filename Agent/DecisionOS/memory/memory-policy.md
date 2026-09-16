# DecisionOS Memory Policy

## Write policy

DecisionOS may write memory only when the memory type, purpose, owner, sensitivity, retention, and source are known.

Write automatically:

- Investigation state needed to complete the current request
- Tool and authorization audit events
- Decision records explicitly requested or approved for retention

Require explicit approval:

- User preferences
- Executive workspace memory
- New organizational lessons or playbooks
- Any memory containing sensitive personal or financial context

Do not write:

- Credentials, tokens, or secrets
- Raw unrestricted customer records
- Unsupported conclusions or hidden chain-of-thought
- Unmarked synthetic data as production fact

## Read policy

Every read must enforce the requesting user's permissions, workspace scope, sensitivity classification, and retention status. A missing authorization result is a denial.

## Lifecycle

1. Capture purpose and consent where required.
2. Classify sensitivity.
3. Store a source reference and version.
4. Apply expiration or review date.
5. Allow correction, deletion, and audit inspection.
6. Revoke or re-evaluate memory when permissions change.
