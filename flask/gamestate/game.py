from typing import Optional

from gamestate.deck import Deck
from gamestate.exceptions import (PlayerNotInGameError, InvalidCardValueError,
                                  IssueNotInBacklogError)
from gamestate.player import Player


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
        self.__tokens = {}      # rejoin-token -> player id, for reconnect reattach (S7)
        self.__resumed = False  # True after a restart re-opens a mid-flight issue (E5)
        self.__driver = None    # soft host gate on destructive actions (S8, EC4)

    def player_joins(self, uuid: str, player: Player, token=None) -> str:
        """Add a player and return the id actually used (S7).

        A `token` (localStorage-backed, sent on re-join) reattaches the same human
        to their existing slot instead of minting a ghost duplicate. Returns the
        effective player id so the caller can hand it back to the client."""
        effective = uuid
        if token is not None:
            existing = self.__tokens.get(token)
            if existing is not None and existing in self.__state:
                effective = existing   # same human rejoining → reuse the slot
            self.__tokens[token] = effective
        self.__state[effective] = player
        if self.__driver is None:
            self.__driver = effective   # first joiner auto-claims the driver role (EC4)
        return effective

    def player_leaves(self, uuid: str):
        self.__state.pop(uuid)
        if uuid == self.__driver:
            # auto-handoff to whoever remains (None when the room empties)
            self.__driver = next(iter(self.__state), None)

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
        self.__resumed = False
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
        self.__resumed = False   # re-voting after a resume clears the prompt (S7)

    def is_resumed(self) -> bool:
        """True when a worker restart re-opened a mid-flight issue and it hasn't been
        re-revealed or advanced yet — the client shows a 'session resumed' toast (E5)."""
        return self.__resumed

    def driver_id(self):
        return self.__driver

    def is_driver(self, player_id: str) -> bool:
        """Soft host gate (S8): is this player the session driver? Voting is never
        gated; only destructive / record-mutating actions are. NOT authentication."""
        return self.__driver == player_id

    def claim_driver(self, player_id: str) -> None:
        """Take over the driver role — a soft, claimable handoff (EC4)."""
        if player_id in self.__state:
            self.__driver = player_id

    def info(self) -> dict:
        return {
            'name': self.name,
            'deck': self.__deck.name,
            'revealed': self.__revealed,
            'driverId': self.__driver
        }

    def set_backlog(self, issues: list, current=None, results=None) -> None:
        """Hydrate the issue queue (S1). `issues` is an ordered list of dicts,
        `current` the index of the active issue, `results` a map of issue id ->
        list of saved result dicts."""
        self.__backlog = list(issues)
        self.__current = current
        self.__results = results or {}
        # A hydrated, mid-estimation issue means we came back from a restart with
        # in-flight (pre-reveal) votes lost — flag it so the client prompts a re-vote.
        active = self.current_issue()
        self.__resumed = active is not None and active['status'] == 'estimating'

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
        """Move the current-issue pointer to `index` (S4).

        Reverts the previously-active issue to `pending` if it was never completed.
        A *pending* target opens for voting (`estimating`); an already-estimated or
        parked target is shown VIEW-ONLY — selecting it must never silently re-open
        an accepted estimate or a parked issue. The host re-opens those explicitly
        via `reopen_current`. Clears the table either way. Returns the issue dicts
        whose status changed, so the caller persists exactly those."""
        if not (0 <= index < len(self.__backlog)):
            raise IssueNotInBacklogError(f'No issue at index {index} in the backlog')
        changed = []
        previous = self.current_issue()
        if previous is not None and previous['status'] == 'estimating':
            previous['status'] = 'pending'
            changed.append(previous)
        self.__current = index
        issue = self.__backlog[index]
        if issue['status'] == 'pending':
            issue['status'] = 'estimating'
            if issue not in changed:
                changed.append(issue)
        self.end_turn()
        return changed

    def reopen_current(self) -> Optional[dict]:
        """Re-open the current estimated/parked issue for a fresh round (host Re-vote).

        Selecting a Done/parked issue is view-only; this is the explicit re-open: it
        flips the issue back to `estimating`, drops any park reason, and clears the
        table. Append-only history is untouched — the next accept records a new round.
        Returns the changed issue dict to persist, or None when nothing is selected."""
        issue = self.current_issue()
        if issue is None:
            return None
        issue['status'] = 'estimating'
        issue['parkReason'] = None
        self.end_turn()
        return issue

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
