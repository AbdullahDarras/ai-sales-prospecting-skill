"""قرارات الاعتماد على السجلات البانتظار. تستدعيها الواجهة."""

from __future__ import annotations
from .states import State
from .store import Store


class ApprovalError(Exception):
    pass


def _lead_in(store: Store, lead_id: str, allowed: set[State], what: str) -> dict:
    try:
        lead = store.get_lead(lead_id)
    except KeyError:
        raise ApprovalError("العميل غير موجود") from None
    if lead["state"] not in allowed:
        raise ApprovalError(f"العميل ليس {what} ({lead['state'].value})")
    return lead


def _pending_lead(store: Store, lead_id: str) -> dict:
    return _lead_in(store, lead_id, {State.PENDING_APPROVAL}, "بانتظار الاعتماد")


def _clean_message(message: str) -> str:
    message = (message or "").strip()
    if not message:
        raise ApprovalError("نص الرسالة فارغ")
    return message


def approve(store: Store, lead_id: str, message: str, channel: str | None = None) -> None:
    _pending_lead(store, lead_id)
    message = _clean_message(message)
    if "[" in message or "]" in message:
        raise ApprovalError("الرسالة فيها نص بديل غير مملوء مثل [اسم الشركة]. عدّله ثم اعتمد")
    if channel is None:
        suggested = store.get_fields(lead_id).get("channel")
        channel = suggested["value"] if suggested else ""
    store.set_field(lead_id, "message_final", message, "ui", "user", 1.0)
    store.set_field(lead_id, "channel_final", channel, "ui", "user", 1.0)
    store.transition(lead_id, State.APPROVED, "اعتماد من المستخدم")


def reject(store: Store, lead_id: str, reason: str = "") -> None:
    _lead_in(store, lead_id, {State.PENDING_APPROVAL, State.UNDECIDED}, "بانتظار الاعتماد أو المراجعة")
    store.transition(lead_id, State.REJECTED, reason.strip() or "رفض من المستخدم")


def edit_message(store: Store, lead_id: str, message: str) -> None:
    _pending_lead(store, lead_id)
    store.set_field(lead_id, "message", _clean_message(message), "ui", "user", 1.0)
