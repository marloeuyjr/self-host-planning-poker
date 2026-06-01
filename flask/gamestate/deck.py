from enum import Enum


class Deck(Enum):
    """List of the decks of cards available.

    The string `'?'` is the abstain card ("voted, but I don't understand the issue
    well enough to size it") — it mirrors `stats.ABSTAIN` and is excluded from the
    mean/median/consensus while still counting toward participation. Hardcoded here
    rather than imported from `stats` to avoid a circular import (stats imports this
    module). Fibonacci is capped at 21 by team choice: anything bigger is "too big,
    split it."
    """
    FIBONACCI = [0, 1, 2, 3, 5, 8, 13, 21, '?']
    MODIFIED_FIBONACCI = [0, 0.5, 1, 2, 3, 5, 8, 13, 20, 40, 100]
    POWERS = [0, 1, 2, 4, 8, 16, 32, 64]
    TRUST_VOTE = [0, 1, 2, 3, 4, 5]
    T_SHIRTS = [1, 2, 3, 4, 5, 6, 7]  # Each value maps to a t-shirt size from XXS to XXL
