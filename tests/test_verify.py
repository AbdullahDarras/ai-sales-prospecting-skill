import pytest

from sales_agent.states import State
from sales_agent.verify import (
    Evidence, names_match, normalize_name, parse_phone, route, verification_score,
)


@pytest.mark.parametrize("raw,country,e164,mobile", [
    ("+966 50 000 0001", "SA", "+966500000001", True),
    ("0500000001", "SA", "+966500000001", True),
    ("00966500000001", "SA", "+966500000001", True),
    ("966500000001", "SA", "+966500000001", True),
    ("011 234 5678", "SA", "+966112345678", False),
    ("+974 5512 3456", "QA", "+97455123456", True),
    ("+965 9912 3456", "KW", "+96599123456", True),
    ("+968 9123 4567", "OM", "+96891234567", True),
    ("050 123 4567", "AE", "+971501234567", True),
    ("0791234567", "JO", "+962791234567", True),
    ("+966 9200 05097", "SA", "+966920005097", False),   # رقم موحّد لشركة
    ("920005097", "SA", "+966920005097", False),
])
def test_parse_phone_accepts_valid_numbers_in_many_formats(raw, country, e164, mobile):
    phone = parse_phone(raw, country)
    assert phone.e164 == e164
    assert phone.is_mobile is mobile


@pytest.mark.parametrize("raw,country", [
    ("12345", "SA"), ("+966 40 000 0001", "SA"), ("", "SA"), ("abc", "QA"),
    ("+971 50 123 4567", "SA"),  # رمز دولة مختلف عن دولة السجل
    ("+974 1234 5678", "QA"),
])
def test_parse_phone_rejects_invalid_numbers(raw, country):
    assert parse_phone(raw, country) is None


def test_normalize_name_ignores_diacritics_alef_forms_and_ta_marbuta():
    assert normalize_name("عِيادة  الأمل لطبّ الأسنان") == normalize_name("عيادة الامل لطب الاسنان")
    assert normalize_name("مركز الشفاء") == normalize_name("مركز الشفاء ")


def test_names_match_tolerates_generic_words_and_the_prefix():
    assert names_match("عيادة الواحة لطب الأسنان", "الواحة لطب الأسنان")
    assert names_match("عيادة الواحة", "مركز واحة")
    assert not names_match("عيادة الواحة لطب الأسنان", "عيادة النور لطب الأسنان")


def ev(**kw):
    base = dict(
        website_up=None, maps_status="unknown", social_last_post_days=None,
        identity=[], email=None, email_domain_resolves=None,
        decision_maker_sources=0, country="SA", phone=None,
    )
    base.update(kw)
    return Evidence(**base)


def test_strong_evidence_scores_high_and_lists_each_check():
    score, checks = verification_score(ev(
        website_up=True, maps_status="open", social_last_post_days=10,
        identity=[
            {"source_class": "maps", "name": "عيادة الواحة", "phone": "+966500000001"},
            {"source_class": "own_site", "name": "الواحة لطب الأسنان", "phone": "0500000001"},
        ],
        phone="+966500000001", email="a@gmail.com", email_domain_resolves=True,
        decision_maker_sources=2,
    ))
    assert score >= 90
    assert {"existence", "cross_match", "contacts", "decision_maker"} <= set(checks)
    assert all("points" in c and "note" in c for c in checks.values())


def test_empty_evidence_scores_zero_without_crashing():
    score, checks = verification_score(ev())
    assert score == 0


def test_closed_on_maps_zeroes_the_maps_part_and_is_noted():
    _, checks = verification_score(ev(website_up=True, maps_status="closed"))
    assert "مغلق" in checks["existence"]["note"]


def test_stale_social_account_does_not_count_as_active():
    fresh, _ = verification_score(ev(social_last_post_days=20))
    stale, _ = verification_score(ev(social_last_post_days=200))
    assert fresh > stale


def test_single_source_cannot_reach_cross_match_full_points():
    one, c1 = verification_score(ev(identity=[
        {"source_class": "maps", "name": "عيادة الواحة", "phone": "+966500000001"}]))
    two, c2 = verification_score(ev(identity=[
        {"source_class": "maps", "name": "عيادة الواحة", "phone": "+966500000001"},
        {"source_class": "own_site", "name": "عيادة الواحة", "phone": "0500000001"}]))
    assert c2["cross_match"]["points"] > c1["cross_match"]["points"]


def test_two_sources_from_same_class_are_not_independent():
    _, checks = verification_score(ev(identity=[
        {"source_class": "maps", "name": "عيادة الواحة", "phone": "+966500000001"},
        {"source_class": "maps", "name": "عيادة الواحة", "phone": "+966500000001"}]))
    assert checks["cross_match"]["points"] < 30


def test_conflicting_phones_across_sources_lower_the_score():
    agree, _ = verification_score(ev(country="SA", identity=[
        {"source_class": "maps", "name": "عيادة الواحة", "phone": "+966500000001"},
        {"source_class": "own_site", "name": "عيادة الواحة", "phone": "0500000001"}]))
    conflict, c = verification_score(ev(country="SA", identity=[
        {"source_class": "maps", "name": "عيادة الواحة", "phone": "+966500000001"},
        {"source_class": "own_site", "name": "عيادة الواحة", "phone": "0555555555"}]))
    assert conflict < agree
    assert "تضارب" in c["cross_match"]["note"]


def test_official_source_agreement_adds_weight():
    plain, _ = verification_score(ev(identity=[
        {"source_class": "maps", "name": "عيادة الواحة", "phone": "+966500000001"},
        {"source_class": "directory", "name": "عيادة الواحة", "phone": "0500000001"}]))
    official, _ = verification_score(ev(identity=[
        {"source_class": "maps", "name": "عيادة الواحة", "phone": "+966500000001"},
        {"source_class": "official", "name": "عيادة الواحة", "phone": "0500000001"}]))
    assert official > plain


def test_any_email_provider_is_accepted_when_domain_resolves():
    gmail, _ = verification_score(ev(email="clinic@gmail.com", email_domain_resolves=True))
    own, _ = verification_score(ev(email="info@oasis-clinic.com", email_domain_resolves=True))
    bad_format, _ = verification_score(ev(email="not-an-email", email_domain_resolves=True))
    assert gmail == own > bad_format


def test_decision_maker_confirmed_by_two_sources_beats_one_or_none():
    two, _ = verification_score(ev(decision_maker_sources=2))
    one, _ = verification_score(ev(decision_maker_sources=1))
    none, c = verification_score(ev(decision_maker_sources=0))
    assert two > one > none
    assert "جهة اتصال فقط" in c["decision_maker"]["note"]


def test_route_discards_low_verification_first():
    assert route(40, 95, None).state == State.DISCARDED


def test_route_hard_exclusion_goes_out_of_icp_with_reason():
    r = route(90, 90, "مستشفى كبير")
    assert r.state == State.OUT_OF_ICP and "مستشفى" in r.reason


def test_route_ready_when_both_scores_high_and_reviewer_agrees():
    assert route(80, 75, None).ready is True


def test_route_middle_scores_are_undecided():
    assert route(60, 90, None).state == State.UNDECIDED
    assert route(90, 60, None).state == State.UNDECIDED


def test_route_reviewer_disagreement_downgrades_to_undecided():
    r = route(90, 90, None, reviewer_disagrees=True)
    assert r.state == State.UNDECIDED and r.ready is False


def test_route_thresholds_are_boundaries():
    assert route(75, 70, None).ready is True
    assert route(74, 70, None).ready is False
    assert route(75, 69, None).ready is False
    assert route(50, 90, None).state == State.UNDECIDED
    assert route(49, 90, None).state == State.DISCARDED


def test_direct_mobile_vs_unified_company_number_is_flagged_as_conflict():
    agree, _ = verification_score(ev(country="SA", identity=[
        {"source_class": "own_site", "name": "مركز مراس الخليج", "phone": "+966541344479"},
        {"source_class": "directory", "name": "مراس الخليج الطبي", "phone": "0541344479"}]))
    conflict, c = verification_score(ev(country="SA", identity=[
        {"source_class": "own_site", "name": "مركز مراس الخليج", "phone": "+966541344479"},
        {"source_class": "directory", "name": "مراس الخليج الطبي", "phone": "+966 9200 05097"}]))
    assert conflict < agree
    assert "تضارب" in c["cross_match"]["note"]
