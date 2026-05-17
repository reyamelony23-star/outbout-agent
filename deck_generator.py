"""Personalised pitch deck generator — Claude writes the copy, output is a self-contained HTML file.

Pipeline:
    prospect dict
        → Claude (sonnet) generates structured slide content as JSON
        → renders into a single self-contained HTML file with 6 full-screen slides,
          navigation arrows, keyboard nav, smooth transitions, Moiboo branding
        → saves to /decks/[BusinessName]_proposal.html
        → returns the URL route /decks/<filename>
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY, DECK_OUTPUT_DIR, PUBLIC_BASE_URL

DECK_CLAUDE_MODEL = "claude-sonnet-4-6"

NAVY = "#0f172a"
BLUE = "#6366f1"
WHITE = "#ffffff"

DECK_SYSTEM_PROMPT = """You write personalised pitch deck copy for B2B outreach by Moiboo Marketing.

You will receive one prospect business with: name, address, rating, review count, phone, website, search query.

Return ONLY a JSON object matching this schema exactly — no preamble, no markdown fences, no commentary:

{
  "found": {
    "bullets": ["...", "...", "..."]
  },
  "opportunity": {
    "paragraph": "...",
    "bullets": ["...", "...", "..."]
  },
  "services": [
    {"name": "...", "description": "..."},
    {"name": "...", "description": "..."},
    {"name": "...", "description": "..."}
  ],
  "investment": {
    "setup_fee": "SGD ...",
    "monthly_retainer": "SGD .../month",
    "ad_budget": "SGD .../month"
  },
  "next_steps": ["...", "...", "..."]
}

Rules for "found":
- 3 or 4 bullet observations about their likely digital presence, derived from rating, review count, location, industry.
- Be specific to THIS prospect. E.g. if rating is low (<4.0), call out reputation gaps; if review count is low, mention discoverability; if no website, mention online presence; if good rating but few reviews, mention untapped advocacy.
- Each bullet <= 22 words. No fluff.

Rules for "opportunity":
- paragraph: 2–3 sentences explaining why THIS business needs digital marketing right now. Reference their industry and location explicitly.
- bullets: exactly 3 specific opportunity bullets tailored to their industry and location.

Rules for "services":
- Pick exactly 3 services most relevant to this prospect from this list ONLY: Google Ads, Meta Ads, Website Build, WhatsApp Reactivation, SEO.
- Use the service name verbatim from that list in the "name" field.
- Each description: 1 sentence, <= 25 words, framed to this prospect's situation.

Rules for "investment":
- setup_fee: a single SGD figure between 800 and 2000 based on services chosen (e.g. "SGD 1,500").
- monthly_retainer: a single SGD figure between 800 and 1500, with "/month" (e.g. "SGD 1,200/month").
- ad_budget: a single SGD figure between 500 and 2000, with "/month" (e.g. "SGD 1,000/month").

Rules for "next_steps":
- Exactly 3 clear action items.
- Each <= 14 words, action-oriented.

Tone: sharp human consultant. No clichés, no exclamation marks, no buzzwords (leverage / synergy / unlock / game-changer)."""


def _claude_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ─── Claude content generation ──────────────────────────────────────────


def generate_deck_content(prospect: dict) -> dict:
    """Ask Claude for the structured 6-slide content tailored to this prospect."""
    user_message = (
        f"Business Name: {prospect.get('Business Name', '')}\n"
        f"Address: {prospect.get('Address', '')}\n"
        f"Rating: {prospect.get('Rating', '')} stars\n"
        f"Review Count: {prospect.get('Review Count', 0)} reviews\n"
        f"Phone: {prospect.get('Phone', '')}\n"
        f"Website: {prospect.get('Website', '')}\n"
        f"Industry / Search Query: {prospect.get('Search Query', '')}\n\n"
        "Generate the deck content now."
    )
    response = _claude_client().messages.create(
        model=DECK_CLAUDE_MODEL,
        max_tokens=2500,
        system=[
            {
                "type": "text",
                "text": DECK_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


# ─── Filename + escaping helpers ────────────────────────────────────────


def _safe_filename(business_name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", business_name).strip("_")
    return f"{slug or 'Prospect'}_proposal.html"


def _e(text) -> str:
    """HTML-escape a value (handles None and non-strings)."""
    if text is None:
        return ""
    return html.escape(str(text), quote=True)


# ─── HTML rendering ─────────────────────────────────────────────────────


def _render_html(business_name: str, content: dict) -> str:
    found_bullets = content.get("found", {}).get("bullets", []) or []
    opp = content.get("opportunity", {}) or {}
    opp_paragraph = opp.get("paragraph", "")
    opp_bullets = opp.get("bullets", []) or []
    services = (content.get("services") or [])[:3]
    inv = content.get("investment", {}) or {}
    next_steps = content.get("next_steps", []) or []

    found_items = "\n".join(f"<li>{_e(b)}</li>" for b in found_bullets)
    opp_items = "\n".join(f"<li>{_e(b)}</li>" for b in opp_bullets)
    service_cards = "\n".join(
        f"""
        <div class="service-card">
          <div class="service-num">0{i + 1}</div>
          <div class="service-body">
            <h3>{_e(svc.get('name', ''))}</h3>
            <p>{_e(svc.get('description', ''))}</p>
          </div>
        </div>
        """
        for i, svc in enumerate(services)
    )
    next_items = "\n".join(f"<li>{_e(s)}</li>" for s in next_steps)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(business_name)} — Digital Growth Proposal</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --navy: {NAVY};
    --blue: {BLUE};
    --white: {WHITE};
    --grey: #64748b;
    --light: #f8fafc;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; overflow: hidden; font-family: 'Inter', system-ui, sans-serif; background: var(--navy); color: var(--navy); }}

  .deck {{ position: relative; width: 100vw; height: 100vh; overflow: hidden; }}
  .slide {{
    position: absolute; inset: 0;
    display: flex; flex-direction: column; justify-content: center;
    padding: 8vh 10vw;
    opacity: 0; visibility: hidden;
    transform: translateX(40px);
    transition: opacity .55s ease, transform .55s ease, visibility 0s linear .55s;
  }}
  .slide.active {{
    opacity: 1; visibility: visible; transform: translateX(0);
    transition: opacity .55s ease, transform .55s ease, visibility 0s;
  }}
  .slide.prev {{ transform: translateX(-40px); }}

  .slide-dark {{ background: var(--navy); color: var(--white); }}
  .slide-light {{ background: var(--white); color: var(--navy); }}

  .accent-bar {{
    position: absolute; top: 0; left: 0; right: 0; height: 6px;
    background: linear-gradient(90deg, var(--blue), #818cf8);
  }}

  .eyebrow {{
    font-size: 13px; letter-spacing: .22em; text-transform: uppercase;
    color: var(--blue); font-weight: 600; margin-bottom: 24px;
  }}
  h1.cover-title {{
    font-size: clamp(40px, 6vw, 84px); font-weight: 800; line-height: 1.05;
    letter-spacing: -.02em; margin-bottom: 20px;
  }}
  .cover-sub {{
    font-size: clamp(20px, 2.2vw, 30px); font-weight: 400;
    color: var(--blue); margin-bottom: 60px;
  }}
  .cover-footer {{
    position: absolute; bottom: 8vh; left: 10vw; right: 10vw;
    display: flex; justify-content: space-between; align-items: center;
    font-size: 14px; color: rgba(255,255,255,.7);
    border-top: 1px solid rgba(255,255,255,.15); padding-top: 18px;
  }}
  .cover-footer strong {{ color: var(--white); font-weight: 600; }}

  h2.section-title {{
    font-size: clamp(32px, 4vw, 52px); font-weight: 700;
    letter-spacing: -.015em; margin-bottom: 32px;
  }}
  .section-lede {{
    font-size: clamp(16px, 1.4vw, 20px); line-height: 1.6;
    color: var(--grey); max-width: 900px; margin-bottom: 32px;
  }}
  .slide-dark .section-lede {{ color: rgba(255,255,255,.75); }}

  ul.bullets {{
    list-style: none; display: grid; gap: 14px; max-width: 900px;
  }}
  ul.bullets li {{
    position: relative; padding-left: 36px;
    font-size: clamp(15px, 1.25vw, 18px); line-height: 1.55;
  }}
  ul.bullets li::before {{
    content: ""; position: absolute; left: 0; top: .55em;
    width: 18px; height: 2px; background: var(--blue);
  }}

  .services-grid {{
    display: grid; gap: 18px; max-width: 1100px;
  }}
  .service-card {{
    display: flex; gap: 24px; align-items: flex-start;
    padding: 22px 26px; border: 1px solid #e2e8f0; border-radius: 14px;
    background: var(--light);
    transition: transform .25s ease, border-color .25s ease;
  }}
  .service-card:hover {{ transform: translateY(-2px); border-color: var(--blue); }}
  .service-num {{
    font-size: 28px; font-weight: 700; color: var(--blue);
    min-width: 48px;
  }}
  .service-body h3 {{
    font-size: 22px; font-weight: 600; margin-bottom: 6px; color: var(--navy);
  }}
  .service-body p {{
    font-size: 15px; line-height: 1.5; color: var(--grey);
  }}

  .pricing {{
    max-width: 800px; border: 1px solid #e2e8f0; border-radius: 16px;
    overflow: hidden;
  }}
  .pricing-row {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 22px 28px; border-bottom: 1px solid #e2e8f0;
  }}
  .pricing-row:last-child {{ border-bottom: 0; }}
  .pricing-row .label {{
    font-size: 17px; font-weight: 500; color: var(--navy);
  }}
  .pricing-row .value {{
    font-size: 22px; font-weight: 700; color: var(--blue);
  }}
  .pricing-note {{
    margin-top: 18px; font-size: 13px; color: var(--grey); max-width: 800px;
  }}

  .cta {{ max-width: 900px; }}
  .cta ul.bullets li::before {{ background: var(--blue); }}
  .contact-card {{
    margin-top: 44px; padding: 26px 30px;
    background: rgba(99, 102, 241, .12);
    border: 1px solid rgba(99, 102, 241, .35);
    border-radius: 14px;
    display: flex; flex-direction: column; gap: 6px;
    max-width: 560px;
  }}
  .contact-card .who {{ font-size: 18px; font-weight: 600; color: var(--white); }}
  .contact-card .role {{ font-size: 13px; color: rgba(255,255,255,.7); letter-spacing: .08em; text-transform: uppercase; }}
  .contact-card a, .contact-card span.line {{ font-size: 15px; color: rgba(255,255,255,.9); text-decoration: none; }}
  .contact-card a:hover {{ color: var(--blue); }}

  .nav-arrow {{
    position: fixed; top: 50%; transform: translateY(-50%);
    width: 52px; height: 52px; border-radius: 50%;
    background: rgba(15, 23, 42, .55); color: var(--white);
    border: 1px solid rgba(255,255,255,.2);
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; cursor: pointer; z-index: 50;
    transition: background .2s, transform .2s, opacity .2s;
    backdrop-filter: blur(8px);
  }}
  .nav-arrow:hover {{ background: var(--blue); transform: translateY(-50%) scale(1.05); }}
  .nav-arrow[disabled] {{ opacity: .25; cursor: not-allowed; }}
  .nav-arrow.prev {{ left: 28px; }}
  .nav-arrow.next {{ right: 28px; }}

  .slide-light .nav-arrow {{ background: rgba(15, 23, 42, .9); }}

  .progress {{
    position: fixed; bottom: 28px; left: 50%; transform: translateX(-50%);
    display: flex; gap: 8px; z-index: 50;
  }}
  .progress .dot {{
    width: 28px; height: 4px; border-radius: 2px;
    background: rgba(148, 163, 184, .5); cursor: pointer;
    transition: background .2s, width .2s;
  }}
  .progress .dot.active {{ background: var(--blue); width: 44px; }}

  .slide-count {{
    position: fixed; top: 24px; right: 28px;
    font-size: 12px; letter-spacing: .12em; text-transform: uppercase;
    color: rgba(148, 163, 184, .8); z-index: 50; font-weight: 500;
  }}
  .slide-dark .slide-count, .slide-light .slide-count {{ color: rgba(148,163,184,.8); }}

  .brand-mark {{
    position: absolute; top: 36px; left: 10vw;
    font-size: 13px; letter-spacing: .26em; text-transform: uppercase;
    font-weight: 600;
  }}
  .slide-dark .brand-mark {{ color: rgba(255,255,255,.7); }}
  .slide-light .brand-mark {{ color: var(--blue); }}

  @media (max-width: 720px) {{
    .slide {{ padding: 6vh 6vw; }}
    .nav-arrow.prev {{ left: 12px; }}
    .nav-arrow.next {{ right: 12px; }}
  }}
</style>
</head>
<body>
<div class="deck">

  <!-- Slide 1: Cover -->
  <section class="slide slide-dark active" data-slide="1">
    <span class="brand-mark">Moiboo Marketing</span>
    <div class="eyebrow">Prepared for</div>
    <h1 class="cover-title">{_e(business_name)}</h1>
    <div class="cover-sub">Digital Growth Proposal</div>
    <div class="cover-footer">
      <span>Prepared by <strong>Reya Melony</strong></span>
      <span>Moiboo Marketing · Singapore</span>
    </div>
  </section>

  <!-- Slide 2: What We Found -->
  <section class="slide slide-light" data-slide="2">
    <div class="accent-bar"></div>
    <span class="brand-mark">Moiboo Marketing</span>
    <div class="eyebrow">Observations</div>
    <h2 class="section-title">What We Found About {_e(business_name)}</h2>
    <ul class="bullets">
      {found_items}
    </ul>
  </section>

  <!-- Slide 3: Opportunity -->
  <section class="slide slide-light" data-slide="3">
    <div class="accent-bar"></div>
    <span class="brand-mark">Moiboo Marketing</span>
    <div class="eyebrow">The case for action</div>
    <h2 class="section-title">The Opportunity</h2>
    <p class="section-lede">{_e(opp_paragraph)}</p>
    <ul class="bullets">
      {opp_items}
    </ul>
  </section>

  <!-- Slide 4: Services -->
  <section class="slide slide-light" data-slide="4">
    <div class="accent-bar"></div>
    <span class="brand-mark">Moiboo Marketing</span>
    <div class="eyebrow">How we help</div>
    <h2 class="section-title">Our Recommended Services</h2>
    <div class="services-grid">
      {service_cards}
    </div>
  </section>

  <!-- Slide 5: Investment -->
  <section class="slide slide-light" data-slide="5">
    <div class="accent-bar"></div>
    <span class="brand-mark">Moiboo Marketing</span>
    <div class="eyebrow">Pricing</div>
    <h2 class="section-title">Investment</h2>
    <div class="pricing">
      <div class="pricing-row">
        <span class="label">Setup fee</span>
        <span class="value">{_e(inv.get('setup_fee', ''))}</span>
      </div>
      <div class="pricing-row">
        <span class="label">Monthly retainer</span>
        <span class="value">{_e(inv.get('monthly_retainer', ''))}</span>
      </div>
      <div class="pricing-row">
        <span class="label">Recommended ad budget</span>
        <span class="value">{_e(inv.get('ad_budget', ''))}</span>
      </div>
    </div>
    <p class="pricing-note">Ad budget is paid directly to platforms. No long-term lock-in — month-to-month engagement.</p>
  </section>

  <!-- Slide 6: Next Steps -->
  <section class="slide slide-dark" data-slide="6">
    <span class="brand-mark">Moiboo Marketing</span>
    <div class="eyebrow">Next steps</div>
    <h2 class="section-title">Let's Get Started</h2>
    <div class="cta">
      <ul class="bullets">
        {next_items}
      </ul>
      <div class="contact-card">
        <span class="role">Your contact</span>
        <span class="who">Reya Melony</span>
        <a href="mailto:reyamelony23@gmail.com">reyamelony23@gmail.com</a>
        <a href="tel:+6586870041">+65 8687 0041</a>
      </div>
    </div>
  </section>

  <button class="nav-arrow prev" aria-label="Previous slide">‹</button>
  <button class="nav-arrow next" aria-label="Next slide">›</button>

  <div class="slide-count"><span id="cur">1</span> / 6</div>

  <div class="progress">
    <span class="dot active" data-go="1"></span>
    <span class="dot" data-go="2"></span>
    <span class="dot" data-go="3"></span>
    <span class="dot" data-go="4"></span>
    <span class="dot" data-go="5"></span>
    <span class="dot" data-go="6"></span>
  </div>
</div>

<script>
(function () {{
  const slides = document.querySelectorAll('.slide');
  const dots = document.querySelectorAll('.progress .dot');
  const prevBtn = document.querySelector('.nav-arrow.prev');
  const nextBtn = document.querySelector('.nav-arrow.next');
  const counter = document.getElementById('cur');
  const total = slides.length;
  let idx = 0;

  function show(n) {{
    n = Math.max(0, Math.min(total - 1, n));
    slides.forEach((s, i) => {{
      s.classList.remove('active', 'prev');
      if (i === n) s.classList.add('active');
      else if (i < n) s.classList.add('prev');
    }});
    dots.forEach((d, i) => d.classList.toggle('active', i === n));
    counter.textContent = (n + 1);
    prevBtn.disabled = n === 0;
    nextBtn.disabled = n === total - 1;
    idx = n;
  }}

  prevBtn.addEventListener('click', () => show(idx - 1));
  nextBtn.addEventListener('click', () => show(idx + 1));
  dots.forEach((d, i) => d.addEventListener('click', () => show(i)));

  document.addEventListener('keydown', (e) => {{
    if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') {{
      e.preventDefault(); show(idx + 1);
    }} else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {{
      e.preventDefault(); show(idx - 1);
    }} else if (e.key === 'Home') {{
      show(0);
    }} else if (e.key === 'End') {{
      show(total - 1);
    }}
  }});

  show(0);
}})();
</script>
</body>
</html>
"""


# ─── Public entrypoint ──────────────────────────────────────────────────


def generate_deck(prospect: dict, content: dict | None = None) -> str:
    """Build a personalised HTML pitch deck for a prospect.

    Returns the full public URL (e.g. 'https://app.reyamelony.me/decks/Carro_Care_proposal.html').
    """
    if content is None:
        content = generate_deck_content(prospect)

    business_name = (prospect.get("Business Name") or "Prospect").strip()
    filename = _safe_filename(business_name)

    deck_dir = Path(DECK_OUTPUT_DIR)
    deck_dir.mkdir(parents=True, exist_ok=True)
    out_path = deck_dir / filename

    out_path.write_text(_render_html(business_name, content), encoding="utf-8")

    return f"{PUBLIC_BASE_URL}/decks/{filename}"
