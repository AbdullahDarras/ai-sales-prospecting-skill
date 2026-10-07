"""تصدير العملاء إلى Excel (عربي، من اليمين لليسار) ليُسلَّم لمدير المبيعات.

لا صيغ بالملف عمدًا: أرقام الملخص لقطة بتاريخ التصدير، فيظهر الملف كاملًا بأي معاينة (جوال، بريد).
"""

from __future__ import annotations
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .countries import COUNTRY_AR
from .channels import choose_channel
from .icp_config import IcpConfigError, list_icps, load_icp
from .states import State, label_ar
from .store import Store
from .verify import FIT_READY, VERIFY_FLOOR, VERIFY_READY

SHEET_SUMMARY, SHEET_REVIEW, SHEET_EXCLUDED, SHEET_NOTES = "ملخص", "للتواصل والمراجعة", "مستبعد", "ملاحظات"

_VIABLE = {State.UNDECIDED, State.PENDING_APPROVAL, State.APPROVED}
_EXCLUDED = {State.OUT_OF_ICP, State.DISCARDED, State.REJECTED, State.STUCK, State.BLOCKED}
_CHANNEL_AR = {"whatsapp": "واتساب", "instagram": "إنستغرام", "email": "إيميل", "linkedin": "لينكدإن"}

_REVIEW_HEADERS = ["#", "الاسم", "الشريحة", "الدولة", "المدينة", "الحالة", "درجة التحقق", "درجة الملاءمة",
                   "صاحب القرار", "المسمى", "الهاتف", "واتساب", "الإيميل", "إنستغرام", "الموقع", "لينكدإن",
                   "القناة المقترحة", "سبب التأهيل", "تنبيهات للمراجع", "مصدر الحكم", "سبب الحالة",
                   "الرسالة المقترحة", "تاريخ الاكتشاف"]
_REVIEW_WIDTHS = [5, 34, 26, 11, 12, 15, 12, 12, 22, 24, 17, 17, 26, 24, 28, 24, 14, 60, 60, 18, 36, 70, 14]
_EXCLUDED_HEADERS = ["#", "الاسم", "الشريحة", "الدولة", "المدينة", "الحالة", "درجة التحقق", "سبب الاستبعاد", "الموقع"]
_EXCLUDED_WIDTHS = [5, 34, 26, 11, 12, 16, 12, 70, 28]

_FONT = "Arial"
_HEAD_FILL = PatternFill("solid", fgColor="3B2A8C")
_GOOD, _MID, _BAD = (PatternFill("solid", fgColor=c) for c in ("C6EFCE", "FFEB9C", "FFC7CE"))
_THIN = Side(style="thin", color="D0CCE6")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _font(bold=False, color="000000", size=10):
    return Font(name=_FONT, bold=bold, color=color, size=size)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _link_for(kind: str, value: str) -> str | None:
    value = (value or "").strip()
    if value.lower().startswith("http"):
        return value
    if kind == "instagram" and value:
        return f"https://www.instagram.com/{value.lstrip('@').strip('/')}/"
    return None


def _suggested_channel(lead: dict, values: dict) -> str:
    """القناة المحفوظة إن وُجدت، وإلا نقترحها من البيانات المتاحة بترتيب الشريحة."""
    if values.get("channel"):
        return _CHANNEL_AR.get(values["channel"], "")
    try:
        icp = load_icp(lead["code"])
    except IcpConfigError:
        return ""
    choice = choose_channel(icp.channel_order, values, lead["country"])
    return _CHANNEL_AR.get(choice.primary or "", "")


def _collect(store: Store, segments: dict[str, str]) -> list[dict]:
    out = []
    for lead in store.search_leads(limit=100000):
        fields = store.get_fields(lead["id"])
        if fields.get("demo", {}).get("value") == "1":
            continue
        values = {k: v["value"] for k, v in fields.items()}
        history = store.history(lead["id"])
        fit_obs = fields.get("fit_reason", {})
        out.append({
            "lead": lead, "v": values, "state": lead["state"],
            "segment": f"{lead['code']} · {segments.get(lead['code'], '')}".strip(" ·"),
            "country": COUNTRY_AR.get(lead["country"], lead["country"]),
            "concerns": [o["value"] for o in store.get_observations(lead["id"], "concern")],
            "reason": history[-1]["reason"] if history else "",
            "fit_source": fit_obs.get("source_url", ""),
            "discovered": lead["created_at"][:10],
            "channel": _suggested_channel(lead, values),
        })
    return out


def _write_table(ws, headers, widths, rows, link_cols=()):
    ws.sheet_view.rightToLeft = True
    ws.append(headers)
    for cell in ws[1]:
        cell.font = _font(bold=True, color="FFFFFF")
        cell.fill = _HEAD_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _BORDER
    ws.row_dimensions[1].height = 30
    for r in rows:
        ws.append(r)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = _font()
            cell.alignment = Alignment(vertical="top", wrap_text=True, horizontal="right")
            cell.border = _BORDER
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions


def _score_fill(cell, score, good_at):
    if score is None:
        return
    cell.fill = _GOOD if score >= good_at else _MID if score >= VERIFY_FLOOR else _BAD
    cell.alignment = Alignment(horizontal="center", vertical="top")


def _hyperlink(cell, target):
    if target:
        cell.hyperlink = target
        cell.font = Font(name=_FONT, size=10, color="0563C1", underline="single")


def _review_sheet(wb, items):
    ws = wb.create_sheet(SHEET_REVIEW)
    items = sorted(items, key=lambda i: (-(_int(i["v"].get("verification_score")) or 0),
                                         -(_int(i["v"].get("fit_score")) or 0)))
    rows = []
    for n, i in enumerate(items, 1):
        v = i["v"]
        rows.append([
            n, i["lead"]["name"], i["segment"], i["country"], i["lead"]["city"], label_ar(i["state"]),
            _int(v.get("verification_score")), _int(v.get("fit_score")),
            v.get("decision_maker_name", ""), v.get("decision_maker_title", ""),
            v.get("phone", ""), v.get("whatsapp", ""), v.get("email", ""), v.get("instagram", ""),
            v.get("website", ""), v.get("linkedin_url", ""),
            i["channel"], v.get("fit_reason", ""),
            "\n".join(f"• {c}" for c in i["concerns"]), "المصدر" if i["fit_source"].startswith("http") else "",
            i["reason"], v.get("message", ""), i["discovered"],
        ])
    _write_table(ws, _REVIEW_HEADERS, _REVIEW_WIDTHS, rows)
    col = {h: n for n, h in enumerate(_REVIEW_HEADERS, 1)}
    for r, i in enumerate(items, 2):
        _score_fill(ws.cell(r, col["درجة التحقق"]), ws.cell(r, col["درجة التحقق"]).value, VERIFY_READY)
        _score_fill(ws.cell(r, col["درجة الملاءمة"]), ws.cell(r, col["درجة الملاءمة"]).value, FIT_READY)
        v = i["v"]
        _hyperlink(ws.cell(r, col["الموقع"]), _link_for("website", v.get("website")))
        _hyperlink(ws.cell(r, col["إنستغرام"]), _link_for("instagram", v.get("instagram")))
        _hyperlink(ws.cell(r, col["لينكدإن"]), _link_for("linkedin", v.get("linkedin_url")))
        _hyperlink(ws.cell(r, col["مصدر الحكم"]), i["fit_source"] if i["fit_source"].startswith("http") else None)
    return ws


def _excluded_sheet(wb, items):
    ws = wb.create_sheet(SHEET_EXCLUDED)
    items = sorted(items, key=lambda i: -(_int(i["v"].get("verification_score")) or 0))
    rows = [[n, i["lead"]["name"], i["segment"], i["country"], i["lead"]["city"], label_ar(i["state"]),
             _int(i["v"].get("verification_score")), i["reason"], i["v"].get("website", "")]
            for n, i in enumerate(items, 1)]
    _write_table(ws, _EXCLUDED_HEADERS, _EXCLUDED_WIDTHS, rows)
    for r, i in enumerate(items, 2):
        _score_fill(ws.cell(r, 7), ws.cell(r, 7).value, VERIFY_READY)
        _hyperlink(ws.cell(r, 9), _link_for("website", i["v"].get("website")))
    return ws


def _summary_sheet(wb, items, exported: date):
    ws = wb.create_sheet(SHEET_SUMMARY, 0)
    ws.sheet_view.rightToLeft = True
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 14

    def put(row, label, value=None, bold=False, fill=None):
        a = ws.cell(row, 1, label)
        a.font = _font(bold=bold, size=12 if bold else 10, color="FFFFFF" if fill else "000000")
        a.alignment = Alignment(horizontal="right", vertical="center")
        if value is not None:
            b = ws.cell(row, 2, value)
            b.font = _font(bold=bold)
            b.alignment = Alignment(horizontal="center")
        if fill:
            a.fill = fill
            ws.cell(row, 2).fill = fill

    put(1, "ملخص العملاء المحتملين", bold=True, fill=_HEAD_FILL)
    put(2, f"لقطة بتاريخ التصدير: {exported.isoformat()} (الأرقام ثابتة ولا تتحدّث)")
    put(4, "الإجمالي", len(items), bold=True)
    r = 6
    for title, key in (("حسب الحالة", "state"), ("حسب الشريحة", "segment"), ("حسب الدولة", "country")):
        put(r, title, bold=True, fill=_HEAD_FILL)
        r += 1
        counts: dict[str, int] = {}
        for i in items:
            label = label_ar(i[key]) if key == "state" else i[key]
            counts[label] = counts.get(label, 0) + 1
        for label, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            put(r, label, n)
            r += 1
        r += 1


_NOTES = [
    ("عن هذا الملف", True),
    ("جُمعت هذه القائمة آليًا بوكيل ذكاء اصطناعي من مصادر عامة على الإنترنت (مواقع المنشآت، حسابات التواصل، الأدلة، الخرائط).", False),
    ("لم يتواصل معها أحد بعد. كل رسالة مقترحة مسودة تحتاج اعتماد صاحب الحساب قبل أي إرسال.", False),
    ("", False),
    ("كيف تُقرأ الدرجات", True),
    ("درجة التحقق (0 إلى 100): تقيس صحة بيانات المنشأة: وجودها ونشاطها، وتطابق اسمها ورقمها بين مصادر مستقلة، وصلاحية قنوات الاتصال، وتأكيد صاحب القرار.", False),
    (f"درجة الملاءمة (0 إلى 100): تقيس مطابقتها للفئة المستهدفة وفق قواعد الشريحة. العتبة الآلية للجاهزية: تحقق {VERIFY_READY} وملاءمة {FIT_READY}.", False),
    ("الألوان: أخضر = فوق العتبة، أصفر = متوسط، أحمر = منخفض.", False),
    ("", False),
    ("معاني الحالات", True),
    ("غير محسوم: الأدلة لا تكفي لقرار آلي، وتحتاج حكم إنسان. اقرأ عمود التنبيهات.", False),
    ("بانتظار الاعتماد: الرسالة جاهزة وتنتظر موافقة صاحب الحساب.", False),
    ("مستبعد: خارج الفئة (مثل حجم الشركة)، أو بيانات ضعيفة لا تستحق التواصل.", False),
    ("", False),
    ("تنبيهات مهمة قبل التواصل", True),
    ("لا عميل في هذه القائمة اجتاز العتبة الآلية بعد. القائمة نقطة بداية للمراجعة وليست أسماء مؤكدة.", False),
    ("أرقام الهاتف وأسماء المالكين من صفحات عامة ولم تُؤكَّد بمكالمة. تحقق منها قبل التواصل.", False),
    ("حالة المنشأة على خرائط جوجل وتواريخ النشر على إنستغرام لم تكن متاحة للوكيل بشكل مباشر، فاعتمد على نظرتك لها.", False),
    ("أي تضارب لاحظه الوكيل بين المصادر مذكور بعمود «تنبيهات للمراجع».", False),
]


def _notes_sheet(wb):
    ws = wb.create_sheet(SHEET_NOTES)
    ws.sheet_view.rightToLeft = True
    ws.column_dimensions["A"].width = 120
    for r, (text, head) in enumerate(_NOTES, 1):
        c = ws.cell(r, 1, text)
        c.font = _font(bold=head, size=12 if head else 10, color="3B2A8C" if head else "000000")
        c.alignment = Alignment(wrap_text=True, vertical="top", horizontal="right")


def build_workbook(store: Store, today: date | None = None) -> Workbook:
    segments = {i["code"]: i["name"] for i in list_icps()}
    items = _collect(store, segments)
    wb = Workbook()
    wb.remove(wb.active)
    _summary_sheet(wb, items, today or datetime.now().date())
    _review_sheet(wb, [i for i in items if i["state"] in _VIABLE])
    _excluded_sheet(wb, [i for i in items if i["state"] in _EXCLUDED])
    _notes_sheet(wb)
    return wb


def export_xlsx(store: Store, path, today: date | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    build_workbook(store, today).save(path)
    return path
