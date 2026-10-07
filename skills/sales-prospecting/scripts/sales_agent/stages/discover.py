"""الاكتشاف: يبحث بالويب عن منشآت مطابقة للشريحة. لا يُحفظ مرشح بلا اسم ورابط مصدر حقيقي."""

from __future__ import annotations
from ..countries import COUNTRY_AR
from ..icp_config import Icp
from ..store import Store
from .common import is_http

TOOLS = ("WebSearch", "WebFetch")
SCHEMA = {
    "type": "object",
    "properties": {"candidates": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"}, "city": {"type": "string"}, "website": {"type": "string"},
            "source_url": {"type": "string"},
            "source_class": {"type": "string", "enum": ["maps", "own_site", "official", "directory", "social"]},
            "note": {"type": "string"},
            "team_estimate": {"type": ["integer", "null"]},
            "branches_estimate": {"type": ["integer", "null"]},
            "looks_large": {"type": ["boolean", "null"]},
        },
        "required": ["name", "city", "source_url", "source_class"],
    }}},
    "required": ["candidates"],
}


def _prompt(icp: Icp, country: str, city: str, want: int, known: list[str]) -> str:
    country_ar = COUNTRY_AR.get(country, country)
    hints = "\n".join("- " + h.format(city=city, country=country_ar) for h in icp.search_hints)
    sources = "\n".join("- " + s for s in icp.source_hints)
    exclusions = "\n".join("- " + x for x in icp.exclusions)
    known_block = "\n".join("- " + n for n in known[:100]) or "- لا يوجد"
    return f"""أنت باحث مبيعات. مهمتك إيجاد منشآت حقيقية تطابق الفئة المستهدفة التالية في {city}، {country_ar}.

الفئة: {icp.name}
الوصف: {icp.description}
التخصصات المقبولة: {', '.join(icp.specialties)}

استبعد:
{exclusions}

أمثلة استعلامات بحث (اكتب غيرها إن لزم):
{hints}

مصادر مفيدة (جرّب أكثر من مصدر ولا تقتصر على واحد):
{sources}

الأولوية: {icp.discover_priority}
لكل منشأة قدّر من نص النتيجة نفسه فقط (بلا تعمق): team_estimate عدد {icp.team_noun} إن ظهر وإلا null، وbranches_estimate عدد الفروع إن ظهر وإلا null، وlooks_large=true إن بدت: {icp.large_hint}.

طريقة العمل (مهم): هذه مرحلة اكتشاف سريعة فقط. لا تتعمق بالتحقق من كل منشأة، فهذا دور مرحلة لاحقة.
نفّذ من 3 إلى 5 عمليات بحث متنوعة، واجمع أسماء المنشآت التي تبدو مطابقة مع رابط الصفحة التي ظهرت فيها، ولا تفتح أكثر من 6 صفحات إجمالًا.

قواعد صارمة:
- أعد فقط منشآت ظهرت فعلًا في نتائج البحث أو الصفحات التي فتحتها.
- لكل منشأة source_url هو رابط الصفحة الحقيقية التي رأيتَ فيها المنشأة. ممنوع اختراع رابط أو اسم.
- ضع website إن وجدت موقع المنشأة نفسها، وإلا اتركه فارغًا.
- العدد الأقصى المطلوب من المنشآت الجديدة: {want}. أعد أقل إن لم تجد، ولا تُكمل العدد بالتخمين.
- هذه منشآت سبق اكتشافها، لا تعدها:
{known_block}"""


def _too_big(c: dict, icp: Icp) -> bool:
    team, branches = c.get("team_estimate"), c.get("branches_estimate")
    return bool((team is not None and icp.max_team and team > icp.max_team)
                or (branches is not None and icp.max_branches and branches > icp.max_branches))


def add_candidates(store: Store, icp: Icp, country: str, city: str, candidates: list[dict],
                   count: int, log=None) -> list[str]:
    """الجزء الحتمي: يحفظ المرشحين الصالحين فقط (اسم + رابط مصدر http، غير مكرر، غير كبير بوضوح)."""
    ids: list[str] = []
    no_source = duplicate = large = 0
    for c in candidates:
        name = (c.get("name") or "").strip()
        url = c.get("source_url", "")
        if not name or not is_http(url):
            no_source += 1
            continue
        if c.get("looks_large") or _too_big(c, icp):
            large += 1  # فلترة مبكرة رخيصة: لا نصرف دقائق إثراء على منشأة سيرفضها الفلتر الحتمي
            continue
        if store.has_lead(icp.code, country, name):
            duplicate += 1
            continue
        lead_id = store.add_lead(icp.code, country, city, name)
        store.set_field(lead_id, "discovered_via", (c.get("note") or name).strip(), url,
                        c.get("source_class", "directory"), 0.5)
        if is_http(c.get("website")):
            store.set_field(lead_id, "website", c["website"].strip(), url, "directory", 0.6)
        ids.append(lead_id)
        if len(ids) >= count:
            break
    if log:
        log(f"أعاد النموذج {len(candidates)} مرشحًا، حُفظ {len(ids)}، "
            f"تُجوهل {no_source + duplicate + large} (بلا مصدر صالح: {no_source}، مكرر: {duplicate}، كبيرة: {large})")
    return ids


def known_names(store: Store, icp: Icp, country: str) -> list[str]:
    return [lead["name"] for lead in store.search_leads(country=country, code=icp.code, limit=100)]


def discover_brief(store: Store, icp: Icp, country: str, city: str, count: int) -> dict:
    return {"instructions": _prompt(icp, country, city, count + 3, known_names(store, icp, country)),
            "schema": SCHEMA, "tools": list(TOOLS)}


def run_discover(ask, store: Store, icp: Icp, country: str, city: str, count: int, log=None) -> list[str]:
    brief = discover_brief(store, icp, country, city, count)
    result = ask(brief["instructions"], SCHEMA, tools=TOOLS)
    return add_candidates(store, icp, country, city, result.get("candidates", []), count, log)
