# Public source and private runtime data

The public repository contains implementation code, schemas, synthetic examples, tests and deployment documentation. It does **not** contain configured accounts, API credentials, business databases, generated plans, backup archives, personal learning records, local screenshots or a preconfigured company deployment.

## Isolation boundaries

| Material | Location / control |
|---|---|
| Model credentials | Local `.env` or runtime environment; only the empty `.env.example` template is published |
| Local access instructions | `.local-access.md`, excluded from Git, source distributions and Docker context |
| Business database, sessions, conversations and generated files | `var/` and `output/`, excluded from publication |
| Backups | `backups/`, excluded; access must be restricted because backups contain business records and password hashes |
| Customer drawings and private input | `customer-data/`, `private-inputs/`; not part of public examples |
| Personal lessons and internal notes | Local lesson documents and internal planning folders excluded; generic example programs remain available |
| Workstation metadata and credentials | OS metadata, database files, private-key files and local logs excluded |
| Commit author identity | Use the GitHub-provided no-reply email, configured for this repository rather than a private mailbox |

The `.gitignore`, `.dockerignore` and `MANIFEST.in` files cover Git, Docker build context and Python source distributions respectively. Ignore rules do not remove previously tracked files or sanitize existing history.

## Release checks

Run these before publication:

```bash
python -m pytest
python scripts/release_audit.py --staged
python scripts/release_audit.py --history
python -m build
python scripts/release_audit.py --archive dist/<wheel-file>.whl --archive dist/<source-file>.tar.gz
```

The staged check reads the actual Git index, so cleaning a working file without restaging it cannot hide a previously staged secret. The audit flags common token/private-key patterns, personal home paths, private email addresses, selected personal identifiers and forbidden runtime filenames. Package checks inspect archives without extracting or executing their contents.

The ignored `.release-audit.local.txt` may contain exact private values for local matching. This file must never be shared with CI or committed; remote CI cannot enforce a local private-value list. Reports redact matching values. Public CI runs generic privacy checks plus the repository's configured GitGuardian secret scan. Local release checks may also use Gitleaks with fully redacted output.

Check binary assets manually: a text scanner cannot establish whether an image or drawing visibly contains private information. Synthetic examples must be clearly identified, and authentic customer files must never be substituted in public tests.

## Existing history

Scan existing commit metadata as well as file contents. New no-reply commits do not erase private email addresses already recorded in old commits. Rewriting published history changes commit IDs and can require collaborators to resynchronize, so handle historical remediation separately from an ordinary upload. Local recovery copies of original history must remain private and must not be pushed as backup branches or tags.

Rewriting a branch is not a guarantee that already-public content disappears from clones, caches or retained commit URLs. If a real credential was ever published, revoke it at the issuer; removing its text alone is insufficient.

## Runtime data and model provider

The UI sends the current order's material/profile, conversation and parameter draft to the configured DeepSeek endpoint when the user chooses to use the Agent. It does not send the full database, local passwords or other orders. Confirm the company's permitted data scope before using real business inputs; manual parameter entry and deterministic calculation work without a model key.

Deployments must create their own employee and reviewer accounts, configure HTTPS, assign backup responsibility and validate actual process parameters. Public source access never grants access to a local workbench or its business data.
