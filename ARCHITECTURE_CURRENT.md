# ARCHITECTURE — CURRENT STATE

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          BROWSER (React + Vite)                          │
│                                                                         │
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │ ReceptionistPage│  │DashboardPage │  │ No Login/Auth UI           │ │
│  │ - Avatar3D      │  │ - Stats      │  │ (ALL routes public)        │ │
│  │ - CameraFeed    │  │ - Visitors   │  │                            │ │
│  │ - ConversationP.│  │ - SysStatus  │  │                            │ │
│  │ - SpeechRecog.  │  │              │  │                            │ │
│  └─────────────────┘  └──────────────┘  └────────────────────────────┘ │
│         │ WebSocket (NO AUTH)    │ HTTP (NO AUTH)                        │
└─────────┼────────────────────────┼──────────────────────────────────────┘
          ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (Single Process)                      │
│                                                                         │
│  ┌─────────┐ ┌───────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────┐ │
│  │Auth(JWT)│ │Conversation│ │Visitor  │ │Employee │ │Dashboard     │ │
│  │(unused) │ │(WS+REST)  │ │(REST)   │ │(REST)   │ │(REST)        │ │
│  └─────────┘ └───────────┘ └─────────┘ └──────────┘ └──────────────┘ │
│       │            │              │           │             │           │
│  ┌────┴────────────┴──────────────┴───────────┴─────────────┴────────┐ │
│  │                    Service Layer (In-Process)                       │ │
│  │ ConversationManager | AIActions | DepartureDetector                │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│       │                    │                       │                     │
│  ┌────┴────┐    ┌─────────┴──────────┐    ┌──────┴───────────┐        │
│  │ Bedrock │    │   Vision Pipeline   │    │   Voice (Polly)  │        │
│  │ (boto3) │    │ YOLO→InsightFace→   │    │   TTS + Visemes  │        │
│  │ Llama 3 │    │ ArcFace→Matching    │    │   (boto3)        │        │
│  └─────────┘    └────────────────────┘    └──────────────────┘        │
│                          │                                              │
│  ┌───────────────────────┴──────────────────────────────────────────┐  │
│  │              SQLAlchemy Async (aiomysql)                           │  │
│  │              Repositories: Visitor, Employee, Visit,               │  │
│  │              Appointment, Conversation, Notification               │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
          │                              │
          ▼                              ▼
┌──────────────────┐          ┌────────────────────┐
│ MySQL 8.0        │          │ Redis 7            │
│ (PUBLICLY EXPOSED)│          │ (PUBLICLY EXPOSED) │
│ 9 tables         │          │ (NOT USED)         │
│ No migrations    │          │                    │
│ No encryption    │          │                    │
└──────────────────┘          └────────────────────┘
```

## Key Characteristics

| Aspect | Current Reality |
|--------|----------------|
| Authentication | JWT exists but not enforced on any endpoint |
| Session Storage | Python dict in ConversationManager (lost on restart) |
| Scalability | Single instance only (in-memory state) |
| Face Search | O(n) full scan in Python memory |
| TTS | Real AWS Polly (non-blocking) |
| STT | Browser Web Speech API only |
| AI | Real AWS Bedrock Llama 3 70B (non-blocking) |
| Vision | Real YOLO + InsightFace (non-blocking via executor) |
| Encryption | None (all data plaintext in MySQL) |
| Observability | structlog only (no metrics, no traces) |
| Testing | Zero automated tests |
| Deployment | Docker Compose with Vite dev server |
| Infrastructure | No IaC, no CI/CD |
