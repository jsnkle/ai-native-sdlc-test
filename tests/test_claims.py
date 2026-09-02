import pytest
from app.claims import get_status


def test_known_claim():
    assert get_status("C-1001") == "received"


def test_unknown_claim():
    with pytest.raises(KeyError):
        get_status("C-9999")


def test_probe_red_on_purpose():
    # Deliberately failing: probes the closing-the-loop workflow's propose path. Close this PR after the test.
    assert False, "closing-the-loop probe"

# push 2
