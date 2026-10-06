"""اختيار قناة التواصل من البيانات المتاحة فعلًا، حسب ترتيب الشريحة."""
import re
from dataclasses import dataclass

from .verify import parse_phone

_LABEL = {"whatsapp": "واتساب", "instagram": "إنستغرام", "email": "إيميل", "linkedin": "لينكدإن"}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


@dataclass(frozen=True)
class Choice:
    primary: str | None
    alt: str | None
    reason: str


def _available(channel: str, fields: dict, country: str) -> bool:
    if channel == "whatsapp":
        if fields.get("whatsapp"):
            return True
        phone = parse_phone(fields.get("phone", ""), country)
        return bool(phone and phone.is_mobile)
    if channel == "instagram":
        return bool(fields.get("instagram"))
    if channel == "email":
        return bool(_EMAIL.match(fields.get("email", "")))
    if channel == "linkedin":
        return bool(fields.get("linkedin_url"))
    return False


def choose_channel(order: list[str], fields: dict, country: str) -> Choice:
    usable = [c for c in order if _available(c, fields, country)]
    if not usable:
        return Choice(None, None, "لا توجد قناة متاحة ببيانات مؤكدة")
    primary = usable[0]
    alt = usable[1] if len(usable) > 1 else None
    return Choice(primary, alt, f"أول قناة متاحة بترتيب الشريحة: {_LABEL[primary]}")
