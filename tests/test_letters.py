"""Tests for app.letters: pure function tests, no socket."""

from datetime import date

import pytest

from app.claims import STATUSES, get_status
from app.letters import DETAILS, get_letter_details

SEVEN_KEYS = [
    "claim_id",
    "customer_name",
    "policy_number",
    "status",
    "date_of_loss",
    "next_step",
    "handler_name",
]


def test_known_claim_returns_exactly_seven_keys_in_order():
    assert list(get_letter_details("C-1002")) == SEVEN_KEYS


@pytest.mark.parametrize("claim_id", sorted(STATUSES))
def test_status_matches_get_status(claim_id):
    assert get_letter_details(claim_id)["status"] == get_status(claim_id)


def test_unknown_claim_raises_keyerror():
    with pytest.raises(KeyError):
        get_letter_details("C-9999")


def test_paid_claim_has_null_next_step_and_handler():
    result = get_letter_details("C-1004")
    assert result["status"] == "paid"
    assert result["next_step"] is None
    assert result["handler_name"] is None


def test_no_field_named_like_amount_or_address():
    for claim_id in DETAILS:
        for key in get_letter_details(claim_id):
            for banned in ("amount", "address", "postcode", "street"):
                assert banned not in key.lower(), (claim_id, key)


def test_claim_id_and_status_never_null():
    for claim_id in DETAILS:
        result = get_letter_details(claim_id)
        assert result["claim_id"] == claim_id
        assert result["status"] is not None


def test_fixture_covers_every_status_id():
    assert set(DETAILS) == set(STATUSES)


def test_date_of_loss_is_iso_date():
    for claim_id in DETAILS:
        value = get_letter_details(claim_id)["date_of_loss"]
        assert date.fromisoformat(value).isoformat() == value
