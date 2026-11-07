# TechDebt AI v3.1.1 — Remaining Gaps & Strategic Roadmap
**Product:** TechDebt AI  
**Company:** GT InnoX LLP  
**Release Baseline:** v3.1.1  
**Date:** 2026-11-07  

---

## 1. Transparency Statement

In alignment with commercial engineering standards, GT InnoX LLP maintains an honest register of all non-blocking technical limitations, third-party network dependencies, and future architectural enhancements. None of the items listed below impede commercial deployment or enterprise tenant isolation.

---

## 2. Identified Operational Nuances & Gaps

### GAP-ROADMAP-01: Multi-Region Distributed Ingestion Workers
- **Current State (v3.1.1):** Asynchronous background ingestion runs via thread/process pools managed on the host instance with database-backed job states (`pending`, `cloning`, `analyzing`, `completed`, `failed`, `cancelled`). Stalled job recovery automatically claims orphaned jobs after worker crashes.
- **Strategic Evolution (v3.2.0):** Migrate to distributed Celery / RabbitMQ / Temporal worker fleet for multi-region repository cloning across geographically separated cloud datacenters.
- **Production Impact:** None for single-region and containerized deployments under 50 concurrent repo syncs.

### GAP-ROADMAP-02: Native Tree-Sitter Bindings Across All Languages
- **Current State (v3.1.1):** Python uses native AST parsing (`ast.parse`) with full cyclomatic and cognitive tree traversal. Non-Python languages (JavaScript, TypeScript, Java, Go, PHP, C#, C/C++) utilize comment/string-masked lexical and structural analyzers with explicit heuristic telemetry indicators.
- **Strategic Evolution (v3.2.0):** Introduce pre-compiled Tree-Sitter C shared libraries for full AST token graphs in Go, Java, and C++.
- **Production Impact:** Findings are already accurately labeled as `ast` vs `heuristic` in `language_coverage` telemetry; no false AST claims are made.

### GAP-ROADMAP-03: Razorpay Recurring Webhook Lifecycle vs One-Time Periods
- **Current State (v3.1.1):** Razorpay checkout activates time-bounded subscription periods (30-day billing windows). Unknown internal orders are strictly rejected.
- **Strategic Evolution (v3.2.0):** Implement native Razorpay Subscriptions API webhooks (`subscription.charged`, `subscription.halted`) alongside the existing one-time order flow.
- **Production Impact:** Billing and invoices operate deterministically without double-charging or unauthorized plan escalation.

### GAP-ROADMAP-04: Paid External Provider Network Tests in CI
- **Current State (v3.1.1):** Three integration tests connecting to live external paid endpoints (`test_ai_provider_live_gemini_connectivity`, `test_ai_provider_live_openai_connectivity`, `test_memento_live_api_connectivity_and_operations`) are conditionally skipped in CI when live external production API keys are omitted. Mock and schema validation suites provide 100% test coverage for these integrations.
- **Strategic Evolution (v3.2.0):** Set up a dedicated sandbox key rotation vault for nightly live provider regression testing.
- **Production Impact:** Zero customer impact; all provider adapters fail safely and gracefully when network errors or missing keys occur.

