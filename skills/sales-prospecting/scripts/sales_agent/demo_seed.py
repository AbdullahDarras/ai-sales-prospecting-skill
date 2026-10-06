"""بيانات تجريبية لمعاينة الواجهة. كلها خيالية وموسومة demo ولا تُستخدم بأي إرسال."""
from .states import State
from .store import Store

_SIGNATURE = "[اسم المرسل] | [اسم الشركة]"

_DEMO = [
    {
        "code": "VIS-1", "country": "SA", "city": "الرياض", "name": "عيادة الواحة لطب الأسنان",
        "fields": {
            "specialty": ("أسنان", "https://maps.example/demo-1", "maps", 0.9),
            "decision_maker_name": ("د. فهد العتيبي", "https://linkedin.example/demo-fahd", "social", 0.8),
            "decision_maker_title": ("المالك والطبيب", "https://oasis-clinic.example/about", "own_site", 0.85),
            "phone": ("+966500000001", "https://oasis-clinic.example/contact", "own_site", 0.85),
            "whatsapp": ("+966500000001", "https://oasis-clinic.example/contact", "own_site", 0.6),
            "instagram": ("@oasis.dental", "https://instagram.example/oasis.dental", "social", 0.9),
            "linkedin_url": ("https://linkedin.example/demo-fahd", "https://linkedin.example/demo-fahd", "social", 0.8),
            "verification_score": ("91", "system", "system", 1.0),
            "verification_sources": ("الخرائط، موقع العيادة، إنستغرام", "system", "system", 1.0),
            "fit_score": ("84", "system", "system", 1.0),
            "fit_reason": ("عيادة أسنان بطبيبين، أعلنت عن فرع جديد قبل شهر، وحسابها نشط لكن التفاعل فيه ضعيف.",
                           "https://instagram.example/oasis.dental/p/demo", "social", 0.75),
            "channel": ("whatsapp", "system", "system", 1.0),
            "channel_alt": ("instagram", "system", "system", 1.0),
            "message": (
                "السلام عليكم ورحمة الله وبركاته، الدكتور فهد العتيبي المحترم،\n\n"
                "تابعتُ حساب عيادة الواحة، ولاحظتُ إعلانكم عن الفرع الجديد قبل شهر، "
                "وأن المحتوى الحالي لا يعكس مستوى العيادة الذي يظهر في الصور.\n\n"
                "يسرّني أن أقدّم لكم تدقيقًا مجانيًا لحساب العيادة خلال 15 دقيقة، "
                "مع ثلاث ملاحظات قابلة للتطبيق فورًا.\n\n"
                "هل يناسبكم أن أرسل لكم الملاحظات هنا؟ وإن لم يكن ذلك مناسبًا فيكفي أن تخبرونا، ولن نراسلكم مجددًا.\n\n"
                f"مع التقدير،\n{_SIGNATURE}",
                "system", "system", 1.0),
        },
    },
    {
        "code": "VIS-1", "country": "QA", "city": "الدوحة", "name": "مركز الشفاء للعلاج الطبيعي",
        "fields": {
            "specialty": ("علاج طبيعي", "https://maps.example/demo-2", "maps", 0.9),
            "email": ("info.shifa.demo@gmail.com", "https://shifa-center.example/contact", "own_site", 0.7),
            "phone": ("+97440000002", "https://maps.example/demo-2", "maps", 0.8),
            "instagram": ("@shifa.physio", "https://instagram.example/shifa.physio", "social", 0.85),
            "verification_score": ("78", "system", "system", 1.0),
            "verification_sources": ("الخرائط، موقع المركز", "system", "system", 1.0),
            "fit_score": ("72", "system", "system", 1.0),
            "fit_reason": ("مركز علاج طبيعي بطبيبين، حسابه نشط بمحتوى قليل التنوع. صاحب القرار غير مؤكد بعد.",
                           "https://instagram.example/shifa.physio", "social", 0.6),
            "channel": ("email", "system", "system", 1.0),
            "channel_alt": ("instagram", "system", "system", 1.0),
            "message": (
                "السلام عليكم ورحمة الله وبركاته،\n\n"
                "تابعتُ حساب مركز الشفاء للعلاج الطبيعي، ولاحظتُ أن المحتوى يتكرر على نمط واحد "
                "رغم تنوع الخدمات التي يقدّمها المركز.\n\n"
                "يسرّني أن أقدّم لكم تدقيقًا مجانيًا للحساب خلال 15 دقيقة، "
                "مع ثلاث ملاحظات قابلة للتطبيق فورًا.\n\n"
                "هل تتفضلون بإرشادي إلى المسؤول عن الحساب لأرسل له الملاحظات؟ "
                "وإن لم يكن ذلك مناسبًا فيكفي أن تخبرونا، ولن نراسلكم مجددًا.\n\n"
                f"مع التقدير،\n{_SIGNATURE}",
                "system", "system", 1.0),
        },
    },
]


def seed_demo(store: Store) -> list[str]:
    ids = []
    for item in _DEMO:
        lead_id = store.add_lead(item["code"], item["country"], item["city"], item["name"])
        ids.append(lead_id)
        if store.get_lead(lead_id)["state"] != State.DISCOVERED:
            continue  # سبق زرعه
        store.set_field(lead_id, "demo", "1", "system", "system", 1.0)
        for field_name, (value, url, source_class, confidence) in item["fields"].items():
            store.set_field(lead_id, field_name, value, url, source_class, confidence)
        for state in (State.ENRICHED, State.VERIFIED, State.SCORED, State.DRAFTED, State.PENDING_APPROVAL):
            store.transition(lead_id, state, "بيانات تجريبية")
    return ids


def clear_demo(store: Store) -> None:
    for lead in store.search_leads(limit=100000):
        if store.get_fields(lead["id"]).get("demo", {}).get("value") == "1":
            store.delete_lead(lead["id"])
