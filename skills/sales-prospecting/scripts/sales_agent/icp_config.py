"""تحميل إعدادات الشريحة من config/icp/<الكود>.yaml. المستخدم يعدّلها بدون لمس الكود."""
from dataclasses import dataclass
from pathlib import Path

import os

import yaml

# أمثلة مرفقة مع المهارة. شرائح المستخدم الخاصة (SALES_ICP_DIR) تتقدم عليها.
BUNDLED_DIR = Path(__file__).resolve().parents[2] / "assets" / "icp-examples"


def search_dirs() -> list[Path]:
    user = os.environ.get("SALES_ICP_DIR")
    return ([Path(user)] if user else []) + [BUNDLED_DIR]
_REQUIRED = ["code", "name", "description", "specialties", "exclusions", "fit_signals",
             "search_hints", "channel_order", "first_offer"]
_CHANNELS = {"whatsapp", "instagram", "email", "linkedin"}


class IcpConfigError(Exception):
    pass


@dataclass(frozen=True)
class Icp:
    code: str
    name: str
    description: str
    specialties: list[str]
    exclusions: list[str]
    fit_signals: list[str]
    search_hints: list[str]
    source_hints: list[str]
    channel_order: list[str]
    first_offer: str
    decision_maker: str
    team_noun: str = "عاملين"           # ما نعدّه: أطباء، موظفين…
    team_noun_large: str = ""           # المفرد المنصوب للأعداد فوق 10 (موظفًا)
    min_team: int | None = None
    max_team: int | None = None
    max_branches: int | None = None
    discover_priority: str = ""         # توجيه إضافي لمرحلة الاكتشاف
    large_hint: str = ""                # ما يُعدّ «كبيرًا» للفلترة المبكرة


def load_icp(code: str, directory: Path | str | None = None) -> Icp:
    dirs = [Path(directory)] if directory else search_dirs()
    path = next((d / f"{code}.yaml" for d in dirs if (d / f"{code}.yaml").exists()), None)
    if path is None:
        raise IcpConfigError(f"لا يوجد ملف إعدادات للشريحة {code}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    missing = [k for k in _REQUIRED if not data.get(k)]
    if missing:
        raise IcpConfigError(f"مفاتيح ناقصة في {path.name}: {', '.join(missing)}")
    unknown = set(data["channel_order"]) - _CHANNELS
    if unknown:
        raise IcpConfigError(f"قنوات غير معروفة: {', '.join(sorted(unknown))}")
    return Icp(
        code=data["code"], name=data["name"], description=data["description"].strip(),
        specialties=data["specialties"], exclusions=data["exclusions"],
        fit_signals=data["fit_signals"], search_hints=data["search_hints"],
        source_hints=data.get("source_hints", []), channel_order=data["channel_order"],
        first_offer=data["first_offer"], decision_maker=data.get("decision_maker", ""),
        team_noun=data.get("team_noun", "عاملين"), team_noun_large=data.get("team_noun_large", ""),
        min_team=data.get("min_team"),
        max_team=data.get("max_team"), max_branches=data.get("max_branches"),
        discover_priority=data.get("discover_priority", ""), large_hint=data.get("large_hint", ""),
    )


def list_icps(directory: Path | str | None = None) -> list[dict]:
    dirs = [Path(directory)] if directory else search_dirs()
    found: dict[str, dict] = {}
    for d in reversed(dirs):            # الأخير أضعف، فيُكتب فوقه الأقوى
        for path in sorted(d.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if data.get("code") and data.get("name"):
                found[data["code"]] = {"code": data["code"], "name": data["name"]}
    return sorted(found.values(), key=lambda i: i["code"])
