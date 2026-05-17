"""Natural-language chat assistant.

Uses Claude tool use to map user messages to one of:
    search_prospects | generate_deck | send_outreach | answer
"""

from __future__ import annotations

import anthropic

import sheets
from config import ANTHROPIC_API_KEY, CHAT_OUTREACH_CAP, CLAUDE_MODEL, DEFAULT_MAX_RESULTS
from deck_generator import generate_deck
from outreach import build_whatsapp_link
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
            "Generate a WhatsApp outreach link (wa.me) for a prospect with a pre-written "
            "message including their deck. Pass a specific business name for one prospect, "
            "or the literal string 'all_new' to generate links for up to a few prospects "
            "whose status is still 'New'."
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
    from datetime import datetime, timezone

    sheets.update_prospect(
        prospect["_row"],
        {
            "Deck Generated": url,
            "Deck Generated At": datetime.now(timezone.utc).date().isoformat(),
        },
    )
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


def _whatsapp_one(prospect: dict) -> dict:
    """Build a wa.me link for one prospect and log it in the sheet.

    Returns dict with keys: ok, business_name, link, message, note.
    """
    from datetime import datetime, timezone

    business_name = prospect.get("Business Name", "")
    phone = (prospect.get("Phone") or "").strip()
    if not phone:
        return {
            "ok": False,
            "business_name": business_name,
            "link": "",
            "message": "",
            "note": f"{business_name}: no phone on file",
        }
    deck_url = (prospect.get("Deck Generated") or "").strip()
    link, message = build_whatsapp_link(prospect, deck_url=deck_url)
    sheets.update_prospect(
        prospect["_row"],
        {
            "Status": "Contacted",
            "WhatsApp Sent": datetime.now(timezone.utc).date().isoformat(),
            "Last Contacted": datetime.now(timezone.utc).date().isoformat(),
        },
    )
    return {
        "ok": True,
        "business_name": business_name,
        "link": link,
        "message": message,
        "note": f"{business_name}: WhatsApp link ready",
    }


def _do_outreach(target: str, owner_email: str | None, sender_name: str) -> dict:
    if target.strip().lower() == "all_new":
        candidates = [
            p
            for p in sheets.list_prospects(owner_email=owner_email)
            if str(p.get("Status", "")).strip().lower() in {"", "new"}
            and (p.get("Phone") or "").strip()
        ][:CHAT_OUTREACH_CAP]
        if not candidates:
            return {"reply": "No 'New' prospects with a phone number on file."}
        results = [_whatsapp_one(p) for p in candidates]
        whatsapp = [
            {"business_name": r["business_name"], "link": r["link"]}
            for r in results
            if r["ok"] and r["link"]
        ]
        lines = "; ".join(r["note"] for r in results)
        return {
            "reply": (
                f"Generated {len(whatsapp)} WhatsApp link(s) (cap {CHAT_OUTREACH_CAP}). {lines}"
            ),
            "whatsapp": whatsapp,
        }
    prospect = sheets.find_prospect_by_name(target, owner_email=owner_email)
    if not prospect:
        return {"reply": f"Couldn't find a prospect named '{target}'."}
    result = _whatsapp_one(prospect)
    if not result["ok"]:
        return {"reply": result["note"]}
    return {
        "reply": f"WhatsApp link ready for {result['business_name']}: {result['link']}",
        "whatsapp": [
            {"business_name": result["business_name"], "link": result["link"]}
        ],
    }


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
        whatsapp_payload = None
        try:
            if name == "search_prospects":
                reply = _do_search(args["query"], owner_email=owner_email or "admin")
            elif name == "generate_deck":
                result = _do_generate_deck(args["business_name"], owner_email=scope)
                reply = result["reply"]
                deck_payload = result.get("deck")
            elif name == "send_outreach":
                result = _do_outreach(args["target"], owner_email=scope, sender_name=sender_name)
                reply = result["reply"]
                whatsapp_payload = result.get("whatsapp")
            else:
                reply = f"Unknown tool: {name}"
        except Exception as e:
            reply = f"Action failed: {e}"
        out = {"reply": reply, "action": name}
        if deck_payload:
            out["deck"] = deck_payload
        if whatsapp_payload:
            out["whatsapp"] = whatsapp_payload
        return out

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return {"reply": text or "(no response)", "action": None}
