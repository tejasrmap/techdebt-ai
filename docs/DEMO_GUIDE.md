# TechDebt AI v1.0.9 — Academic Demonstration & Evaluation Guide

**Target Audience:** University Lecturers, Academic Reviewers, Technical Evaluators, and Viva Examiners  
**Platform Version:** TechDebt AI v1.0.9 (Release Candidate)  
**Organization:** GT InnoX LLP  
**Demonstration Time:** 5 to 7 Minutes  

---

## 1. Overview & Evaluation Objectives

TechDebt AI is a production-grade software engineering intelligence platform designed to evaluate, quantify, and track architectural and technical debt in software projects. 

This demonstration guide provides a structured, verifiable script to showcase the core academic and engineering contributions:
1. **Explainable 8-Dimension Technical Debt Evaluation Model** (deterministic mathematical formulation with transparent weights).
2. **Multi-Tenant Security Architecture** (Fernet encryption at rest, token revocation on logout, strict tenant data isolation).
3. **Multi-Ecosystem Automated Dependency Parsing** (npm, pip, cargo, maven, gradle, go modules).
4. **Distributed Concurrency & Transactional Fencing** (PostgreSQL row-level locking with monotonic fencing tokens and stale-write rejection).
5. **Longitudinal Memory & Architecture Drift** (authoritative PostgreSQL historical snapshotting and delta comparison).

---

## 2. Quick Environment Setup

### 2.1 Backend Startup
```bash
# In project root
$env:PYTHONPATH='backend'
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
*Backend API available at: `http://localhost:8000` (Swagger UI at `/docs`)*

### 2.2 Frontend Startup
```bash
cd frontend
npm run dev
```
*Frontend Application available at: `http://localhost:5173`*

### 2.3 Automated Test Quality Gate
```bash
# Execute standard 85 automated test suite (100% pass)
$env:PYTHONPATH='backend'
python -m pytest backend/tests/ -v -m "not postgresql"

# Execute frontend Vitest suite (100% pass)
cd frontend; npm test -- --run
```

---

## 3. Step-by-Step 5-Minute Demonstration Script

### Minute 1: Multi-Tenancy & Authentication (Security & RBAC)
1. **Navigate to `http://localhost:5173`**.
2. **Register a new Organization:**
   - Full Name: `Dr. Academic Evaluator`
   - Email: `evaluator@university.edu`
   - Organization: `Computer Science Dept`
   - Password: `Password123!`
3. **Verify Role Assignment:**
   - The user is automatically assigned the `Administrator` role for their isolated organization.
   - All database queries transparently filter by `org_id`.
4. **Demonstrate Token Security:**
   - Show how logging out adds the JWT `jti` to the database `revoked_tokens` table, immediately invalidating the token.

---

### Minute 2: Multi-Ecosystem Ingestion & Catalog Parsing
1. **Create a New Project:**
   - Name: `Distributed Cloud Gateway`
   - Repository: `https://github.com/cs-dept/cloud-gateway`
   - Primary Stack: `TypeScript`, `Node.js`, `Python`
2. **Import Dependencies:**
   - Navigate to the **Technology Catalog** tab.
   - Click **Import Dependencies** and upload or paste sample manifest files:
     - `package.json` with outdated packages (e.g. `"react": "16.8.0"`, `"lodash": "4.17.15"`, `"axios": "^0.21.1"`).
     - Or `requirements.txt` with legacy Python dependencies (e.g. `"flask==1.1.2"`, `"requests==2.22.0"`).
3. **Inspect Dependency Discovery:**
   - The system automatically extracts libraries, versions, ecosystems, and cross-references them against known CVEs via the Google OSV (Open Source Vulnerabilities) API.

---

### Minute 3: Explainable 8-Dimension Technical Debt Evaluation
1. **Trigger Assessment:**
   - Click **Run Assessment** on the project page.
2. **Explain the Mathematical Debt Formula:**
   Show the lecturer that the overall score is **not an ungrounded black-box LLM output**, but a deterministic weighted calculation:
   $$\text{Overall Score} = \sum_{i=1}^{8} (w_i \times S_i)$$
   - **Maintenance Health ($w_1 = 0.20$):** Release frequency, active commit status, commit velocity.
   - **Security Exposure ($w_2 = 0.20$):** CVE severity count and vulnerability age.
   - **Version Currency ($w_3 = 0.15$):** Semantic version drift ($\Delta$ major, minor, patch).
   - **Community Activity ($w_4 = 0.10$):** GitHub stars, contributor diversity, issue closure rate.
   - **Documentation Quality ($w_5 = 0.10$):** Migration guides, changelogs, API documentation.
   - **Ecosystem Compatibility ($w_6 = 0.10$):** Supported runtime versions (e.g. Node 20+, Python 3.11+).
   - **Long-term Sustainability ($w_7 = 0.10$):** Foundation backing, corporate stewardship.
   - **Upgrade Complexity ($w_8 = 0.05$):** Breaking API changes and dependency tree depth.
3. **Classification Thresholds:**
   - $Score \ge 80$: **Healthy / Good**
   - $60 \le Score < 80$: **Moderate Risk**
   - $40 \le Score < 60$: **High Risk**
   - $Score < 40$: **Critical Debt**

---

### Minute 4: Longitudinal Memory & Drift Comparison
1. **Run a Second Assessment:**
   - Simulate a package upgrade (e.g. update React from `16.8.0` to `18.2.0`).
   - Click **Run Assessment** again.
2. **View Architecture Drift Comparison:**
   - Navigate to the **Comparison** view.
   - Show how TechDebt AI computes delta differences:
     - $\Delta \text{ Health Score}$ (+12.4 points).
     - New vs. Resolved Risks.
     - Version drift reduction.
   - Point out the **Authoritative Storage Provenance**: snapshots and drift metrics are authoritatively stored in **PostgreSQL** with strict multi-tenant isolation.

---

### Minute 5: Risk Center Triage & Scheduler Concurrency
1. **Risk Management Center:**
   - Navigate to **Risk Center**.
   - Show actionable risk tickets auto-generated from assessment evidence.
   - Demonstrate triage actions: assign ticket to a team member, update status (`Open` $\rightarrow$ `In Progress` $\rightarrow$ `Resolved`).
2. **Distributed Scheduler Architecture:**
   - Highlight the distributed lock architecture (`backend/app/services/scheduler_service.py`):
     - Background APScheduler runs strictly inside `app.worker`.
     - Distributed lock table with atomic conditional SQL.
     - **Fencing generation tokens**: prevents split-brain writes during worker failover or lease expiration.
     - **Post-commit completion boundary**: atomic commit of assessment + historical snapshot, ensuring durable completion cannot be rolled back by post-commit network lease timeouts.

---

## 4. Key Academic & Theoretical Questions Addressed

| Evaluation Criterion | Implementation & Demonstration Reference |
|---|---|
| **Deterministic vs. Generative Scoring** | Pure Python weighted score calculation (`backend/app/services/scoring.py`), grounded with verified evidence, eliminating LLM hallucination risks. |
| **Concurrency & Distributed Systems** | Monotonic fencing token (`generation`) and PostgreSQL row-level locks (`SELECT ... FOR UPDATE`), validated via multiprocessing tests. |
| **Security & Tenant Isolation** | AES-128 Fernet credential encryption at rest, JWT blacklisting on logout, organization ID foreign-key boundaries on all tables. |
| **Data Integrity & Atomicity** | Atomic single-transaction commit of assessment, technology scores, risk findings, and historical snapshot. |
| **Real Test Database Safety** | `POSTGRES_TEST_DATABASE_URL` strict isolation guards, rejecting production URLs and non-test database names. |

---

## 5. Demonstration Conclusion & Viva Summary

TechDebt AI v1.0.9 demonstrates complete readiness for university project submission and viva examination, combining academic rigor in debt measurement metrics with enterprise-grade distributed systems reliability.

