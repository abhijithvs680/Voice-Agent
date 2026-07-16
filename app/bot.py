"""The Pipecat voice-agent pipeline.

Wires Twilio Media Streams (over a FastAPI WebSocket) to Google's Gemini Live
API, giving a real-time, bidirectional, interruptible (barge-in) voice
conversation with tool calling, a knowledge base and conversation memory.

Audio path:
    Twilio (8kHz mu-law)  <->  TwilioFrameSerializer (resamples)  <->  Pipecat
    pipeline  <->  Gemini Live (speech-to-speech).

Pipeline order (context aggregators wrap the LLM so the running transcript /
memory is maintained across the whole call):

    transport.input -> user_aggregator -> llm -> transport.output -> assistant_aggregator
"""

from fastapi import WebSocket

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService, InputParams
from pipecat.transcriptions.language import Language
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from app.config import get_settings
from app.prompts import INITIAL_GREETING_INSTRUCTION, get_system_prompt
from app.tools import build_tools_schema, register_tools
from app.utils.logger import (
    log_call_ended,
    log_call_started,
    log_error,
    logger,
)


def _resolve_language(name: str) -> Language:
    """Map a PRIMARY_LANGUAGE env string (e.g. 'EN_US', 'ML') to a Language enum."""
    try:
        return Language[name.strip().upper()]
    except (KeyError, AttributeError):
        logger.warning(f"Unknown PRIMARY_LANGUAGE '{name}', falling back to EN_US")
        return Language.EN_US


async def run_bot(websocket: WebSocket, stream_sid: str, call_sid: str) -> None:
    """Build and run the Pipecat pipeline for a single Twilio call."""
    settings = get_settings()

    # --- Twilio <-> Pipecat serializer (handles mu-law <-> PCM + auto hang-up) ---
    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
    )

    # --- WebSocket transport (VAD enables interruption / barge-in detection) ---
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            # stop_secs kept short and close to Gemini Live's internal endpointing
            # so turn-taking and barge-in feel responsive.
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5)),
            serializer=serializer,
        ),
    )

    # --- Gemini Live speech-to-speech LLM ---
    llm = GeminiLiveLLMService(
        api_key=settings.resolved_gemini_key,
        model=settings.gemini_model,
        voice_id=settings.gemini_voice_id,
        system_instruction=get_system_prompt(settings.system_prompt),
        tools=build_tools_schema(),
        params=InputParams(
            temperature=0.7,
            language=_resolve_language(settings.primary_language),
        ),
    )
    register_tools(llm)

    # --- Conversation context / memory ---
    # A single kickoff turn makes the agent greet first; the aggregators then
    # accumulate the full dialogue (user + assistant) for the whole call.
    context = LLMContext(
        [{"role": "user", "content": INITIAL_GREETING_INSTRUCTION}]
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            llm,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        log_call_started(call_sid=call_sid, stream_sid=stream_sid, to_number=settings.call_to_number)
        # Kick off the conversation so the agent speaks first.
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client):
        log_call_ended(call_sid=call_sid)
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)

    try:
        await runner.run(task)
    except Exception as e:  # noqa: BLE001 - log any pipeline-level failure
        log_error("pipeline run", e)
        raise
