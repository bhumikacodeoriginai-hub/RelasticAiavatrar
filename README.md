# AI Avatar Receptionist — Code Origin.AI

An intelligent AI-powered office receptionist that detects visitors via camera, recognizes returning visitors by face, conducts real-time voice conversations using AWS Bedrock (Llama 3 70B), speaks using Amazon Polly with a 3D animated avatar, and provides a management dashboard.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React + Vite)                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ Avatar3D │  │  Camera  │  │Conversation│  │  Dashboard   │  │
│  │(Three.js)│  │  Feed    │  │   Panel    │  │              │  │
│  └──────────┘  └──────────┘  └───────────┘  └──────────────┘  │
│         ↕ WebSocket                    ↕ REST + WebSocket       │
└─────────────────────────────────────────────────────────────────┘
                              ↕
┌─────────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI + Python)                   │
│  ┌─────────────┐  ┌───────────┐  ┌──────────┐  ┌───────────┐  │
│  │   Vision    │  │    AI     │  │   Voice  │  │    API     │  │
│  │  Pipeline   │  │  Engine   │  │  Engine  │  │  Routes    │  │
│  ├─────────────┤  ├───────────┤  ├──────────┤  ├───────────┤  │
│  │ YOLO Person │  │ Bedrock   │  │ Polly    │  │ Visitor    │  │
│  │ InsightFace │  │ Llama 3   │  │ TTS      │  │ Employee   │  │
│  │ ArcFace 512D│  │ Prompts   │  │ Visemes  │  │ Auth       │  │
│  │ FaceMatcher │  │ Actions   │  │ VAD      │  │ Dashboard  │  │
│  └─────────────┘  └───────────┘  └──────────┘  └───────────┘  │
│                              ↕                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              DATABASE (MySQL) + REPOSITORIES                 ││
│  │  visitors | employees | visits | appointments | conversations││
│  │  notifications | audit_logs | conversation_messages          ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## Features (Actually Implemented)

### ✅ Face Recognition Pipeline
- YOLO v8 person-only detection (class 0, filters chairs/bags/laptops)
- InsightFace face detection with quality estimation (blur, angle, size)
- ArcFace 512-dimensional face embeddings (normalized)
- Cosine similarity matching against MySQL stored embeddings
- Configurable thresholds (similarity, min face size, cooldown)
- Recognition cooldown to prevent rapid re-identification
- Shared model instance (FaceDetector + FaceEmbedder use same InsightFace)
- All CV operations non-blocking (asyncio.to_thread)

### ✅ Visitor Flow
- **New visitor**: Camera → Person → Face → Unknown → Greeting → Name capture → Explicit consent → Registration
- **Returning visitor**: Camera → Person → Face → Match → Greeting by name → Visit record
- **Consent handling**: Never stores face embedding without explicit consent. Consent can be granted/denied via speech or UI buttons.
- **GDPR compliance**: Consent revocation deletes biometric data

### ✅ Conversation Engine
- AWS Bedrock Llama 3 70B Instruct (non-blocking)
- Structured state machine (13 states, backend-controlled)
- Structured context injection (visitor info, session state)
- Employee lookup and notification
- Intent detection (meeting requests, farewell)
- Name extraction from natural speech

### ✅ Voice
- **STT**: Browser Web Speech API (production), AWS Transcribe Streaming (future)
- **TTS**: Amazon Polly (Kajal, neural, en-IN) with speech marks
- **VAD**: WebRTC VAD with configurable aggressiveness/timeouts
- **Barge-in**: Visitor can interrupt avatar; audio stops immediately

### ✅ 3D Avatar
- React Three Fiber procedural 3D head
- Polly viseme-based lip sync (maps all 17 Polly visemes)
- Idle animation (breathing, subtle head movement)
- Natural blinking (random 2-5s intervals)
- Eye movement (subtle look-around)
- Speaking/listening/thinking visual states
- Smooth interpolation between mouth shapes

### ✅ Dashboard & Management
- Real-time stats (visitors today, active, new/returning)
- System health (DB, Bedrock, TTS, Vision, Camera, WebSocket)
- Recent visitors feed with live WebSocket updates
- Visit lifecycle (check-in, departure detection, history)

### ✅ Security
- JWT authentication with roles (ADMIN, RECEPTIONIST, VIEWER)
- Configurable secret key, no hardcoded credentials in code
- CORS restrictions
- Global exception handler (no stack traces in production)
- Biometric consent enforcement

### ✅ Infrastructure
- Docker Compose (MySQL, Redis, Backend, Frontend)
- Non-root Docker user
- Health checks
- Configurable via .env (all URLs, thresholds, timeouts)
- Structured logging (structlog, JSON in production)

## State Machine

```
IDLE → PERSON_DETECTED → IDENTIFYING
  ↓
GREETING_NEW → WAITING_FOR_NAME → ASKING_CONSENT
  ↓                                    ↓
  ↓                            REGISTERING_VISITOR
  ↓                                    ↓
  ↓←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←↓
  ↓
GREETING_RETURNING → ACTIVE_CONVERSATION
                          ↓         ↓
              WAITING_FOR_EMPLOYEE   ENDING → ENDED
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- AWS account with Bedrock and Polly access
- Webcam (optional for development)

### 1. Clone & Configure

```bash
git clone <repo-url>
cd RelasticAiavatrar
cp .env.example .env
# Edit .env with your AWS credentials and settings
```

### 2. Start with Docker

```bash
docker compose up -d
```

Services:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **MySQL**: localhost:3306

### 3. Development (without Docker)

```bash
# Backend
cd backend
pip install -r requirements.txt
python main.py

# Frontend
cd frontend
npm install
npm run dev
```

### 4. Initialize Database

The MySQL init script runs automatically with Docker. For manual setup:

```sql
mysql -u root -p < backend/database/init.sql
```

## Environment Variables

See `.env.example` for the complete list. Key variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_REGION` | AWS region | `ap-south-1` |
| `BEDROCK_MODEL_ID` | Llama model ID | `meta.llama3-70b-instruct-v1:0` |
| `POLLY_VOICE_ID` | Polly voice | `Kajal` |
| `POLLY_ENGINE` | Polly engine | `neural` |
| `DATABASE_HOST` | MySQL host | `localhost` |
| `DATABASE_PORT` | MySQL port | `3306` |
| `FACE_SIMILARITY_THRESHOLD` | Match confidence | `0.60` |
| `RECOGNITION_COOLDOWN_SECONDS` | Re-ID cooldown | `7.0` |
| `SESSION_TIMEOUT_SECONDS` | Inactivity timeout | `300` |
| `DEPARTURE_TIMEOUT_SECONDS` | No-person timeout | `30` |

## API Endpoints

### Authentication
- `POST /api/auth/login` — Get JWT token
- `GET /api/auth/me` — Current user info

### Visitors
- `POST /api/visitors/register` — Register visitor
- `GET /api/visitors/` — List visitors (paginated)
- `GET /api/visitors/{id}` — Get visitor
- `PUT /api/visitors/{id}/consent` — Update consent
- `DELETE /api/visitors/{id}` — Delete visitor (GDPR)

### Employees
- `GET /api/employees/` — List employees
- `GET /api/employees/search/{name}` — Search by name
- `POST /api/employees/` — Create employee
- `PUT /api/employees/{id}/availability` — Update availability

### Conversations
- `POST /api/conversation/start` — Start conversation
- `POST /api/conversation/message` — Send message
- `POST /api/conversation/end/{id}` — End conversation
- `GET /api/conversation/active` — Active count

### Visits
- `GET /api/visits/active` — Active visits
- `POST /api/visits/{id}/depart` — Mark departure
- `GET /api/visits/stats/today` — Today's stats

### Dashboard
- `GET /api/dashboard/stats` — Dashboard statistics
- `GET /api/dashboard/recent-visitors` — Recent visitors
- `GET /api/dashboard/system-status` — System health

### WebSocket
- `ws://host/ws/conversation/{client_id}` — Real-time conversation
- `ws://host/ws/dashboard` — Dashboard live updates

## WebSocket Protocol

### Client → Server
```json
{"type": "speech", "text": "...", "is_final": true}
{"type": "frame", "data": "<base64 JPEG>"}
{"type": "start_session", "match_status": "no_match"}
{"type": "end_session"}
{"type": "consent", "value": true}
{"type": "ping"}
```

### Server → Client
```json
{"type": "response", "text": "...", "audio": "<base64>", "speech_marks": [...], "state": "...", "session_id": "..."}
{"type": "detection", "person_detected": true, "face_detected": true}
{"type": "recognition", "status": "match_found", "visitor_name": "Rahul", "confidence": 0.87}
{"type": "registration", "status": "success", "visitor_id": "..."}
{"type": "state", "state": "active_conversation", "session_id": "..."}
{"type": "error", "code": "...", "message": "..."}
```

## Database Schema

```
visitors          - Registered visitors with face embeddings (JSON)
employees         - Internal staff directory
visits            - Visit check-in/check-out records
appointments      - Scheduled meetings
conversations     - Conversation session records
conversation_messages - Individual messages
notifications     - Employee notifications
audit_logs        - Security audit trail
```

## Known Limitations

1. **Face embeddings in MySQL JSON**: No native vector index. Similarity search is O(n) over all consented visitors. Suitable for offices up to ~10,000 visitors. For larger scale, consider adding a vector search service.
2. **In-memory sessions**: Active conversation sessions are in memory. Server restart loses active sessions (but completed conversations are persisted to DB).
3. **Single worker**: Vision pipeline models (YOLO, InsightFace) are loaded once. Multi-worker deployment requires shared model serving.
4. **Browser STT**: Speech recognition depends on Chrome/Edge Web Speech API. Not supported in Firefox/Safari for continuous mode.
5. **3D Avatar**: Procedural geometry (no custom GLB model loaded yet). Can be upgraded to use a custom GLB with morph targets for better visuals.
6. **Default passwords**: Auth system has default passwords that MUST be changed for production.

## AWS Requirements

- **Bedrock**: Access to Meta Llama 3 70B Instruct model in your region
- **Polly**: Standard access (Kajal voice, neural engine)
- **IAM**: Credentials with bedrock:InvokeModel, polly:SynthesizeSpeech permissions

## Hardware Requirements

- **CPU**: 4+ cores recommended (YOLO + InsightFace inference)
- **RAM**: 8GB minimum (models load ~3GB)
- **GPU**: Optional (CPU inference works, GPU accelerates detection)
- **Camera**: USB webcam or IP camera (optional for demo mode)
- **Network**: Internet access for AWS services

## License

Proprietary — Code Origin.AI
