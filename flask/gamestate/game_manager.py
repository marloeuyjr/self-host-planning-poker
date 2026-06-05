import uuid
from typing import Optional

from peewee import DoesNotExist

from gamestate.deck import Deck
from gamestate.exceptions import (GameDoesNotExistError, DeckDoesNotExistError,
                                  GameNotOngoingError, NoCurrentIssueError, NotDriverError)
from gamestate.game import Game
from gamestate.intake import parse_issues
from gamestate.models import StoredGame, Issue, EstimationResult, database_proxy
from gamestate.player import Player
from gamestate.stats import compute_stats, is_numeric_deck


class GameManager:
    """Class that manages games"""
    def __init__(self):
        self.games = {}

    def create(self, name: str, deck_name='FIBONACCI', issues=None, source=None) -> str:
        """Create a game and, optionally, its starting backlog in one transaction (S3).

        `issues` is a list of parsed dicts (`jira_key`, `summary`, optional `url` /
        `description`) from `gamestate.intake`. The game row and every issue row are
        written atomically so a bad row never leaves a half-created session.
        """
        game_uuid = str(uuid.uuid4())
        deck = self.__get_deck(deck_name)
        with database_proxy.atomic():
            stored_game = StoredGame.create(uuid=game_uuid, name=name, deck=deck_name)
            if issues:
                Issue.insert_many([{
                    'game': game_uuid,
                    'jira_key': i['jira_key'],
                    'summary': i['summary'],
                    'description': i.get('description'),
                    'url': i.get('url'),
                    'order_index': idx,
                    'status': 'pending',
                    'source': source,
                } for idx, i in enumerate(issues)]).execute()
        game = Game(name, deck)
        if issues:
            self.__hydrate_backlog(game, stored_game)
        self.games[game_uuid] = game
        return game_uuid

    def list_sessions(self, limit=50) -> list[dict]:
        """Most-recent saved sessions for the home-page recall list (B2).

        Returns up to `limit` `StoredGame`s newest-first, each with its issue counts:
        `{uuid, name, deck, total, estimated, createdAt}`. Read-only — a handful of
        SELECTs, safe on the single eventlet worker. Legacy rows created before the
        `created_at` column have NULL timestamps and sort last (`DESC NULLS LAST`).

        Deliberately does NOT compute a session points-total: re-opening an issue
        appends a new round, so a naive sum of `final_value`s would double-count.
        The correct latest-final-value-per-issue total belongs in the export/detail
        view, not this list.
        """
        games = list(StoredGame
                     .select()
                     .order_by(StoredGame.created_at.desc(nulls='LAST'))
                     .limit(limit))
        sessions = []
        for g in games:
            total = Issue.select().where(Issue.game == g.uuid).count()
            estimated = (Issue.select()
                         .where((Issue.game == g.uuid) & (Issue.status == 'estimated'))
                         .count())
            sessions.append({
                'uuid': str(g.uuid),
                'name': g.name,
                'deck': g.deck,
                'total': total,
                'estimated': estimated,
                'createdAt': g.created_at.isoformat() if g.created_at else None,
            })
        return sessions

    def export_session(self, game_uuid: str) -> Optional[dict]:
        """Full per-issue results of one session for CSV/JSON export.

        Returns None when the game is unknown (the route turns that into a 404).
        Read-only over the persisted tables (StoredGame -> Issues -> append-only
        EstimationResult), independent of whether the game is cached in memory.

        Per issue, `finalValue` is the `final_value` of the **latest round that has
        one** — accepted rounds set it, revote rounds leave it null — so a re-opened
        issue reports its last accepted estimate, never a double-count. `average` /
        `agreement` / `voterCount` come from that same deciding round. `pointsTotal`
        is the sum of those per-issue final values (one per issue, so re-opens never
        inflate it), exposed only for numeric decks — this is the latest-final-value-
        per-issue total that `list_sessions` deliberately defers to here.
        """
        stored = StoredGame.get_or_none(StoredGame.uuid == game_uuid)
        if stored is None:
            return None
        numeric = stored.deck in Deck.__members__ and is_numeric_deck(Deck[stored.deck])
        issues_out = []
        estimated = 0
        points_total = 0.0
        has_points = False
        for issue in stored.issues.order_by(Issue.order_index):
            rows = list(issue.results.order_by(EstimationResult.round_number))
            accepted = [r for r in rows if r.final_value is not None]
            final_row = accepted[-1] if accepted else None   # latest decided round
            deciding = final_row or (rows[-1] if rows else None)   # else latest round, for its stats
            final_value = final_row.final_value if final_row else None
            if issue.status == 'estimated':
                estimated += 1
            if numeric and final_value is not None:
                points_total += final_value
                has_points = True
            issues_out.append({
                'orderIndex': issue.order_index,
                'key': issue.jira_key,
                'summary': issue.summary,
                'status': issue.status,
                'parkReason': issue.park_reason,
                'finalValue': final_value,
                'rounds': len(rows),
                'average': deciding.average if deciding else None,
                'agreement': deciding.agreement if deciding else None,
                'voterCount': deciding.voter_count if deciding else None,
                'deck': deciding.deck_at_vote if deciding else stored.deck,
            })
        return {
            'uuid': str(stored.uuid),
            'name': stored.name,
            'deck': stored.deck,
            'createdAt': stored.created_at.isoformat() if stored.created_at else None,
            'total': len(issues_out),
            'estimated': estimated,
            'pointsTotal': round(points_total, 2) if (numeric and has_points) else None,
            'issues': issues_out,
        }

    def get(self, game_uuid: str) -> Game:
        game = self.games.get(game_uuid)
        if game is None:
            try:
                stored_game = StoredGame.get(StoredGame.uuid == game_uuid)
                game = Game(stored_game.name, Deck[stored_game.deck])
                self.__hydrate_backlog(game, stored_game)
                self.games[game_uuid] = game
            except DoesNotExist:
                raise GameDoesNotExistError(f'Game {game_uuid} does not exist')
        return game

    def __get_ongoing_game(self, game_uuid: str) -> Game:
        game = self.games.get(game_uuid)
        if game is None:
            raise GameNotOngoingError(f'Game {game_uuid} is not ongoing')
        return game
    
    def set_deck(self, game_uuid: str, deck_name: str) -> tuple[dict, dict]:
        deck = self.__get_deck(deck_name)
        game = self.__get_ongoing_game(game_uuid)
        game.set_deck(deck)
        StoredGame.update(deck=deck_name).where(StoredGame.uuid == uuid.UUID(game_uuid)).execute()
        return game.info(), game.state()

    def join_game(self, game_uuid: str, player_id: str, player_name: str,
                  is_spectator: bool, token=None) -> tuple[dict, dict, str, bool]:
        """Join (or reattach via `token`, S7). Returns info, state, the effective
        player id, and whether this is a post-restart resume (E5)."""
        game = self.get(game_uuid)
        player = Player(player_name, is_spectator)
        effective_id = game.player_joins(player_id, player, token=token)
        return game.info(), game.state(), effective_id, game.is_resumed()

    def leave_game(self, game_uuid: str, player_uuid: str) -> dict:
        game = self.__get_ongoing_game(game_uuid)
        game.player_leaves(player_uuid)
        if game.is_game_empty():
            self.games.pop(game_uuid)
        return game.state()

    def rename_game(self, game_uuid: str, game_name: str) -> dict:
        game = self.__get_ongoing_game(game_uuid)
        game.name = game_name
        StoredGame.update(name=game_name).where(StoredGame.uuid == uuid.UUID(game_uuid)).execute()
        return game.info()

    def set_player_name(self, game_uuid: str, player_uuid: str, player_name: str) -> dict:
        game = self.__get_ongoing_game(game_uuid)
        player = game.get_player(player_uuid)
        player.name = player_name
        return game.state()

    def set_player_spectator(self, game_uuid: str, player_uuid: str, is_spectator: bool) -> dict:
        game = self.__get_ongoing_game(game_uuid)
        player = game.get_player(player_uuid)
        player.spectator = is_spectator
        player.clear_hand()
        return game.state()

    def pick_card(self, game_uuid: str, player_uuid: str, pick: Optional[int]) -> dict:
        game = self.__get_ongoing_game(game_uuid)
        game.player_picks(player_uuid, pick)
        return game.state()

    def reveal_cards(self, game_uuid: str) -> tuple[dict, dict, dict]:
        """Reveal and compute the round's stats server-side (S5, no browser math)."""
        game = self.__get_ongoing_game(game_uuid)
        game.reveal_hands()
        return game.state(), game.info(), self.__round_results(game)

    def end_turn(self, game_uuid: str) -> tuple[dict, dict]:
        game = self.__get_ongoing_game(game_uuid)
        game.end_turn()
        return game.state(), game.info()

    @staticmethod
    def __round_results(game: Game) -> dict:
        """Server-computed stats for the current hands + the proposed final value (E4)."""
        stats = compute_stats(game.get_cast_votes(), game.get_deck())
        proposed = stats['mode'][0] if len(stats['mode']) == 1 else None
        return {**stats, 'proposedFinalValue': proposed, 'round': game.current_round()}

    def accept_estimate(self, game_uuid: str, final_value=None) -> tuple[dict, dict, dict]:
        """Record the current round and advance — the durability fix (S5, E4).

        Writes an append-only `EstimationResult` (the proven synchronous-write
        pattern) BEFORE clearing hands, flips the issue to `estimated`, and moves the
        pointer to the next pending issue. `final_value` defaults to the modal card."""
        game = self.__get_ongoing_game(game_uuid)
        issue = game.current_issue()
        if issue is None:
            raise NoCurrentIssueError('No issue is currently selected')
        stats = compute_stats(game.get_cast_votes(), game.get_deck())
        if final_value is None:
            final_value = stats['mode'][0] if len(stats['mode']) == 1 else None
        # One transaction so the appended round row and the issue-status flips commit
        # together — a crash mid-accept can't leave a recorded round without its
        # 'estimated' status (or the advance half-applied).
        with database_proxy.atomic():
            self.__write_round(game, issue, stats, final_value)
            game.mark_current('estimated')
            Issue.update(status='estimated').where(Issue.id == issue['id']).execute()
            for changed in game.advance_to_next_pending():
                Issue.update(status=changed['status']).where(Issue.id == changed['id']).execute()
        return game.backlog(), game.state(), game.info()

    def revote(self, game_uuid: str) -> tuple[dict, dict, dict]:
        """Record the current (inconclusive) round, then re-open the SAME issue (E3).

        Keeps the issue selected (no advance), clears hands, and increments the round.
        The recorded round has no `final_value` — it surfaces only as a muted prior
        reference, never on the live surface (EC2 anti-anchoring)."""
        game = self.__get_ongoing_game(game_uuid)
        issue = game.current_issue()
        if issue is None:
            raise NoCurrentIssueError('No issue is currently selected')
        stats = compute_stats(game.get_cast_votes(), game.get_deck())
        self.__write_round(game, issue, stats, final_value=None)
        game.end_turn()
        return game.backlog(), game.state(), game.info()

    @staticmethod
    def __write_round(game: Game, issue: dict, stats: dict, final_value) -> None:
        """Persist one round and mirror it in memory, while hands are still set."""
        deck_name = game.get_deck().name
        voter_count = stats['count'] + stats['abstains']
        round_number = game.current_round()
        EstimationResult.create(
            issue=issue['id'], round_number=round_number, final_value=final_value,
            average=stats['average'], median=stats['median'], agreement=stats['agreement'],
            deck_at_vote=deck_name, voter_count=voter_count)
        game.record_round(round_number, final_value, stats['average'], stats['median'],
                          stats['agreement'], deck_name, voter_count)

    def backlog(self, game_uuid: str) -> dict:
        game = self.__get_ongoing_game(game_uuid)
        return game.backlog()

    def info(self, game_uuid: str):
        """Current info, or None if the game is no longer in memory (room emptied)."""
        game = self.games.get(game_uuid)
        return game.info() if game else None

    def require_driver(self, game_uuid: str, player_id: str) -> None:
        """Soft host gate (S8, EC4): raise unless `player_id` drives this session.

        Server-enforced — the destructive handlers call this before mutating the
        durable record. A fat-finger guardrail, explicitly NOT authentication."""
        game = self.__get_ongoing_game(game_uuid)
        if not game.is_driver(player_id):
            raise NotDriverError('Only the session driver can do that')

    def claim_driver(self, game_uuid: str, player_id: str) -> tuple[dict, dict]:
        """Take over the (soft, claimable) driver role."""
        game = self.__get_ongoing_game(game_uuid)
        game.claim_driver(player_id)
        return game.info(), game.state()

    def select_issue(self, game_uuid: str, index: int) -> tuple[dict, dict, dict]:
        """Move the pointer and persist the resulting status changes (S4)."""
        game = self.__get_ongoing_game(game_uuid)
        changed = game.select_issue(index)
        for issue in changed:
            Issue.update(status=issue['status']).where(Issue.id == issue['id']).execute()
        return game.backlog(), game.state(), game.info()

    def reopen_issue(self, game_uuid: str) -> tuple[dict, dict, dict]:
        """Re-open the current estimated/parked issue for a fresh round (S4/E4).

        The host's explicit Re-vote on a Done/parked issue (selecting one is
        view-only). Append-only rounds are preserved — the next accept appends a new
        `round_number` (EC2); the park reason is dropped since it's no longer parked."""
        game = self.__get_ongoing_game(game_uuid)
        issue = game.reopen_current()
        if issue is None:
            raise NoCurrentIssueError('No issue is currently selected')
        Issue.update(status=issue['status'], park_reason=None).where(Issue.id == issue['id']).execute()
        return game.backlog(), game.state(), game.info()

    def park_issue(self, game_uuid: str, status='refinement', reason=None) -> tuple[dict, dict, dict]:
        """Flag the current issue needs-refinement / skipped and advance (S6)."""
        game = self.__get_ongoing_game(game_uuid)
        issue = game.current_issue()
        if issue is None:
            raise NoCurrentIssueError('No issue is currently selected')
        if status not in ('refinement', 'skipped'):
            status = 'refinement'
        # Park + advance commit together (see accept_estimate).
        with database_proxy.atomic():
            game.park_current(status, reason)
            Issue.update(status=status, park_reason=reason).where(Issue.id == issue['id']).execute()
            for changed in game.advance_to_next_pending():
                Issue.update(status=changed['status']).where(Issue.id == changed['id']).execute()
        return game.backlog(), game.state(), game.info()

    def add_issues(self, game_uuid: str, text: str, fmt='paste') -> dict:
        """Append parsed issues to a live session's queue, persisted (B1).

        Parses `text` (paste/CSV), drops any keys already in the backlog (idempotent
        re-paste), and creates the new rows at the tail of the contiguous
        `order_index` range — all in one transaction. Never auto-selects: the
        pointer and any in-flight round are left untouched (a classic game gaining
        its first issues stays at `currentIndex = None` until the driver selects).
        Lets `InvalidBacklogError` (4007) propagate to the handler. Returns the
        broadcast-ready backlog payload."""
        game = self.__get_ongoing_game(game_uuid)
        parsed = parse_issues(text, fmt)
        existing = {i['key'] for i in game.backlog()['issues']}
        new = [p for p in parsed if p['jira_key'] not in existing]
        if not new:
            return game.backlog()   # idempotent no-op (re-broadcast is harmless)
        start = max((i['orderIndex'] for i in game.backlog()['issues']), default=-1) + 1
        new_dicts = []
        with database_proxy.atomic():
            for offset, p in enumerate(new):
                row = Issue.create(
                    game=game_uuid, jira_key=p['jira_key'], summary=p['summary'],
                    description=p.get('description'), url=p.get('url'),
                    order_index=start + offset, status='pending', source=fmt)
                new_dicts.append({
                    'id': row.id,
                    'key': p['jira_key'],
                    'summary': p['summary'],
                    'description': p.get('description'),
                    'url': p.get('url'),
                    'status': 'pending',
                    'parkReason': None,
                    'orderIndex': start + offset,
                })
        game.append_issues(new_dicts)
        return game.backlog()

    @staticmethod
    def __hydrate_backlog(game: Game, stored_game: StoredGame) -> None:
        """Rebuild the in-memory issue queue from the database on cache-miss (S1, E5).

        Accepted results and queue position always survive a worker restart; the
        active issue simply re-opens for voting (in-flight pre-reveal votes are not
        persisted, by design)."""
        issues = []
        current = None
        for idx, issue in enumerate(stored_game.issues.order_by(Issue.order_index)):
            issues.append({
                'id': issue.id,
                'key': issue.jira_key,
                'summary': issue.summary,
                'description': issue.description,
                'url': issue.url,
                'status': issue.status,
                'parkReason': issue.park_reason,
                'orderIndex': issue.order_index,
            })
            if issue.status == 'estimating' and current is None:
                current = idx
        if current is None:
            for idx, item in enumerate(issues):
                if item['status'] in ('pending', 'estimating'):
                    current = idx
                    break
        results = {}
        for issue in stored_game.issues:
            rows = list(issue.results.order_by(EstimationResult.round_number))
            if rows:
                results[issue.id] = [{
                    'round': r.round_number,
                    'finalValue': r.final_value,
                    'average': r.average,
                    'median': r.median,
                    'agreement': r.agreement,
                    'deck': r.deck_at_vote,
                    'voterCount': r.voter_count,
                } for r in rows]
        game.set_backlog(issues, current, results)

    @staticmethod
    def __get_deck(deck_name) -> Deck:
        if deck_name not in Deck.__members__.keys():
            raise DeckDoesNotExistError(f'Deck {deck_name} does not exist')
        deck = Deck[deck_name]
        return deck
    