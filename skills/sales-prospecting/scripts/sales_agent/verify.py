"""منطق التحقق والتوجيه الحتمي. لا شبكة ولا ذكاء هنا: يستقبل أدلة جاهزة ويحسب الدرجات.

أوزان التحقق (من 100): الوجود والنشاط 30، التطابق بين المصادر 30، قنوات الاتصال 20، صاحب القرار 20.
العتبات (75 و70 و50) مؤقتة حتى تُعايَر بالمجموعة المرجعية.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field

from .states import State

VERIFY_READY = 75
FIT_READY = 70
VERIFY_FLOOR = 50

_COUNTRY_CODE = {"SA": "966", "QA": "974", "KW": "965", "OM": "968", "AE": "971", "JO": "962"}
# (طول الرقم الوطني، بدايات الأرقام، هل هو جوال)
_PHONE_RULES = {
    "SA": [(9, {"5"}, True), (9, {"1"}, False), (9, {"9"}, False)],  # 9200xxxxx رقم موحّد لشركة
    "QA": [(8, {"3", "5", "6", "7"}, True), (8, {"4"}, False)],
    "KW": [(8, {"5", "6", "9"}, True), (8, {"2"}, False)],
    "OM": [(8, {"7", "9"}, True), (8, {"2"}, False)],
    "AE": [(9, {"5"}, True), (8, {"2", "3", "4", "6", "7", "9"}, False)],
    "JO": [(9, {"7"}, True), (8, {"2", "3", "5", "6"}, False)],
}


@dataclass(frozen=True)
class Phone:
    e164: str
    is_mobile: bool


def parse_phone(raw: str, country: str) -> Phone | None:
    cc, rules = _COUNTRY_CODE.get(country), _PHONE_RULES.get(country)
    if not cc or not rules or not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    candidates = []
    if digits.startswith(cc):
        candidates.append(digits[len(cc):])
    if digits.startswith("0"):
        candidates.append(digits[1:])
    candidates.append(digits)
    for national in candidates:
        for length, prefixes, is_mobile in rules:
            if len(national) == length and national[0] in prefixes:
                return Phone(f"+{cc}{national}", is_mobile)
    return None


_DIACRITICS = re.compile(r"[ً-ٰٟـ]")
_STOP = {
    "عياده", "عيادات", "مركز", "مجمع", "مستوصف", "لطب", "طب", "اسنان", "علاج", "طبيعي",
    "د", "دكتور", "و", "في", "dental", "clinic", "clinics", "center", "centre", "physio",
    "physiotherapy",
}


def normalize_name(name: str) -> str:
    text = _DIACRITICS.sub("", name or "")
    text = re.sub("[أإآٱ]", "ا", text).replace("ة", "ه").replace("ى", "ي").lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(name: str) -> set[str]:
    words = []
    for word in normalize_name(name).split():
        if word.startswith("ال") and len(word) > 3:
            word = word[2:]
        words.append(word)
    meaningful = {w for w in words if w not in _STOP}
    return meaningful or set(words)


def names_match(a: str, b: str) -> bool:
    """تطابق استدلالي: الكلمات العامة (عيادة، مركز، لطب…) و«ال» لا تُحتسب.
    لا يطابق بين الحروف العربية واللاتينية؛ نحتاج اسم المنشأة بالصيغتين من الإثراء."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    jaccard = len(ta & tb) / len(ta | tb)
    return jaccard >= 0.5 or ta <= tb or tb <= ta


@dataclass
class Evidence:
    country: str
    website_up: bool | None = None
    maps_status: str = "unknown"          # open | closed | unknown
    social_last_post_days: int | None = None
    identity: list[dict] = field(default_factory=list)   # {source_class, name, phone}
    phone: str | None = None
    email: str | None = None
    email_domain_resolves: bool | None = None
    decision_maker_sources: int = 0


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def _existence(e: Evidence) -> dict:
    if e.maps_status == "closed":
        return {"points": 0, "note": "مغلق نهائيًا على الخرائط"}
    pts, notes = 0, []
    if e.website_up:
        pts += 10; notes.append("الموقع يعمل")
    if e.maps_status == "open":
        pts += 10; notes.append("نشط على الخرائط")
    if e.social_last_post_days is not None:
        if e.social_last_post_days <= 60:
            pts += 10; notes.append(f"آخر منشور قبل {e.social_last_post_days} يوم")
        else:
            notes.append(f"الحساب خامل ({e.social_last_post_days} يوم)")
    return {"points": pts, "note": "، ".join(notes) or "لا دليل على النشاط"}


def _cross_match(e: Evidence) -> dict:
    entries = [i for i in e.identity if i.get("name")]
    if not entries:
        return {"points": 0, "note": "لا مصادر للهوية"}
    best: list[dict] = []
    for anchor in entries:
        cluster = [i for i in entries if names_match(anchor["name"], i["name"])]
        if len({i["source_class"] for i in cluster}) > len({i["source_class"] for i in best}):
            best = cluster
    classes = {i["source_class"] for i in best}
    pts = {1: 5, 2: 15}.get(len(classes), 20 if len(classes) >= 3 else 5)
    notes = [f"{len(classes)} مصدر مستقل متطابق الاسم"]

    phones = {}
    for i in best:
        parsed = parse_phone(i.get("phone") or "", e.country)
        if parsed:
            phones.setdefault(i["source_class"], set()).add(parsed.e164)
    distinct = set().union(*phones.values()) if phones else set()
    if len(phones) >= 2:
        if len(distinct) == 1:
            pts += 10; notes.append("الهاتف متطابق")
        else:
            pts = max(0, pts - 10); notes.append("تضارب بالهاتف بين المصادر")
    if "official" in classes and len(classes) >= 2:
        pts += 5; notes.append("مصدر رسمي ضمن المتطابقين")
    return {"points": min(30, pts), "note": "، ".join(notes)}


def _contacts(e: Evidence) -> dict:
    pts, notes = 0, []
    phone = parse_phone(e.phone or "", e.country)
    if phone:
        pts += 12 if phone.is_mobile else 8
        notes.append("جوال صالح" if phone.is_mobile else "هاتف أرضي صالح")
    if e.email and _EMAIL.match(e.email) and e.email_domain_resolves:
        pts += 8; notes.append("إيميل صالح")
    elif e.email:
        notes.append("إيميل غير صالح أو نطاقه لا يعمل")
    return {"points": pts, "note": "، ".join(notes) or "لا قنوات اتصال صالحة"}


def _decision_maker(e: Evidence) -> dict:
    if e.decision_maker_sources >= 2:
        return {"points": 20, "note": "صاحب القرار مؤكد من مصدرين"}
    if e.decision_maker_sources == 1:
        return {"points": 8, "note": "صاحب القرار من مصدر واحد"}
    return {"points": 0, "note": "جهة اتصال فقط، المالك غير معروف"}


def verification_score(e: Evidence) -> tuple[int, dict[str, dict]]:
    checks = {
        "existence": _existence(e), "cross_match": _cross_match(e),
        "contacts": _contacts(e), "decision_maker": _decision_maker(e),
    }
    return sum(c["points"] for c in checks.values()), checks


@dataclass(frozen=True)
class Route:
    state: State
    reason: str
    ready: bool = False


def route(verification: int, fit: int | None, excluded_reason: str | None,
          reviewer_disagrees: bool = False) -> Route:
    if verification < VERIFY_FLOOR:
        return Route(State.DISCARDED, f"تحقق منخفض ({verification})")
    if excluded_reason:
        return Route(State.OUT_OF_ICP, excluded_reason)
    if fit is None:
        return Route(State.UNDECIDED, "لم يُقيَّم بعد")
    if reviewer_disagrees:
        return Route(State.UNDECIDED, "المراجِع المعاكس خالف الحكم")
    if verification >= VERIFY_READY and fit >= FIT_READY:
        return Route(State.SCORED, "جاهز للصياغة", ready=True)
    return Route(State.UNDECIDED, f"درجات متوسطة (تحقق {verification}، ملاءمة {fit})")
