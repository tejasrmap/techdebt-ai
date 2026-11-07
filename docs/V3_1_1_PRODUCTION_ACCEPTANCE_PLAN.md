# TechDebt AI v3.1.1 — Production Acceptance & Hardening Plan

**Product:** TechDebt AI  
**Developer Organization:** GT InnoX LLP  
**Baseline Version:** v3.1.0  
**Target Release:** v3.1.1  
**Working Branch:** `release/v3.1.1-hardening`  
**Target Branch:** `main`  
**Date:** 2026-11-07  

---

## 1. Objective & Scope

The objective of v3.1.1 is commercial production readiness, operational reliability, application security, and independent verification. Rather than introducing unvetted features, v3.1.1 hardens existing platform modules across:

1. **PostgreSQL Production Validation**: Dedicated integration tests, schema validation, foreign keys, unique constraints, isolation, rollback, and concurrency.
2. **Repository Ingestion Reliability**: Exponential backoff retry, worker failure recovery, timeout protection, stalled job remediation, and cancellation handling.
3. **Static Analysis Quality**: Transparent AST vs heuristic labeling, language coverage reporting, and exclusion of minified/malformed artifacts.
4. **Live Vulnerability & License Intelligence**: OSV timeouts, registry fallbacks, cache invalidation, and freshness indicators without false safety claims.
5. **Technical Debt Scoring Calibration**: Validation across 6 controlled corpora (clean, high debt, security, architecture, poor testing, vulnerable dependencies).
6. **AI Provider Resilience**: Gemini and OpenAI timeout handling, quota exhaustion, secret redaction, token metering, and honest fallback provenance.
7. **Commercial Billing & Razorpay Workflow**: One-time payment orders vs subscriptions distinction, server-side matching, webhook replay defense.
8. **Application Security & Tenant Isolation**: Two-tenant cross-isolation penetration tests, TOTP MFA challenges, and trusted-proxy rate limiter IP extraction.
9. **Database Performance & Observability**: SQL aggregation for AI usage ledgers and dashboard KPIs, avoiding memory-intensive N+1 queries.
10. **System Health Probes**: Genuine multi-component readiness checks distinguishing configured, available, connected, healthy, and degraded states.
11. **Frontend Acceptance**: Complete view coverage, SPA navigation without full-page reloads, accessible contrast, and zero fabricated stats.
12. **CI/CD, Release Packaging & Verification**: Automated PostgreSQL CI pipeline, reproducible zip distribution, and SHA256 checksum sidecar.

---

## 2. Acceptance Gates & Verification Methodology

Every verification requirement must strictly report one of the following statuses:
- **`PASS`** — Automated or operational test executed with verifiable evidence.
- **`FAIL`** — Test executed and failed assertion.
- **`PARTIAL`** — Implementation exists but relies partially on mock environment.
- **`NOT RUN`** — Not executed due to missing local dependency.
- **`BLOCKED`** — Blocked by external third-party infrastructure.

### Acceptance Criteria Matrix

| Domain | Key Acceptance Criteria | Target Test Suites |
| :--- | :--- | :--- |
| **PostgreSQL Integration** | Real PostgreSQL connection, zero silent SQLite fallbacks, migration 001-005 upgrade idempotency, row-level locking (`FOR UPDATE`), transaction rollbacks. | `test_postgresql_concurrency.py`, `test_postgresql_migration_and_isolation.py`, `test_alembic_v31_migration.py` |
| **Ingestion Resilience** | Exponential backoff on remote archive downloads, stalled job cleanup on worker startup, cancellation workflow, ZIP symlink & traversal rejection. | `test_v31_repository_ingestion.py`, `test_v311_ingestion_resilience.py` |
| **Static Code Quality** | Comment/string-masked lexical analysis for non-Python languages, honest `heuristic` classification, language coverage report, minified file bypass. | `test_v31_static_analyzer_corpus.py`, `test_v311_static_analysis_quality.py` |
| **Vulnerability Intelligence** | Explicit `CHECK_FAILED` state when OSV is unreachable (never `CLEAN`), cache invalidation API, freshness timestamps on all results. | `test_v31_vulnerability_and_license.py`, `test_v311_vulnerability_resilience.py` |
| **Debt Engine Calibration** | Evaluation against 6 controlled repository corpora; clean repo health $\ge 80$, high debt $\le 60$; explainable 10D scores. | `test_v31_debt_scoring_and_explainability.py`, `test_v311_scoring_controlled_dataset.py` |
| **AI Provider Abstraction** | Outbound secret redaction, schema validation, transparent fallback reporting (`origin: deterministic-engine-v3` vs `llm_generated`). | `test_v31_ai_assistant_provider_abstraction.py`, `test_v311_ai_provider_resilience.py` |
| **Billing Integrity** | Server-side `PaymentOrder` verification, webhook idempotency via `BillingWebhookEvent`, rejection of client-dictated plan/amount. | `test_razorpay_billing.py`, `test_v31_billing_and_security.py` |
| **Security & Rate Limiting** | Rate limiter trusts `X-Forwarded-For` only when client is a trusted proxy; RFC 6238 Base32 TOTP challenge; two-tenant cross-org isolation. | `test_v31_rate_limiter_and_cache.py`, `test_v311_security_and_proxy.py` |
| **Database Performance** | SQL-side `func.sum()` and `group_by()` aggregation for AI usage ledgers; latest-assessment query isolation in dashboard. | `test_v311_database_performance.py` |
| **Health Checks** | `/health` and `/ready` inspect live database, storage, Redis, worker heartbeat, and external provider reachability. | `test_v311_system_health.py` |
| **Frontend Reliability** | Zero dead buttons, SPA tab switching for billing plan changes, accessible contrast across all views, valid TypeScript build. | `vitest run`, `oxlint`, `tsc -b && vite build` |
| **Release Artifacts** | Deterministic zip archive, forward-slash normalized entries, clean SHA256 digest sidecar. | `scripts/package_v311.py`, `SHA256SUMS.txt` |

---

## 3. Execution Schedule & Milestones

1. **Phase A — Audit & Acceptance Plan**: Inspect main baseline, identify all defects and gaps, commit acceptance plan.
2. **Phase B — Critical Engineering Hardening**:
   - Fix rate limiter client IP spoofing vulnerability (trusted proxy validation).
   - Implement genuine multi-component health checks in `main.py` and `historical_memory_adapter.py`.
   - Optimize AI usage ledger aggregation using SQL-side queries (`func.sum`, `group_by`).
   - Harden repository ingestion with stalled job recovery, worker recovery, and cancellation.
   - Add language coverage reporting and minified file detection in `SourceCodeAnalyzer`.
   - Add cache invalidation and explicit freshness indicators in `VulnerabilityIntelligenceService`.
3. **Phase C — Test Suites & Validation**:
   - Write and execute controlled dataset scoring tests (`test_v311_scoring_controlled_dataset.py`).
   - Write and execute ingestion resilience & cancellation tests (`test_v311_ingestion_resilience.py`).
   - Write and execute rate limiter trusted-proxy and security tests (`test_v311_security_and_proxy.py`).
   - Write and execute SQL aggregation performance tests (`test_v311_database_performance.py`).
   - Write and execute system health check tests (`test_v311_system_health.py`).
4. **Phase D — CI/CD Pipeline & GitHub Actions Upgrade**:
   - Add dedicated PostgreSQL integration job in `.github/workflows/ci.yml`.
   - Add secret scanning and dependency audit stages.
5. **Phase E — Release Packaging & Verification**:
   - Package `techdebt-ai-v3.1.1-production.zip` with `scripts/package_v311.py`.
   - Verify SHA256 checksums and perform fresh unpack test.
6. **Phase F — Final Acceptance & Documentation**:
   - Compile all 8 required audit and acceptance reports in `docs/`.
   - Update `README.md`, `CHANGELOG.md`, `RELEASE_MANIFEST.md`, and `SHA256SUMS.txt`.
   - Push and prepare clean merge into `main`.

