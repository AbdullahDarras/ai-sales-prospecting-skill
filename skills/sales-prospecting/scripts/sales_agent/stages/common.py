from __future__ import annotations

import re

from ..store import Store

_HTTP = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)


def is_http(url: str | None) -> bool:
    return bool(url) and bool(_HTTP.match(url))


def latest_values(store: Store, lead_id: str) -> dict[str, str]:
    return {k: v["value"] for k, v in store.get_fields(lead_id).items()}


def known_urls(store: Store, lead_id: str) -> set[str]:
    return {o["source_url"] for obs in store.all_observations(lead_id).values()
            for o in obs if is_http(o["source_url"])}


def dossier(store: Store, lead_id: str) -> str:
    """ملخص نصي بما جُمع عن العميل مع مصدر كل معلومة، يُمرَّر للنموذج."""
    lines = []
    for field, observations in store.all_observations(lead_id).items():
        if field in ("message", "message_final", "verification_checks"):
            continue
        for o in observations:
            src = o["source_url"] if is_http(o["source_url"]) else o["source_class"]
            lines.append(f"- {field}: {o['value']}  (المصدر: {src})")
    return "\n".join(lines) or "لا توجد بيانات مجمّعة"
