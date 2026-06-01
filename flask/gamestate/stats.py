"""Server-side, deck-aware vote statistics for an estimation round.

This is the single source of truth for the numbers a session records and shows
(average, agreement, consensus, ...). It replaces the previous browser-side math
which divided by zero on an empty round and mishandled a `0` vote. Pure module:
no Socket.IO or database coupling, so it is cheap to unit-test and safe to call
from the reveal handler.

Decisions: E3 (consensus = all votes within one deck step; multi-modal tie =
no-consensus), E4 (the modal card is the proposed final value).
"""
from statistics import mean as _mean, median as _median

from gamestate.deck import Deck

# Sentinel for an explicit abstain ("I voted, but don't score me"). The abstain
# *card* itself is wired into the deck/UI in a later slice; the stats already
# handle it so the maths is correct the moment it lands.
ABSTAIN = '?'

# Decks for which a mean/median is meaningful (story points). T_SHIRTS and
# TRUST_VOTE are treated as ordinal — distribution only, no mean (E3 / proposal).
_NUMERIC_DECKS = (Deck.FIBONACCI, Deck.MODIFIED_FIBONACCI, Deck.POWERS)


def is_numeric_deck(deck: Deck) -> bool:
    """True for decks where a mean / median / points-total is meaningful (story
    points). Ordinal decks (T_SHIRTS, TRUST_VOTE) report distribution only — and
    summing their mapped ordinals into a 'total' would be nonsense."""
    return deck in _NUMERIC_DECKS


def compute_stats(votes, deck: Deck) -> dict:
    """Summarise one round of votes.

    `votes` is the list of cast values from non-spectator players who picked a
    card — each an int in `deck.value`, or `ABSTAIN`. Players who have not picked
    are excluded by the caller. `deck` is the active deck.
    """
    numeric_deck = is_numeric_deck(deck)

    abstains = sum(1 for v in votes if v == ABSTAIN)
    cast = [v for v in votes if v != ABSTAIN]
    count = len(cast)

    distribution: dict = {}
    for v in cast:
        distribution[v] = distribution.get(v, 0) + 1

    if count:
        top = max(distribution.values())
        mode = sorted(value for value, n in distribution.items() if n == top)
        agreement = round(top / count, 2)
    else:
        mode = []
        agreement = None

    average = median = low = high = None
    if numeric_deck and count:
        average = round(_mean(cast), 2)
        median = _median(cast)
        low = min(cast)
        high = max(cast)

    unanimous = count > 0 and len(distribution) == 1
    # Consensus (the re-vote gate): all cast votes on the same or adjacent deck
    # cards AND not a multi-modal tie (E3).
    consensus = count > 0 and len(mode) <= 1 and _within_one_step(cast, deck)

    return {
        'numeric': numeric_deck,
        'count': count,
        'abstains': abstains,
        'distribution': distribution,
        'average': average,
        'median': median,
        'mode': mode,
        'low': low,
        'high': high,
        'agreement': agreement,
        'consensus': consensus,
        'unanimous': unanimous,
    }


def _within_one_step(cast, deck: Deck) -> bool:
    """True if every cast vote sits on the same or an adjacent card of the deck.

    Adjacency is measured by position in `deck.value`, not raw value, so the
    non-linear decks (8 and 13 are adjacent on Fibonacci) behave correctly.
    """
    if len(cast) <= 1:
        return True
    order = deck.value
    try:
        indices = [order.index(v) for v in cast]
    except ValueError:
        # A value not on the current deck — can't reason about adjacency.
        return False
    return max(indices) - min(indices) <= 1
