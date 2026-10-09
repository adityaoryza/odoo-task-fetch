"""Read a choice such as "1,3-5" from a numbered list."""

from __future__ import annotations


def parse_selection(text: str, count: int) -> list[int]:
    """Return the chosen positions (1-based, in the order given, without repeats) of a list of `count` items.

    Accepts numbers and ranges separated by commas or spaces: `2`, `1,3`, `2-4`, `1 3-5`. Raises ValueError with a
    message for the user when something is not understood or out of range.
    """
    chosen: list[int] = []
    for part in text.replace(",", " ").split():
        low, dash, high = part.partition("-")
        if not low.isdigit() or (dash and not high.isdigit()):
            raise ValueError(f"'{part}' is not a number or a range like 2-4")
        start, end = int(low), int(high) if dash else int(low)
        if start > end:
            raise ValueError(f"'{part}' is a range written backwards")
        for number in range(start, end + 1):
            if not 1 <= number <= count:
                raise ValueError(f"{number} is not in the list (1-{count})")
            if number not in chosen:
                chosen.append(number)
    if not chosen:
        raise ValueError("Nothing chosen")
    return chosen
