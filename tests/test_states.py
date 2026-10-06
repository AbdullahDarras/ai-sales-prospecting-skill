import pytest

from sales_agent.states import State, InvalidTransition, check_transition, label_ar


def test_happy_path_is_allowed_step_by_step():
    path = [
        State.DISCOVERED, State.ENRICHED, State.VERIFIED, State.SCORED,
        State.DRAFTED, State.PENDING_APPROVAL, State.APPROVED, State.SENT,
    ]
    for current, nxt in zip(path, path[1:]):
        check_transition(current, nxt)


def test_cannot_skip_verification():
    with pytest.raises(InvalidTransition):
        check_transition(State.ENRICHED, State.SCORED)


def test_cannot_send_without_approval():
    with pytest.raises(InvalidTransition):
        check_transition(State.PENDING_APPROVAL, State.SENT)
    with pytest.raises(InvalidTransition):
        check_transition(State.DRAFTED, State.SENT)


def test_sent_is_terminal_except_block():
    with pytest.raises(InvalidTransition):
        check_transition(State.SENT, State.APPROVED)
    check_transition(State.SENT, State.BLOCKED)


@pytest.mark.parametrize("state", [
    State.DISCOVERED, State.ENRICHED, State.VERIFIED, State.SCORED,
    State.DRAFTED, State.PENDING_APPROVAL, State.APPROVED, State.SENT,
    State.UNDECIDED, State.STUCK,
])
def test_opt_out_can_block_from_any_active_state(state):
    check_transition(state, State.BLOCKED)


def test_low_verification_is_discarded_after_verify_stage():
    check_transition(State.ENRICHED, State.DISCARDED)


def test_out_of_icp_only_from_scoring_stage():
    check_transition(State.SCORED, State.OUT_OF_ICP)
    with pytest.raises(InvalidTransition):
        check_transition(State.ENRICHED, State.OUT_OF_ICP)


def test_active_stages_can_become_stuck():
    for s in (State.DISCOVERED, State.ENRICHED, State.VERIFIED,
              State.SCORED, State.DRAFTED, State.APPROVED):
        check_transition(s, State.STUCK)


def test_every_state_has_arabic_label():
    for s in State:
        assert label_ar(s)


def test_undecided_can_be_promoted_back_to_scored_for_drafting():
    check_transition(State.UNDECIDED, State.SCORED)


def test_undecided_cannot_skip_to_approved():
    with pytest.raises(InvalidTransition):
        check_transition(State.UNDECIDED, State.APPROVED)
