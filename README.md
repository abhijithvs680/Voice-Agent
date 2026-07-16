# Voice Agent

A real-time, bilingual (**English + Malayalam**) voice agent built with **Twilio**,
**Google Gemini Live**, and **Pipecat**. Call in or trigger an outbound call, talk
naturally over the phone, and the agent answers questions from a local knowledge base
and calls tools (date/time, calculator, weather, appointment booking) when it makes sense.

---

## Architecture Overview

```
                 (1) POST /call
   You ──────────────────────────────►  FastAPI (app/main.py)
                                              │
                                              │ (2) Twilio REST: calls.create(twiml=<Connect><Stream>)
                                              ▼
                                          Twilio Voice ──────► dials CALL_TO_NUMBER (your phone)
                                              │
              (3) Twilio opens a bidirectional Media Stream (WebSocket, 8kHz mu-law)
                                              ▼
   Twilio  ◄────────────────  wss://<public-url>/ws  ────────────────►  FastAPI WebSocket
                                                                          (app/websocket.py)
                                              │
                                              ▼
                                   Pipecat pipeline (app/bot.py)
        transport.input → user_aggregator → Gemini Live LLM → transport.output → assistant_aggregator
                                              │        ▲
                                (audio S2S)   ▼        │ (tool calls / results)
                                      Google Gemini Live API
                                              │
                                              ▼
                          Tools (app/tools.py) + Knowledge base (app/knowledge.py)
```

**How it works**

1. You hit `POST /call`. The server asks Twilio to place an outbound call whose
   TwiML is `<Connect><Stream url="wss://.../ws"/>` — a **bidirectional** media stream.
2. When you answer, Twilio connects to our `/ws` WebSocket and streams your voice
   as 8 kHz mu-law audio.
3. `TwilioFrameSerializer` transcodes audio both ways. Pipecat feeds it into
   **Gemini Live** (speech-to-speech), which listens, thinks, calls tools when
   useful, and speaks back — all in real time.
4. **Silero VAD** detects when you start talking so the agent can be interrupted
   (**barge-in**). **Context aggregators** keep the full transcript so the agent
   remembers earlier parts of the call.

### Project structure

```
voice-agent/
├── app/
│   ├── __init__.py         # Package init
│   ├── main.py             # FastAPI app: /call, /twiml, /ws, health
│   ├── websocket.py        # Reads Twilio start event, launches the bot
│   ├── bot.py              # Pipecat pipeline (Twilio <-> Gemini Live)
│   ├── prompts.py          # Configurable bilingual system prompt
│   ├── config.py           # Typed settings loaded from .env
│   ├── tools.py            # Gemini function/tool calling
│   ├── knowledge.py        # Local knowledge base retrieval
│   ├── services/
│   │   ├── __init__.py     # Package init
│   │   └── twilio_client.py  # Outbound call + TwiML builder
│   └── utils/
│       ├── __init__.py     # Package init
│       └── logger.py       # Event logging (call started/ended/errors)
├── knowledge/
│   └── knowledge.json      # FAQ / business knowledge base
├── Dockerfile              # Container image (Python 3.12 + deps)
├── docker-compose.yml      # App + ngrok tunnel on port 8888
├── .dockerignore
├── requirements.txt
├── .env.example
├── README.md
└── AI_USAGE.md
```

---

## Stack

**Pipecat** handles the hard parts: Twilio Media Streams serialization, Gemini Live
speech-to-speech, VAD-based barge-in, conversation memory, and function calling. That
kept the app small while still giving low-latency, real-time voice on a phone call.

---

## Prerequisites

- **Docker** and **Docker Compose** — the supported way to run this project.
- An **ngrok authtoken** — free from [ngrok dashboard](https://dashboard.ngrok.com/get-started/your-authtoken), used by the bundled ngrok container to expose port 8888.
- A **Gemini API key** — free from [Google AI Studio](https://aistudio.google.com/apikey).
- A **Twilio trial account** with Account SID, Auth Token and a trial phone
  number (this project uses `+1 478 780 7306`). Verify the mobile number you want to call.

> Running without Docker (a local Python 3.11/3.12 virtualenv) is also possible;
> see [Running without Docker](#running-without-docker) below. You will still need a
> public HTTPS URL for Twilio (ngrok or a cloud deployment).

---

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/abhijithvs680/Voice-Agent.git
cd Voice-Agent

# 2. Configure environment
cp .env.example .env             # Windows: copy .env.example .env
# then edit .env and fill in your keys
```

Fill in `.env`:

```env
GEMINI_API_KEY=...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
CALL_TO_NUMBER=+91XXXXXXXXXX      # your verified phone, E.164 format
PUBLIC_URL=https://your-public-host   # public HTTPS URL Twilio can reach
PORT=8888
```

---

## Running (Docker Compose)

The app listens on **port 8888**. An **ngrok** service is included to expose it publicly
for Twilio.

Add your ngrok authtoken to `.env` (free at [ngrok dashboard](https://dashboard.ngrok.com/get-started/your-authtoken)):

```env
NGROK_AUTHTOKEN=your_ngrok_authtoken
```

```bash
# Build and start (app + ngrok)
docker compose up --build

# (or run detached)
docker compose up --build -d
```

**Set `PUBLIC_URL` from ngrok:**

1. Open [http://localhost:4040](http://localhost:4040) (ngrok inspect UI).
2. Copy the **HTTPS** forwarding URL (e.g. `https://abcd-12-34.ngrok-free.app`).
3. Put it in `.env` as `PUBLIC_URL=https://abcd-12-34.ngrok-free.app` (no trailing slash).
4. Restart the app container:

```bash
docker compose restart voice-agent
```

Twilio will then connect to `wss://<PUBLIC_URL>/ws` when a call starts.

**Call the agent:**

Call **+1 478 780 7306** from your phone to talk to the agent directly.

**Outbound call:**

```bash
curl -X POST http://localhost:8888/call
# or call a specific number:
curl -X POST http://localhost:8888/call -H "Content-Type: application/json" -d "{\"to\": \"+9198XXXXXXXX\"}"
```

Your phone rings. Answer it and start talking — in English or Malayalam.

**Stop / view logs:**

```bash
docker compose logs -f     # follow logs
docker compose down        # stop and remove the container
```

---

## Running without Docker

```bash
git clone https://github.com/abhijithvs680/Voice-Agent.git
cd Voice-Agent

python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # then edit .env
python -m app.main               # serves on port 8888
# or: uvicorn app.main:app --host 0.0.0.0 --port 8888
```

---

## Example conversations

Things to try once you're on a call with Maya (the clinic receptionist):

| Topic | Say something like |
|---|---|
| English | "Hi, what services do you offer?" |
| Malayalam | "നിങ്ങളുടെ ക്ലിനിക് എത്ര മണിക്കാണ് തുറക്കുന്നത്?" |
| Clinic FAQs | "How much is a cleaning?" / "Where are you located?" |
| Date & time | "What's today's date and time?" |
| Calculator | "If a cleaning is 1500 rupees for two people, what's the total?" |
| Weather | "What's the weather in Kochi?" |
| Appointment | "Book me a cleaning tomorrow at 5 PM. My name is Abhijith." |
| Memory | Give your name early, then later ask "What's my name again?" |
| Barge-in | Talk over the agent mid-sentence — it should stop and listen |

---

## Configuration reference

All configuration lives in `.env` (see `.env.example`). Key options:

- `GEMINI_MODEL` — defaults to `models/gemini-3.1-flash-live-preview`
  (Gemini 3.1 Flash Live; low-latency voice agents with tool calling and Malayalam).
- `GEMINI_VOICE_ID` — Gemini Live voice (`Puck`, `Charon`, `Aoede`, `Kore`, ...).
- `PRIMARY_LANGUAGE` — initial language hint (`EN_US`, `ML`, ...). The agent
  understands and replies in both English and Malayalam regardless.
- `SYSTEM_PROMPT` — optional full override of the prompt in `app/prompts.py`.

---

## Logging

Lifecycle events are logged to stderr via loguru:

- `CALL STARTED | call_sid=... stream_sid=... to=...`
- `TOOL <name> -> ...` for every tool invocation
- `CALL ENDED | call_sid=... reason=...`
- `ERROR | <context>: ...`

---

## Troubleshooting

- **Call connects but there's silence** — `PUBLIC_URL` must match the current ngrok
  HTTPS URL from [http://localhost:4040](http://localhost:4040). Update `.env` and run
  `docker compose restart voice-agent`. No trailing slash; WebSocket must reach `/ws`.
- **`auto_hang_up ... missing required parameters`** — Twilio credentials are
  missing/incorrect in `.env`.
- **Twilio can't call the number** — on a trial account you can only call
  **verified** numbers, in E.164 format (`+91...`).
- **Port already in use** — something else is on `8888`; stop it or change `PORT`
  in `.env` and the published port in `docker-compose.yml`.
- **Local (non-Docker) install fails / native build errors** — you're likely on
  Python 3.13/3.14. Use Python 3.11 or 3.12 (the Docker image already uses 3.12).

---

## Notes

Appointments are stored in memory and weather is mocked — fine for a prototype, not
production. No auth on the HTTP endpoints. Build history and AI workflow are in
`AI_USAGE.md`.
