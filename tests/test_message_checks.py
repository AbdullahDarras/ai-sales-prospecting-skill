import pytest

from sales_agent.message_checks import check_message

GOOD = (
    "السلام عليكم ورحمة الله وبركاته، الدكتور فهد العتيبي المحترم،\n\n"
    "تابعتُ حساب عيادة الواحة، ولاحظتُ إعلانكم عن الفرع الجديد قبل شهر، "
    "وأن المحتوى الحالي لا يعكس مستوى العيادة الذي يظهر في الصور.\n\n"
    "يسرّني أن أقدّم لكم تدقيقًا مجانيًا لحساب العيادة خلال 15 دقيقة، "
    "مع ثلاث ملاحظات قابلة للتطبيق فورًا.\n\n"
    "هل يناسبكم أن أرسل لكم الملاحظات هنا؟ وإن لم يكن ذلك مناسبًا فيكفي أن تخبرونا، ولن نراسلكم مجددًا.\n\n"
    "مع التقدير،\nسامي المثال | شركة المثال"
)
URLS = {"https://instagram.com/oasis/p/1"}


def check(message=GOOD, **kw):
    args = dict(company="شركة المثال", sender="سامي المثال", decision_maker="د. فهد العتيبي",
                observation_url="https://instagram.com/oasis/p/1", known_urls=URLS)
    args.update(kw)
    return check_message(message, **args)


def test_good_message_passes():
    assert check() == []


@pytest.mark.parametrize("word", ["السعر", "بسعر", "تكلفة", "دينار", "دولار", "ريال", "درهم", "$", "رسوم", "خصم"])
def test_any_price_word_fails(word):
    problems = check(GOOD.replace("مجانيًا", f"مجانيًا {word}"))
    assert any("سعر" in p for p in problems)


def test_missing_opt_out_fails():
    problems = check(GOOD.replace("ولن نراسلكم مجددًا", ""))
    assert any("إلغاء" in p for p in problems)


def test_missing_company_name_fails():
    problems = check(GOOD.replace("شركة المثال", ""))
    assert any("اسم الشركة" in p for p in problems)


def test_unfilled_placeholder_fails():
    problems = check(GOOD.replace("شركة المثال", "[اسم الشركة]"), company="[اسم الشركة]")
    assert any("اسم الشركة" in p for p in problems)


def test_known_decision_maker_name_must_appear():
    problems = check(GOOD.replace("فهد العتيبي", "فلان"))
    assert any("اسم المخاطَب" in p for p in problems)


def test_unknown_decision_maker_skips_name_check():
    assert check(decision_maker=None) == []


def test_observation_must_come_from_a_stored_source():
    problems = check(observation_url="https://invented.example/x")
    assert any("المصدر" in p for p in problems)
    assert any("المصدر" in p for p in check(observation_url=None))


def test_too_short_or_too_long_fails():
    assert any("طول" in p for p in check("السلام عليكم"))
    assert any("طول" in p for p in check(GOOD + " كلمة" * 400))


@pytest.mark.parametrize("dialect", ["شو رأيك", "بدي أساعدكم", "ليش ما ترد", "يلا نبدأ"])
def test_dialect_words_fail_formal_arabic_rule(dialect):
    problems = check(GOOD.replace("يسرّني", dialect + " يسرّني"))
    assert any("فصحى" in p for p in problems)


def test_missing_sender_name_fails():
    problems = check(GOOD.replace("سامي المثال", ""))
    assert any("اسم المرسل" in p for p in problems)


def test_unfilled_sender_placeholder_fails():
    problems = check(GOOD.replace("سامي المثال", "[اسم المرسل]"), sender="[اسم المرسل]")
    assert any("اسم المرسل" in p for p in problems)
