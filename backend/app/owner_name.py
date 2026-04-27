def parse_owner_name(raw: str) -> tuple[str, str]:
    """Parse a freeform name into (first_name, last_name).

    Comma takes priority — first name is in front of the comma:
        "Doe, John" -> ("Doe", "John")
    Otherwise split on the first whitespace run:
        "John Smith" -> ("John", "Smith")
        "Cher"       -> ("Cher", "")
    Empty / whitespace-only input returns ("", "").
    """
    if raw is None:
        return ("", "")
    s = raw.strip()
    if not s:
        return ("", "")
    if "," in s:
        first, _, last = s.partition(",")
        return (first.strip(), last.strip())
    parts = s.split(None, 1)
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], parts[1].strip())
