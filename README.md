# TechDebt AI v3.1.0 — Commercial Software Engineering Intelligence & Technical Debt Platform

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com)
[![React 19](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0%2B-3178C6.svg)](https://www.typescriptlang.org)
[![Tailwind CSS v4](https://img.shields.io/badge/TailwindCSS-v4-38B2AC.svg)](https://tailwindcss.com)
[![Release](https://img.shields.io/badge/Release-v3.1.0-emerald.svg)](release/techdebt-ai-v3.1.0-production.zip)
[![License: Commercial / Proprietary](https://img.shields.io/badge/License-Proprietary-blue.svg)](LICENSE)

**TechDebt AI** is an enterprise-grade Software Engineering Intelligence and Technical Debt Management Platform engineered and commercially deployed by **GT InnoX LLP**. Designed for engineering executives, software architects, and DevOps teams, TechDebt AI bridges static code diagnostics, multi-ecosystem dependency security, and generative AI reasoning to quantify technical debt into transparent financial and operational metrics: Technical Debt Ratio (TDR), remediation hours, and architectural modernization roadmaps.

---

## 🚀 Key Architectural Capabilities in v3.1.0

### 1. Durable Repository Intelligence & Ingestion Pipeline
- **Provider Integrations**: Deep ingestion for **GitHub** (OAuth, GitHub App, PAT), **GitLab**, **Bitbucket**, and **ZIP uploads** with automated branch, commit SHA, and author metadata extraction.
- **Durable Analysis Persistence**: Analysis snapshots (`RepositoryIngestionRun`, `RepositoryAnalysisSnapshot`, `CodeFinding`) persist full file metrics, dependency inventories, AST/heuristic findings, and architecture graph data before temporary directory cleanup. Historical reviews and reports require zero local workspace retention.
- **Enterprise SSRF Protection**: Strict RFC-1918, RFC-3927 loopback, CGNAT `100.64.0.0/10`, IPv4-mapped IPv6, and cloud metadata (`169.254.169.254`, `metadata.google.internal`) rejection on all repository endpoints with fail-closed DNS resolution and cross-host redirect authorization stripping.
- **Zip-Slip & Path Traversal Defense**: Streamed byte-counted ZIP extraction rejecting null bytes, `../` directory traversals, absolute paths, and Unix symlinks (`0o120000`). Enforces 50MB archive caps, 5,000 file limits, and 5MB per-file thresholds.

### 2. Multi-Language Source Code Static Intelligence Engine
- **Multi-Language AST & Heuristic Parsing**: Deep source inspection for **Python (AST)** and comment/string-masked lexical analysis for **JavaScript / TypeScript**, **Java**, **Go**, **PHP**, **C#**, and **C / C++**.
- **McCabe Cyclomatic Complexity & Nesting Depth**: Extracts functions, methods, branching logic, loop constructs, and deep cognitive nesting with language-specific heuristics.
- **Code Duplication Detector**: Locates cross-file duplicate code blocks using sliding line hashes with comment/docstring exclusion.
- **Dangerous API & Secret Detection**: Flags `eval()`, `exec()`, `subprocess(shell=True)`, and SQL raw string formatting. High-entropy regex scanner masks AWS keys, GitHub tokens, and private keys in evidence payloads.
- **Coverage Parsing**: Ingests `lcov.info` and `coverage.xml` test coverage artifacts when present without fabricating coverage numbers.

### 3. Live Vulnerability & Dependency Intelligence
- **Ecosystem Manifest & Lockfile Parsing**: Direct and transitive dependency extraction across 13 package manager formats (npm, PyPI, Maven, Gradle, Cargo, Go Modules, Composer, NuGet).
- **Google OSV Intelligence & Registry Telemetry**: Batch vulnerability queries (`/v1/querybatch`) against the Google OSV database with persistent `VulnerabilityCacheEntry` TTL caching, accurate compound SPDX license expression parsing, and explicit `CLEAN` / `VULNERABLE` / `UNKNOWN` / `CHECK_FAILED` states.

### 4. Commercial 10-Dimension Technical Debt Scoring Engine
Deterministic, evidence-grounded scoring formulation (`scoring_version = "v3.1.0"`):
| Dimension | Weight | Mathematical Basis |
| :--- | :--- | :--- |
| **Code Maintainability** | 15% | Maintainability Index minus duplication and excessive complexity penalties |
| **Architecture Quality** | 10% | Tarjan SCC cyclic modules, instability hotspots, and layer boundary violations |
| **Dependency Health** | 15% | Registry currency, deprecation status, unpinned ranges, and license risk |
| **Security Posture** | 15% | CVE counts, CVSS base scores, and static code security anti-patterns |
| **Test Quality** | 10% | Test file density, test-to-code ratio, and parsed coverage metrics |
| **Documentation Quality** | 5% | README completeness, docstring coverage, and architecture specification |
| **Reliability** | 10% | Swallowed exception handlers, empty catch blocks, and runtime safeguards |
| **Performance Static Indicators** | 5% | Synchronous I/O in loops, N+1 query smells, and memory leak vectors |
| **Development Complexity** | 10% | Max function nesting depth and cognitive cyclomatic hotspots |
| **Upgrade Risk** | 5% | Semver breaking changes (major version jumps) and unsupported runtimes |

- **Confidence Calibration**: Quality scores are strictly separated from evidence coverage. Missing inputs degrade confidence rather than masquerading as clean health.
- **Technical Debt Ratio (TDR)**: Calculated as `(Remediation Hours / Total Development Effort) * 100%`.
- **Deduplicated Effort Ranges**: Displays deterministic `Low`, `Expected`, and `High` effort bounds with configurable hourly rates.

### 5. Architecture Intelligence & Dependency Graphs
- **Source-Derived Graph Construction**: Extracts directed module import graphs for Python, JS/TS, Java, Go, PHP, C#, and C/C++.
- **Tarjan SCC Cycle Detection**: Identifies circular dependency components (cycles of length >= 2) with exact cycle member paths and decoupled refactoring recommendations.
- **Coupling & Instability Metrics**: Computes Fan-In ($C_a$), Fan-Out ($C_e$), and Martin Instability metric ($I = C_e / (C_a + C_e)$).
- **Clean Architecture Boundaries**: Detects and flags layering violations (presentation directly invoking persistence/models, data layer invoking controllers).

### 6. Remediation Prioritization & ROI Engine
- **Deterministic Multi-Factor Scoring**: Ranks findings using severity, debt category, blast radius, effort ROI, confidence, and age.
- **Remediation ROI Simulation Planner**: Configurable capacity, developer hourly rates, sprint team size, and horizon to project net financial ROI, hours saved, and risk avoidance percentage.
- **Assignable Work Packages**: Group findings into trackable `RemediationWorkPackage` units with owner assignments and status workflows (`Open`, `In Progress`, `Resolved`, `Accepted Risk`).

### 7. Historical Intelligence & Webhook Automation
- **Commit-Linked Snapshots**: Diff historical assessments commit-by-commit across all 10 dimensions, code findings, and dependencies.
- **Methodology Change Detection**: Explicitly alerts when analyzer versions or scoring algorithms change between runs.
- **Idempotent Webhooks**: DB-backed `WebhookDeliveryEvent` deduplication with mandatory HMAC verification across GitHub, GitLab, and Bitbucket push and PR events.

### 8. Commercial Billing & Multi-Tenant Security
- **Razorpay Order Verification**: Server-side `PaymentOrder` persistence with pre-checkout order generation and cryptographic HMAC-SHA256 signature verification.
- **Webhooks & Idempotency**: Persistent `BillingWebhookEvent` tracking preventing duplicate activations and replaying.
- **Multi-Tenant Scoping & TOTP MFA**: RFC 6238 Base32 Two-Factor Authentication, login challenges, and Supabase PostgreSQL Row Level Security (RLS).
- **Distributed Rate Limiting**: Distributed sliding-window rate limiting with Redis support and transactional database fallback (`RateLimitBucket`).

---

## 🛠️ Quickstart & Local Installation

### Prerequisites
- Python 3.10+
- Node.js 20+ and npm 10+
- PostgreSQL 15+ (optional; SQLite fallback enabled for local evaluation)

### 1. Backend Setup
```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database schema migrations
alembic upgrade head

# Start API web server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Dedicated Scheduler Worker
In a separate terminal:
```bash
cd backend
python -m app.worker
```

### 3. Frontend Setup
```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm ci

# Start Vite development server
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🧪 Quality Gate Verification

TechDebt AI enforces strict automated quality gates across backend and frontend codebases:

```bash
# 1. Run Complete Backend Test Suite (324+ tests passed)
cd backend
python -m pytest -q -p no:cacheprovider

# 2. Run Alembic PostgreSQL & SQLite Migration Validation
cd backend
python -m pytest tests/test_alembic_v31_migration.py -v

# 3. Frontend Static Linter
cd frontend
npm run lint

# 4. Frontend Vitest Unit Tests
cd frontend
npm run test

# 5. Frontend TypeScript Compilation & Production Build
cd frontend
npm run build
```

---

## 🚢 Docker Compose Deployment

TechDebt AI includes production-ready Docker containers with non-root security boundaries and SPA Nginx reverse proxying:

```bash
# Copy and configure environment secrets
cp .env.example .env

# Build and start all 4 services (PostgreSQL, Backend API, Scheduler Worker, Nginx Frontend)
docker compose up -d --build

# Verify container health
docker compose ps
```

Services:
- **Frontend SPA**: `http://localhost:80` (Nginx with `/api` reverse proxy and 50MB upload limits)
- **Backend API**: `http://localhost:8000` (FastAPI with Swagger at `/docs`)
- **Health Probes**: `http://localhost:8000/health` (Liveness) and `http://localhost:8000/ready` (Readiness)
- **PostgreSQL**: `localhost:5432`

---

## 🏢 Enterprise Support & Licensing

Developed and maintained by **GT InnoX LLP**.  
For commercial licensing, enterprise self-hosted deployment, or custom security connectors, contact:
- **Email**: `licensing@gtinnox.com`
- **Support**: `support@gtinnox.com`
- **Website**: `https://gtinnox.com`
