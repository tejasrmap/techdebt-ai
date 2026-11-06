# TechDebt AI v3.0.0 — Commercial Release Acceptance Criteria

**Standard:** Commercial Enterprise SaaS Production Gate  
**Version:** v3.0.0  
**Target Delivery:** 50 Verified Engineering Commits  

---

## 1. Acceptance Gates

| Gate # | Quality Dimension | Required Acceptance Standard | Verification Mechanism | Status |
|---|---|---|---|---|
| **GATE-01** | Account & Auth Security | No plain reset tokens in API responses; SHA-256 hashed single-use tokens; email verification mandatory; rate-limited brute force protection. | `test_security_multitenancy.py`, auth unit tests | Pending (Commit 02-03) |
| **GATE-02** | Multi-Tenant Isolation | Strict organization boundary enforcement on every endpoint. No cross-tenant data leakage under negative ID manipulation. | Negative tenancy test suites | Pending (Commit 05, 10) |
| **GATE-03** | Repository & Git Ingestion | Secure GitHub App installation flow, GitLab OAuth, ZIP upload validation with safe extraction, asynchronous background ingestion with job polling. | Mocked provider & local git tests | Pending (Commit 11-15) |
| **GATE-04** | Multi-Language AST Quality | True parsing and rule inspection for Python, JS/TS, Java, PHP, Go, C# with file path and line number evidence. | Language analyzer test suites | Pending (Commit 16-20) |
| **GATE-05** | Dependencies & Vulnerabilities | Accurate manifest parsing across 10 ecosystems, lockfile resolution, OSV advisory correlation, license compliance warnings. | Dependency engine tests | Pending (Commit 21-25) |
| **GATE-06** | AI Intelligence & Cost Control | LLM recommendation generation referencing concrete evidence, prompt injection defenses, tenant context isolation, token accounting. | AI provider tests, token accounting | Pending (Commit 26-30) |
| **GATE-07** | Commercial Billing & Webhooks | Stripe webhook HMAC-SHA256 signature verification, quota limits enforced server-side, idempotency on duplicate billing events. | Billing and entitlement tests | Pending (Commit 31-35) |
| **GATE-08** | Customer Experience & UI | Accessible, responsive React 19 UI with loading states, error boundaries, zero console errors, full TypeScript type safety (`tsc -b`). | Vitest, tsc, Oxlint, Vite build | Passed Baseline |
| **GATE-09** | Database Reliability & Fencing | PostgreSQL transactional fencing tokens, row-level locks, bounded heartbeat renewals, zero stale writes, clean migration rollback. | PostgreSQL concurrency suite | Pending (Commit 41-42) |
| **GATE-10** | Release Package Hygiene | Clean production archive with forward slashes, detached SHA-256 checksums, annotated `v3.0.0` git tag, verified manifest. | Package validator script | Pending (Commit 50) |

---

## 2. Release Sign-Off Checklist

- [ ] All 50 Milestone Commits completed and verified on branch `release/v3.0.0`.
- [ ] Pytest backend test suite passes 100%.
- [ ] Frontend Vitest test suite passes 100%.
- [ ] TypeScript compilation (`tsc -b --noEmit`) passes with 0 errors.
- [ ] Code linter (`oxlint`) passes cleanly.
- [ ] Production Dockerfiles build cleanly.
- [ ] No unhandled exceptions or unverified mocked data in customer flows.
- [ ] Detached SHA-256 checksum generated and matched.
- [ ] Annotated Git tag `v3.0.0` created on passing commit 50.
