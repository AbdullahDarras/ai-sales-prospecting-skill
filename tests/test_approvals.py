import pytest

from sales_agent.approvals import ApprovalError, approve, edit_message, reject
from sales_agent.states import State
from sales_agent.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "leads.db")


def pending_lead(store, name="عيادة النور", message="السلام عليكم دكتور"):
    lead_id = store.add_lead("VIS-1", "SA", "الرياض", name)
    for s in (State.ENRICHED, State.VERIFIED, State.SCORED, State.DRAFTED, State.PENDING_APPROVAL):
        store.transition(lead_id, s, "test")
    store.set_field(lead_id, "message", message, "system", "system", 1.0)
    return lead_id


def test_approve_stores_final_message_and_channel_and_moves_to_approved(store):
    lead_id = pending_lead(store)
    approve(store, lead_id, "نص نهائي معدّل", channel="whatsapp")
    assert store.get_lead(lead_id)["state"] == State.APPROVED
    fields = store.get_fields(lead_id)
    assert fields["message_final"]["value"] == "نص نهائي معدّل"
    assert fields["channel_final"]["value"] == "whatsapp"


def test_approve_without_channel_keeps_suggested_channel(store):
    lead_id = pending_lead(store)
    store.set_field(lead_id, "channel", "email", "system", "system", 1.0)
    approve(store, lead_id, "نص")
    assert store.get_fields(lead_id)["channel_final"]["value"] == "email"


def test_approve_with_blank_message_is_refused_and_state_unchanged(store):
    lead_id = pending_lead(store)
    with pytest.raises(ApprovalError):
        approve(store, lead_id, "   ")
    assert store.get_lead(lead_id)["state"] == State.PENDING_APPROVAL


def test_approve_lead_not_pending_is_refused(store):
    lead_id = store.add_lead("VIS-1", "SA", "الرياض", "عيادة")
    with pytest.raises(ApprovalError):
        approve(store, lead_id, "x")
    assert store.get_lead(lead_id)["state"] == State.DISCOVERED


def test_approve_unknown_lead_is_refused(store):
    with pytest.raises(ApprovalError):
        approve(store, "nope", "x")


def test_reject_moves_to_rejected_and_keeps_reason(store):
    lead_id = pending_lead(store)
    reject(store, lead_id, "خارج الاهتمام")
    assert store.get_lead(lead_id)["state"] == State.REJECTED
    assert store.history(lead_id)[-1]["reason"] == "خارج الاهتمام"


def test_edit_updates_message_and_keeps_pending(store):
    lead_id = pending_lead(store)
    edit_message(store, lead_id, "نسخة جديدة")
    assert store.get_lead(lead_id)["state"] == State.PENDING_APPROVAL
    assert store.get_fields(lead_id)["message"]["value"] == "نسخة جديدة"


def test_edit_with_blank_message_is_refused(store):
    lead_id = pending_lead(store)
    with pytest.raises(ApprovalError):
        edit_message(store, lead_id, "")


def test_approve_refuses_message_with_unfilled_placeholder(store):
    lead_id = pending_lead(store)
    with pytest.raises(ApprovalError) as e:
        approve(store, lead_id, "مع التقدير، سامي | [اسم الشركة]")
    assert "نص بديل" in str(e.value)
    assert store.get_lead(lead_id)["state"] == State.PENDING_APPROVAL


def test_reject_also_works_for_undecided_leads(store):
    lead_id = store.add_lead("VIS-3", "SA", "الرياض", "مطعم")
    for s in (State.ENRICHED, State.VERIFIED, State.SCORED, State.UNDECIDED):
        store.transition(lead_id, s, "test")
    reject(store, lead_id, "ليس مناسبًا")
    assert store.get_lead(lead_id)["state"] == State.REJECTED
