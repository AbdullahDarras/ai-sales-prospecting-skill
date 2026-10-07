"""منجم بيانات من OpenStreetMap: مصدر مجاني وقانوني (ODbL)، يعطي أسماء وأرقام ومواقع الأماكن العامة.

يُستخرج المزيد من وسائل التواصل بقراءة صفحة الموقع الرئيسية للمكان (بدون أي نموذج لغوي).
لا يُضاف مكان إلا إذا كان عليه وسيلة تواصل مباشرة، وكل معلومة تحمل رابط مصدرها.
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from ..stages.enrich import apply_enrichment
from ..stages.verify_stage import default_dns, run_verify
from ..states import State
from ..store import Store
from ..verify import normalize_name, parse_phone

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "sales-prospecting-research/0.1 (+https://github.com/AbdullahDarras/ai-sales-prospecting-skill)"
DEFAULT_KINDS = ["amenity=cafe", "amenity=restaurant", "amenity=fast_food", "shop=bakery", "shop=pastry"]
_PHONE_KEYS = ("phone", "contact:phone", "contact:mobile", "mobile")
_WEB_KEYS = ("website", "contact:website", "url")
_IG_KEYS = ("contact:instagram", "instagram")
_FB_KEYS = ("contact:facebook", "facebook")
_MAIL_KEYS = ("email", "contact:email")
# سلاسل عالمية وإقليمية معروفة (خريطة OSM لا تعلّم كل الماركات). حذف الفراغات والتشكيل قبل المقارنة.
KNOWN_CHAINS = [
    "starbucks", "ستاربكس", "mcdonald", "ماكدونالد", "kfc", "كنتاكي", "burgerking", "برجركنج", "burgerking",
    "dominos", "دومينوز", "pizzahut", "بيتزاهت", "papajohn", "باباجونز", "hardees", "هارديز", "subway", "صب واي",
    "dunkin", "دانكن", "timhortons", "تيمهورتنز", "costacoffee", "كوستا", "caribou", "كاريبو", "segafredo", "سيغافريدو",
    "gloriajean", "جلوريا جينز", "tgifridays", "chilis", "تشيليز", "applebee", "popeyes", "بوبايز", "baskinrobbins",
    "cinnabon", "krispykreme", "shakeshack", "fuddruckers", "wingstop", "texasroadhouse", "carlsjr", "ikea",
    "zaatarwzeit", "زعترو زيت", "zaatarwzeit", "reemalbawadi", "ريم البوادي", "shawermareem", "shawarmareem", "شاورماريم",
    "alromansiah", "kudu", "كودو", "herfy", "هرفي", "albaik", "البيك", "maestro", "مايسترو بيتزا",
]
_IG_RESERVED = {"p", "explore", "reel", "reels", "accounts", "tv", "stories", "about", "direct", "web"}
_FB_RESERVED = {"sharer", "sharer.php", "plugins", "tr", "dialog", "share", "login", "policies"}


def _http_post(url: str, body: str, headers: dict) -> bytes:
    req = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=150) as r:
        return r.read()


def _http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        r = urllib.request.urlopen(req, timeout=8)
    except ssl.SSLError:                     # قراءة صفحة عامة فقط، بلا إرسال بيانات
        r = urllib.request.urlopen(req, timeout=8, context=ssl._create_unverified_context())
    with r:
        return r.read(400_000).decode("utf-8", errors="ignore")


def build_query(area_en: str, kinds: list[str]) -> str:
    lines = []
    for kind in kinds:
        key, _, value = kind.partition("=")
        lines.append(f'  node["{key}"="{value}"](area.a);')
        lines.append(f'  way["{key}"="{value}"](area.a);')
    return ('[out:json][timeout:120];\n'
            f'area["name:en"="{area_en}"]["boundary"="administrative"]->.a;\n'
            "(\n" + "\n".join(lines) + "\n);\nout center tags;")


_TRANSIENT_HTTP = {429, 500, 502, 503, 504}


def fetch_overpass(query: str, post=None, url: str = OVERPASS_URL, sleep=time.sleep, attempts: int = 3) -> list[dict]:
    """الخادم المجاني يزدحم أحيانًا (504/429): نعيد المحاولة بتأخير متزايد، ولا نعيد لأخطاء الاستعلام نفسه."""
    post = post or _http_post
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json",
               "Content-Type": "application/x-www-form-urlencoded"}
    body = urllib.parse.urlencode({"data": query})
    for attempt in range(1, attempts + 1):
        try:
            return json.loads(post(url, body, headers))["elements"]
        except urllib.error.HTTPError as e:
            if e.code not in _TRANSIENT_HTTP or attempt == attempts:
                raise
            sleep(10 * attempt)


def _squash(name: str) -> str:
    return re.sub(r"[^\w]", "", normalize_name(name)).replace("_", "")


def is_known_chain(name: str) -> bool:
    s = _squash(name)
    return any(_squash(c) and _squash(c) in s for c in KNOWN_CHAINS)


def _first(tags: dict, keys) -> str | None:
    return next((tags[k].strip() for k in keys if tags.get(k, "").strip()), None)


def parse_elements(elements: list[dict]) -> list[dict]:
    """يحوّل عناصر الخريطة إلى مرشحين، ويدمج الأماكن المتشابهة بالاسم (فروع) بمرشح واحد."""
    merged: dict[str, dict] = {}
    for e in elements:
        tags = e.get("tags", {})
        name = tags.get("name:ar") or tags.get("name") or tags.get("name:en")
        if not name:
            continue
        key = normalize_name(name)
        phones = []
        for k in _PHONE_KEYS:
            phones += [p.strip() for p in tags.get(k, "").split(";") if p.strip()]
        cand = merged.get(key)
        if cand is None:
            cand = merged[key] = {
                "name": name.strip(), "kind": tags.get("amenity") or tags.get("shop") or "",
                "phones": [], "website": _first(tags, _WEB_KEYS), "instagram": _first(tags, _IG_KEYS),
                "facebook": _first(tags, _FB_KEYS), "email": _first(tags, _MAIL_KEYS),
                "source_url": f"https://www.openstreetmap.org/{e['type']}/{e['id']}",
                "is_chain": False, "branches": 0}
        cand["branches"] += 1
        cand["is_chain"] = cand["is_chain"] or bool(tags.get("brand") or tags.get("brand:wikidata")) or is_known_chain(name)
        for p in phones:
            if p not in cand["phones"]:
                cand["phones"].append(p)
        for field, keys in (("website", _WEB_KEYS), ("instagram", _IG_KEYS), ("facebook", _FB_KEYS), ("email", _MAIL_KEYS)):
            cand[field] = cand[field] or _first(tags, keys)
    return list(merged.values())


def _decode_cf(hexstr: str) -> str:
    key = int(hexstr[:2], 16)
    return "".join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2))


def extract_links(html: str) -> dict:
    out = {"instagram": None, "facebook": None, "whatsapp": None, "emails": [], "phones": []}
    for m in re.finditer(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)/?", html):
        if m.group(1).lower() not in _IG_RESERVED:
            out["instagram"] = m.group(0)
            break
    for m in re.finditer(r"https?://(?:www\.|m\.)?facebook\.com/([A-Za-z0-9_.\-]+)/?", html):
        if m.group(1).lower() not in _FB_RESERVED:
            out["facebook"] = m.group(0)
            break
    m = re.search(r"wa\.me/(\d{8,15})|api\.whatsapp\.com/send\?phone=(\d{8,15})", html)
    if m:
        out["whatsapp"] = "+" + (m.group(1) or m.group(2))
    emails = [x.strip() for x in re.findall(r"mailto:([^\"'?>\s]+)", html)]
    emails += [_decode_cf(x) for x in re.findall(r'data-cfemail="([0-9a-fA-F]{4,})"', html)]
    out["emails"] = list(dict.fromkeys(e for e in emails if "@" in e))
    out["phones"] = list(dict.fromkeys(re.sub(r"[\s\-()]", "", p) for p in re.findall(r"tel:([+\d\s\-()]{7,})", html)))
    return out


def light_enrich(candidate: dict, fetch=None) -> dict:
    """يقرأ صفحة الموقع الرئيسية فقط: هل يعمل؟ وما وسائل التواصل المذكورة فيه."""
    empty = extract_links("")
    site = candidate.get("website")
    if not site:
        return {"website_up": None, "links": empty}
    try:
        return {"website_up": True, "links": extract_links((fetch or _http_get)(site))}
    except Exception:
        return {"website_up": False, "links": empty}


def _contact_score(c: dict) -> int:
    return 2 * bool(c["phones"]) + bool(c["website"]) + 2 * bool(c["instagram"]) + bool(c["facebook"]) + bool(c["email"])


def _payload(c: dict, light: dict) -> dict:
    osm, site, links = c["source_url"], c.get("website"), light["links"]
    fields = []

    def add(field, value, url, cls, conf):
        if value:
            fields.append({"field": field, "value": value, "source_url": url, "source_class": cls, "confidence": conf})

    for p in c["phones"][:2]:
        add("phone", p, osm, "maps", 0.6)
    if not c["phones"] and links["phones"]:
        add("phone", links["phones"][0], site, "own_site", 0.8)
    add("website", site, osm, "maps", 0.6)
    add("instagram", c["instagram"], osm, "maps", 0.6) if c["instagram"] else add("instagram", links["instagram"], site, "own_site", 0.8)
    add("facebook", c["facebook"], osm, "maps", 0.6) if c["facebook"] else add("facebook", links["facebook"], site, "own_site", 0.8)
    add("whatsapp", links["whatsapp"], site, "own_site", 0.8)
    add("email", c["email"], osm, "maps", 0.6) if c["email"] else add("email", (links["emails"] or [None])[0], site, "own_site", 0.8)
    facts = {"website_up": light["website_up"], "source_url": site} if light["website_up"] is not None else {}
    identity = [{"source_class": "maps", "source_url": osm, "name": c["name"], "phone": (c["phones"] or [""])[0]}]
    return {"fields": fields, "facts": facts, "identity": identity, "signals": [], "concerns": []}


def _has_channel(payload: dict, country: str) -> bool:
    for f in payload["fields"]:
        if f["field"] in ("instagram", "facebook", "email", "whatsapp"):
            return True
        if f["field"] == "phone" and parse_phone(f["value"], country):
            return True
    return False


def mine(store: Store, icp, country: str, city: str, candidates: list[dict], limit: int,
         light_fetch=None, sleep=time.sleep, dns_check=None) -> dict:
    skipped = {"chain": 0, "known": 0, "no_contact": 0}
    added: list[str] = []
    for c in sorted(candidates, key=_contact_score, reverse=True):
        if len(added) >= limit:
            break
        if c["is_chain"] or (icp.max_branches and c["branches"] > icp.max_branches):
            skipped["chain"] += 1
            continue
        if store.has_lead(icp.code, country, c["name"]):
            skipped["known"] += 1
            continue
        light = {"website_up": None, "links": extract_links("")}
        if light_fetch and c.get("website"):
            light = light_enrich(c, light_fetch)
            sleep(0.4)                      # لطف مع مواقع الناس
        payload = _payload(c, light)
        if not _has_channel(payload, country):
            skipped["no_contact"] += 1
            continue
        lead_id = store.add_lead(icp.code, country, city, c["name"])
        store.set_field(lead_id, "discovered_via", f"OpenStreetMap ({c['kind']})", c["source_url"], "maps", 0.6)
        apply_enrichment(store, lead_id, payload)
        store.transition(lead_id, State.ENRICHED, "بيانات من الخريطة")
        run_verify(store, lead_id, dns_check=dns_check or default_dns)
        if store.get_lead(lead_id)["state"] == State.VERIFIED:
            store.transition(lead_id, State.UNDECIDED,
                             "من الخريطة: بيانات أولية والملاءمة لم تُقيَّم، للمراجعة اليدوية")
        added.append(lead_id)
    return {"added": added, "skipped": skipped}
