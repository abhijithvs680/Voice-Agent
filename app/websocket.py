"""Twilio Media Streams WebSocket handling.

Twilio connects here (via the TwiML ``<Stream>``) and sends a short sequence of
JSON text messages. We read up to the ``start`` event to learn the ``streamSid``
and ``callSid``, then hand the socket to the Pipecat pipeline in ``app.bot``.
"""

import json

from fastapi import WebSocket

from app.bot import run_bot
from app.utils.logger import log_error, logger


async def handle_twilio_websocket(websocket: WebSocket) -> None:
    """Accept the Twilio WebSocket, read the start event, and run the bot."""
    await websocket.accept()
    logger.info("Twilio WebSocket connection accepted")

    stream_sid = None
    call_sid = None

    # Twilio sends a 'connected' event first, then a 'start' event that carries
    # the streamSid / callSid we need to build the serializer.
    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event")
            if event == "start":
                start = data.get("start", {})
                stream_sid = start.get("streamSid")
                call_sid = start.get("callSid")
                break
            elif event == "stop":
                logger.info("Received stop before start; closing.")
                return
    except Exception as e:  # noqa: BLE001
        log_error("reading Twilio start event", e)
        return

    if not stream_sid:
        logger.warning("No streamSid received from Twilio; aborting.")
        return

    logger.info(f"Media stream started | stream_sid={stream_sid} call_sid={call_sid}")

    try:
        await run_bot(websocket, stream_sid, call_sid)
    except Exception as e:  # noqa: BLE001
        log_error("running bot", e)
