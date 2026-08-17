# ARCHITECTURE — TARGET STATE (Enterprise Production)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CloudFront + WAF                                 │
│                    (HTTPS, CSP, HSTS, rate limiting)                          │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
┌──────────────────┐  ┌───────────────────┐  ┌──────────────────────┐
│ S3 + CloudFront  │  │ ALB (Private)     │  │ Cognito User Pool    │
│ (Static Frontend)│  │ (WebSocket+REST)  │  │ (Identity Provider)  │
│ - React Build    │  │ - Health checks   │  │ - MFA               │
│ - No dev server  │  │ - TLS termination │  │ - OIDC/SAML         │
│ - Gzipped        │  │                   │  │ - 8 roles            │
└──────────────────┘  └────────┬──────────┘  └──────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
┌────────────────────────┐  ┌──────────────────────────────────────┐
│ ECS Fargate (Backend)  │  │ ECS/EC2 (Vision Inference Worker)    │
│ - FastAPI              │  │ - GPU/CPU inference                  │
│ - Stateless            │  │ - YOLO + InsightFace + Liveness      │
│ - Auto-scaling         │  │ - Bounded worker pool                │
│ - Redis sessions       │  │ - Model versioning + checksums       │
│ - Auth enforcement     │  │ - Anti-spoofing                      │
│ - Bedrock Guardrails   │  │                                      │
│ - Structured logging   │  │                                      │
│ - OpenTelemetry        │  │                                      │
└───────────┬────────────┘  └──────────────────┬───────────────────┘
            │                                   │
    ┌───────┴───────────────────────────────────┴─────────────┐
    │                    Private Subnets (VPC)                  │
    │                                                          │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
    │  │ RDS MySQL    │  │ ElastiCache  │  │ S3 (Private) │  │
    │  │ Multi-AZ     │  │ Redis Cluster│  │ - Biometric  │  │
    │  │ Encrypted    │  │ - Sessions   │  │   templates  │  │
    │  │ Automated    │  │ - Rate limits│  │ - Encrypted  │  │
    │  │   backup     │  │ - Pub/Sub    │  │ - Lifecycle  │  │
    │  │ Migrations   │  │ - Idempotency│  │   policies   │  │
    │  └──────────────┘  └──────────────┘  └──────────────┘  │
    │                                                          │
    │  ┌──────────────────────────────────────────────────┐   │
    │  │              AWS Services (VPC Endpoints)          │   │
    │  │  KMS | Secrets Manager | Bedrock | Polly |        │   │
    │  │  Transcribe | CloudWatch | X-Ray | SQS | SNS     │   │
    │  └──────────────────────────────────────────────────┘   │
    └──────────────────────────────────────────────────────────┘
```

## Key Design Principles

| Principle | Implementation |
|-----------|---------------|
| Zero trust | Every request authenticated and authorized |
| Defense in depth | WAF → ALB → Auth → RBAC → Encryption |
| Least privilege | IAM roles scoped to minimum required permissions |
| Data minimization | Retain only what's needed, auto-delete on schedule |
| Encryption everywhere | TLS in transit, AES-256 + KMS at rest |
| Stateless compute | All state in Redis/RDS, compute scales horizontally |
| Observable | OpenTelemetry traces + CloudWatch metrics + structured logs |
| Resilient | Multi-AZ, auto-scaling, circuit breakers, graceful degradation |
| Auditable | Tamper-evident logs, consent records, change history |
| Accessible | WCAG 2.2 AA, keyboard navigation, screen reader support |

## Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| CloudFront + WAF | TLS termination, DDoS protection, geo-blocking, caching |
| ALB | WebSocket routing, health checks, request routing |
| Cognito | Authentication, MFA, token management, user lifecycle |
| ECS Fargate (API) | Business logic, conversation, notification orchestration |
| ECS/EC2 (Vision) | Face detection, embedding, liveness, matching |
| RDS MySQL | Structured data (visitors, employees, visits, appointments) |
| ElastiCache Redis | Sessions, rate limits, pub/sub, caching |
| S3 (Biometric) | Encrypted biometric templates, profile images |
| KMS | Key management for biometric encryption |
| Secrets Manager | Database passwords, API keys, JWT secrets |
| Bedrock | Conversation AI with guardrails |
| Polly | TTS with speech marks |
| Transcribe | Production STT (streaming) |
| CloudWatch + X-Ray | Observability, alerting, distributed tracing |
| SQS/SNS | Notification delivery queue |

## Data Flow: New Visitor

```
1. Camera frame → Vision Worker (liveness check)
2. Face embedding generated → encrypted with KMS
3. Search existing templates → no match
4. WebSocket sends "new_person" event to frontend
5. Avatar greets visitor
6. Visitor provides name via STT
7. Avatar asks for biometric consent
8. If YES: encrypted embedding stored in S3
9. If NO: visitor record created without biometric
10. Visit record created in RDS
11. Conversation continues via Bedrock
12. Host notified via SQS → Lambda → Teams/Email
```
