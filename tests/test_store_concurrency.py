"""الواجهة تطلب عدة نقاط معًا والمشغّل يكتب بالخلفية: لا يجوز أن تتداخل الخيوط على اتصال واحد."""
import threading

from sales_agent.states import State
from sales_agent.store import Store


def test_many_threads_reading_and_writing_never_corrupt_results(tmp_path):
    store = Store(tmp_path / "leads.db")
    ids = [store.add_lead("VIS-3", "JO", "عمّان", f"مكان {i}") for i in range(60)]
    for lead_id in ids:
        for s in (State.ENRICHED, State.VERIFIED, State.SCORED, State.UNDECIDED):
            store.transition(lead_id, s, "t")
    errors, stop = [], threading.Event()

    def reader():
        try:
            while not stop.is_set():
                assert sum(store.count_by_state().values()) == 60      # استعلام واحد = لقطة متسقة
                for lead in store.leads_in_state(State.UNDECIDED, limit=500):
                    assert lead["state"] in (State.UNDECIDED, State.REJECTED)
                store.search_leads(limit=500)
                store.count_by_state()
                store.get_fields(ids[0])
        except Exception as e:                                   # noqa: BLE001
            errors.append(repr(e))
            stop.set()

    def writer():
        try:
            for lead_id in ids[:30]:
                store.set_field(lead_id, "note", "x", "https://a.example", "web", 0.5)
                store.transition(lead_id, State.REJECTED, "t")
        except Exception as e:                                   # noqa: BLE001
            errors.append(repr(e))
        finally:
            stop.set()

    threads = [threading.Thread(target=reader) for _ in range(6)] + [threading.Thread(target=writer)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert errors == []
    assert len(store.leads_in_state(State.REJECTED, limit=500)) == 30


def test_each_thread_gets_its_own_connection(tmp_path):
    store = Store(tmp_path / "leads.db")
    seen = []
    t = threading.Thread(target=lambda: seen.append(id(store._db)))
    t.start(); t.join()
    assert seen[0] != id(store._db)
