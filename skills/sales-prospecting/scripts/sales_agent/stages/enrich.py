"""الإثراء: يجمع بيانات الاتصال والأدلة. القاعدة: لا تُحفظ معلومة بدون رابط مصدر http."""

from __future__ import annotations
import json

from ..countries import COUNTRY_AR
from ..icp_config import Icp
from ..states import State
from ..store import Store
from .common import is_http, dossier

TOOLS = ("WebSearch", "WebFetch")
ALLOWED_FIELDS = ["specialty", "website", "phone", "whatsapp", "email", "instagram", "linkedin_url",
                  "decision_maker_name", "decision_maker_title", "name_ar", "name_en"]
_CLASSES = ["maps", "own_site", "official", "directory", "social"]
_NULL_BOOL, _NULL_INT = {"type": ["boolean", "null"]}, {"type": ["integer", "null"]}
SCHEMA = {
    "type": "object",
    "properties": {
        "fields": {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string", "enum": ALLOWED_FIELDS}, "value": {"type": "string"},
            "source_url": {"type": "string"}, "source_class": {"type": "string", "enum": _CLASSES},
            "confidence": {"type": "number"}},
            "required": ["field", "value", "source_url", "source_class", "confidence"]}},
        "facts": {"type": "object", "properties": {
            "website_up": _NULL_BOOL, "maps_status": {"type": "string", "enum": ["open", "closed", "unknown"]},
            "social_last_post_days": _NULL_INT, "team_size": _NULL_INT, "branches_count": _NULL_INT,
            "is_private": _NULL_BOOL,
            "source_url": {"type": "string"}}},
        "identity": {"type": "array", "items": {"type": "object", "properties": {
            "source_class": {"type": "string", "enum": _CLASSES}, "source_url": {"type": "string"},
            "name": {"type": "string"}, "phone": {"type": "string"}},
            "required": ["source_class", "source_url", "name"]}},
        "signals": {"type": "array", "items": {"type": "object", "properties": {
            "detail": {"type": "string"}, "source_url": {"type": "string"}},
            "required": ["detail", "source_url"]}},
        "concerns": {"type": "array", "items": {"type": "object", "properties": {
            "detail": {"type": "string"}, "source_url": {"type": "string"}},
            "required": ["detail", "source_url"]}},
    },
    "required": ["fields", "facts", "identity", "signals", "concerns"],
}


MAX_TEXT = 300


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT - 1] + "…"


def apply_enrichment(store: Store, lead_id: str, payload: dict) -> None:
    for f in payload.get("fields", []):
        value = (f.get("value") or "").strip()
        if f.get("field") not in ALLOWED_FIELDS or not value or not is_http(f.get("source_url")):
            continue
        conf = min(1.0, max(0.0, float(f.get("confidence", 0.5))))
        store.set_field(lead_id, f["field"], value, f["source_url"], f.get("source_class", "directory"), conf)

    facts = payload.get("facts") or {}
    if is_http(facts.get("source_url")):
        url = facts["source_url"]
        for key in ("website_up", "is_private"):
            if facts.get(key) is not None:
                store.set_field(lead_id, key, "true" if facts[key] else "false", url, "web", 0.8)
        for key in ("social_last_post_days", "team_size", "branches_count"):
            if facts.get(key) is not None:
                store.set_field(lead_id, key, str(int(facts[key])), url, "web", 0.7)
        if facts.get("maps_status") in ("open", "closed", "unknown"):
            store.set_field(lead_id, "maps_status", facts["maps_status"], url, "web", 0.8)

    for i in payload.get("identity", []):
        if (i.get("name") or "").strip() and is_http(i.get("source_url")):
            value = json.dumps({"name": i["name"].strip(), "phone": (i.get("phone") or "").strip()}, ensure_ascii=False)
            store.set_field(lead_id, "identity", value, i["source_url"], i.get("source_class", "directory"), 0.8)

    for key, field_name in (("signals", "signal"), ("concerns", "concern")):
        for s in payload.get(key, []):
            if (s.get("detail") or "").strip() and is_http(s.get("source_url")):
                store.set_field(lead_id, field_name, _clip(s["detail"]), s["source_url"], "web", 0.7)


def _prompt(store: Store, lead: dict, icp: Icp) -> str:
    country_ar = COUNTRY_AR.get(lead["country"], lead["country"])
    noun, signals = icp.team_noun, "، ".join(icp.fit_signals[:5])
    return f"""أنت باحث مبيعات تجمع بيانات منشأة لتأهيلها. افتح موقعها وحساباتها وخرائطها وأي مصدر عام، وأعد ما وجدتَه فقط.

المنشأة: {lead['name']}
المدينة: {lead['city']}، {country_ar}
الفئة المستهدفة: {icp.name} ({', '.join(icp.specialties)})
صاحب القرار المطلوب: {icp.decision_maker}

المعروف حاليًا:
{dossier(store, lead['id'])}

المطلوب:
1) fields: بيانات الاتصال والتعريف (الهاتف، الواتساب، الإيميل، إنستغرام، الموقع، لينكدإن، اسم صاحب القرار ومسماه، التخصص، الاسم بالعربية والإنجليزية). لكل معلومة رابط الصفحة التي رأيتها فيها بالضبط، وتصنيف المصدر، ودرجة ثقة بين 0 و1.
2) facts: هل الموقع يعمل، وحالة المنشأة على الخرائط (open أو closed أو unknown)، وعدد الأيام منذ آخر منشور على السوشال، وعدد {noun} (team_size)، وعدد الفروع (branches_count)، وهل هي منشأة خاصة (غير حكومية). ضع null لما لم تتأكد منه. وضع في source_url رابط الصفحة الأهم التي بنيتَ عليها.
3) identity: لكل مصدر مستقل ظهر فيه اسم المنشأة (خرائط، موقعها، سجل رسمي، دليل، سوشال) اكتب اسمها كما ورد فيه ورقم هاتفها كما ورد فيه إن وُجد، مع الرابط.
4) signals: إشارات إيجابية فقط تدعم الملاءمة، بدليلها (مثل: {signals}).
5) concerns: أي تضارب أو شك يجب أن يعرفه المراجع البشري (تضارب هوية، منشأة مغلقة، تشابه أسماء، رقم مختلف بين المصادر)، بدليله.
كل نص في signals وconcerns جملة واحدة قصيرة (أقل من 160 حرفًا). لا فقرات.

قواعد صارمة: ممنوع اختراع رقم أو إيميل أو اسم أو رابط. لا تخمّن اسم صاحب القرار من اسم المنشأة. المعلومة التي لا مصدر لها لا تكتبها. اتركها فارغة أو null."""


def enrich_brief(store: Store, lead_id: str, icp: Icp) -> dict:
    return {"instructions": _prompt(store, store.get_lead(lead_id), icp), "schema": SCHEMA, "tools": list(TOOLS)}


def run_enrich(ask, store: Store, lead_id: str, icp: Icp) -> None:
    lead = store.get_lead(lead_id)
    payload = ask(_prompt(store, lead, icp), SCHEMA, tools=TOOLS)
    apply_enrichment(store, lead_id, payload)
    store.transition(lead_id, State.ENRICHED, "اكتمل الإثراء")
