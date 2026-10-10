# TechDebt AI v2.0.0 — Commercial Software Engineering Intelligence & Technical Debt Platform

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com)
[![React 19](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0%2B-3178C6.svg)](https://www.typescriptlang.org)
[![Tailwind CSS v4](https://img.shields.io/badge/TailwindCSS-v4-38B2AC.svg)](https://tailwindcss.com)
[![Release](https://img.shields.io/badge/Release-v2.0.0-emerald.svg)](release/techdebt-ai-v2.0.0-production.zip)
[![License: Commercial / Proprietary](https://img.shields.io/badge/License-Proprietary-blue.svg)](LICENSE)

**TechDebt AI** is an enterprise-grade Software Engineering Intelligence and Technical Debt Management Platform engineered and commercially deployed by **GT InnoX LLP**. Designed for engineering executives, software architects, and DevOps teams, TechDebt AI bridges static code diagnostics, multi-ecosystem dependency security, and generative AI reasoning to quantify technical debt into transparent financial and operational metrics: Technical Debt Ratio (TDR), remediation hours, and architectural modernization roadmaps.

---

## 🚀 Key Architectural Capabilities

### 1. Repository Intelligence & Safe Ingestion Pipeline
- **Git Provider Connectivity**: Ingest from GitHub (OAuth / GitHub App / Personal Access Token), GitLab, and Bitbucket.
- **Manual Repository Uploads**: Support for direct compressed ZIP archives with automated language profiling and manifest discovery.
- **Enterprise SSRF Protection**: Strict RFC-1918, RFC-3927 loopback, private CIDR, and cloud metadata (`169.254.169.254`, `metadata.google.internal`) rejection on all repository endpoints.
- **Zip-Slip & Path Traversal Defense**: Rejects null bytes, `../` directory traversals, and absolute extraction paths. Enforces 100MB extraction caps, 5,000 files limits, and 5MB per-file thresholds.

### 2. Multi-Language Source Code Static Intelligence Engine
- **Multi-Language AST & Lexical Parsing**: Deep source inspection for **Python (AST)**, **JavaScript / TypeScript**, **Java**, **Go**, **PHP**, **C#**, and **C / C++**.
- **McCabe Cyclomatic Complexity**: Identifies high-complexity routines (branching, loops, boolean short-circuits) and hotspots.
- **Code Duplication Detector**: Locates cross-file duplicate code blocks using Rabin-Karp inspired sliding line hashes.
- **Dangerous API Detection**: Flags `eval()`, `exec()`, `subprocess(shell=True)`, and SQL raw string formatting.
- **Hardcoded Secret Scanner**: High-entropy regex detection for AWS keys, GitHub tokens, and private keys with automated masking in evidence payloads.
- **Test File Ratio & Maintainability Index (MI)**: Formulates normalized maintainability indices derived from Halstead volume and cyclomatic complexity.

### 3. Advanced Dependency Intelligence & Registry Telemetry
- **Ecosystem Manifest & Lockfile Parsing**: Direct and transitive dependency extraction across 12 package managers:
  - `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` (Node.js / npm)
  - `requirements.txt`, `poetry.lock`, `pyproject.toml`, `Pipfile.lock` (Python)
  - `pom.xml`, `build.gradle` (Java / Kotlin / Android)
  - `Cargo.toml`, `Cargo.lock` (Rust)
  - `go.mod`, `go.sum` (Go Modules)
  - `composer.json`, `composer.lock` (PHP)
  - `.csproj`, `packages.config` (C# / .NET)
- **Live Vulnerability Auditing**: Real-time CVE / GHSA correlation via Google Open Source Vulnerabilities (OSV) API.

### 4. Commercial 10-Dimension Technical Debt Scoring Engine
Deterministic, evidence-grounded scoring formulation (`scoring_version = "v2.0.0"`):
| Dimension | Weight | Mathematical Basis |
| :--- | :--- | :--- |
| **Code Maintainability** | 15% | Maintainability Index minus duplication and excessive complexity penalties |
| **Architecture Quality** | 10% | God classes, oversized files (>500 LOC), and cross-file duplication |
| **Dependency Health** | 15% | Registry currency, maintenance vitality, and deprecation status |
| **Security Posture** | 15% | CVE counts, CVSS base scores, and static code security anti-patterns |
| **Test Quality** | 10% | Test file density, test-to-code ratio, and automated test discoverability |
| **Documentation Quality** | 5% | README completeness, docstring coverage, and official API source links |
| **Reliability** | 10% | Bare/swallowed exception handlers, empty catch blocks, and runtime safeguards |
| **Performance Static Indicators** | 5% | Synchronous I/O in loops, N+1 query smells, and memory leak vectors |
| **Development Complexity** | 10% | Max function nesting depth and cognitive cyclomatic hotspots |
| **Upgrade Risk** | 5% | Semver breaking changes (major version jumps) and unsupported runtime runtimes |

- **Technical Debt Ratio (TDR)**: Calculated as `(Remediation Hours / Total Development Effort) * 100%`.
- **Remediation Effort**: Deterministic hour modeling based on finding severity (Critical: 6h, High: 3h, Medium: 1.5h, Low: 0.5h).

### 5. Generative AI Engineering Assistant
- **AI Refactoring Recipes**: Concrete, step-by-step diffs and procedural recommendations for resolving code findings.
- **30/60/90-Day Modernization Roadmap**: Prioritized milestone schedules targeting immediate security mitigations (30d), architecture cleanup (60d), and platform upgrades (90d).
- **Executive Summaries**: High-level board and stakeholder briefings synthesized from multi-factor evidence.

### 6. Multi-Tenant SaaS Architecture & RBAC
- **Strict Tenant Scoping**: All database models, queries, file workspaces, and review jobs strictly partitioned by `org_id`.
- **6-Tier Role-Based Access Control**:
  - `SuperAdmin`: Global platform monitoring and administration.
  - `Owner`: Organization account owner and commercial billing administrator.
  - `Administrator`: Full team, integration, and project management permissions.
  - `Engineering Manager`: Project creation, review scheduling, and risk assignments.
  - `Developer`: Repository connection, code findings review, and risk resolution.
  - `Viewer`: Read-only reporting and dashboard visibility.
- **Security Features**: Email verification tokens, secure password reset, TOTP Two-Factor Authentication (2FA/MFA), cryptographic token revocation on logout (`jti` blocklist), and self-service account deletion.

### 7. Commercial Subscriptions & Metered Billing
- **4 Subscription Tiers**:
  - **Community Free** ($0/mo): 1 repository, 10 monthly assessments, 1 team seat, 10-dimension debt score.
  - **Team Starter** ($49/mo): 5 repositories, 50 monthly assessments, 5 team seats, AI refactoring recipes.
  - **Professional** ($199/mo): 50 repositories, 500 monthly assessments, 25 team seats, 30/60/90-day roadmaps, priority support.
  - **Enterprise** ($499/mo): Unlimited repositories, 10,000 monthly assessments, 1,000 team seats, dedicated SLA, custom RBAC.
- **Stripe & Sandbox Mode**: Seamless Stripe Checkout session creation for production with automatic offline sandbox fallback when API keys are absent.
- **Usage Metering**: Persistent monthly consumption tracking (`UsageRecord`) and historical invoice generation (`Invoice`).

### 8. Distributed Review Orchestration & Transactional Fencing
- **Dedicated Background Worker**: Reviews run exclusively in the dedicated background worker process (`python -m app.worker`).
- **Atomic Locking & Monotonic Fencing**: Distributed locks with monotonic `generation` tokens and `LockHeartbeat` renewal threads.
- **Stale Write Defense**: Fencing lease verified at 10 pipeline checkpoints. Commit stage uses guarded transactions with post-commit telemetry boundaries.

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
alembic -c alembic.ini upgrade head

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
npm install

# Start Vite development server
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🧪 Quality Gate Verification

TechDebt AI enforces strict automated quality gates across backend and frontend codebases:

```bash
# 1. Run Complete Backend Test Suite (100% Pass Rate)
$env:PYTHONPATH="backend"; python -m pytest backend/tests/ --ignore=backend/tests/test_postgresql_concurrency.py -v

# 2. Run Commercial Tests Specifically
$env:PYTHONPATH="backend"; python -m pytest backend/tests/test_repository_intelligence.py backend/tests/test_source_code_analyzer.py backend/tests/test_billing_and_entitlements.py backend/tests/test_commercial_e2e.py -v

# 3. Frontend TypeScript Compilation
cd frontend && npx tsc --noEmit

# 4. Frontend Vitest Unit Tests
cd frontend && npm test -- --run

# 5. Frontend Production Build
cd frontend && npm run build
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
- **Frontend SPA**: `http://localhost:3000` (Nginx with `/api` reverse proxy)
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
