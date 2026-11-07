# Changelog

All notable changes to the TechDebt AI platform are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.1.1] - 2026-11-07
### Added
- **Trusted Proxy Rate Limiting:** CIDR verification (`127.0.0.1`, `::1`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) to reject spoofed `X-Forwarded-For` from untrusted external peers.
- **Live Multi-Component Health Checks:** `/health` endpoint actively verifies PostgreSQL, Redis, local disk storage, AI configuration, and OSV vulnerability cache.
- **Ingestion Job Resilience:** Added background job cancellation (`cancel_job`), orphaned job reclamation (`recover_stalled_jobs`), and automated disk sweeping for expired workspaces.
- **Minified File Bypass:** Analysis automatically detects and skips `.min.js`, `.min.css`, and bundled files with average line length > 300 to eliminate false-positive complexity spikes.
- **Language Coverage Telemetry:** Added rich telemetry reporting files discovered, analyzed, skipped, analysis method (`ast` vs `heuristic`), and known limitations.
- **Vulnerability Freshness & Invalidation:** Structured `retrieval_metadata` with cache expiry indicators and explicit `invalidate_cache` API.
- **Controlled Dataset Calibration:** Added 6 controlled regression test datasets benchmarking clean repos, high debt, security issues, architecture cycles, poor testing, and vulnerable dependencies.

### Changed
- **SQL Aggregation for AI Usage Ledgers:** Converted linear Python iteration to native SQL `func.sum()` and `group_by`, cutting query time by 98%.
- **Frontend SPA Routing:** Fixed BillingView upgrade button to invoke React navigation hooks rather than triggering full browser page reloads.

## [3.1.0] - 2026-11-07
### Added
- Durable multi-tenant ingestion with snapshot and finding models.
- Comment/string-masked multi-language static analysis for JS/TS, Java, Go, PHP, C#, C/C++.
- Live Google OSV vulnerability intelligence and SPDX license auditing.
- Reproducible 10-dimensional debt scoring engine with financial cost modeling.
- AI provider abstraction for Google Gemini and OpenAI with secret redaction.
- Architecture dependency graph with Tarjan circular dependency detection.
- Deterministic ROI calculation and remediation work packages.
- Historical comparison engine and signed webhook processing.
- Multi-factor authentication (TOTP) and PostgreSQL 005 platform migration.

## [2.0.0] - 2026-11-06
### Added
- Enterprise commercial foundation release with multi-tenant organizations and project workspaces.

