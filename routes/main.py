"""Main blueprint — dashboard, prospects table, navigation pages."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, render_template, send_from_directory
from flask_login import current_user, login_required

import sheets
from config import DECK_OUTPUT_DIR

main_bp = Blueprint("main", __name__)


def _scope_email():
    """Admins see everything; clients see only their own rows."""
    if current_user.is_admin:
        return None
    return current_user.email


def _deck_dir() -> Path:
    return Path(DECK_OUTPUT_DIR).resolve()


def _human_name_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    if stem.endswith("_proposal"):
        stem = stem[: -len("_proposal")]
    return stem.replace("_", " ").strip()


def _list_decks_on_disk() -> list[dict]:
    """Scan the decks/ directory for .html files and return display metadata."""
    deck_dir = _deck_dir()
    if not deck_dir.exists():
        return []
    out: list[dict] = []
    for p in deck_dir.iterdir():
        if not p.is_file() or p.suffix.lower() != ".html":
            continue
        stat = p.stat()
        out.append(
            {
                "filename": p.name,
                "business_name": _human_name_from_filename(p.name),
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%b %d, %Y · %H:%M"),
                "created_ts": stat.st_mtime,
                "size_kb": stat.st_size / 1024,
            }
        )
    out.sort(key=lambda d: d["created_ts"], reverse=True)
    return out


@main_bp.route("/")
@login_required
def index():
    return dashboard()


@main_bp.route("/dashboard")
@login_required
def dashboard():
    scope = _scope_email()
    return render_template(
        "dashboard.html",
        stats=sheets.stats(owner_email=scope),
        recent=sheets.list_prospects(owner_email=scope)[-5:][::-1],
        page="dashboard",
    )


@main_bp.route("/prospects")
@login_required
def prospects():
    scope = _scope_email()
    rows = sheets.list_prospects(owner_email=scope)
    return render_template(
        "prospects.html",
        prospects=rows[::-1],
        page="prospects",
        campaign_filter=None,
    )


@main_bp.route("/campaigns")
@login_required
def campaigns():
    scope = _scope_email()
    items = sheets.list_campaigns(owner_email=scope)
    items.sort(key=lambda c: (c.get("date") or "", c.get("name") or ""), reverse=True)
    return render_template("campaigns.html", campaigns=items, page="campaigns")


@main_bp.route("/campaigns/<path:name>")
@login_required
def campaign_detail(name: str):
    scope = _scope_email()
    rows = sheets.list_prospects(owner_email=scope, campaign=name)
    return render_template(
        "prospects.html",
        prospects=rows[::-1],
        page="campaigns",
        campaign_filter=name,
    )


@main_bp.route("/decks")
@login_required
def decks():
    return render_template("decks.html", decks=_list_decks_on_disk(), page="decks")


@main_bp.route("/decks/<filename>")
@login_required
def view_deck(filename: str):
    """Serve a generated HTML deck inline so it opens in the browser."""
    deck_dir = _deck_dir()
    target = (deck_dir / filename).resolve()
    if not str(target).startswith(str(deck_dir) + os.sep) or not target.is_file():
        abort(404)
    if target.suffix.lower() != ".html":
        abort(404)
    return send_from_directory(deck_dir, filename, mimetype="text/html")


@main_bp.route("/settings")
@login_required
def settings():
    return render_template("settings.html", page="settings")
