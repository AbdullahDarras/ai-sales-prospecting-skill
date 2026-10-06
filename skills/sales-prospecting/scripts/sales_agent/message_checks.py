"""فحوصات آلية على الرسالة قبل أن تصل المستخدم. تعيد قائمة مشاكل (فارغة = سليمة)."""
import re

_PRICE = re.compile(r"سعر|أسعار|اسعار|تكلف|رسوم|دينار|دولار|ريال|درهم|خصم|\$")
_DIALECT = {"شو", "بدي", "ليش", "يلا", "هيك", "كيفك", "شلونك", "شنو", "وش", "ايش", "كتير"}
_TITLES = {"د", "دكتور", "الدكتور", "دكتورة", "الدكتورة", "م", "المهندس", "أ", "الأستاذ"}
MIN_LEN, MAX_LEN = 250, 1200


def check_message(message: str, *, company: str, sender: str, decision_maker: str | None,
                  observation_url: str | None, known_urls: set[str]) -> list[str]:
    problems = []
    if _PRICE.search(message):
        problems.append("الرسالة تذكر السعر أو التكلفة")
    if "لن نراسلكم" not in message:
        problems.append("لا يوجد سطر إلغاء اشتراك واضح")
    if "[" in message or "]" in message:
        problems.append("يوجد نص بديل غير مملوء")
    if not company or "[" in company or company not in message:
        problems.append("اسم الشركة غير مضبوط أو غير موجود بالرسالة")
    if not sender or "[" in sender or sender not in message:
        problems.append("اسم المرسل غير مضبوط أو غير موجود بالتوقيع")
    if decision_maker:
        names = [t for t in re.split(r"[\s.،]+", decision_maker) if t and t not in _TITLES and len(t) >= 3]
        if names and not any(n in message for n in names):
            problems.append("اسم المخاطَب غير مذكور بالرسالة")
    if not observation_url or observation_url not in known_urls:
        problems.append("المصدر غير مخزَّن للملاحظة الواردة بالرسالة")
    if not MIN_LEN <= len(message) <= MAX_LEN:
        problems.append(f"طول الرسالة خارج الحد ({MIN_LEN}-{MAX_LEN} حرفًا)")
    words = set(re.findall(r"[؀-ۿ]+", message))
    if words & _DIALECT:
        problems.append("كلمات عامية، المطلوب فصحى رسمية")
    return problems
