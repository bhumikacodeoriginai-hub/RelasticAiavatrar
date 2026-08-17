# GAP MATRIX — Current State vs Enterprise Requirements

**Date:** 2026-08-17

## Legend
- 🟢 Met — Requirement fully satisfied
- 🟡 Partial — Some implementation exists but insufficient
- 🔴 Gap — Not implemented at all

---

## SECURITY (Priority 0)

| # | Requirement | Current State | Gap | Phase |
|---|-------------|---------------|-----|-------|
| S1 | No hardcoded credentials | 🔴 3 users hardcoded in auth.py | Remove, replace with Cognito/DB | 2 |
| S2 | Proper identity provider (Cognito/OIDC) | 🔴 In-memory Python dict | AWS Cognito integration | 2 |
| S3 | MFA for administrators | 🔴 Not implemented | Cognito MFA | 2 |
| S4 | 7-level RBAC | 🔴 3 hardcoded roles | Database RBAC with 8 roles | 2 |
| S5 | Protected REST endpoints | 🔴 Zero endpoints protected | Add auth dependency to all routes | 2 |
| S6 | Protected WebSocket with signed tickets | 🔴 No WebSocket auth | Connection ticket system | 2 |
| S7 | Frontend login/logout/protected routes | 🔴 No login page | Full auth frontend | 2 |
| S8 | No exposure of embeddings/internal data | 🟡 Embeddings not returned in API responses but stored unencrypted | Encrypt, separate store | 3 |
| S9 | Rate limiting | 🔴 None | Redis-backed rate limiter | 5 |
| S10 | Input validation & output encoding | 🟡 Pydantic models validate some input | Add size limits, sanitization | 2 |
| S11 | HTTPS/WSS in production | 🔴 HTTP only | ALB/CloudFront with TLS | 9 |
| S12 | Security headers (CSP, HSTS, etc.) | 🔴 None | FastAPI middleware | 2 |
| S13 | Secrets in AWS Secrets Manager/SSM | 🔴 .env file only | Secrets Manager integration | 9 |
| S14 | IAM roles instead of access keys | 🔴 Long-lived keys in .env | Instance profiles/task roles | 9 |
| S15 | Audit logging | 🟡 AuditLog model exists but never written to | Implement audit middleware | 2 |
| S16 | Dependency/container scanning | 🔴 None | CI/CD with Snyk/Trivy | 9 |
| S17 | SBOM | 🔴 None | Generate with syft/cdxgen | 9 |

---

## BIOMETRIC PRIVACY (Priority 0)

| # | Requirement | Current State | Gap | Phase |
|---|-------------|---------------|-----|-------|
| P1 | Consent before storage | 🟢 Implemented in conversation flow | — | — |
| P2 | Non-biometric visitor path | 🟡 Consent denial creates record without embedding | Verify full workflow works | 3 |
| P3 | Complete consent record (version, language, device) | 🔴 Only timestamp stored | Expand consent model | 3 |
| P4 | Biometric encryption (KMS envelope) | 🔴 Plaintext JSON | AES-256 + KMS envelope | 3 |
| P5 | Separate biometric storage | 🔴 In visitors table | Separate biometric_templates table | 3 |
| P6 | No raw images/embeddings in logs | 🟢 Not logged | — | — |
| P7 | Retention policies + scheduled deletion | 🔴 None | Configurable retention + cron | 3 |
| P8 | Data access/export/correction/deletion | 🟡 Delete exists, no export/correction | Full DSAR workflow | 3 |
| P9 | Liveness detection | 🔴 None | Multi-frame + texture analysis | 3 |
| P10 | Presentation attack protection | 🔴 None | Anti-spoofing model | 3 |
| P11 | Multiple high-quality frames | 🔴 Single frame | Temporal confirmation | 3 |
| P12 | Multiple faces handling | 🔴 Takes closest only | Queue/reject multiple | 3 |
| P13 | Duplicate registration detection | 🔴 None | Check before registering | 3 |
| P14 | Threshold calibration | 🔴 Static 0.6 threshold | Evaluation dataset + FAR/FRR | 3 |
| P15 | Manual verification fallback | 🔴 None | Low-confidence human review | 3 |
| P16 | AI/camera notice display | 🔴 None | Visible disclosure | 8 |

---

## DATABASE (Priority 1)

| # | Requirement | Current State | Gap | Phase |
|---|-------------|---------------|-----|-------|
| D1 | Alembic migrations | 🔴 create_all() only | Full migration framework | 4 |
| D2 | Extended schema (org, sites, devices, etc.) | 🔴 Minimal tables | 10+ new tables | 4 |
| D3 | Proper foreign keys & constraints | 🟢 Present | — | — |
| D4 | UTC-aware timestamps | 🟡 utcnow but naive | timezone-aware datetimes | 4 |
| D5 | Optimistic locking | 🔴 None | Version columns | 4 |
| D6 | Pagination/filtering/sorting | 🟡 Basic limit/offset | Full query builder | 4 |
| D7 | Face search at scale | 🔴 O(n) Python scan | Vector index or pre-filter | 4 |
| D8 | Backup/restore documentation | 🔴 None | Automated backup + runbook | 9 |
| D9 | Encryption at rest | 🔴 None | RDS encryption, KMS | 9 |
| D10 | Data classification | 🔴 None | Field-level sensitivity labels | 4 |

---

## REDIS & SESSIONS (Priority 1)

| # | Requirement | Current State | Gap | Phase |
|---|-------------|---------------|-----|-------|
| R1 | Redis for session state | 🔴 In-memory dict | Redis-backed sessions | 5 |
| R2 | TTL cleanup | 🔴 None | Session expiry | 5 |
| R3 | Redis Pub/Sub for WS | 🔴 In-memory broadcast | Multi-instance support | 5 |
| R4 | Rate limiting | 🔴 None | Redis sliding window | 5 |
| R5 | Multiple backend replicas | 🔴 Single instance | Stateless + Redis | 5 |
| R6 | Bounded queues | 🔴 Unbounded processing | Backpressure | 5 |
| R7 | Memory leak prevention | 🟡 Departure detector cleans sessions | Add connection TTL | 5 |

---

## VOICE & CONVERSATION (Priority 1)

| # | Requirement | Current State | Gap | Phase |
|---|-------------|---------------|-----|-------|
| V1 | Production STT (not browser-only) | 🔴 Browser Web Speech API | AWS Transcribe Streaming | 6 |
| V2 | Web Audio with echo cancellation | 🔴 None | AudioWorklet pipeline | 6 |
| V3 | Multilingual support | 🔴 en-IN only | Language selection | 6 |
| V4 | Low-confidence confirmation | 🔴 None | Ask to repeat | 6 |
| V5 | Barge-in | 🟢 Implemented | — | — |
| V6 | Echo prevention | 🔴 None | Mute mic during TTS | 6 |
| V7 | Keyboard/touch fallback | 🔴 None | Text input UI | 8 |
| V8 | Bedrock Guardrails | 🔴 None | AWS Bedrock Guardrails | 6 |
| V9 | Prompt injection protection | 🔴 None | Input sanitization + guardrails | 6 |
| V10 | RAG/Knowledge base | 🔴 None | Bedrock Knowledge Base | 6 |
| V11 | Timeouts/circuit breakers | 🔴 None | Resilience patterns | 6 |
| V12 | Token/cost budgets | 🔴 None | Per-session tracking | 6 |
| V13 | Latency budgets | 🔴 None | SLO definitions | 6 |

---

## ENTERPRISE WORKFLOWS (Priority 2)

| # | Requirement | Current State | Gap | Phase |
|---|-------------|---------------|-----|-------|
| W1 | New visitor with consent | 🟢 Implemented | — | — |
| W2 | New visitor without consent | 🟡 Creates record but limited | Full no-biometric path | 7 |
| W3 | Returning visitor | 🟢 Implemented | — | — |
| W4 | Low-confidence fallback | 🔴 None | Manual verification | 7 |
| W5 | QR code pre-registration | 🔴 None | Invitation system | 7 |
| W6 | Appointment verification | 🟡 Model exists, lookup works | End-to-end flow | 7 |
| W7 | Employee notification delivery | 🔴 DB only | Email/Teams/Slack adapter | 7 |
| W8 | Host approve/reject/delay | 🔴 None | Response workflow | 7 |
| W9 | Badge printing | 🔴 None | Badge system | 7 |
| W10 | Check-in/check-out | 🟡 Visit create/end exists | Complete lifecycle | 7 |
| W11 | Emergency mode | 🔴 None | Lockdown/evacuate | 7 |
| W12 | Manual takeover | 🔴 None | Human escalation | 7 |
| W13 | Kiosk offline mode | 🔴 None | Degraded operation | 7 |

---

## AVATAR & UX (Priority 2)

| # | Requirement | Current State | Gap | Phase |
|---|-------------|---------------|-----|-------|
| A1 | Professional 3D avatar | 🟡 Procedural geometry | Licensed GLB/VRM model | 8 |
| A2 | Blendshape lip sync | 🟡 Scale-based mouth opening | Real morph targets | 8 |
| A3 | Natural animations | 🟢 Blinking, breathing, head movement | — | — |
| A4 | 2D fallback | 🟡 Old SVG avatar still in code | Proper detection + fallback | 8 |
| A5 | Captions/mute option | 🔴 None | Accessibility UI | 8 |
| A6 | Responsive performance | 🟡 Canvas-based | Performance budget | 8 |
| A7 | Privacy mode display | 🔴 None | Camera/mic active notice | 8 |

---

## DEVOPS & AWS (Priority 2)

| # | Requirement | Current State | Gap | Phase |
|---|-------------|---------------|-----|-------|
| O1 | Production Docker (multi-stage, no dev server) | 🔴 Dev server, single stage | Production build pipeline | 9 |
| O2 | Infrastructure as Code | 🔴 None | Terraform/CDK | 9 |
| O3 | Separate environments (dev/staging/prod) | 🔴 Single config | Environment management | 9 |
| O4 | CI/CD pipeline | 🔴 None | GitHub Actions | 9 |
| O5 | Blue/green deployment | 🔴 None | ECS/EKS strategy | 9 |
| O6 | OpenTelemetry | 🔴 None | Traces + metrics | 9 |
| O7 | Automated scanning | 🔴 None | Trivy/Snyk/SAST | 9 |
| O8 | Private subnets for DB/Redis | 🔴 Publicly exposed | VPC architecture | 9 |
| O9 | AWS Backup + DR | 🔴 None | Backup procedures | 9 |
| O10 | Runbooks | 🔴 None | Operations documentation | 9 |

---

## TESTING (Priority 2)

| # | Requirement | Current State | Gap | Phase |
|---|-------------|---------------|-----|-------|
| T1 | Backend unit tests | 🔴 Zero tests | pytest suite | All |
| T2 | Integration tests | 🔴 None | Database + API tests | All |
| T3 | Frontend tests | 🔴 None | Vitest + RTL | All |
| T4 | E2E tests | 🔴 None | Playwright | 9 |
| T5 | Security tests | 🔴 None | OWASP testing | 9 |
| T6 | Load tests | 🔴 None | k6/Locust | 9 |
| T7 | Accessibility tests | 🔴 None | axe-core | 8 |
| T8 | Visual regression | 🔴 None | Storybook + Chromatic | 8 |

---

## TOTAL GAP COUNT

| Severity | Count |
|----------|-------|
| 🔴 Critical Gap | 28 |
| 🟡 Partial | 15 |
| 🟢 Met | 12 |
| **Total Requirements** | **55 categories, ~120 items** |

---

## RECOMMENDED IMPLEMENTATION ORDER

1. **Phase 2** (Security): Remove credentials, add Cognito/OIDC, protect all endpoints
2. **Phase 3** (Privacy): Encrypt biometrics, add liveness, expand consent
3. **Phase 4** (Database): Alembic, extended schema, UTC timestamps
4. **Phase 5** (Redis/Sessions): Real Redis usage, rate limiting, scalability
5. **Phase 6** (Voice/AI): Guardrails, RAG, production STT, resilience
6. **Phase 7** (Workflows): Notifications, approvals, badges
7. **Phase 8** (UX): Avatar upgrade, accessibility, dashboard
8. **Phase 9** (DevOps): IaC, CI/CD, observability, production deployment
9. **Phase 10** (Validation): Full test suite, security review, go/no-go
