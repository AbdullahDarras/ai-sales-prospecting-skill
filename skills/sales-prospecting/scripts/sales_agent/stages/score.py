"""التقييم: النموذج يقترح، والكود الحتمي يقرر. الفلاتر الحتمية تتغلب على حكم النموذج،
والدرجة العالية بلا دليل مخزَّن تُخفَّض، والحالات الحدّية يراجعها مراجِع معاكس."""
from dataclasses import dataclass

from ..icp_config import Icp
from ..states import State
from ..store import Store
from ..verify import FIT_READY, route
from .common import dossier, is_http, known_urls, latest_values

SCHEMA = {
    "type": "object",
    "properties": {
        "fit_score": {"type": "integer"},
        "excluded_reason": {"type": ["string", "null"]},
        "reason": {"type": "string"},
        "label": {"type": "string", "enum": ["confirmed", "inferred", "unknown"]},
        "evidence_urls": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["fit_score", "excluded_reason", "reason", "label", "evidence_urls"],
}
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {"agrees": {"type": "boolean"}, "objection": {"type": "string"}},
    "required": ["agrees", "objection"],
}
UNPROVEN_CAP = 65


def hard_exclusion(values: dict, icp: Icp) -> str | None:
    if values.get("maps_status") == "closed":
        return "المنشأة مغلقة نهائيًا"
    if values.get("is_private") == "false":
        return "جهة غير خاصة (حكومية أو عامة)"
    team, branches = values.get("team_size"), values.get("branches_count")
    if team:
        def noun(n: int) -> str:
            return icp.team_noun_large if n > 10 and icp.team_noun_large else icp.team_noun
        if icp.max_team and int(team) > icp.max_team:
            return f"أكثر من {icp.max_team} {noun(icp.max_team)} ({team})"
        if icp.min_team and int(team) < icp.min_team:
            return f"أقل من {icp.min_team} {noun(icp.min_team)} ({team})"
    if branches and icp.max_branches and int(branches) > icp.max_branches:
        return f"أكثر من {icp.max_branches} فروع ({branches})"
    return None


def _prompt(store: Store, lead: dict, icp: Icp) -> str:
    return f"""قيّم ملاءمة هذه المنشأة للفئة المستهدفة، اعتمادًا فقط على الأدلة المسجلة أدناه.

الفئة: {icp.name}
الوصف: {icp.description}
التخصصات المقبولة: {', '.join(icp.specialties)}
استبعد إذا: {'؛ '.join(icp.exclusions)}
إشارات ترفع الملاءمة: {'؛ '.join(icp.fit_signals)}

المنشأة: {lead['name']} ({lead['city']})
الأدلة المجمّعة:
{dossier(store, lead['id'])}

أعد: fit_score من 0 إلى 100. وexcluded_reason إن انطبق أي استبعاد (وإلا null). وreason جملة واحدة قصيرة (أقل من 200 حرف) تذكر الدليل الأقوى.
وlabel: confirmed إذا حكمك مبني على أدلة مباشرة مذكورة أعلاه، وinferred إذا استنتجتَه، وunknown إذا الأدلة لا تكفي.
وevidence_urls: روابط من الأدلة أعلاه فقط تدعم حكمك. ممنوع رابط غير مذكور.
لا تعتمد على السعر أو الميزانية بأي شكل. إذا الأدلة لا تكفي فقل unknown ودرجة منخفضة ولا تخمّن."""


def _review_prompt(lead: dict, reason: str, score: int, urls: list[str]) -> str:
    return f"""أنت مراجِع معاكس. حاول إثبات أن هذا الحكم خطأ.

المنشأة: {lead['name']} ({lead['city']})
الحكم: ملاءمة {score}/100. السبب: {reason}
الأدلة: {', '.join(urls) or 'لا شيء'}

هل تجد سببًا وجيهًا أن المنشأة لا تناسب الفئة أو أن الدليل لا يخص هذه المنشأة تحديدًا (تشابه أسماء مثلًا)؟
agrees=true فقط إذا حاولتَ ولم تجد اعتراضًا مقنعًا. وإلا agrees=false مع objection موجز."""


@dataclass
class Assessment:
    score: int
    urls: list[str]
    label: str
    model_exclusion: str | None
    reason: str
    verification: int
    needs_review: bool


class ReviewRequired(Exception):
    """الحالة حدّية: لازم مراجِع معاكس قبل التطبيق. لم يُكتب شيء بالمخزن."""

    def __init__(self, assessment: Assessment):
        super().__init__("review required")
        self.assessment = assessment


def precheck_score(store: Store, lead_id: str, icp: Icp) -> str | None:
    """يطبّق الاستبعاد الحتمي فورًا (بلا حاجة لحكم نموذج). يعيد السبب أو None."""
    excluded = hard_exclusion(latest_values(store, lead_id), icp)
    if not excluded:
        return None
    store.transition(lead_id, State.SCORED, "بدء التقييم")
    store.set_field(lead_id, "fit_score", "0", "system", "system", 1.0)
    store.set_field(lead_id, "fit_reason", excluded, "system", "system", 1.0)
    store.transition(lead_id, State.OUT_OF_ICP, excluded)
    return excluded


def score_brief(store: Store, lead_id: str, icp: Icp) -> dict:
    return {"instructions": _prompt(store, store.get_lead(lead_id), icp), "schema": SCHEMA}


def assess(store: Store, lead_id: str, icp: Icp, result: dict) -> Assessment:
    values = latest_values(store, lead_id)
    verification = int(values.get("verification_score", "0"))
    allowed = known_urls(store, lead_id)
    urls = [u for u in result.get("evidence_urls", []) if u in allowed and is_http(u)]
    score = max(0, min(100, int(result.get("fit_score", 0))))
    if not urls or result.get("label") == "unknown":
        score = min(score, UNPROVEN_CAP)  # لا دليل، لا ثقة
    model_exclusion = (result.get("excluded_reason") or "").strip() or None
    needs_review = not model_exclusion and (60 <= score < 80 or 70 <= verification < 80)
    return Assessment(score, urls, result.get("label", "unknown"), model_exclusion,
                      (result.get("reason") or "").strip()[:300] or "بلا سبب مذكور", verification, needs_review)


def review_brief(store: Store, lead_id: str, a: Assessment) -> dict:
    return {"instructions": _review_prompt(store.get_lead(lead_id), a.reason, a.score, a.urls),
            "schema": REVIEW_SCHEMA}


def apply_score(store: Store, lead_id: str, icp: Icp, result: dict, review: dict | None = None) -> State:
    """الجزء الحتمي: يقيّد حكم النموذج ثم يوجّه. يرفع ReviewRequired إن لزم مراجِع ولم يُمرَّر."""
    if precheck_score(store, lead_id, icp):
        return State.OUT_OF_ICP
    a = assess(store, lead_id, icp, result)
    if a.needs_review and review is None:
        raise ReviewRequired(a)
    disagrees = bool(a.needs_review and not review.get("agrees", False))

    store.transition(lead_id, State.SCORED, "بدء التقييم")
    store.set_field(lead_id, "fit_score", str(a.score), "system", "system", 1.0)
    store.set_field(lead_id, "fit_label", a.label, "system", "system", 1.0)
    store.set_field(lead_id, "fit_reason", a.reason, a.urls[0] if a.urls else "system",
                    "web" if a.urls else "system", 0.7)
    decision = route(a.verification, a.score, a.model_exclusion, reviewer_disagrees=disagrees)
    if decision.state in (State.OUT_OF_ICP, State.UNDECIDED):
        store.transition(lead_id, decision.state, decision.reason)
    return store.get_lead(lead_id)["state"]


def run_score(ask, store: Store, lead_id: str, icp: Icp) -> None:
    if precheck_score(store, lead_id, icp):
        return
    brief = score_brief(store, lead_id, icp)
    result = ask(brief["instructions"], SCHEMA, tools=())
    try:
        apply_score(store, lead_id, icp, result)
    except ReviewRequired as needed:
        rb = review_brief(store, lead_id, needed.assessment)
        review = ask(rb["instructions"], REVIEW_SCHEMA, tools=())
        apply_score(store, lead_id, icp, result, review=review)
