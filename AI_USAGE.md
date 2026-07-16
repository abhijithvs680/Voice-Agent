# AI Usage

I used AI as a coding assistant while building this, but the design decisions,
architecture, and debugging direction were mine. This note explains how.

## Tools

- **Cursor** with **Claude Opus** for most of the implementation — I described what
  I wanted, reviewed the output, and corrected it where it was wrong or didn't match
  how I wanted the code structured.
- Pipecat, Gemini Live, and Twilio docs for the actual API details. Pipecat's API
  changes often, so I checked the real source instead of trusting generated code.

## How I worked with it

I already knew the shape I wanted: a FastAPI service that places/receives Twilio
calls, bridges the audio to Gemini Live over a WebSocket, and runs a Pipecat pipeline
for the conversation. So I drove the work module by module and used the assistant to
fill in the mechanical parts.

A few things I specifically directed rather than accepted as-is:

- **Framework choice and version.** I picked Pipecat because it already solves the
  Twilio↔Gemini audio bridge, VAD-based barge-in, and context memory. The generated
  code targeted a newer Pipecat API that had renamed classes, so I pinned
  `pipecat-ai==0.0.99` and had it rewritten against that version.
- **Project layout.** I wanted config, transport, pipeline, tools, and knowledge base
  each in their own module (`app/config.py`, `app/websocket.py`, `app/bot.py`,
  `app/tools.py`, `app/knowledge.py`) instead of one big file.
- **The domain.** I chose a dental clinic receptionist ("Sunrise Dental Clinic",
  Kochi) so the knowledge base and appointment tool have a real reason to exist, and
  wrote the FAQs and system prompt around that.
- **Bilingual behaviour.** Instead of hard-coding a language, I had the system prompt
  detect and mirror the caller's language, leaning on Gemini Live's native
  English/Malayalam support.
- **Safety.** The calculator tool uses an AST evaluator, not `eval`.

## What I changed by hand

- Swapped the Gemini model to `gemini-3.1-flash-live-preview` after an older model ID
  failed at runtime.
- Tuned the system prompt for short, natural, voice-friendly replies and
  knowledge-base-first answering.
- Reworked config so it accepts `GEMINI_API_KEY` or `GOOGLE_API_KEY` and derives the
  `wss://` URL from `PUBLIC_URL`.
- Set up Docker Compose with an ngrok sidecar for local runs, and documented calling
  the Twilio number directly as the primary demo path.

## Problems I hit

- **Pipecat API drift** — generated code used class names from a newer release.
  Fixed by reading the `v0.0.99` source and pinning it.
- **Silent call at start** — Gemini Live only responds when prompted, so I seed the
  context and queue an `LLMRunFrame` on connect to make the agent greet first.
- **Wrong Gemini model** — an outdated Live model ID returned a WebSocket `1008`
  error; switched to the current one.
- **Local Python 3.14** had no Pipecat wheels, so the Docker image runs Python 3.12.
- **Reaching localhost from Twilio** — solved locally with the bundled ngrok tunnel;
  on a VPS you just point `PUBLIC_URL` at the public HTTPS URL.
