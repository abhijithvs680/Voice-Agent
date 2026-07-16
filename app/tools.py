"""Gemini function / tool calling.

Defines the tool schemas advertised to Gemini Live and their Python handlers.
Handlers follow Pipecat's convention: they are async, receive a
``FunctionCallParams`` (with ``.arguments`` and ``.result_callback``) and return
their result by awaiting ``params.result_callback(...)``.

Tools implemented:
    * get_current_datetime  - current date/day/time (IST)
    * calculate             - safe arithmetic evaluation
    * get_weather           - (mock) current weather for a location
    * book_appointment      - schedule a clinic visit (in-memory)
    * search_knowledge_base - answer questions from knowledge/knowledge.json
"""

import ast
import operator
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams

from app import knowledge
from app.utils.logger import logger

# India Standard Time (UTC+5:30). Kept explicit so the demo is timezone-correct
# regardless of where the server runs.
IST = timezone(timedelta(hours=5, minutes=30))

# In-memory store of appointments booked during the process lifetime. A real
# system would persist these; for a prototype this is enough to prove the flow.
APPOINTMENTS: List[Dict[str, Any]] = []


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #
async def get_current_datetime(params: FunctionCallParams) -> None:
    """Return the current date, weekday and time in IST."""
    now = datetime.now(IST)
    result = {
        "date": now.strftime("%Y-%m-%d"),
        "day_of_week": now.strftime("%A"),
        "time_24h": now.strftime("%H:%M"),
        "time_spoken": now.strftime("%I:%M %p").lstrip("0"),
        "timezone": "India Standard Time (IST)",
    }
    logger.info(f"TOOL get_current_datetime -> {result['date']} {result['time_24h']}")
    await params.result_callback(result)


# Only these operators are permitted inside `calculate`.
_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    """Recursively evaluate a parsed arithmetic expression, safely."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Only numeric constants are allowed.")
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPERATORS:
        return _ALLOWED_OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Unsupported expression.")


async def calculate(params: FunctionCallParams) -> None:
    """Safely evaluate a basic arithmetic expression (no code execution)."""
    expression = str(params.arguments.get("expression", "")).strip()
    try:
        tree = ast.parse(expression, mode="eval")
        value = _safe_eval(tree.body)
        # Present whole numbers without a trailing .0
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        result = {"expression": expression, "result": value}
        logger.info(f"TOOL calculate -> {expression} = {value}")
    except Exception as e:  # noqa: BLE001 - report any parse/eval failure to the model
        result = {"expression": expression, "error": f"Could not evaluate: {e}"}
        logger.warning(f"TOOL calculate failed for '{expression}': {e}")
    await params.result_callback(result)


async def get_weather(params: FunctionCallParams) -> None:
    """Return (mock) current weather for a location.

    This is a stub so the prototype has no external dependency; swap the body
    for a real weather API call to make it live.
    """
    location = str(params.arguments.get("location", "Kochi")).strip() or "Kochi"
    result = {
        "location": location,
        "conditions": "partly cloudy",
        "temperature_c": 31,
        "humidity_percent": 78,
        "note": "This is mock weather data for the prototype.",
    }
    logger.info(f"TOOL get_weather -> {location}")
    await params.result_callback(result)


async def book_appointment(params: FunctionCallParams) -> None:
    """Record an appointment request and return a confirmation reference."""
    name = str(params.arguments.get("name", "")).strip()
    service = str(params.arguments.get("service", "")).strip()
    preferred_time = str(params.arguments.get("preferred_time", "")).strip()

    if not name or not preferred_time:
        await params.result_callback(
            {
                "status": "needs_info",
                "message": "I still need the caller's name and a preferred day/time.",
            }
        )
        return

    reference = f"SDC-{uuid.uuid4().hex[:6].upper()}"
    appointment = {
        "reference": reference,
        "name": name,
        "service": service or "general consultation",
        "preferred_time": preferred_time,
        "booked_at": datetime.now(IST).isoformat(),
    }
    APPOINTMENTS.append(appointment)
    logger.info(f"TOOL book_appointment -> {reference} for {name} ({preferred_time})")
    await params.result_callback(
        {
            "status": "confirmed",
            "reference": reference,
            "name": name,
            "service": appointment["service"],
            "preferred_time": preferred_time,
            "message": (
                f"Appointment confirmed. Reference {reference}. Read the reference "
                "aloud clearly, one character at a time."
            ),
        }
    )


async def search_knowledge_base(params: FunctionCallParams) -> None:
    """Look up an answer in the local knowledge base."""
    query = str(params.arguments.get("query", "")).strip()
    result = knowledge.search(query)
    match_count = len(result.get("matches", []))
    logger.info(f"TOOL search_knowledge_base -> '{query}' ({match_count} match(es))")
    await params.result_callback(result)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
_DATETIME_SCHEMA = FunctionSchema(
    name="get_current_datetime",
    description="Get the current date, day of the week and time in India Standard Time.",
    properties={},
    required=[],
)

_CALCULATE_SCHEMA = FunctionSchema(
    name="calculate",
    description="Evaluate a basic arithmetic expression and return the result.",
    properties={
        "expression": {
            "type": "string",
            "description": "Arithmetic expression, e.g. '1500 * 2 + 300' or '(45+55)/2'.",
        }
    },
    required=["expression"],
)

_WEATHER_SCHEMA = FunctionSchema(
    name="get_weather",
    description="Get the current weather for a location.",
    properties={
        "location": {
            "type": "string",
            "description": "City name, e.g. 'Kochi'. Defaults to Kochi if omitted.",
        }
    },
    required=[],
)

_APPOINTMENT_SCHEMA = FunctionSchema(
    name="book_appointment",
    description=(
        "Book a dental appointment at Sunrise Dental Clinic. Collect the caller's "
        "name, the desired service and a preferred day/time before calling this."
    ),
    properties={
        "name": {"type": "string", "description": "The caller's full name."},
        "service": {
            "type": "string",
            "description": "The treatment or service requested, e.g. 'cleaning', 'root canal'.",
        },
        "preferred_time": {
            "type": "string",
            "description": "Preferred day and time, e.g. 'tomorrow at 5 PM' or 'Saturday morning'.",
        },
    },
    required=["name", "preferred_time"],
)

_KNOWLEDGE_SCHEMA = FunctionSchema(
    name="search_knowledge_base",
    description=(
        "Search the clinic's knowledge base to answer questions about hours, "
        "location, services, prices, doctors, insurance, payment and more. "
        "Always use this before answering clinic questions from general knowledge."
    ),
    properties={
        "query": {
            "type": "string",
            "description": "The caller's question, in English keywords if possible.",
        }
    },
    required=["query"],
)


def build_tools_schema() -> ToolsSchema:
    """Return the ToolsSchema advertised to Gemini Live."""
    return ToolsSchema(
        standard_tools=[
            _DATETIME_SCHEMA,
            _CALCULATE_SCHEMA,
            _WEATHER_SCHEMA,
            _APPOINTMENT_SCHEMA,
            _KNOWLEDGE_SCHEMA,
        ]
    )


# Map tool name -> handler, used to register handlers on the LLM service.
HANDLERS = {
    "get_current_datetime": get_current_datetime,
    "calculate": calculate,
    "get_weather": get_weather,
    "book_appointment": book_appointment,
    "search_knowledge_base": search_knowledge_base,
}


def register_tools(llm) -> None:
    """Register every tool handler on the given Pipecat LLM service."""
    for name, handler in HANDLERS.items():
        llm.register_function(name, handler)
    logger.info(f"Registered {len(HANDLERS)} tools: {', '.join(HANDLERS)}")
