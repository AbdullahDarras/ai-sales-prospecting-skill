import pytest

from sales_agent.states import State, InvalidTransition
from sales_agent.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "leads.db")


def test_new_lead_starts_as_discovered(store):
    lead_id = store.add_lead("VIS-1", "SA", "الرياض", "عيادة النور لطب الأسنان")
    lead = store.get_lead(lead_id)
    assert lead["state"] == State.DISCOVERED
    assert lead["code"] == "VIS-1"
    assert lead["country"] == "SA"


def test_same_business_is_not_added_twice(store):
    a = store.add_lead("VIS-1", "SA", "الرياض", "عيادة النور لطب الأسنان")
    b = store.add_lead("VIS-1", "SA", "الرياض", "  عيادة  النور لطب الأسنان ")
    assert a == b
    assert len(store.leads_in_state(State.DISCOVERED)) == 1


def test_same_name_in_other_country_is_a_different_lead(store):
    a = store.add_lead("VIS-1", "SA", "الرياض", "عيادة النور")
    b = store.add_lead("VIS-1", "KW", "الكويت", "عيادة النور")
    assert a != b


def test_transition_updates_state_and_logs_reason(store):
    lead_id = store.add_lead("VIS-1", "QA", "الدوحة", "عيادة الصفا")
    store.transition(lead_id, State.ENRICHED, "تم جمع الموقع والهاتف")
    assert store.get_lead(lead_id)["state"] == State.ENRICHED
    history = store.history(lead_id)
    assert [h["to_state"] for h in history] == [State.DISCOVERED, State.ENRICHED]
    assert history[-1]["reason"] == "تم جمع الموقع والهاتف"


def test_invalid_transition_is_rejected_and_state_unchanged(store):
    lead_id = store.add_lead("VIS-1", "QA", "الدوحة", "عيادة الصفا")
    with pytest.raises(InvalidTransition):
        store.transition(lead_id, State.SENT, "محاولة تجاوز")
    assert store.get_lead(lead_id)["state"] == State.DISCOVERED


def test_stuck_remembers_previous_state_and_resume_returns_to_it(store):
    lead_id = store.add_lead("VIS-1", "KW", "الكويت", "مركز الشفاء")
    store.transition(lead_id, State.ENRICHED, "ok")
    store.transition(lead_id, State.STUCK, "انتهت المهلة")
    assert store.get_lead(lead_id)["state"] == State.STUCK
    store.resume(lead_id)
    assert store.get_lead(lead_id)["state"] == State.ENRICHED


def test_resume_on_non_stuck_lead_is_rejected(store):
    lead_id = store.add_lead("VIS-1", "KW", "الكويت", "مركز الشفاء")
    with pytest.raises(InvalidTransition):
        store.resume(lead_id)


def test_field_keeps_source_and_confidence(store):
    lead_id = store.add_lead("VIS-1", "SA", "جدة", "عيادة الأمل")
    store.set_field(lead_id, "phone", "+966500000000",
                    source_url="https://example.com/contact",
                    source_class="own_site", confidence=0.8)
    f = store.get_fields(lead_id)["phone"]
    assert f["value"] == "+966500000000"
    assert f["source_url"] == "https://example.com/contact"
    assert f["source_class"] == "own_site"
    assert f["confidence"] == 0.8


def test_setting_same_field_again_keeps_both_observations(store):
    lead_id = store.add_lead("VIS-1", "SA", "جدة", "عيادة الأمل")
    store.set_field(lead_id, "phone", "+966500000000", "https://a.com", "own_site", 0.6)
    store.set_field(lead_id, "phone", "+966500000000", "https://b.com", "maps", 0.7)
    observations = store.get_observations(lead_id, "phone")
    assert {o["source_url"] for o in observations} == {"https://a.com", "https://b.com"}


def test_confidence_must_be_between_zero_and_one(store):
    lead_id = store.add_lead("VIS-1", "SA", "جدة", "عيادة الأمل")
    with pytest.raises(ValueError):
        store.set_field(lead_id, "phone", "x", "https://a.com", "maps", 1.5)


def test_leads_in_state_respects_limit(store):
    for i in range(5):
        store.add_lead("VIS-1", "SA", "الرياض", f"عيادة {i}")
    assert len(store.leads_in_state(State.DISCOVERED, limit=3)) == 3


def test_blocked_contact_is_remembered_across_leads(store):
    lead_id = store.add_lead("VIS-1", "SA", "الرياض", "عيادة النور")
    store.block_contact("+966500000000", reason="طلب إلغاء الاشتراك")
    assert store.is_blocked("+966500000000")
    assert not store.is_blocked("+966511111111")
    store.transition(lead_id, State.BLOCKED, "طلب إلغاء الاشتراك")
    assert store.get_lead(lead_id)["state"] == State.BLOCKED
