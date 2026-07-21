"""JSON schemas advertised to the LLM. Kept separate from tools.py so the
runtime signatures and the LLM-visible surface don't drift together."""

TOOL_SCHEMAS = [
    {
        "name": "lookup_citizen",
        "description": (
            "Look up a citizen profile by Emirates ID. May return a 503-style "
            "SERVICE_UNAVAILABLE error — the caller should retry once, then fall "
            "back to asking the citizen or proceeding with what is known."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "emirates_id": {
                    "type": "string",
                    "description": "Emirates ID in the form 784-YYYY-NNNNNNN-N",
                }
            },
            "required": ["emirates_id"],
        },
    },
    {
        "name": "search_lost_items",
        "description": (
            "Search recovered lost items by free-text query. Returns 0-5 fuzzy "
            "matches with a confidence score. Results may be ambiguous; if "
            "multiple plausible matches are returned the agent MUST ask the "
            "citizen to disambiguate rather than picking one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "filters": {
                    "type": "object",
                    "description": "Optional {location, date_from, date_to, kind, color}",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_policy",
        "description": (
            "Fetch official policy text for a topic. Returns null when no policy "
            "is on file. If null, the agent MUST NOT invent policy — it must "
            "acknowledge that it doesn't have that information and offer to "
            "escalate or file a service request."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
    {
        "name": "file_service_request",
        "description": (
            "File a service request. Non-idempotent unless idempotency_key is "
            "supplied — retries WITHOUT an idempotency_key will create duplicate "
            "tickets. Always pass a stable idempotency_key when filing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "e.g. lost_item, car_renewal"},
                "details": {"type": "object"},
                "idempotency_key": {
                    "type": "string",
                    "description": "Stable key so retries do not create duplicates.",
                },
            },
            "required": ["type", "details"],
        },
    },
    {
        "name": "check_service_status",
        "description": (
            "Check ticket status. May return a stale snapshot (indicated by "
            "`stale: true` in the response); treat stale results as advisory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}},
            "required": ["ticket_id"],
        },
    },
    {
        "name": "book_appointment",
        "description": (
            "Book a government service appointment. Rate-limited to 2 calls "
            "per minute. Slot conflicts are possible — on CONFLICT, propose "
            "an alternative time rather than retrying immediately."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "datetime_iso": {"type": "string", "description": "ISO-8601 datetime"},
            },
            "required": ["service", "datetime_iso"],
        },
    },
    {
        "name": "pay_fine",
        "description": (
            "PRIVILEGED: Pay a fine on behalf of the citizen. This tool must "
            "NEVER be called unless the citizen has explicitly confirmed the "
            "specific payment (fine_id + amount) in the SAME turn as the call. "
            "citizen_confirmed=true is a hard requirement; the runtime "
            "authorization gate will reject the call otherwise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fine_id": {"type": "string"},
                "amount_aed": {"type": "number"},
                "citizen_confirmed": {
                    "type": "boolean",
                    "description": "Must be true AND matched by a same-turn confirmation.",
                },
            },
            "required": ["fine_id", "amount_aed", "citizen_confirmed"],
        },
    },
    {
        "name": "translate",
        "description": "Translate text between Arabic and English. Optional helper.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "target_lang": {"type": "string", "enum": ["ar", "en"]},
            },
            "required": ["text", "target_lang"],
        },
    },
]
