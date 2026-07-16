"""Twilio helpers: placing the outbound call and building the Media Streams TwiML."""

from twilio.rest import Client
from twilio.twiml.voice_response import Connect, VoiceResponse

from app.config import Settings
from app.utils.logger import logger


def build_stream_twiml(websocket_url: str) -> str:
    """Return TwiML that connects the call's audio to our WebSocket.

    ``<Connect><Stream>`` opens a bidirectional Media Stream, which is what lets
    the agent both hear the caller and speak back over the same call.
    """
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=websocket_url)
    response.append(connect)
    return str(response)


def place_outbound_call(settings: Settings, to_number: str) -> str:
    """Place an outbound call that streams audio to our WebSocket.

    Args:
        settings: Application settings (Twilio credentials + public URL).
        to_number: Destination phone number in E.164 format (e.g. +9198...).

    Returns:
        The created Twilio Call SID.
    """
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    twiml = build_stream_twiml(settings.websocket_url)

    logger.info(f"Placing outbound call to {to_number} (stream -> {settings.websocket_url})")
    call = client.calls.create(
        to=to_number,
        from_=settings.twilio_phone_number,
        twiml=twiml,
    )
    logger.info(f"CALL CREATED | call_sid={call.sid} to={to_number}")
    return call.sid
