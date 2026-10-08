# Private GitHub publication check

Date: 2026-10-08. Target: `zamusikmain/nexora`, private repository, branch `main`.

The existing five commits are preserved. Application source, dependency graphs, migrations and behavior are unchanged by publication preparation. Only ignore rules and this report are added.

## Security verification
- Gitleaks v8.30.1 with default rules and redacted output: no leaks in the original entire Git history and tracked working tree. The final publication commit is scanned again before push.
- Original tracked snapshot: 94 files. Historical path inventory: 123 entries, no environment secrets, private keys, local databases/dumps, uploaded/user documents or temporary data found in history.
- Expanded `.gitignore` covers `.env` variants, local credentials/private keys, DB files/dumps/backups, private data/uploads/user document folders, office/PDF documents, logs and temporary/cache files.
- Automated ignore checks confirm private artifact exclusion while `.env.example` and application `/documents` route source remain publishable.
- Synthetic development/demo/test passwords in examples and tests are intentional examples. Actual `.env`, persisted DB, uploads and backup contents are excluded. No authentication token is written into the repository or remote URL.
- Scanner runs with repository mounted read-only and network disabled. Redacted JSON reports remain in ignored `.tmp/publication/`, not in Git.

## Publication safeguards
Authenticate the intended account, check repository owner/privacy and remote refs, preserve all local history, fetch any existing remote history and require remote main to be an ancestor before push. Use ordinary fast-forward push only; never force push. Verify remote main SHA equals local HEAD and repository visibility remains private after push. A divergent or unrelated existing main requires reconciliation before publishing.

This check covers secret exposure in Git publication; the application's enterprise/security limitations remain documented in `verification.md` and `security.md`.
