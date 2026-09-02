"""Letter details for DocGen: the seven fields an update letter needs.

The details record holds five fields beyond the claim id and status. It has
no place for an amount or an address, so neither can ever be served (see
``intent/letters-claim-details-prefill/spec.md``, R2). ``status`` always comes
from ``app.claims.get_status`` so this lookup and the status route can never
disagree.

Every value here is a placeholder fixture, as ``STATUSES`` is.
"""

from app.claims import get_status


class LettersUnavailable(Exception):
    """The source of letter details cannot be reached. The HTTP layer maps
    this to ``503``. The fixture never raises it; a future feed will."""


DETAILS = {
    "C-1001": {
        "customer_name": "B. Example",
        "policy_number": "P-10001",
        "date_of_loss": "2026-08-02",
        "next_step": "Awaiting documents from customer",
        "handler_name": "H. Handler",
    },
    "C-1002": {
        "customer_name": "A. Example",
        "policy_number": "P-88213",
        "date_of_loss": "2026-08-14",
        "next_step": "Awaiting engineer's report",
        "handler_name": "H. Handler",
    },
    "C-1003": {
        "customer_name": "C. Example",
        "policy_number": "P-10003",
        "date_of_loss": "2026-07-21",
        "next_step": "Payment being arranged",
        "handler_name": "K. Handler",
    },
    "C-1004": {
        "customer_name": "D. Example",
        "policy_number": "P-10004",
        "date_of_loss": "2026-06-30",
        "next_step": None,
        "handler_name": None,
    },
}


def get_letter_details(claim_id: str) -> dict:
    """Return the seven letter fields for a claim id, in spec order.

    Raises ``KeyError`` for an unknown id and ``LettersUnavailable`` when the
    source cannot be reached. The result is built field by field from a fixed
    allow-list, never by copying the record, so a field added to the record
    later cannot reach a letter without a change here.
    """
    record = DETAILS[claim_id]
    return {
        "claim_id": claim_id,
        "customer_name": record["customer_name"],
        "policy_number": record["policy_number"],
        "status": get_status(claim_id),
        "date_of_loss": record["date_of_loss"],
        "next_step": record["next_step"],
        "handler_name": record["handler_name"],
    }
