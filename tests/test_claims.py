import pytest
from app.claims import get_status


def test_known_claim():
    assert get_status("C-1001") == "received"


def test_unknown_claim():
    with pytest.raises(KeyError):
        get_status("C-9999")
