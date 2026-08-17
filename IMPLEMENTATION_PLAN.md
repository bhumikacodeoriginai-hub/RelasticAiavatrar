# IMPLEMENTATION PLAN — Enterprise Upgrade

**Estimated Phases:** 10  
**Priority:** Security → Privacy → Data → Infrastructure → Features → Testing  

---

## Phase 1: Reproducible Baseline (Current — COMPLETE)
- ✅ Full audit completed
- ✅ COMPLETE_AUDIT.md produced
- ✅ GAP_MATRIX.md produced
- ✅ SECURITY_THREAT_MODEL.md produced
- ✅ IMPLEMENTATION_PLAN.md (this document)

---

## Phase 2: Authentication, Authorization & Secret Removal

### Objectives
1. Remove ALL hardcoded credentials from source code
2. Implement proper identity management
3. Protect every REST and WebSocket endpoint
4. Add frontend authentication flow

### Changes Required

| File | Change | Priority |
|------|--------|----------|
| `backend/api/auth.py` | Remove hardcoded ADMIN_USERS dict. Replace with database-backed users + bcrypt. Add login rate limiting. | CRITICAL |
| `backend/config.py` | Remove default secret key. Require SECRET_KEY env var. | CRITICAL |
| `backend/api/visitor.py` | Add `Depends(require_auth)` to all endpoints | CRITICAL |
| `backend/api/employee.py` | Add `Depends(require_auth)` to all endpoints | CRITICAL |
| `backend/api/dashboard.py` | Add `Depends(require_auth)` to all endpoints | CRITICAL |
| `backend/api/websocket.py` | Add connection ticket validation before accept() | CRITICAL |
| `backend/database/models.py` | Add User, Role, Permission models | HIGH |
| `frontend/src/pages/LoginPage.tsx` | NEW — Login form | HIGH |
| `frontend/src/context/AuthProvider.tsx` | NEW — Auth context with token management | HIGH |
| `frontend/src/App.tsx` | Add protected routes, redirect to login | HIGH |
| `docker-compose.yml` | Remove plaintext passwords, use .env refs | HIGH |

### Acceptance Criteria
- [ ] No credentials in source code (secret scan passes)
- [ ] Login with valid credentials returns JWT
- [ ] Invalid credentials return 401
- [ ] 5+ failed attempts trigger 60s lockout
- [ ] All /api/* endpoints return 401 without token
- [ ] WebSocket connection rejected without valid ticket
- [ ] Frontend redirects to /login when unauthenticated
- [ ] Admin can create/disable users
- [ ] Token expires after configured duration

---

## Phase 3: Biometric Privacy, Encryption & Liveness

### Objectives
1. Encrypt biometric templates at rest
2. Implement liveness detection
3. Expand consent records
4. Add retention policies

### Changes Required

| File | Change | Priority |
|------|--------|----------|
| `backend/database/models.py` | Add BiometricTemplate table (separate from visitors), ConsentRecord table with full fields | CRITICAL |
| `backend/services/biometric_crypto.py` | NEW — AES-256-GCM + KMS envelope encryption for embeddings | CRITICAL |
| `backend/vision/liveness.py` | NEW — Multi-frame temporal analysis, texture analysis, depth estimation | CRITICAL |
| `backend/vision/pipeline.py` | Integrate liveness check before recognition | CRITICAL |
| `backend/services/retention.py` | NEW — Scheduled deletion based on policy | HIGH |
| `backend/database/repositories.py` | Update to use encrypted storage/retrieval | HIGH |
| `frontend/src/components/PrivacyNotice.tsx` | NEW — Visible AI/camera/mic disclosure | HIGH |

### Acceptance Criteria
- [ ] Face embeddings encrypted with AES-256-GCM, key in KMS
- [ ] Printed photo does not pass liveness (tested with 10 photos)
- [ ] Video replay does not pass liveness
- [ ] Consent record includes: decision, text_version, policy_version, purpose, language, timestamp, device_id, withdrawal_timestamp
- [ ] Retention scheduler deletes expired records
- [ ] Privacy notice visible on kiosk screen

---

## Phase 4: Database Migrations & Data Model

### Objectives
1. Implement Alembic migration framework
2. Extend schema for enterprise requirements
3. Fix timestamp handling

### Changes Required
- Initialize Alembic in `backend/`
- Create initial migration from current models
- Add models: Organization, Site, Device, ConsentRecord, BiometricTemplate, SecurityEvent, etc.
- Convert all timestamps to timezone-aware (UTC)
- Add version columns for optimistic locking
- Implement scalable face search (pre-filtering by site/time)

---

## Phase 5: Redis, Sessions & Scalability

### Objectives
1. Use Redis for session state
2. Implement rate limiting
3. Enable multi-instance deployment

### Changes Required
- Redis-backed conversation sessions (replace Python dict)
- Redis rate limiter middleware
- Redis Pub/Sub for WebSocket broadcast across instances
- Connection TTL management
- Idempotency keys for critical operations

---

## Phase 6: Voice, AI Guardrails & RAG

### Objectives
1. Add AWS Bedrock Guardrails
2. Implement prompt injection protection
3. Add corporate knowledge base (RAG)
4. Production STT via AWS Transcribe Streaming

---

## Phase 7: Enterprise Workflows & Notifications

### Objectives
1. Implement full visitor lifecycle workflows
2. Add real notification delivery (email/Teams/Slack)
3. Host approval workflow
4. Badge/QR code system

---

## Phase 8: Avatar, Dashboard, Accessibility

### Objectives
1. Professional avatar (licensed GLB/VRM)
2. Enterprise dashboard with full features
3. WCAG 2.2 AA compliance
4. Kiosk/admin UI separation

---

## Phase 9: AWS Infrastructure & CI/CD

### Objectives
1. Terraform/CDK infrastructure
2. GitHub Actions CI/CD pipeline
3. Multi-stage Docker builds
4. Production deployment architecture
5. OpenTelemetry observability

---

## Phase 10: Full Validation & Production Readiness

### Objectives
1. Complete automated test suite
2. Security penetration testing
3. Load/performance testing
4. Accessibility audit
5. Production go/no-go checklist
6. All runbooks completed

---

## RISK REGISTER (Post-Implementation)

To be updated after each phase with residual risks.

---

## DEPENDENCIES

```
Phase 2 ──▶ Phase 3 ──▶ Phase 4
                │              │
                ▼              ▼
           Phase 5 ──▶ Phase 6 ──▶ Phase 7
                                       │
                                       ▼
                              Phase 8 ──▶ Phase 9 ──▶ Phase 10
```

Phases 2-3 are blockers. Phases 4-8 can partially overlap. Phase 9-10 require all prior phases.
