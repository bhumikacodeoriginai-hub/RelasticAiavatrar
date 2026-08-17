# PRIVACY & BIOMETRIC ASSESSMENT

**System:** AI Avatar Receptionist  
**Date:** 2026-08-17  
**Classification:** CONFIDENTIAL — Legal/Privacy Team Review Required  

---

## 1. BIOMETRIC DATA INVENTORY

| Data Type | Storage Location | Format | Encrypted | Retention | Consent Required |
|-----------|-----------------|--------|-----------|-----------|-----------------|
| Face embedding (512D) | MySQL `visitors.face_embedding` | JSON array | ❌ NO | Indefinite | ✅ Yes (asked) |
| Profile image | Filesystem (path in DB) | JPEG | ❌ NO | Indefinite | ✅ Yes (with embedding) |
| Camera frames | Not persisted | In-memory numpy | N/A | Duration of processing | ⚠️ Implicit (camera active) |
| Voice audio | Not persisted | Browser-local only | N/A | Session duration | ⚠️ Browser handles |
| Speech transcript | MySQL `conversation_messages` | Text | ❌ NO | Indefinite | ⚠️ No explicit consent |

---

## 2. CONSENT MECHANISM ASSESSMENT

### Current Implementation
- **Where:** `ai/conversation_manager.py` ASKING_CONSENT state
- **How:** Avatar asks "Would you like me to remember your face for future visits?"
- **Positive detection:** Keyword match (yes, sure, okay, etc.)
- **Negative detection:** Keyword match (no, don't, prefer not, etc.)
- **Storage:** `visitors.consent_status` (enum) + `consent_timestamp`

### Gaps vs Enterprise Requirements

| Requirement | Status | Finding |
|-------------|--------|---------|
| Informed consent (clear explanation of what's stored) | ⚠️ Partial | Avatar mentions "mathematical representation" but no written policy reference |
| Specific purpose | ⚠️ Partial | "Greet you by name next time" — limited scope declaration |
| Consent version tracking | ❌ Missing | No version field — if policy changes, old consent is unversifiable |
| Language of consent | ❌ Missing | Only English, no language field stored |
| Device/site identifier | ❌ Missing | Cannot determine where consent was given |
| Withdrawal mechanism | ✅ Present | PUT /api/visitors/{id}/consent with "revoked" triggers deletion |
| Withdrawal effect | ✅ Present | Embedding and image_path nullified |
| Under-age protection | ❌ Missing | No age verification before biometric collection |
| Third-party disclosure | ❌ Missing | No notice about AWS processing (Bedrock, Polly) |

---

## 3. LIVENESS & ANTI-SPOOFING ASSESSMENT

### Current State: NO LIVENESS DETECTION

| Attack Vector | Defended | Method |
|--------------|----------|--------|
| Printed photograph | ❌ NO | — |
| Phone/tablet screen display | ❌ NO | — |
| Video replay on monitor | ❌ NO | — |
| Deepfake real-time | ❌ NO | — |
| 3D mask | ❌ NO | — |
| Multiple-frame consistency | ❌ NO | Single frame recognition |

### Risk Assessment
- **Probability of attack:** HIGH in enterprise environment (disgruntled employees, social engineering)
- **Impact:** Unauthorized building access, visitor impersonation, audit trail corruption
- **Recommendation:** MUST implement before production

### Recommended Approach
1. **Texture analysis** — detect paper/screen pixel patterns (Laplacian + frequency analysis)
2. **Temporal consistency** — require 3+ frames over 1-2 seconds showing natural movement
3. **Blink detection** — require at least one blink during enrollment/recognition
4. **Challenge-response** (optional) — "Please turn your head slightly"
5. **Depth estimation** (if hardware supports) — monocular depth or structured light

---

## 4. DATA PROTECTION IMPACT ASSESSMENT (DPIA) — Required Items

| DPIA Element | Status |
|--------------|--------|
| Description of processing | ⚠️ In README but not formal |
| Purpose and legal basis | ❌ Not documented |
| Necessity and proportionality | ❌ Not assessed |
| Risks to individuals | ❌ Not formally assessed |
| Safeguards and mitigations | ❌ Incomplete |
| Data Protection Officer sign-off | ❌ Not obtained |
| Regular review schedule | ❌ Not defined |

---

## 5. DATA SUBJECT RIGHTS (DSAR) IMPLEMENTATION

| Right | Current Support | Gap |
|-------|----------------|-----|
| Right to be informed | ⚠️ Avatar mentions storage | No written privacy notice |
| Right of access | ❌ No self-service export | Need data export API |
| Right to rectification | ❌ No correction mechanism | Need correction workflow |
| Right to erasure | ✅ DELETE /api/visitors/{id} | Lacks cascade verification |
| Right to restrict processing | ❌ Not implemented | Need processing restriction flag |
| Right to data portability | ❌ Not implemented | Need machine-readable export |
| Right to object | ⚠️ Can refuse consent | No processing objection mechanism |

---

## 6. ENCRYPTION REQUIREMENTS

### Current: NONE
Face embeddings are stored as plaintext JSON arrays in MySQL.

### Required Architecture:
```
┌─────────────────────────────────────────────────────────┐
│ Application Layer                                       │
│                                                         │
│ Embedding (512 floats) → AES-256-GCM encrypt           │
│                          │                               │
│                          ▼                               │
│            Ciphertext + IV + Auth Tag                    │
│                          │                               │
│                          ▼                               │
│        Data Encryption Key (DEK) — random per record    │
│                          │                               │
│                          ▼                               │
│        Encrypted DEK (via AWS KMS CMK)                  │
│                          │                               │
│                          ▼                               │
│        Store: { encrypted_embedding, encrypted_dek,     │
│                 iv, auth_tag, kms_key_id, version }     │
└─────────────────────────────────────────────────────────┘
```

### For face matching with encrypted embeddings:
1. Retrieve encrypted embedding from DB
2. Decrypt DEK via KMS
3. Decrypt embedding with DEK
4. Compute cosine similarity in memory
5. Zero memory after comparison

---

## 7. RETENTION POLICY REQUIREMENTS

| Data Type | Recommended Retention | Justification |
|-----------|----------------------|---------------|
| Face embeddings (active visitors) | While consent valid | Operational need |
| Face embeddings (revoked consent) | Immediate deletion | Legal requirement |
| Face embeddings (inactive visitors) | Configurable (e.g., 2 years) | Proportionality |
| Visit records | Organization policy (e.g., 5 years) | Business/legal records |
| Conversation transcripts | Configurable (e.g., 90 days) | Quality improvement |
| Camera frames | Never persisted | Not needed |
| Profile images | Same as embedding | Linked to biometric |
| Audit logs | Minimum 7 years | Compliance |

---

## 8. RECOMMENDATIONS

### Must-Have Before Production
1. ❗ Encrypt all biometric templates with KMS envelope encryption
2. ❗ Implement liveness detection (min: texture analysis + temporal consistency)
3. ❗ Store complete consent records with version tracking
4. ❗ Display visible privacy notice on kiosk
5. ❗ Obtain legal/privacy team sign-off on consent text
6. ❗ Implement automated retention enforcement
7. ❗ Add DSAR self-service or workflow

### Should-Have
8. Separate biometric storage from visitor PII
9. Field-level encryption for sensitive non-biometric data
10. Regular penetration testing of biometric systems
11. Annual bias/fairness evaluation of face recognition
12. Incident response plan for biometric data breach

### Nice-to-Have
13. Hardware security module for key material
14. Federated/on-premise biometric processing (no cloud)
15. Formal ISO 27001 certification

---

## 9. SIGN-OFF REQUIRED

This assessment must be reviewed and approved by:
- [ ] Data Protection Officer (DPO)
- [ ] Chief Information Security Officer (CISO)
- [ ] Legal Counsel
- [ ] IT Security Lead
- [ ] HR Representative (for employee data handling)

**DO NOT DEPLOY TO PRODUCTION without these approvals.**
