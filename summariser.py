"""
summariser.py — AI-powered listing summary using Claude
"""

import os
import logging
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)
_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


async def summarise_listing(listing: dict, notes: list) -> str:
    """Return a 3-5 sentence AI summary of a listing's notes.

    Returns plain text (no Markdown) suitable for embedding inside a formatted card.
    Falls back to a graceful error string if the API call fails.
    """
    if not notes:
        return "No notes yet — add observations via /note after your viewing."

    note_lines = "\n".join(
        f"- {n['sender']}: {n.get('text') or '(photo only)'}"
        for n in notes
    )

    rent = listing.get("rent_sgd")
    rent_str = f"SGD ${rent:,}/mo" if rent else "not set"

    prompt = (
        "You are helping a couple (Michael and Natalie) shortlist rental apartments in Singapore.\n\n"
        f"Listing: {listing.get('nickname', '?')}\n"
        f"Address: {listing.get('address') or 'not set'}\n"
        f"Rent: {rent_str}\n"
        f"Size: {listing.get('size_sqft') or '?'} sqft  |  Floor: {listing.get('floor_level') or '?'}\n"
        f"MRT: {listing.get('mrt') or 'not set'}\n\n"
        f"Notes from Michael and Natalie:\n{note_lines}\n\n"
        "Write a concise 3-5 sentence summary of what the notes reveal about this listing. "
        "Highlight key pros and cons, flag any unresolved questions or action items, "
        "and give an overall gut-feel verdict. "
        "Do not repeat the basic listing stats. Be direct and practical. "
        "Do not use markdown formatting in your response."
    )

    try:
        client = _get_client()
        response = await client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning(f"AI summary failed for '{listing.get('nickname')}': {e}")
        return f"⚠️ AI summary unavailable — ensure ANTHROPIC_API_KEY is set in Railway Variables."
