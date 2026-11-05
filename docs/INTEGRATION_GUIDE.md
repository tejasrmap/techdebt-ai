# TechDebt AI v1.0.9 — Integration Guide

**Product:** TechDebt AI – Technology Debt Review Assistant  
**Release Version:** v1.0.9  

---

## 1. Integration Architecture Overview

TechDebt AI integrates with external intelligence and memory providers:
1. **Firecrawl API:** Web intelligence engine that crawls documentation, security advisories, release notes, and deprecation notices.
2. **GenAI Inference Engines:** Google Gemini API and OpenAI API for multi-dimensional debt evaluation, risk categorization, and modernization recommendations.
3. **Historical Assessment Memory:** Authoritative PostgreSQL multi-tenant persistence layer tracking continuous score drift and risk lifecycle.
4. **Google OSV API:** Real vulnerability database querying published CVEs across software ecosystems.

---

## 2. Organization-Aware Credential Resolution

In multi-tenant production deployments, each organization manages its own credentials:
- Credentials entered via the Settings view are encrypted at rest using Fernet (`AES-128-CBC` with `HMAC-SHA256`).
- When a review starts, `IntegrationConfigService` loads the requesting organization's `IntegrationSetting` record, decrypts the keys in-memory, and injects them into the service instances.
- Global platform keys (`.env`) serve strictly as a fallback when explicitly enabled via `ALLOW_PLATFORM_INTEGRATION_FALLBACK=true`. When disabled, unconfigured organizations operate in deterministic rule-based fallback mode.

---

## 3. Official Memento Evaluation & PostgreSQL Memory Storage

### Product Architecture Evaluation
A thorough architectural review of the official Memento project (`runmemento.com`, `github.com/veerps57/memento`) established:
- **Local-First MCP Protocol:** Official Memento is an open-source Model Context Protocol (MCP) server that runs as a local subprocess over `stdio` using an embedded SQLite database (`~/.local/share/memento/memento.db`).
- **Target Use Case:** It is specifically engineered as a developer tool for individual IDEs (Cursor, Claude Desktop).
- **Multi-Tenant Constraint:** It does not provide a hosted, secure, multi-tenant cloud REST API. Spawning local stdio subprocesses across distributed workers would introduce cross-tenant data leakage and SQLite write contention.

### Solution in TechDebt AI
1. **PostgreSQL as Authoritative Store:** TechDebt AI authoritatively persists longitudinal assessment snapshots, risk progressions, and score drifts directly in PostgreSQL (`historical_assessments` table) with strict organization boundaries.
2. **Transparent Provenance:** The frontend and API truthfully report `PostgreSQL Authoritative Storage` provenance, eliminating any unverified claims of "Memento Cloud".
3. **No Unused API Keys:** Frontend configuration forms require only valid external API keys (Firecrawl, Gemini, OpenAI).

---

## 4. Firecrawl Web Intelligence

- **Target:** Official package registries and documentation URLs (`docs.python.org`, `npmjs.com`, `github.com`).
- **Prompt Injection Defense:** Crawled markdown content is enclosed in structural XML delimiter tags: `<untrusted_crawled_content>`.
- **Publication Date Accuracy:** Missing or unverified publication dates remain `None`, preventing false timestamps.
- **Maintenance State Distinctions:** Distinguishes between `Active`, `Deprecated`, `End of life`, and `Unmaintained` (>3 years without release).

---

## 5. Google Gemini & OpenAI Reasoning Engines

- **Supported Models:** `gemini-1.5-flash`, `gemini-1.5-pro`, `gpt-4o`, `gpt-4o-mini`.
- **JSON Schema Output:** LLM outputs are validated against strict Pydantic schemas.
- **Deterministic Composite Scoring:** 8-category weighted debt score is calculated deterministically in Python to prevent hallucinated scores:
  - Maintenance Health: 20%
  - Security Exposure: 20%
  - Version Currency: 15%
  - Community Activity: 10%
  - Documentation Quality: 10%
  - Ecosystem Compatibility: 10%
  - Long-term Sustainability: 10%
  - Upgrade Complexity: 5%

