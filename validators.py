import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(value):
    return bool(value) and bool(EMAIL_RE.match(value.strip()))


def is_strong_enough_password(value):
    """Minimal real-world bar: 8+ chars, at least one letter and one digit.
    Not enterprise-grade complexity rules, but enough to stop trivial passwords."""
    if not value or len(value) < 8:
        return False
    has_letter = any(ch.isalpha() for ch in value)
    has_digit = any(ch.isdigit() for ch in value)
    return has_letter and has_digit
