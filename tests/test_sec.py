import pytest

from tirramind.sec import SecClient


def test_refuses_without_contact(monkeypatch):
    monkeypatch.delenv("TIRRAMIND_CONTACT", raising=False)
    with pytest.raises(RuntimeError):
        SecClient()
    with pytest.raises(RuntimeError):
        SecClient("not-an-email")


def test_user_agent_declares_contact():
    c = SecClient("ops@example.com")
    assert "ops@example.com" in c.session.headers["User-Agent"]
    assert c.session.headers["User-Agent"].startswith("tirramind/")


def test_throttle_never_exceeds_ten_per_second():
    t = [0.0]
    slept = []

    def clock():
        return t[0]

    def sleep(s):
        slept.append(s)
        t[0] += s

    c = SecClient("ops@example.com", sleep=sleep, clock=clock)
    for _ in range(25):
        c._throttle()
        t[0] += 0.01
    # 25 requests at 10/s need at least ~1.5s of wall time; the fake clock
    # only advanced 0.25s on its own, so the throttle must have slept.
    assert sum(slept) >= 1.2
    # And at no point were more than 10 timestamps within any 1s window.
    stamps = list(c._sent)
    assert len(stamps) <= 10
