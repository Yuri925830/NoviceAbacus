# NoviceAbacus

<div align="center">


### AI-Native Personal Finance Operating System

**Versioned financial truth. Deterministic capital allocation. Explainable intelligence.**

[![Version](https://img.shields.io/badge/version-v1.1.0-6D28D9)]()
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)]()
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)]()
[![TypeScript](https://img.shields.io/badge/TypeScript-Strict-3178C6?logo=typescript)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-Python-009688?logo=fastapi)]()
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-State_Core-4169E1?logo=postgresql&logoColor=white)]()
[![Redis](https://img.shields.io/badge/Redis-Coordination-DC382D?logo=redis&logoColor=white)]()
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)]()
[![PWA](https://img.shields.io/badge/PWA-Installable-5A0FC8?logo=pwa)]()

</div>

---

# Vision

Most personal finance products are optimized to record the past.

NoviceAbacus is engineered to operate the present.

It transforms fragmented account evidence into a verified financial state, converts that state into precise capital assignments, evaluates decisions against real constraints, and turns intelligence into accountable action.

The system continuously answers the questions that actually matter:

- What do I own right now?
- Where is my capital concentrated?
- How much can I spend without weakening my financial position?
- Which goal is each unit of capital funding?
- What changed, why did it change, and what should happen next?

> **Financial clarity should be computed, not guessed.**

---

# Product Thesis

Personal finance is not a collection of screens.

It is a state machine.

NoviceAbacus treats financial reality as **versioned, structured, auditable state** rather than a loose collection of balances, charts, and conversations. Every major product surface is connected to the latest confirmed clearing snapshot and governed by the same monetary rules.

The platform combines three systems that are usually built in isolation:

- A trusted financial system of record
- A deterministic capital allocation engine
- A context-aware intelligence and execution layer

This is not another expense tracker.

This is a personal financial operating system.

---

# Core Doctrine

NoviceAbacus is built around a small set of non-negotiable engineering contracts.

### Truth Before Intelligence

OCR and AI may propose candidate data. Only user-confirmed financial state becomes authoritative.

### One Unit of Capital, One Valid Use

The same money cannot silently fund multiple goals. Every allocation is constrained by the remaining balance of the latest confirmed asset state.

### Deterministic Money, Explainable AI

Application code owns monetary arithmetic, validation, and persistence. AI owns interpretation, scenario framing, risk explanation, and recommended action.

### Incremental Mutation

A save operation changes only the asset-goal relationships explicitly touched by the user. Unrelated financial state is preserved by default.

### Action Over Narration

An insight is incomplete until it can become a tracked decision, funded goal, or executable action.

> **The model may interpret financial truth. It may never invent it.**

---

# Financial Operating Loop

```text
 Account Screenshots / Manual Input
                  │
                  ▼
       Browser-Side Privacy Masking
                  │
                  ▼
        OCR-Assisted Candidate State
                  │
                  ▼
          Human Verification Gate
                  │
                  ▼
      Latest Confirmed Asset Snapshot
                  │
      ┌───────────┼───────────┬──────────────┐
      │           │           │              │
      ▼           ▼           ▼              ▼
 Asset Model   Safe-to-Spend  Goal Funding   Trend Attribution
      │           │           │              │
      └───────────┴───────────┴──────┬───────┘
                                      │
                                      ▼
                         Financial Constitution
                                      │
                                      ▼
                     Ask White / Intelligence Cockpit
                                      │
                                      ▼
                           Executable Action Ledger
                                      │
                                      ▼
                               Review and Reconcile
```

The product loop is deliberately stateful:

> **Capture → Verify → Compute → Allocate → Decide → Execute → Review**

---

# System Architecture

```text
                    ┌──────────────────────────────────────┐
                    │   Next.js 16 · React 19 · TypeScript │
                    │       Responsive Web · PWA           │
                    └──────────────────┬───────────────────┘
                                       │
                              Typed Experience Layer
                                       │
                    ┌──────────────────▼───────────────────┐
                    │          FastAPI Domain Core         │
                    │                                      │
                    │ Auth · Clearing · Assets · Funding   │
                    │ Goals · Spending · Trends · Export   │
                    │ Audit · Validation · Concurrency     │
                    └───────────┬──────────┬──────────┬────┘
                                │          │          │
                 ┌──────────────▼─┐   ┌────▼─────┐   ┌▼──────────────────┐
                 │ PostgreSQL     │   │ Redis    │   │ AI Orchestration   │
                 │ + SQLAlchemy   │   │ Cache &  │   │ Qwen + Private     │
                 │ Versioned State│   │ Extension│   │ OpenAI Gateway     │
                 └──────────────┬─┘   └──────────┘   └─────────┬─────────┘
                                │                              │
                                └──────────────┬───────────────┘
                                               ▼
                              Docker Compose / Cloud Topology
                         Independent Frontend, API, Data, and AI
```

The architecture separates four concerns that must never collapse into one another:

- **Experience state** — interaction, visualization, mobile ergonomics, and client-side privacy controls
- **Domain state** — financial rules, ownership boundaries, validation, and transactional mutation
- **Persistent state** — snapshots, assets, goals, allocations, histories, settings, and audit records
- **Model execution** — external intelligence, regional routing, timeout isolation, and graceful fallback

AI can fail without corrupting the financial core. A stale browser response can be rejected without losing confirmed state. A new deployment topology can be introduced without rewriting domain logic.

---

# Key Capabilities

## Verified Asset Clearing

- OCR-assisted extraction from account screenshots
- Browser-side masking of sensitive image regions before recognition
- Continuous multi-image processing inside a single clearing session
- Manual creation, correction, deletion, and carry-forward of assets and liabilities
- Human confirmation before any recognized value enters financial computation
- Versioned clearing history with revision, traceability, deletion, and export
- Immediate synchronization of the latest confirmed snapshot across dependent modules

## Financial Command Center

- Net worth, total assets, liabilities, liquidity, and high-signal financial indicators
- Asset aggregation across cash, equities, funds, fixed deposits, and other categories
- In-place expansion from category-level structure to individual underlying assets
- Unified visibility into goals, risk, trends, and safe-spending capacity
- Mobile-first interaction with desktop-grade analytical density

## Safe-to-Spend Engine

NoviceAbacus converts budget assumptions into an explicit spending verdict.

The engine models:

- Recurring income
- Essential living expenses
- Current lifestyle expenditure
- Required emergency-reserve duration
- Planned purchase amount

It then computes safe spending capacity, post-purchase margin, financial battery level, and decision risk. Every verdict can be preserved for later review.

## Capital Allocation Engine

Capital is allocated, not merely tagged.

- Select one destination goal for each allocation operation
- Allocate by asset category or individual asset
- Support full and partial allocation
- Use remaining allocatable balance rather than gross asset value
- Preserve untouched assets and existing allocations
- Reuse residual balances across multiple goals
- Reject stale writes against a newer clearing snapshot
- Revalidate amount, ownership, balance, and concurrency on the server

## Goal Lifecycle Engineering

- Create, edit, plan, complete, retain, upgrade, or delete financial goals
- Derive progress from real capital assignments instead of manually entered percentages
- Maintain staged plans that convert a target amount into an execution path
- Trigger explicit completion confirmation when funded value reaches the target
- Treat goal completion as a transition into the next financial decision, not a dead endpoint

## Trend Intelligence and Attribution

- Multi-resolution net-worth trend analysis
- Event annotations at meaningful financial moments
- Structured attribution that connects balance changes to real-world causes
- AI-generated summaries grounded in confirmed snapshots
- Separation of observed fact, inferred cause, conditional risk, and recommended action

## Ask White and the Intelligence Cockpit

- Context-aware personal finance Q&A
- Financial scoring and risk signaling
- Multi-goal scheduling under income, expense, and priority constraints
- Region-aware routing across Qwen and a private OpenAI gateway
- Structured recommendations that can be promoted into the action ledger
- Model isolation and fallback so external AI failure never blocks core finance workflows

## Financial Constitution

Users can encode persistent financial policy rather than repeatedly restating preferences.

Examples include:

- Emergency-fund floors
- Protected or untouchable capital
- Goal priority rules
- Spending discipline
- Current financial focus

These constraints become reusable decision context across spending, allocation, planning, and AI-assisted analysis.

## Product X-Ray

Product X-Ray converts opaque financial-product material into inspectable structure.

- Parse product information from images or PDFs
- Extract duration, fees, liquidity, redemption conditions, downside scenarios, and red flags
- Surface missing or ambiguous terms
- Evaluate the product against the user’s existing financial structure and goals
- Preserve the distinction between extracted fact and analytical interpretation

## Gold Intelligence

- Ingest XAU/USD and foreign-exchange data
- Convert international gold pricing into RMB-per-gram valuation
- Save quoted prices with their valuation context
- Estimate current gold holdings without conflating reference price and realized transaction value

## Data Center and Governance

- CSV, JSON, and PDF export
- Encrypted backup creation, download, and controlled recovery
- Audit history and image-lifecycle inspection
- Account-level data deletion
- Notifications, reminder plans, email settings, security controls, and trusted-device management

---

# Deterministic Financial Core

Financial correctness is enforced as a domain invariant, not presented as a frontend suggestion.

```text
goal.funded_amount
    = Σ active_allocations(goal)

asset.allocated_amount
    = Σ active_allocations(asset)

asset.available_amount
    = latest_confirmed_snapshot(asset).amount
      - asset.allocated_amount

0 ≤ asset.allocated_amount
  ≤ latest_confirmed_snapshot(asset).amount

full_allocate(asset)
    = asset.available_amount
```

## Integrity Mechanisms

### Cent-Level Arithmetic

Monetary values are normalized to the smallest currency unit to eliminate floating-point drift, false insufficient-balance errors, and display-versus-storage divergence.

### Stable Asset Identity

Assets retain stable identity across clearing sessions, carry-forward operations, renames, and legacy mappings. Equality is not inferred from display name or amount alone.

### Snapshot Version Validation

Every allocation write proves that the financial state visible to the client is still current. Stale operations are rejected with a recoverable refresh path.

### Pairwise Incremental Mutation

`asset + goal` is the minimum write boundary. Updating one relationship does not overwrite allocations belonging to other goals.

### Layered Balance Validation

The system validates gross asset value, previously allocated value, remaining allocatable balance, category totals, and requested mutation independently.

### Historical Reconciliation

When a newer clearing deletes, renames, or changes an asset, historical allocations are migrated, clipped, or explicitly surfaced for resolution before further mutation is accepted.

> **Correctness is not a quality attribute added later. It is the product.**

---

# AI-Native, Not AI-Dependent

NoviceAbacus integrates AI as a bounded intelligence plane.

It does not delegate authoritative arithmetic, financial ownership, or state mutation to a language model.

## Model Strategy

- Qwen-powered domestic model path
- Private OpenAI gateway for supported regions
- Region-aware routing and explicit provider selection
- Timeout isolation and automatic fallback
- Structured financial context instead of uncontrolled prompt history
- Core workflows preserved when every external model is unavailable

## Response Contract

AI output is organized into explicit semantic layers:

```text
Confirmed Facts
      ↓
System Interpretation
      ↓
Conditional Risks
      ↓
Recommended Actions
      ↓
Known Data Limitations
```

The result is intelligence that can be inspected, challenged, converted into action, and audited against the state that produced it.

---

# Security and Data Governance

Financial software earns trust through architecture, not marketing language.

## Identity and Session Security

- Argon2 password hashing
- JWT access tokens with managed refresh-token lifecycle
- TOTP-based two-factor authentication
- Offline recovery codes
- Trusted-device visibility and session revocation
- Additional verification for recovery, deletion, and security-sensitive operations

## Privacy Controls

- Sensitive screenshot regions can be masked locally in the browser
- Recognition images have explicit lifecycle and deletion state
- Financial records, model credentials, backups, and audit data remain isolated by responsibility
- Secrets, gateway addresses, signing keys, and database credentials are injected through environment configuration
- Protected resources are account-bound and reauthorized on the server before every write

## Data Sovereignty

- Encrypted backup packaging
- Controlled restore flow
- Audit records for sensitive operations
- User-controlled CSV, JSON, and PDF export
- Account-level data clearing
- No production credentials or user financial data committed to source control

Security is not a settings page.

It is an end-to-end system boundary.

---

# Product Surface

```text
/dashboard      Financial command center and latest-state overview
/clearing       OCR-assisted clearing, manual input, carry-forward, and confirmation
/assets         Clearing history, revision, deletion, traceability, and export
/funding        Category-level and asset-level full or partial capital allocation
/spending       Safe-to-spend model, purchase simulation, verdict, and history
/goals          Goal lifecycle, staged plans, completion, and next-step handling
/assistant      Ask White — context-aware financial intelligence
/intelligence   Scoring, risk, multi-goal scheduling, and action ledger
/trend          Net-worth trends, annotations, attribution, and AI insight
/constitution   Persistent personal financial rules and priority constraints
/xray           Financial-product analysis from images or PDFs
/data           Export, encrypted backup, recovery, audit, and deletion
/settings       Account security, TOTP, devices, reminders, and email
```

---

# Technology Stack

## Experience Layer

- Next.js 16
- React 19
- TypeScript
- Progressive Web App
- Responsive mobile and desktop interaction system
- Browser-side image masking

## Domain Layer

- Python
- FastAPI
- Typed request and response boundaries
- Authentication and session orchestration
- Clearing, assets, allocation, goals, spending, trends, export, and audit services

## State Layer

- PostgreSQL
- SQLAlchemy
- Versioned clearing snapshots
- Stable asset identities
- Goal and allocation state
- Decision histories and audit records

## Coordination Layer

- Redis
- Cache and service coordination
- Extension path for asynchronous workloads and retryable tasks

## Intelligence Layer

- Qwen integration
- Private OpenAI gateway
- Region-aware model orchestration
- Structured responses, fallback, and failure isolation

## Runtime Layer

- Docker Compose
- Independently deployable frontend, API, gateway, database, and cache
- Environment-driven configuration
- Cloud-ready service separation

---

# Reliability Engineering

NoviceAbacus is designed to preserve financial state under refreshes, renames, carry-forward, concurrent updates, network races, and model failure.

- Stale client requests are cancelled or rejected
- Response versions are checked before replacing newer state
- Confirmed clearing triggers active downstream synchronization
- Core finance workflows remain usable when AI services fail
- Dense analytical pages load data on demand
- API, database, cache, and gateway layers can scale independently
- Backup, database, gateway, and health-check paths are operationally observable

Graceful degradation is a default behavior, not an incident response strategy.

---

# Quality Engineering

Version **v1.1.0** has passed the current integrated validation baseline:

- 14 backend automated tests passed
- ESLint validation passed
- TypeScript validation passed
- 17 production pages built successfully
- Desktop browser acceptance passed
- Mobile browser acceptance passed
- Continuous image-recognition workflow verified
- Goal-completion notification and celebration flow verified
- Exact multi-goal incremental-allocation regression verified

A representative financial regression proves that a `10,000` equity asset and a `30,000` fixed deposit can be assigned across two goals as `3,000 + 37,000` without overwriting prior state, double-using capital, or exceeding available balances.

The quality bar is not that a page renders.

The quality bar is that financial truth survives every legitimate state transition.

---

# Design Principles

- Financial truth before visual decoration
- Precision before convenience
- Progressive disclosure before repetitive forms
- Explainability before authority
- Privacy before data appetite
- Incremental mutation before wholesale replacement
- Mobile reachability without desktop compromise
- Graceful degradation under external failure
- Decisions that terminate in accountable action

---

# Scope Boundary

NoviceAbacus is designed for financial organization, scenario analysis, planning, and decision support.

It does not execute trades, guarantee investment returns, replace product due diligence, or substitute for individualized advice from licensed financial professionals. OCR output, product terms, market data, and AI interpretations must remain reviewable by the user before consequential decisions are made.

---

# Roadmap

- Deeper multi-goal scheduling and conflict resolution
- Expanded scenario simulation and risk attribution
- Richer Product X-Ray schemas and data adapters
- Stronger observability, asynchronous orchestration, and automated recovery
- Enhanced installable PWA behavior and notification delivery
- Native mobile packaging and distribution readiness
- Separate public-release architecture for multi-tenancy, governance, privacy, and compliance

---

# Status

Current Release

**v1.1.0 — Integrated Financial Operating Loop**

Current Stage

**Actively evolving**

NoviceAbacus has progressed beyond isolated finance pages into a shared-state system where clearing, asset structure, spending safety, goal funding, trend intelligence, AI reasoning, and action tracking operate on the same verified financial truth.

---

<div align="center">


### NoviceAbacus

**Financial clarity, engineered as infrastructure.**

</div>
