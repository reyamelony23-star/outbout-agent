"""Outreach helpers — build wa.me links with a pre-written pitch message."""

from __future__ import annotations

import re
from urllib.parse import quote


def _normalize_phone(phone: str) -> str:
    """Strip everything but digits — wa.me wants international format, no '+'."""
    return re.sub(r"\D", "", phone or "")


def build_whatsapp_link(prospect: dict, deck_url: str = "") -> tuple[str, str]:
    """Build a wa.me link with a pre-written message for this prospect.

    Returns (link, message). Link is empty if no phone number on file.
    """
    business_name = (prospect.get("Business Name") or "there").strip()
    phone = _normalize_phone(prospect.get("Phone") or "")
    message = (
        f"Hi {business_name} team! I'm Reya from Moiboo Marketing. "
        f"I noticed your business on Google and have put together a quick "
        f"digital growth proposal for you. Would you be open to a 15-minute "
        f"call this week?"
    )
    if deck_url:
        message = f"{message} {deck_url}"
    if not phone:
        return "", message
    return f"https://wa.me/{phone}?text={quote(message)}", message
