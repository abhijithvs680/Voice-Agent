"""FastAPI application: outbound call trigger, TwiML webhook and Media Stream WebSocket.

Endpoints
    GET  /            -> health check + config sanity
    POST /call        -> place an outbound call (optional JSON body: {"to": "+91..."})
    GET|POST /twiml   -> TwiML for inbound calls (points Twilio at our WebSocket)
    WS   /ws          -> Twilio Media Streams endpoint (audio in/out)
"""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.config import get_settings
from app.services.twilio_client import build_stream_twiml, place_outbound_call
from app.utils.logger import log_error, logger, setup_logging
from app.websocket import handle_twilio_websocket

load_dotenv(override=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    settings = get_settings()
    logger.info("Voice Agent starting up")
    logger.info(f"Gemini model: {settings.gemini_model} | voice: {settings.gemini_voice_id}")
    logger.info(f"Public URL: {settings.public_url or '(not set)'}")
    if not settings.resolved_gemini_key:
        logger.warning("GEMINI_API_KEY is not set - calls will fail until configured.")
    yield
    logger.info("Voice Agent shutting down")


app = FastAPI(title="Voice Agent", version="1.0.0", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index():
    """Simple status page."""
    settings = get_settings()
    ready = "yes" if settings.resolved_gemini_key and settings.twilio_account_sid else "no"
    return f"""
    <html><head><title>Voice Agent</title></head>
    <body style="font-family: system-ui; max-width: 640px; margin: 40px auto;">
      <h1>Voice Agent</h1>
      <p>Real-time bilingual (English / Malayalam) voice agent &mdash;
         Twilio + Gemini Live + Pipecat.</p>
      <ul>
        <li>Configured &amp; ready: <b>{ready}</b></li>
        <li>WebSocket: <code>{settings.websocket_url or '(set PUBLIC_URL)'}</code></li>
      </ul>
      <p>Trigger an outbound call with:
         <code>curl -X POST {settings.public_url or 'http://localhost:8888'}/call</code></p>
    </body></html>
    """


@app.post("/call")
async def call(request: Request):
    """Place an outbound call. Optional JSON body: {"to": "+91..."}."""
    settings = get_settings()
    try:
        settings.require_for_call()
    except ValueError as e:
        log_error("outbound call config", e)
        return JSONResponse(status_code=400, content={"error": str(e)})

    to_number = settings.call_to_number
    try:
        body = await request.json()
        if isinstance(body, dict) and body.get("to"):
            to_number = str(body["to"])
    except Exception:  # noqa: BLE001 - empty/invalid body is fine, fall back to env
        pass

    if not to_number:
        return JSONResponse(
            status_code=400,
            content={"error": "No destination number. Set CALL_TO_NUMBER or pass {'to': '+91...'}."},
        )

    try:
        call_sid = place_outbound_call(settings, to_number)
    except Exception as e:  # noqa: BLE001
        log_error("placing outbound call", e)
        return JSONResponse(status_code=500, content={"error": str(e)})

    return {"status": "calling", "to": to_number, "call_sid": call_sid}


@app.api_route("/twiml", methods=["GET", "POST"])
async def twiml():
    """Return Media Streams TwiML (useful for configuring an inbound number)."""
    settings = get_settings()
    return Response(content=build_stream_twiml(settings.websocket_url), media_type="application/xml")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Twilio Media Streams WebSocket endpoint."""
    await handle_twilio_websocket(websocket)


def main():
    """Run the server with uvicorn (used by `python -m app.main`)."""
    import uvicorn

    settings = get_settings()
    setup_logging()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
