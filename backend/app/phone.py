import re


def normalize_phone(number: str) -> str:
    """Normalize a phone number to E.164 format (+1XXXXXXXXXX for US/Canada).

    Accepts: (555) 123-4567 / 555-123-4567 / 5551234567 / 15551234567 / +15551234567
    Raises ValueError for anything that doesn't resolve to a 10-digit US number.
    """
    digits = re.sub(r"\D", "", number)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    raise ValueError(
        f"Invalid phone number '{number}'. Enter a 10-digit US number, e.g. +15551234567."
    )
