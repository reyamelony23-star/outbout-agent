"""Natural-language chat assistant.

Uses Claude tool use to map user messages to one of:
    search_prospects | generate_deck | send_outreach | answer
"""

from __future__ import annotations

import anthropic

import sheets
from config import ANTHROPIC_API_KEY, CHAT_OUTREACH_CAP, CLAUDE_MODEL, DEFAULT_MAX_RESULTS
from deck_generator import generate_deck
from outreach import compose_email, send_email
from scraper import scrape_prospects

CHAT_SYSTEM_PROMPT = """You are the outbound sales operations assistant for a B2B agency.

You help the user run their outbound pipeline by calling the available tools.
Be concise — confirm the action you took and any counts. If the request is
ambiguous (e.g. "send outreach" with no target), ask one clarifying question
instead of guessing.

If the user is just chatting or asking a question that doesn't need a tool,
answer in 1-2 short sentences."""

TOOLS = [
    {
        "name": "search_prospects",
        "description": (
            "Search Google Maps for businesses matching a query and save them to the "
            "Prospects sheet. Use whenever the user asks to find / scrape / search for prospects."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The Google Maps search string, e.g. 'automotive workshops in Jurong'",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "generate_deck",
        "description": "Generate a personalized pitch deck for one prospect by business name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "business_name": {
                    "type": "string",
                    "description": "Exact or near-exact business name of the prospect.",
                }
            },
            "required": ["business_name"],
        },
    },
    {
        "name": "send_outreach",
        "description": (
            "Send personalized outreach emails. Pass a specific business name to email one "
            "prospect, or the literal string 'all_new' to email up to a few prospects whose "
            "status is still 'New'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Either a specific business name or the literal 'all_new'.",
                }
            },
            "required": ["target"],
        },
    },
]


def _claude() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _do_search(query: str, owner_email: str) -> str:
    prospects = scrape_prospects(query, max_results=DEFAULT_MAX_RESULTS)
    added, skipped = sheets.append_prospects(prospects, owner_email=owner_email)
    return (
        f"Searched Google Maps for '{query}'. Added {added} new prospect(s) to the sheet "
        f"({skipped} duplicate(s) skipped, {len(prospects)} total returned by Apify)."
    )


def _do_generate_deck(business_name: str, owner_email: str | None) -> dict:
    prospect = sheets.find_prospect_by_name(business_name, owner_email=owner_email)
    if not prospect:
        return {"reply": f"Couldn't find a prospect named '{business_name}' in the sheet."}
    url = generate_deck(prospect)
    sheets.update_prospect(prospect["_row"], {"Deck Generated": url})
    import os as _os

    filename = _os.path.basename(url)
    return {
        "reply": f"Deck ready! View it here: {url}",
        "deck": {
            "filename": filename,
            "business_name": prospect["Business Name"],
            "view_url": url,
        },
    }


def _send_one(prospect: dict, sender_name: str) -> tuple[bool, str]:
    to = (prospect.get("Email") or "").strip()
    if not to:
        return False, f"{prospect['Business Name']}: no email on file"
    subject, body = compose_email(prospect, sender_name=sender_name)
    ok, msg = send_email(to, subject, body)
    if ok:
        from datetime import datetime, timezone

        sheets.update_prospect(
            prospect["_row"],
            {
                "Status": "Contacted",
                "Last Contacted": datetime.now(timezone.utc).date().isoformat(),
            },
        )
        return True, f"{prospect['Business Name']}: sent to {to}"
    return False, f"{prospect['Business Name']}: {msg}"


def _do_outreach(target: str, owner_email: str | None, sender_name: str) -> str:
    if target.strip().lower() == "all_new":
        candidates = [
            p
            for p in sheets.list_prospects(owner_email=owner_email)
            if str(p.get("Status", "")).strip().lower() in {"", "new"}
            and (p.get("Email") or "").strip()
        ][:CHAT_OUTREACH_CAP]
        if not candidates:
            return "No 'New' prospects with an email address on file."
        results = [_send_one(p, sender_name) for p in candidates]
        sent = sum(1 for ok, _ in results if ok)
        lines = "; ".join(msg for _, msg in results)
        return f"Sent {sent} of {len(results)} outreach email(s) (cap {CHAT_OUTREACH_CAP}). {lines}"
    prospect = sheets.find_prospect_by_name(target, owner_email=owner_email)
    if not prospect:
        return f"Couldn't find a prospect named '{target}'."
    ok, msg = _send_one(prospect, sender_name)
    return msg


def handle_chat(message: str, owner_email: str | None, sender_name: str, is_admin: bool) -> dict:
    """Run one chat turn. Returns {'reply': str, 'action': str | None}."""
    scope = None if is_admin else owner_email

    response = _claude().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": CHAT_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=TOOLS,
        messages=[{"role": "user", "content": message}],
    )

    if response.stop_reason == "tool_use":
        tool_block = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_block is None:
            return {"reply": "Sorry, I couldn't parse that.", "action": None}
        name = tool_block.name
        args = tool_block.input or {}
        deck_payload = None
        try:
            if name == "search_prospects":
                reply = _do_search(args["query"], owner_email=owner_email or "admin")
            elif name == "generate_deck":
                result = _do_generate_deck(args["business_name"], owner_email=scope)
                reply = result["reply"]
                deck_payload = result.get("deck")
            elif name == "send_outreach":
                reply = _do_outreach(args["target"], owner_email=scope, sender_name=sender_name)
            else:
                reply = f"Unknown tool: {name}"
        except Exception as e:
            reply = f"Action failed: {e}"
        out = {"reply": reply, "action": name}
        if deck_payload:
            out["deck"] = deck_payload
        return out

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return {"reply": text or "(no response)", "action": None}
