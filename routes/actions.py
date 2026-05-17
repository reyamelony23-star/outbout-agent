"""Actions blueprint — POST endpoints that mutate state.

Endpoints:
    POST /search                 → scrape + save
    POST /generate-deck/<row>    → generate one deck
    POST /send-outreach/<row>    → send one email
    POST /chat                   → natural-language router
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

import sheets
from chat import handle_chat
from config import DEFAULT_MAX_RESULTS
from deck_generator import generate_deck
from scraper import scrape_prospects

actions_bp = Blueprint("actions", __name__)


def _scope_email():
    if current_user.is_admin:
        return None
    return current_user.email


@actions_bp.route("/search", methods=["POST"])
@login_required
def search():
    payload = request.get_json(silent=True) or request.form
    query = (payload.get("query") or "").strip()
    if not query:
        return jsonify({"ok": False, "error": "query is required"}), 400
    try:
        prospects = scrape_prospects(query, max_results=DEFAULT_MAX_RESULTS)
    except Exception as e:
        return jsonify({"ok": False, "error": f"scraper failed: {e}"}), 500
    added, skipped = sheets.append_prospects(prospects, owner_email=current_user.email)
    return jsonify(
        {"ok": True, "added": added, "skipped": skipped, "total_seen": len(prospects)}
    )


def _find_row(row_index: int):
    for p in sheets.list_prospects(owner_email=_scope_email()):
        if p["_row"] == row_index:
            return p
    return None


@actions_bp.route("/generate-deck/<int:row>", methods=["POST"])
@login_required
def generate_deck_route(row: int):
    prospect = _find_row(row)
    if not prospect:
        return jsonify({"ok": False, "error": "prospect not found"}), 404
    try:
        url = generate_deck(prospect)
    except Exception as e:
        return jsonify({"ok": False, "error": f"deck generation failed: {e}"}), 500
    sheets.update_prospect(
        row,
        {
            "Deck Generated": url,
            "Deck Generated At": datetime.now(timezone.utc).date().isoformat(),
        },
    )
    return jsonify({"ok": True, "deck_url": url})


@actions_bp.route("/send-outreach/<int:row>", methods=["POST"])
@login_required
def send_outreach_route(row: int):
    try:
        prospect = _find_row(row)
        if not prospect:
            return jsonify({"ok": False, "error": "prospect not found"}), 404

        phone = str(prospect.get("Phone", "") or "")
        phone = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not phone:
            return jsonify({"ok": False, "error": "no phone number on file"}), 400

        phone = re.sub(r"\D", "", phone)
        if len(phone) == 8 and phone[0] in ("6", "8", "9"):
            phone = "65" + phone
        if not phone:
            return jsonify({"ok": False, "error": "phone number is empty after cleaning"}), 400

        business_name = (prospect.get("Business Name") or "there").strip()
        message = (
            f"Hi {business_name} team! I came across your business and put together "
            f"a quick digital growth proposal for you. Would you be open to a 15-min "
            f"call this week? - Reya from Moiboo Marketing"
        )
        whatsapp_url = f"https://wa.me/{phone}?text={quote(message)}"

        today = datetime.now(timezone.utc).date().isoformat()
        sheets.update_prospect(
            row,
            {
                "Status": "Contacted",
                "WhatsApp Sent": today,
                "Last Contacted": today,
            },
        )
        return jsonify({"ok": True, "whatsapp_url": whatsapp_url, "message": message})
    except Exception as e:
        return jsonify({"ok": False, "error": f"send-outreach failed: {e}"}), 500


@actions_bp.route("/chat", methods=["POST"])
@login_required
def chat():
    try:
        payload = request.get_json(silent=True) or {}
        message = (payload.get("message") or "").strip()
        if not message:
            return jsonify({"ok": False, "error": "message is required"}), 400
        result = handle_chat(
            message=message,
            owner_email=current_user.email,
            sender_name=current_user.name.split()[0],
            is_admin=current_user.is_admin,
        )
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
