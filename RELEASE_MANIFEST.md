# TechDebt AI v3.1.0 — Commercial Production Release Manifest

**Product:** TechDebt AI – Software Engineering Intelligence & Technical Debt Platform  
**Release Tag:** `v3.1.0`  
**Developer Organization:** GT InnoX LLP  
**Build Timestamp:** 2026-11-07T08:00:00Z  
**Backend Version:** `3.1.0`  
**Frontend Version:** `3.1.0`  
**Distribution Archive:** `release/techdebt-ai-v3.1.0-production.zip`  
**SHA-256 Digest:** `9e40eae2daf5f687ab64052eafa94e17c8c31c1b28e46f7e6cb4d0ad3cdcf93d`  
**Database Migration Revision:** `005_v3_1_platform_strengthening`  
**Commercial SaaS Status:** Certified for Enterprise Commercial Production Deployment  

---

## 1. Executive Summary

TechDebt AI v3.1.0 is a comprehensive platform strengthening release delivering production reliability, deep engineering intelligence, and commercial readiness across all platform subsystems.

Key architectural enhancements include:

1. **Durable Ingestion & Snapshot Persistence (`GAP-ING-01..05`)**: Decoupled ingestion from transient container workspaces using `RepositoryIngestionRun`, `RepositoryAnalysisSnapshot`, and `CodeFinding` models. Full support for GitHub, GitLab, Bitbucket, and ZIP archives with strict SSRF defense (fail-closed DNS, CGNAT/IPv4-mapped IP blocking) and symlink/traversal-safe zip extraction.
2. **Comment-Masked Multi-Language Static Analysis (`GAP-ANA-01`)**: Comment/string-aware complexity and nesting depth analysis for JS/TS, Java, Go, PHP, C#, C/C++ alongside full Python AST parsing and optional coverage artifact ingestion (`lcov.info`, `coverage.xml`).
3. **Live Vulnerability Intelligence (`GAP-VULN-01`)**: High-throughput Google OSV batch querying with persistent `VulnerabilityCacheEntry` TTL caching, multi-registry support (npm, PyPI, Maven, Crates, Go, Packagist, NuGet, RubyGems), and compound SPDX license classification.
4. **Reproducible 10-Dimensional Debt Scoring (`GAP-SCR-01`)**: 10-dimension debt engine (`scoring_version = "v3.1.0"`) with evidence coverage confidence calibration, bounded effort estimates (`Low`, `Expected`, `High`), and raw evidence snapshot persistence.
5. **AI Assistant Provider Abstraction (`GAP-AI-01`)**: Clean Gemini and OpenAI provider abstraction with per-organization encrypted key management, outbound secret redaction, Pydantic schema validation, and finding ID traceability.
6. **Architecture Intelligence & Dependency Graphs (`GAP-ARCH-01`)**: Source-derived multi-language import graphs, Tarjan SCC circular dependency detection (cycles length >= 2), fan-in/fan-out coupling instability, and layer boundary validation.
7. **Remediation Prioritization & ROI Engine (`GAP-ROI-01`)**: Deterministic multi-factor prioritization engine, configurable ROI simulation planner, SQL severity ordering, and trackable `RemediationWorkPackage` units.
8. **Historical Intelligence & Webhook Deduplication (`GAP-HIST-01`)**: Commit-linked 10-dimension snapshot diffing, methodology change notices, fingerprint-based triage carry-forward, and DB-backed `WebhookDeliveryEvent` deduplication with mandatory HMAC verification.
9. **Reporting & Dashboard Safety (`GAP-REP-01`)**: XML entity escaping preventing ReportLab parser crashes, formula-injection neutralization in CSV exports, and latest-assessment query isolation in dashboard metrics.
10. **Commercial Billing & Security (`GAP-BILL-01`, `GAP-SEC-01`)**: Server-side Razorpay order verification, DB-backed webhook idempotency, RFC 6238 Base32 TOTP MFA with login challenge, and Supabase PostgreSQL Row Level Security (RLS).
11. **Distributed Database & Cache Performance (`GAP-DB-01`)**: Migration 005 reconciling schema columns, distributed sliding-window rate limiting with Redis and database fallback (`RateLimitBucket`), and TTL/LRU cache eviction.
12. **Frontend Reliability & Dark Theme Contrast (`GAP-FE-01`)**: Harmonized dark-mode contrast across all 18 views, authenticated blob report downloads, and TypeScript/Vite compilation.
13. **CI/CD Pipeline & Deployment (`GAP-OPS-01`)**: PostgreSQL migration validation in GitHub Actions CI, 50MB Nginx upload limits, and production Docker Compose configuration.

---

## 2. Quality Gate Verification Results

| Quality Gate | Test Scope | Result | Status |
| :--- | :--- | :--- | :--- |
| **Backend Test Suite** | 336 Tests (`backend/tests/`) | 324 passed, 12 skipped (PostgreSQL container integration tests), 0 failed | **100% PASS** |
| **Alembic Migrations** | Fresh SQLite & PostgreSQL 001->005 | Idempotent upgrade head validated | **PASS** |
| **Frontend Unit Tests** | Vitest (`frontend/src/test/`) | 9 passed, 0 failed | **100% PASS** |
| **Frontend Static Linter** | `oxlint` (33 files) | 0 errors | **PASS** |
| **Frontend TypeScript & Build** | `tsc -b && vite build` | Clean production bundle generated (853 kB JS / 60 kB CSS) | **PASS** |
| **Docker Compose** | 4 services (db, backend, worker, frontend) | Validated syntax, healthchecks, and volume mappings | **PASS** |
| **Release Archive Packaging** | Forward-slash normalized, integrity tested, SHA256 verified | Verified | **PASS** |

---

## 3. Distribution Files & Checksums

- **Distribution ZIP:** `release/techdebt-ai-v3.1.0-production.zip`
- **Detached SHA-256 Checksum Sidecar:** `release/SHA256SUMS.txt`
```
9e40eae2daf5f687ab64052eafa94e17c8c31c1b28e46f7e6cb4d0ad3cdcf93d  techdebt-ai-v3.1.0-production.zip
```

---

## 4. Verification Instructions

```bash
# Verify checksum on Windows (PowerShell)
Get-FileHash release/techdebt-ai-v3.1.0-production.zip -Algorithm SHA256

# Verify checksum on Linux / macOS
sha256sum -c release/SHA256SUMS.txt
```
