"""Outreach sender — Claude drafts copy, Gmail SMTP delivers."""

from __future__ import annotations

import json
import os
import re
import smtplib
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

import anthropic

from config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    GMAIL_ADDRESS,
    GMAIL_APP_PASSWORD,
)

EMAIL_SYSTEM_PROMPT = """You write personalized cold outreach emails for B2B sales.

Return JSON with this exact shape — no preamble, no markdown fences:
{"subject": "...", "body": "..."}

Rules:
- Subject: <= 60 chars, no spammy language, reference the prospect by name or category.
- Body: 80-120 words, plain text, 2-3 short paragraphs.
- Tone: warm, specific, no hard sell. End with a soft ask (15-min chat).
- Sign off with the sender's first name only.
- Never use words: 'leverage', 'synergy', 'unlock', 'game-changer'."""


def _claude_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def compose_email(prospect: dict, sender_name: str = "Alex") -> tuple[str, str]:
    """Generate a personalized (subject, body) pair via Claude."""
    user_message = (
        f"Prospect: {prospect.get('Business Name', '')}\n"
        f"Industry/Query: {prospect.get('Search Query', '')}\n"
        f"Address: {prospect.get('Address', '')}\n"
        f"Rating: {prospect.get('Rating', '')} ({prospect.get('Review Count', 0)} reviews)\n"
        f"Website: {prospect.get('Website', '')}\n"
        f"Sender first name: {sender_name}\n\n"
        "Write the email now."
    )

    response = _claude_client().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": EMAIL_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    data = json.loads(text)
    return data["subject"], data["body"]


def send_email(
    to_address: str,
    subject: str,
    body: str,
    attachment_path: str | None = None,
) -> tuple[bool, str]:
    """Send a single email via Gmail SMTP. Returns (ok, message)."""
    if not to_address:
        return False, "No recipient email address"

    msg = MIMEMultipart()
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={os.path.basename(attachment_path)}",
        )
        msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, [to_address], msg.as_string())
        return True, "sent"
    except smtplib.SMTPException as e:
        return False, str(e)
