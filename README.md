# SecondRing

## Overview

SecondRing helps local service businesses recover revenue from missed incoming phone calls. When a customer calls and gets no answer, the service captures the incident, triggers an automated outbound voice agent to call the customer back, and books appointment slots directly from the resulting conversation. Phone numbers stay encrypted at rest and masked in responses, ensuring customer privacy throughout the recovery lifecycle.

## Features

- **Automated Outbound Recovery**: Automatically schedules and triggers outbound voice calls via BimpeAI when customer calls go unanswered.
- **Transcript Parsing and Booking**: Extracts scheduled slots directly from conversation transcripts and persists confirmed bookings.
- **Field-Level Data Encryption**: Encrypts phone numbers at rest with Fernet symmetric encryption and generates HMAC-SHA256 hashes for fast lookup without exposing plaintext.
- **Data Masking**: Returns phone numbers in masked format across API responses to protect sensitive customer information.
- **Race Condition Prevention**: Employs atomic state transitions to ensure multiple workers cannot initiate redundant callbacks for the same customer.
- **Lifecycle Tracking**: Keeps external voice agent states synchronized independently of appointment extraction logic.

## Technologies Used

| Technology | Purpose | Link |
| --- | --- | --- |
| FastAPI | Web framework and API routing | [fastapi.tiangolo.com](https://fastapi.tiangolo.com/) |
| SQLAlchemy | SQL toolkit and Object Relational Mapper | [sqlalchemy.org](https://www.sqlalchemy.org/) |
| PostgreSQL / Psycopg | Relational database and database driver | [psycopg.org](https://www.psycopg.org/) |
| Pydantic | Data validation and parsing | [docs.pydantic.dev](https://docs.pydantic.dev/) |
| Cryptography | Fernet symmetric phone number encryption | [cryptography.io](https://cryptography.io/) |
| BimpeAI SDK | Outbound voice agent integration | [bimpeai.com](https://bimpeai.com/) |
| Uvicorn | ASGI web server implementation | [uvicorn.org](https://www.uvicorn.org/) |

## Installation

### Prerequisites

- Python 3.10 or higher
- A running PostgreSQL instance
- BimpeAI API credentials

### Setup Steps

1. Clone the repository:
```bash
git clone https://github.com/Ace-g-ops/second_ring
cd second_ring
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
```

On Linux or macOS:
```bash
source venv/bin/activate
```

On Windows (Command Prompt / PowerShell):
```powershell
.\venv\Scripts\activate
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
Create a `.env` file in the root directory and define the following variables:
```env
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/secondring
PHONE_ENCRYPTION_KEY=your_generated_fernet_key
PHONE_HASH_SECRET=your_phone_hash_secret_string
BIMPEAI_API_KEY=your_bimpeai_api_key
BIMPE_AGENT_ID=your_bimpe_agent_id
```

Generate a valid Fernet key in Python if needed:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

5. Set operating system environment variables (optional alternative to `.env`):

On Windows (PowerShell):
```powershell
setx DATABASE_URL "postgresql+psycopg://username:password@localhost:5432/secondring"
```

On macOS / Linux (including Termux):
```bash
echo 'export DATABASE_URL="postgresql+psycopg://username:password@localhost:5432/secondring"' >> ~/.bashrc
source ~/.bashrc
```

## Usage

Start the development server using Uvicorn:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Once the server is running, you can access the automatic interactive API documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

To test the end-to-end recovery pipeline locally:

1. Create a dummy missed call record:
```bash
curl -X POST http://localhost:8000/api/missed_calls/test
```

2. Trigger the callback voice agent for the pending record:
```bash
curl -X POST http://localhost:8000/api/callback/test
```

3. Query the outcome and parse the conversation logs:
```bash
curl -X GET http://localhost:8000/api/callback/MC-1700000000/result
```

## API Documentation

All endpoints return JSON responses. Sensitive fields like customer phone numbers are masked in all outward payloads.

### Environment Variables

| Variable | Description | Example |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg://postgres:secret@localhost:5432/secondring` |
| `PHONE_ENCRYPTION_KEY` | 32 url-safe base64-encoded bytes used by Fernet | `gAAAAABlZ6qY...` |
| `PHONE_HASH_SECRET` | Secret key used for HMAC-SHA256 phone hashing | `super-secret-hash-key` |
| `BIMPEAI_API_KEY` | API token for BimpeAI voice agent calls | `bmp_live_xxxxxxxx` |
| `BIMPE_AGENT_ID` | Voice agent identifier assigned by BimpeAI | `agt_123456789` |

---

#### GET /

**Description**: Root check confirming whether the API service is active.

**Request**:
```bash
curl -X GET http://localhost:8000/
```

**Response**:
```json
{
  "message": "Secondring is live"
}
```

**Errors**:
- None

---

#### GET /health

**Description**: Liveness and readiness endpoint for monitoring agents.

**Request**:
```bash
curl -X GET http://localhost:8000/health
```

**Response**:
```json
{
  "status": "ok"
}
```

**Errors**:
- None

---

#### GET /api/missed_calls

**Description**: Retrieves a descending list of all registered missed calls with masked customer phone numbers.

**Request**:
```bash
curl -X GET http://localhost:8000/api/missed_calls
```

**Response**:
```json
[
  {
    "id": "MC-1711200300",
    "business_id": "sharp-cuts",
    "customer_name": "Nuel",
    "customer_phone_masked": "+234****119",
    "missed_at": "2025-03-30T10:15:00Z",
    "status": "pending_callback",
    "bimpe_call_id": null
  }
]
```

**Errors**:
- 500: Database connection error.

---

#### POST /api/missed_calls/test

**Description**: Seeds a test missed call into the database for testing callback pipelines.

**Request**:
```bash
curl -X POST http://localhost:8000/api/missed_calls/test
```

**Response**:
```json
{
  "message": "Test missed call created.",
  "missed_call": {
    "id": "MC-1711200300",
    "customer_name": "Nuel",
    "customer_phone_masked": "+234****119",
    "status": "pending_callback"
  }
}
```

**Errors**:
- 500: Database insertion error.

---

#### POST /api/callback/test

**Description**: Selects the oldest pending missed call record and initiates an outbound callback via BimpeAI.

**Request**:
```bash
curl -X POST http://localhost:8000/api/callback/test
```

**Response**:
```json
{
  "message": "Test callback initiated.",
  "missed_call_id": "MC-1711200300",
  "bimpe_call_id": "call_abc12345"
}
```

**Errors**:
- 404: No pending missed calls found.
- 409: Callback is no longer available to start.
- 502: BimpeAI provider failed to initiate call.

---

#### POST /api/callback/{missed_call_id}/trigger

**Description**: Initiates an outbound callback voice agent for a specific missed call record.

**Request**:
```bash
curl -X POST http://localhost:8000/api/callback/MC-1711200300/trigger
```

**Response**:
```json
{
  "message": "Callback initiated.",
  "missed_call_id": "MC-1711200300",
  "bimpe_call_id": "call_abc12345"
}
```

**Errors**:
- 400: Callback is already in progress or completed.
- 404: Missed call record not found.
- 409: Callback is no longer available to start.
- 502: BimpeAI provider failed to initiate call.

---

#### GET /api/callback/{missed_call_id}/result

**Description**: Fetches call status and conversation logs from BimpeAI, syncs status, parses transcript for appointments, and saves confirmed bookings.

**Request**:
```bash
curl -X GET http://localhost:8000/api/callback/MC-1711200300/result
```

**Response**:
```json
{
  "missed_call": {
    "id": "MC-1711200300",
    "business_id": "sharp-cuts",
    "customer_name": "Nuel",
    "customer_phone_masked": "+234****119",
    "missed_at": "2025-03-30T10:15:00Z",
    "status": "callback_completed",
    "bimpe_call_id": "call_abc12345"
  },
  "call_status": "completed",
  "answered_at": "2025-03-30T10:16:05Z",
  "error_reason": null,
  "started_at": "2025-03-30T10:16:00Z",
  "ended_at": "2025-03-30T10:17:30Z",
  "transcript": [
    {
      "role": "assistant",
      "message": "Hello, this is Sharp Cuts following up on your call.",
      "created_at": "2025-03-30T10:16:06Z"
    },
    {
      "role": "user",
      "message": "Yes, I would like to book for Saturday at 4:00 PM.",
      "created_at": "2025-03-30T10:16:15Z"
    },
    {
      "role": "assistant",
      "message": "Your appointment is confirmed for Saturday at 4:00 PM.",
      "created_at": "2025-03-30T10:16:20Z"
    }
  ],
  "booking": {
    "id": "BK-MC-1711200300",
    "missed_call_id": "MC-1711200300",
    "customer_name": "Nuel",
    "customer_phone_masked": "+234****119",
    "service": "Haircut",
    "slot": "Saturday 4:00 PM",
    "status": "confirmed",
    "created_at": "2025-03-30T10:17:35Z"
  }
}
```

**Errors**:
- 400: Missed call does not have an associated BimpeAI call ID.
- 404: Missed call not found.
- 409: A newer callback has started for this missed call.

---

#### GET /api/bookings

**Description**: Retrieves a descending list of all saved appointments and recovery outcomes.

**Request**:
```bash
curl -X GET http://localhost:8000/api/bookings
```

**Response**:
```json
[
  {
    "id": "BK-MC-1711200300",
    "missed_call_id": "MC-1711200300",
    "customer_name": "Nuel",
    "customer_phone_masked": "+234****119",
    "service": "Haircut",
    "slot": "Saturday 4:00 PM",
    "status": "confirmed",
    "created_at": "2025-03-30T10:17:35Z"
  }
]
```

**Errors**:
- 500: Database retrieval error.

## Contributing

Contributions are welcome. If you find a bug or want to enhance recovery rules, open an issue or submit a pull request:

1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/recovery-improvement`).
3. Commit your changes (`git commit -m 'Add recovery improvement'`).
4. Push to the branch (`git push origin feature/recovery-improvement`).
5. Open a pull request.

## Author Info

- GitHub: [Ace-g-ops](https://github.com/Ace-g-ops)

## Badges

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)