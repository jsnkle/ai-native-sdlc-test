import pytest
from app.claims import get_status


def test_known_claim():
    assert get_status("C-1001") == "received"


def test_unknown_claim():
    with pytest.raises(KeyError):
        get_status("C-9999")


def test_status_history_is_recorded():
    # WIP: status history is out of scope for claims-status-self-service and does not exist yet.
    from app.claims import get_status_history
    assert get_status_history("C-1001") == ["received"]

# second attempt, still WIP
