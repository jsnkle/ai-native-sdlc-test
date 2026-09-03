"""Claims status lookup for the customer portal."""

STATUSES = {"C-1001": "received", "C-1002": "in_review", "C-1003": "approved", "C-1004": "paid"}


def get_status(claim_id: str) -> str:
    """Return the status for a claim id, or raise KeyError if unknown."""
    return STATUSES[claim_id]

def broken(:
    pass
