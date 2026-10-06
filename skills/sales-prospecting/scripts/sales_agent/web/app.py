"""واجهة الويب المحلية: API + صفحة التطبيق. تُربط على 127.0.0.1 فقط."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..approvals import ApprovalError, approve, edit_message, reject
from ..icp_config import list_icps
from ..runner import RunError, RunManager
from ..states import State, label_ar
from ..store import Store

STATIC = Path(__file__).parent / "static"


class ApproveBody(BaseModel):
    message: str = ""
    channel: str | None = None


class RejectBody(BaseModel):
    reason: str = ""


class EditBody(BaseModel):
    message: str = ""


class SettingsBody(BaseModel):
    company_name: str = ""
    sender_name: str = ""


class RunBody(BaseModel):
    code: str = ""
    country: str = ""
    city: str = ""
    count: int | str = 0


def _lead_card(store: Store, lead: dict) -> dict:
    return {
        "id": lead["id"], "code": lead["code"], "country": lead["country"],
        "city": lead["city"], "name": lead["name"],
        "state": lead["state"].value, "state_label": label_ar(lead["state"]),
        "fields": store.get_fields(lead["id"]),
        "concerns": [{"value": o["value"], "source_url": o["source_url"]}
                     for o in store.get_observations(lead["id"], "concern")],
    }


def create_app(store: Store, daily_cap: int = 20, runs: RunManager | None = None) -> FastAPI:
    runs = runs or RunManager(store)
    app = FastAPI(title="نظام المبيعات")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/summary")
    def summary():
        counts = store.count_by_state()
        return {
            "counts": counts,
            "total": sum(counts.values()),
            "sent_today": store.transitions_today(State.SENT),
            "daily_cap": daily_cap,
        }

    @app.get("/api/approvals")
    def approvals():
        leads = store.leads_in_state(State.PENDING_APPROVAL, limit=500)
        return [_lead_card(store, lead) for lead in leads]

    def _run(action):
        try:
            action()
        except ApprovalError as e:
            raise HTTPException(status_code=409, detail=str(e)) from None
        return {"ok": True}

    @app.post("/api/approvals/{lead_id}/approve")
    def approve_lead(lead_id: str, body: ApproveBody):
        return _run(lambda: approve(store, lead_id, body.message, body.channel))

    @app.post("/api/approvals/{lead_id}/reject")
    def reject_lead(lead_id: str, body: RejectBody):
        return _run(lambda: reject(store, lead_id, body.reason))

    @app.post("/api/approvals/{lead_id}/edit")
    def edit_lead(lead_id: str, body: EditBody):
        return _run(lambda: edit_message(store, lead_id, body.message))

    @app.get("/api/leads")
    def leads(state: str | None = None, code: str | None = None,
              country: str | None = None, q: str | None = None):
        try:
            state_filter = State(state) if state else None
        except ValueError:
            raise HTTPException(status_code=422, detail="حالة غير معروفة") from None
        found = store.search_leads(state_filter, code, country, q)
        return [_lead_card(store, lead) for lead in found]

    @app.get("/api/leads/{lead_id}")
    def lead_detail(lead_id: str):
        try:
            lead = store.get_lead(lead_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="العميل غير موجود") from None
        card = _lead_card(store, lead)
        card["observations"] = store.all_observations(lead_id)
        card["history"] = [
            {**h, "to_state": h["to_state"].value,
             "from_state": h["from_state"].value if h["from_state"] else None}
            for h in store.history(lead_id)
        ]
        return card

    @app.get("/api/review")
    def review():
        cards = []
        for lead in store.leads_in_state(State.UNDECIDED, limit=500):
            card = _lead_card(store, lead)
            card["undecided_reason"] = store.history(lead["id"])[-1]["reason"]
            cards.append(card)
        return cards

    @app.post("/api/review/{lead_id}/promote")
    def promote(lead_id: str):
        state = _run_action(lambda: runs.promote(lead_id))
        return {"state": state.value}

    @app.get("/api/icps")
    def icps():
        return list_icps()

    @app.get("/api/settings")
    def get_settings():
        return {"company_name": store.get_setting("company_name"),
                "sender_name": store.get_setting("sender_name")}

    @app.post("/api/settings")
    def save_settings(body: SettingsBody):
        store.set_setting("company_name", body.company_name.strip())
        store.set_setting("sender_name", body.sender_name.strip())
        return {"ok": True}

    def _run_action(action):
        try:
            return action()
        except RunError as e:
            raise HTTPException(status_code=409, detail=str(e)) from None

    @app.post("/api/runs")
    def start_run(body: RunBody):
        return {"id": _run_action(lambda: runs.start(body.model_dump()))}

    @app.get("/api/runs")
    def list_runs():
        return store.list_runs(20)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: int, after: int = 0):
        try:
            run = store.get_run(run_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="التشغيل غير موجود") from None
        run["logs"] = store.get_logs(run_id, after_id=after)
        return run

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: int):
        runs.cancel(run_id)
        return {"ok": True}

    @app.post("/api/runs/{run_id}/resume")
    def resume_run(run_id: int):
        _run_action(lambda: runs.resume(run_id))
        return {"ok": True}

    return app
