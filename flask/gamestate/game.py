from typing import Optional

from gamestate.deck import Deck
from gamestate.exceptions import (PlayerNotInGameError, InvalidCardValueError,
                                  IssueNotInBacklogError)
from gamestate.player import Player

# Statuses that are terminal for navigation: selecting another issue must not
# silently un-mark an estimate that was already accepted.
_TERMINAL_STATUSES = ('estimated',)


class Game:
    """Class representing the state of a game of Planning Poker"""
    def __init__(self, name: str, deck: Deck = Deck.FIBONACCI):
        self.name = name
        self.__state = {}
        self.__deck = deck
        self.__revealed = False
        self.__backlog = []
        self.__current = None
        self.__results = {}

    def player_joins(self, uuid: str, player: Player):
        self.__state[uuid] = player

    def player_leaves(self, uuid: str):
        self.__state.pop(uuid)

    def set_deck(self, deck: Deck):
        existing_deck = self.__deck
        self.__deck = deck
        if existing_deck is not deck:
            self.end_turn()

    def get_deck(self) -> Deck:
        return self.__deck

    def get_revealed(self) -> bool:
        return self.__revealed

    def list_players(self) -> [tuple[str, Player]]:
        return list(self.__state.items())

    def list_players_uuid(self) -> [str]:
        return list(self.__state)

    def get_player(self, uuid: str) -> Player:
        if uuid not in self.__state.keys():
            raise PlayerNotInGameError(f'Player with UUID {uuid} is not in this game')
        return self.__state.get(uuid)
        
    def player_picks(self, uuid: str, card: Optional[int]):
        if card is not None and card not in self.__deck.value:
            raise InvalidCardValueError(f'Card value {card} is not valid. Current deck is {self.__deck.name}')
        player: Player = self.get_player(uuid)
        player.set_hand(card)

    def end_turn(self) -> None:
        self.__revealed = False
        for player in self.__state.values():
            player.clear_hand()

    def is_game_empty(self) -> bool:
        return len(self.__state) == 0

    def has_all_players_picked_card(self) -> bool:
        non_spectators = self.get_non_spectator_players()
        players_that_played_count = sum(1 for p in non_spectators if p.has_picked_card())
        return players_that_played_count == len(non_spectators)

    def get_non_spectator_players(self) -> [Player]:
        return list(filter(lambda p: p.spectator is False, self.__state.values()))

    def state(self) -> dict:
        """Returns the game's state with the players' hands hidden or shown depending on revealed's value"""
        return dict(list(map(
            lambda i: (i[0], i[1].state_with_hand() if self.__revealed else i[1].state()),
            self.list_players()
        )))

    def reveal_hands(self) -> None:
        """Return the players' with their hands"""
        self.__revealed = True

    def info(self) -> dict:
        return {
            'name': self.name,
            'deck': self.__deck.name,
            'revealed': self.__revealed
        }

    def set_backlog(self, issues: list, current=None, results=None) -> None:
        """Hydrate the issue queue (S1). `issues` is an ordered list of dicts,
        `current` the index of the active issue, `results` a map of issue id ->
        list of saved result dicts."""
        self.__backlog = list(issues)
        self.__current = current
        self.__results = results or {}

    def has_backlog(self) -> bool:
        return len(self.__backlog) > 0

    def backlog(self) -> dict:
        """Serialisable backlog payload for broadcast to the room."""
        return {
            'issues': self.__backlog,
            'currentIndex': self.__current,
            'results': self.__results,
        }

    def current_issue(self) -> Optional[dict]:
        """The in-memory dict of the issue under the pointer, or None."""
        if self.__current is None or not (0 <= self.__current < len(self.__backlog)):
            return None
        return self.__backlog[self.__current]

    def select_issue(self, index: int) -> list:
        """Move the current-issue pointer to `index` and start a fresh vote (S4).

        Reverts the previously-active issue to `pending` if it was never completed,
        flips the target to `estimating` (which re-opens a parked issue, S6), and
        clears the table so prior votes don't carry over. Returns the list of issue
        dicts whose status changed, so the caller persists exactly those."""
        if not (0 <= index < len(self.__backlog)):
            raise IssueNotInBacklogError(f'No issue at index {index} in the backlog')
        changed = []
        previous = self.current_issue()
        if previous is not None and previous['status'] == 'estimating':
            previous['status'] = 'pending'
            changed.append(previous)
        self.__current = index
        issue = self.__backlog[index]
        if issue['status'] not in _TERMINAL_STATUSES and issue['status'] != 'estimating':
            issue['status'] = 'estimating'
            if issue not in changed:
                changed.append(issue)
        self.end_turn()
        return changed

    def get_cast_votes(self) -> list:
        """The hands of non-spectators who have picked — the input to stats (S5)."""
        return [p.get_hand() for p in self.get_non_spectator_players() if p.has_picked_card()]

    def current_round(self) -> int:
        """1-based round number for the current issue: one past what's been recorded."""
        issue = self.current_issue()
        if issue is None:
            return 1
        return len(self.__results.get(issue['id'], [])) + 1

    def record_round(self, round_number: int, final_value, average, median,
                     agreement, deck_name: str, voter_count: int) -> None:
        """Mirror a recorded round into the in-memory results so the backlog payload
        and `current_round()` stay correct without re-reading the DB (S5)."""
        issue = self.current_issue()
        if issue is None:
            return
        self.__results.setdefault(issue['id'], []).append({
            'round': round_number,
            'finalValue': final_value,
            'average': average,
            'median': median,
            'agreement': agreement,
            'deck': deck_name,
            'voterCount': voter_count,
        })

    def mark_current(self, status: str) -> Optional[dict]:
        issue = self.current_issue()
        if issue is not None:
            issue['status'] = status
        return issue

    def park_current(self, status: str, reason=None) -> Optional[dict]:
        """Flag the current issue as needs-refinement / skipped, with a reason (S6)."""
        issue = self.current_issue()
        if issue is not None:
            issue['status'] = status
            issue['parkReason'] = reason
        return issue

    def advance_to_next_pending(self) -> list:
        """Move the pointer to the next still-`pending` issue (wrapping once so no
        pending issue is stranded) and re-open it; clear the table. Returns the list
        of changed issue dicts to persist. Pointer becomes None when none remain."""
        start = (self.__current + 1) if self.__current is not None else 0
        order = list(range(start, len(self.__backlog))) + list(range(0, start))
        next_index = next((i for i in order if self.__backlog[i]['status'] == 'pending'), None)
        self.__current = next_index
        changed = []
        if next_index is not None:
            issue = self.__backlog[next_index]
            issue['status'] = 'estimating'
            changed.append(issue)
        self.end_turn()
        return changed
