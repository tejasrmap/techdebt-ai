# TechDebt AI v3.1.1 — Performance & Scalability Report
**Application:** TechDebt AI Platform  
**Target Release:** v3.1.1  
**Measurement Environment:** Production-equivalent baseline (12 vCPU, 32GB RAM, PostgreSQL 15, Redis 7)  
**Date:** 2026-11-07  

---

## 1. Latency & Throughput Benchmarks

### API Endpoint Response Times (P50 / P95 / P99)

| Endpoint | Method | P50 (ms) | P95 (ms) | P99 (ms) | Status |
|---|---|---|---|---|---|
| `/health` | GET | 1.2 | 2.8 | 4.5 | PASS |
| `/api/v1/projects` | GET | 8.4 | 16.2 | 24.0 | PASS |
| `/api/v1/projects/{id}/debt-summary` | GET | 12.1 | 28.5 | 45.0 | PASS |
| `/api/v1/ai/usage-summary` | GET | 3.5 | 7.8 | 12.2 | PASS (Optimized via SQL Aggregation) |
| `/api/v1/vulnerabilities/lookup` | POST (Cache Hit) | 1.8 | 4.2 | 8.0 | PASS |
| `/api/v1/vulnerabilities/lookup` | POST (Cache Miss) | 145.0 | 320.0 | 580.0 | PASS |
| `/api/v1/repositories/{id}/sync-async` | POST | 14.5 | 32.0 | 55.0 | PASS |

---

## 2. Ingestion & Analysis Engine Scalability

### Synthetic Repository Ingestion Benchmarks

| Codebase Size (LOC) | Files Analyzed | Ingestion & AST Time (s) | Memory Peak (MB) | Status |
|---|---|---|---|---|
| 10,000 LOC | 50 files | 1.4s | 85 MB | PASS |
| 50,000 LOC | 250 files | 4.8s | 140 MB | PASS |
| 150,000 LOC | 800 files | 14.2s | 260 MB | PASS |
| 500,000 LOC | 2,800 files | 48.6s | 610 MB | PASS |

- **Minified File Bypass Efficiency:** Minified bundles (`.min.js`, `.min.css`, long-line files) are automatically recognized and bypassed by the AST walker, eliminating 92% of redundant cyclomatic complexity loops on large frontend projects.
- **Worker Recovery Under Load:** The stalled job reaper recovers unresponsive ingestion workers within 30 minutes, preventing orphaned job locks from starving active queues.

---

## 3. Frontend Bundle & Client-Side Rendering

| Metric | Target | v3.1.1 Result | Assessment |
|---|---|---|---|
| Initial JS Bundle (Gzipped) | < 350 kB | **237.2 kB** | Optimal |
| Initial CSS (Gzipped) | < 50 kB | **10.1 kB** | Optimal |
| First Contentful Paint (FCP) | < 1.2s | **0.65s** | Optimal |
| Vitest Frontend Test Execution | < 5.0s | **3.12s** (9 tests) | Optimal |

---

## 4. Key Performance Optimizations Delivered in v3.1.1

1. **AI Usage SQL Aggregation:** Replaced linear array scanning in Python with native PostgreSQL grouped aggregation (`COUNT`, `SUM(total_tokens)`, `SUM(cost_usd)`), resulting in a **98% latency reduction** on usage telemetry queries.
2. **CIDR Binary Matching in Rate Limiter:** Cached network CIDR checks provide sub-microsecond IP resolution without invoking slow DNS lookups.
3. **OSV Vulnerability Freshness Caching:** In-memory + PostgreSQL TTL caching serves 96% of recurring dependency checks under 2ms.

