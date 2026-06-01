import unittest
import uuid
from unittest.mock import Mock

from peewee import SqliteDatabase

from gamestate.deck import Deck
from gamestate.exceptions import GameDoesNotExistError, DeckDoesNotExistError, \
    GameNotOngoingError, NoCurrentIssueError, NotDriverError
from gamestate.game_manager import GameManager
from gamestate.models import StoredGame, Issue, EstimationResult, database_proxy, create_tables
from gamestate.player import Player


class GameManagerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_db = SqliteDatabase(':memory:')
        database_proxy.initialize(test_db)
        if database_proxy.is_closed():
            database_proxy.connect()
        create_tables()

    def test_create(self):
        gm = GameManager()
        name = 'PBR Team Pizza'
        game_id = gm.create(name)
        self.assertIsNotNone(game_id)
        # should not raise an exception because the UUID is invalid
        self.assertIsNotNone(uuid.UUID(game_id))
        self.assertTrue(game_id in gm.games.keys())
        game = gm.games.get(game_id)
        self.assertEqual(game.name, name)
        # should have an entry in db
        stored_game = StoredGame.get(StoredGame.uuid == game_id)
        self.assertEqual(stored_game.uuid, uuid.UUID(game_id))
        self.assertEqual(stored_game.name, name)
        self.assertEqual(stored_game.deck, 'FIBONACCI')

    def test_create_other_deck(self):
        gm = GameManager()
        name = 'PBR Team Pizza'
        deck_name = 'POWERS'
        game_id = gm.create(name, deck_name)
        self.assertIsNotNone(game_id)
        # should not raise an exception because the UUID is invalid
        self.assertIsNotNone(uuid.UUID(game_id))
        self.assertTrue(game_id in gm.games.keys())
        game = gm.games.get(game_id)
        self.assertEqual(game.name, name)
        # should have an entry in db
        stored_game = StoredGame.get(StoredGame.uuid == game_id)
        self.assertEqual(stored_game.uuid, uuid.UUID(game_id))
        self.assertEqual(stored_game.name, name)
        self.assertEqual(stored_game.deck, deck_name)

    def test_create_invalid_deck(self):
        gm = GameManager()
        name = 'PBR Team Pizza'
        deck_name = 'PIZZA'
        with self.assertRaises(DeckDoesNotExistError) as ex:
            gm.create(name, deck_name)
        self.assertEqual(str(ex.exception), f'Deck {deck_name} does not exist')

    def test_get_from_memory(self):
        gm = GameManager()
        game_mock1 = Mock()
        game_mock2 = Mock()
        gm.games = {'uuid1': game_mock1, 'uuid2': game_mock2}
        self.assertEqual(gm.get('uuid1'), game_mock1)
        self.assertEqual(gm.get('uuid2'), game_mock2)

    def test_get_from_db(self):
        game_id = str(uuid.uuid4())
        name = 'PBR Pizza'
        deck = 'POWERS'
        StoredGame.create(uuid=game_id, name=name, deck=deck)
        gm = GameManager()
        game = gm.get(game_id)
        self.assertEqual(game.name, name)
        self.assertEqual(game.get_deck(), Deck[deck])

        game_id2 = str(uuid.uuid4())
        with self.assertRaises(GameDoesNotExistError) as ex:
            gm.get(game_id2)
        self.assertEqual(str(ex.exception), f'Game {game_id2} does not exist')

    def test_set_deck(self):
        game_id = str(uuid.uuid4())
        name = 'PBR Pizza'
        deck = 'FIBONACCI'
        StoredGame.create(uuid=game_id, name=name, deck=deck)

        gm = GameManager()
        game_mock = Mock(**{'info.return_value': {'name': name, 'deck': deck}, 'state.return_value': {'foo': 'bar'}})
        gm.games = {game_id: game_mock}

        with self.assertRaises(DeckDoesNotExistError) as ex1:
            gm.set_deck(game_id, 'holdem')
        self.assertEqual(str(ex1.exception), 'Deck holdem does not exist')
        with self.assertRaises(GameNotOngoingError) as ex2:
            gm.set_deck('uuid2', 'POWERS')
        self.assertEqual(str(ex2.exception), 'Game uuid2 is not ongoing')

        game_info, game_state = gm.set_deck(game_id, 'POWERS')
        game_mock.set_deck.assert_called_with(Deck.POWERS)
        game_mock.info.assert_called()
        game_mock.state.assert_called()
        self.assertEqual(game_info, {'name': name, 'deck': deck})
        self.assertEqual(game_state, {'foo': 'bar'})
        stored_game = StoredGame.get(StoredGame.uuid == uuid.UUID(game_id))
        self.assertEqual(stored_game.deck, 'POWERS')

    def test_join_game(self):
        gm = GameManager()
        game_mock = Mock(**{'state.return_value': "{'foo': 'bar'}", 'info.return_value': "{'fizz': 'buzz'}",
                            'player_joins.return_value': 'p1', 'is_resumed.return_value': False})
        gm.games = {'uuid1': game_mock}

        player_name = 'Peter'
        player_id = 'p1'
        is_spectator = True

        info, state, effective_id, resumed = gm.join_game('uuid1', player_id, player_name, is_spectator)
        game_mock.player_joins.assert_called()
        args = game_mock.player_joins.call_args.args
        self.assertEqual(args[0], player_id)
        player = args[1]
        self.assertEqual(player.name, player_name)
        self.assertEqual(player.spectator, is_spectator)
        game_mock.state.assert_called()
        game_mock.info.assert_called()
        self.assertEqual(state, "{'foo': 'bar'}")
        self.assertEqual(info, "{'fizz': 'buzz'}")
        self.assertEqual(effective_id, 'p1')
        self.assertFalse(resumed)

        with self.assertRaises(GameDoesNotExistError) as ex:
            gm.join_game('uuid2', 'p2', player_name, is_spectator)
        self.assertEqual(str(ex.exception), 'Game uuid2 does not exist')

    def test_leave_game(self):
        gm = GameManager()
        game_mock1 = Mock(**{'is_game_empty.return_value': False, 'state.return_value': "{'foo': 'bar'}"})
        game_mock2 = Mock(**{'is_game_empty.return_value': True, 'state.return_value': "{'bar': 'bang'}"})
        gm.games = {'uuid1': game_mock1, 'uuid2': game_mock2}

        state1 = gm.leave_game('uuid1', 'p1')
        game_mock1.player_leaves.assert_called_with('p1')
        game_mock1.state.assert_called()
        self.assertEqual(state1, "{'foo': 'bar'}")

        state2 = gm.leave_game('uuid2', 'p2')
        game_mock2.player_leaves.assert_called_with('p2')
        self.assertFalse('uuid2' in gm.games.keys())
        game_mock2.state.assert_called()
        self.assertEqual(state2, "{'bar': 'bang'}")

        with self.assertRaises(GameNotOngoingError) as ex:
            gm.leave_game('uuid3', 'p3')
        self.assertEqual(str(ex.exception), 'Game uuid3 is not ongoing')

    def test_rename_game(self):
        game_id = str(uuid.uuid4())
        name = 'PBR Pizza'
        deck = 'FIBONACCI'
        StoredGame.create(uuid=game_id, name=name, deck=deck)

        new_name = 'PBR Spaghetti'
        gm = GameManager()
        expected_info = {'name': new_name, 'deck': deck}
        game_mock = Mock(**{'info.return_value': expected_info})
        gm.games = {game_id: game_mock}

        game_info = gm.rename_game(game_id, new_name)
        game_mock.info.assert_called()
        self.assertEqual(game_info, expected_info)

        stored_game = StoredGame.get(StoredGame.uuid == uuid.UUID(game_id))
        self.assertEqual(stored_game.name, new_name)

    def test_set_player_name(self):
        gm = GameManager()
        player_mock = Mock()
        game_mock = Mock(**{'get_player.return_value': player_mock, 'state.return_value': "{'foo': 'bar'}"})
        gm.games = {'uuid1': game_mock}
        new_player_name = 'John'

        state = gm.set_player_name('uuid1', 'puuid1', new_player_name)
        game_mock.get_player.assert_called_with('puuid1')
        self.assertEqual(player_mock.name, new_player_name)
        game_mock.state.assert_called()
        self.assertEqual(state, "{'foo': 'bar'}")

        with self.assertRaises(GameNotOngoingError) as ex:
            gm.leave_game('uuid2', 'p3')
        self.assertEqual(str(ex.exception), 'Game uuid2 is not ongoing')

    def test_set_player_spectator(self):
        gm = GameManager()
        player_mock = Mock()
        game_mock = Mock(**{'get_player.return_value': player_mock, 'state.return_value': "{'foo': 'bar'}"})
        gm.games = {'uuid1': game_mock}

        state = gm.set_player_spectator('uuid1', "puuid1", True)
        game_mock.get_player.assert_called_with('puuid1')
        self.assertEqual(player_mock.spectator, True)
        player_mock.clear_hand.assert_called()
        game_mock.state.assert_called()
        self.assertEqual(state, "{'foo': 'bar'}")

        with self.assertRaises(GameNotOngoingError) as ex:
            gm.set_player_spectator('uuid2', 'p3', True)
        self.assertEqual(str(ex.exception), 'Game uuid2 is not ongoing')

    def test_pick_card(self):
        gm = GameManager()
        game_mock = Mock(**{'state.return_value': "{'foo': 'bar'}"})
        gm.games = {'uuid1': game_mock}

        state = gm.pick_card('uuid1', "puuid1", 3)
        game_mock.player_picks.assert_called_with("puuid1", 3)
        game_mock.state.assert_called()
        self.assertEqual(state, "{'foo': 'bar'}")

        with self.assertRaises(GameNotOngoingError) as ex:
            gm.pick_card('uuid2', 'p3', True)
        self.assertEqual(str(ex.exception), 'Game uuid2 is not ongoing')

    def test_reveal_cards_not_ongoing(self):
        gm = GameManager()
        with self.assertRaises(GameNotOngoingError) as ex:
            gm.reveal_cards('uuid2')
        self.assertEqual(str(ex.exception), 'Game uuid2 is not ongoing')

    def test_end_turn(self):
        gm = GameManager()
        game_mock = Mock(**{'state.return_value': "{'foo': 'bar'}", 'info.return_value': "{'fizz': 'buzz'}"})
        gm.games = {'uuid1': game_mock}

        state, info = gm.end_turn("uuid1")
        game_mock.end_turn.assert_called()
        game_mock.state.assert_called()
        game_mock.info.assert_called()
        self.assertEqual(state, "{'foo': 'bar'}")
        self.assertEqual(info, "{'fizz': 'buzz'}")
        with self.assertRaises(GameNotOngoingError) as ex:
            gm.end_turn('uuid2')
        self.assertEqual(str(ex.exception), 'Game uuid2 is not ongoing')

    def test_get_hydrates_backlog_from_db(self):
        game_id = str(uuid.uuid4())
        StoredGame.create(uuid=game_id, name='Sprint', deck='FIBONACCI')
        sg = StoredGame.get(StoredGame.uuid == game_id)
        i1 = Issue.create(game=sg, jira_key='OPS-1', summary='one', order_index=0, status='estimated')
        Issue.create(game=sg, jira_key='OPS-2', summary='two', order_index=1, status='pending')
        EstimationResult.create(issue=i1, round_number=1, final_value=5.0, average=5.0,
                                agreement=1.0, deck_at_vote='FIBONACCI', voter_count=3)
        gm = GameManager()
        game = gm.get(game_id)
        payload = game.backlog()
        self.assertEqual([i['key'] for i in payload['issues']], ['OPS-1', 'OPS-2'])
        self.assertEqual(payload['currentIndex'], 1)  # first not-yet-estimated issue
        self.assertIn(i1.id, payload['results'])
        self.assertEqual(payload['results'][i1.id][0]['finalValue'], 5.0)

    def test_create_with_backlog_inserts_issues_in_order(self):
        gm = GameManager()
        issues = [
            {'jira_key': 'OPS-1', 'summary': 'one', 'url': 'http://j/1', 'description': 'first'},
            {'jira_key': 'OPS-2', 'summary': 'two', 'url': None, 'description': None},
        ]
        game_id = gm.create('Sprint', 'FIBONACCI', issues, source='paste')
        sg = StoredGame.get(StoredGame.uuid == game_id)
        rows = list(sg.issues.order_by(Issue.order_index))
        self.assertEqual([r.jira_key for r in rows], ['OPS-1', 'OPS-2'])
        self.assertEqual([r.order_index for r in rows], [0, 1])
        self.assertEqual(rows[0].url, 'http://j/1')
        self.assertEqual(rows[0].description, 'first')
        self.assertEqual(rows[0].source, 'paste')
        self.assertTrue(all(r.status == 'pending' for r in rows))
        # The in-memory game is ready to broadcast its backlog immediately.
        payload = gm.get(game_id).backlog()
        self.assertEqual([i['key'] for i in payload['issues']], ['OPS-1', 'OPS-2'])
        self.assertEqual(payload['currentIndex'], 0)

    def test_create_with_backlog_is_one_transaction(self):
        # A bad row mid-insert rolls the whole thing back — no half-created game.
        gm = GameManager()
        before_games = StoredGame.select().count()
        bad_issues = [
            {'jira_key': 'OPS-1', 'summary': 'ok'},
            {'jira_key': None, 'summary': 'this row violates NOT NULL'},
        ]
        with self.assertRaises(Exception):
            gm.create('Doomed', 'FIBONACCI', bad_issues)
        self.assertEqual(StoredGame.select().count(), before_games)
        self.assertEqual(Issue.select().where(Issue.summary == 'ok').count(), 0)

    def test_create_without_backlog_still_works(self):
        gm = GameManager()
        game_id = gm.create('No backlog', 'POWERS')
        self.assertFalse(gm.get(game_id).has_backlog())

    def test_select_issue_persists_status_and_returns_backlog(self):
        gm = GameManager()
        issues = [{'jira_key': 'OPS-1', 'summary': 'a'}, {'jira_key': 'OPS-2', 'summary': 'b'}]
        game_id = gm.create('Sprint', 'FIBONACCI', issues, source='paste')
        backlog, state, info = gm.select_issue(game_id, 1)
        self.assertEqual(backlog['currentIndex'], 1)
        # The selected issue's status persisted so it survives a restart.
        sg = StoredGame.get(StoredGame.uuid == game_id)
        statuses = {i.jira_key: i.status for i in sg.issues}
        self.assertEqual(statuses['OPS-2'], 'estimating')
        # A fresh GameManager (cache-miss) rehydrates the pointer onto the active issue.
        gm2 = GameManager()
        self.assertEqual(gm2.get(game_id).backlog()['currentIndex'], 1)

    # --- S5: reveal -> server stats -> accept/re-vote -> advance ---

    def _started_game(self, gm, votes, deck='FIBONACCI'):
        """A 2-issue game with issue 0 selected and real players who picked `votes`."""
        issues = [{'jira_key': 'OPS-1', 'summary': 'a'}, {'jira_key': 'OPS-2', 'summary': 'b'}]
        game_id = gm.create('Sprint', deck, issues, source='paste')
        gm.select_issue(game_id, 0)
        game = gm.get(game_id)
        for i, v in enumerate(votes):
            p = Player(f'P{i}', False)
            game.player_joins(f'p{i}', p)
            p.set_hand(v)
        return game_id, game

    def test_reveal_computes_server_side_stats(self):
        gm = GameManager()
        game_id, game = self._started_game(gm, [5, 5, 8])
        state, info, results = gm.reveal_cards(game_id)
        self.assertTrue(info['revealed'])
        self.assertEqual(results['count'], 3)
        self.assertEqual(results['average'], round((5 + 5 + 8) / 3, 2))
        self.assertEqual(results['distribution'], {5: 2, 8: 1})
        self.assertEqual(results['proposedFinalValue'], 5)   # modal card (E4)
        self.assertEqual(results['round'], 1)
        self.assertTrue(results['consensus'])                # 5 & 8 adjacent on Fibonacci

    def test_accept_persists_before_clear_then_advances(self):
        gm = GameManager()
        game_id, game = self._started_game(gm, [3, 3, 3])
        gm.reveal_cards(game_id)
        issue0_id = game.current_issue()['id']
        backlog, state, info = gm.accept_estimate(game_id)   # default final = mode = 3
        r = EstimationResult.get(EstimationResult.issue == issue0_id)
        self.assertEqual(r.final_value, 3.0)
        self.assertEqual(r.round_number, 1)
        self.assertEqual(r.voter_count, 3)
        self.assertEqual(r.deck_at_vote, 'FIBONACCI')
        sg = StoredGame.get(StoredGame.uuid == game_id)
        statuses = {i.jira_key: i.status for i in sg.issues}
        self.assertEqual(statuses['OPS-1'], 'estimated')
        self.assertEqual(statuses['OPS-2'], 'estimating')   # advanced + re-opened
        self.assertEqual(backlog['currentIndex'], 1)
        self.assertFalse(info['revealed'])                  # hands cleared

    def test_accept_with_overridden_value(self):
        gm = GameManager()
        game_id, game = self._started_game(gm, [3, 5])
        gm.reveal_cards(game_id)
        issue0_id = game.current_issue()['id']
        gm.accept_estimate(game_id, final_value=8)
        self.assertEqual(EstimationResult.get(EstimationResult.issue == issue0_id).final_value, 8.0)

    def test_accepted_result_survives_a_restart(self):
        gm = GameManager()
        game_id, game = self._started_game(gm, [5, 5])
        gm.reveal_cards(game_id)
        gm.accept_estimate(game_id)
        gm2 = GameManager()                                  # fresh process → cache-miss
        payload = gm2.get(game_id).backlog()
        issue0 = payload['issues'][0]
        self.assertEqual(issue0['status'], 'estimated')
        self.assertEqual(payload['results'][issue0['id']][0]['finalValue'], 5.0)

    def test_revote_records_round_keeps_issue_and_increments(self):
        gm = GameManager()
        game_id, game = self._started_game(gm, [3, 13])      # divergent (>1 deck step)
        gm.reveal_cards(game_id)
        issue0_id = game.current_issue()['id']
        backlog, state, info = gm.revote(game_id)
        r = EstimationResult.get((EstimationResult.issue == issue0_id) &
                                 (EstimationResult.round_number == 1))
        self.assertIsNone(r.final_value)                     # inconclusive round, no final
        self.assertEqual(backlog['currentIndex'], 0)         # same issue
        self.assertFalse(info['revealed'])
        self.assertEqual(game.current_issue()['status'], 'estimating')
        self.assertEqual(game.current_round(), 2)            # next reveal is round 2

    def test_revote_then_accept_appends_a_second_round(self):
        gm = GameManager()
        game_id, game = self._started_game(gm, [3, 13])
        gm.reveal_cards(game_id)
        gm.revote(game_id)
        for _, p in game.list_players():
            p.set_hand(5)                                    # round 2: consensus
        gm.reveal_cards(game_id)
        issue0_id = game.current_issue()['id']
        gm.accept_estimate(game_id, final_value=5)
        rounds = [r.round_number for r in EstimationResult.select()
                  .where(EstimationResult.issue == issue0_id)
                  .order_by(EstimationResult.round_number)]
        self.assertEqual(rounds, [1, 2])
        r2 = EstimationResult.get((EstimationResult.issue == issue0_id) &
                                  (EstimationResult.round_number == 2))
        self.assertEqual(r2.final_value, 5.0)

    def test_accept_without_current_issue_raises(self):
        gm = GameManager()
        game_id = gm.create('No backlog', 'FIBONACCI')
        with self.assertRaises(NoCurrentIssueError):
            gm.accept_estimate(game_id)

    # --- S6: park / needs-refinement ---

    def test_park_flags_issue_with_reason_and_advances(self):
        gm = GameManager()
        issues = [{'jira_key': 'OPS-1', 'summary': 'vague'}, {'jira_key': 'OPS-2', 'summary': 'b'}]
        game_id = gm.create('Sprint', 'FIBONACCI', issues, source='paste')
        gm.select_issue(game_id, 0)
        parked_id = gm.get(game_id).current_issue()['id']
        backlog, state, info = gm.park_issue(game_id, 'refinement', 'needs AC')
        sg = StoredGame.get(StoredGame.uuid == game_id)
        parked = Issue.get(Issue.id == parked_id)
        self.assertEqual(parked.status, 'refinement')
        self.assertEqual(parked.park_reason, 'needs AC')
        # advanced to the next pending issue
        self.assertEqual(backlog['currentIndex'], 1)
        statuses = {i.jira_key: i.status for i in sg.issues}
        self.assertEqual(statuses['OPS-2'], 'estimating')

    def test_parked_issue_is_view_only_on_reselect(self):
        # Behaviour change (see decisions): re-selecting a parked issue VIEWS it; it
        # does not silently re-open for voting. Re-opening is the explicit host action.
        gm = GameManager()
        issues = [{'jira_key': 'OPS-1', 'summary': 'a'}, {'jira_key': 'OPS-2', 'summary': 'b'}]
        game_id = gm.create('Sprint', 'FIBONACCI', issues, source='paste')
        gm.select_issue(game_id, 0)
        gm.park_issue(game_id, 'skipped', None)
        backlog, _, _ = gm.select_issue(game_id, 0)
        self.assertEqual(backlog['currentIndex'], 0)
        self.assertEqual(backlog['issues'][0]['status'], 'skipped')   # viewed, not re-opened

    def test_reopen_issue_reopens_parked_and_clears_reason(self):
        gm = GameManager()
        issues = [{'jira_key': 'OPS-1', 'summary': 'a'}, {'jira_key': 'OPS-2', 'summary': 'b'}]
        game_id = gm.create('Sprint', 'FIBONACCI', issues, source='paste')
        gm.select_issue(game_id, 0)
        parked_id = gm.get(game_id).current_issue()['id']
        gm.park_issue(game_id, 'refinement', 'needs AC')   # advances to OPS-2
        gm.select_issue(game_id, 0)                        # view the parked issue
        self.assertEqual(gm.get(game_id).current_issue()['status'], 'refinement')
        backlog, _, _ = gm.reopen_issue(game_id)           # explicit host re-open
        self.assertEqual(backlog['currentIndex'], 0)
        self.assertEqual(backlog['issues'][0]['status'], 'estimating')
        parked = Issue.get(Issue.id == parked_id)
        self.assertEqual(parked.status, 'estimating')      # persisted
        self.assertIsNone(parked.park_reason)              # reason dropped on re-open

    def test_reopen_estimated_issue_appends_next_round(self):
        # The host re-votes a Done issue: prior rounds survive (append-only, EC2).
        gm = GameManager()
        game_id, game = self._started_game(gm, [5, 5])     # OPS-1 selected, 2 voters
        gm.reveal_cards(game_id)
        issue0_id = game.current_issue()['id']
        gm.accept_estimate(game_id, final_value=5)         # round 1 → estimated, advance
        gm.select_issue(game_id, 0)                        # view OPS-1 (estimated)
        gm.reopen_issue(game_id)                            # host re-vote
        self.assertEqual(game.current_issue()['status'], 'estimating')
        self.assertEqual(game.current_round(), 2)          # prior round preserved
        for _, p in game.list_players():
            p.set_hand(8)
        gm.reveal_cards(game_id)
        gm.accept_estimate(game_id, final_value=8)
        rounds = [r.round_number for r in EstimationResult.select()
                  .where(EstimationResult.issue == issue0_id)
                  .order_by(EstimationResult.round_number)]
        self.assertEqual(rounds, [1, 2])                   # append-only

    def test_reopen_without_current_issue_raises(self):
        gm = GameManager()
        game_id = gm.create('No backlog', 'FIBONACCI')
        with self.assertRaises(NoCurrentIssueError):
            gm.reopen_issue(game_id)

    def test_park_without_current_issue_raises(self):
        gm = GameManager()
        game_id = gm.create('No backlog', 'FIBONACCI')
        with self.assertRaises(NoCurrentIssueError):
            gm.park_issue(game_id, 'refinement', None)

    # --- B1: add issues to a live session's queue ---

    def test_add_issues_appends_at_end(self):
        gm = GameManager()
        issues = [{'jira_key': 'OPS-1', 'summary': 'a'}, {'jira_key': 'OPS-2', 'summary': 'b'}]
        game_id = gm.create('Sprint', 'FIBONACCI', issues, source='paste')
        backlog = gm.add_issues(game_id, 'OPS-3  late arrival', 'paste')
        self.assertEqual([i['key'] for i in backlog['issues']], ['OPS-1', 'OPS-2', 'OPS-3'])
        last = backlog['issues'][-1]
        self.assertEqual(last['orderIndex'], 2)
        sg = StoredGame.get(StoredGame.uuid == game_id)
        added = Issue.get((Issue.game == game_id) & (Issue.jira_key == 'OPS-3'))
        self.assertEqual(added.order_index, 2)

    def test_add_issues_dedupes_existing_keys(self):
        gm = GameManager()
        issues = [{'jira_key': 'OPS-1', 'summary': 'a'}]
        game_id = gm.create('Sprint', 'FIBONACCI', issues, source='paste')
        backlog = gm.add_issues(game_id, 'OPS-1  dup\nOPS-2  new', 'paste')
        # OPS-1 already exists, so only OPS-2 is appended.
        self.assertEqual([i['key'] for i in backlog['issues']], ['OPS-1', 'OPS-2'])

    def test_add_issues_preserves_current_pointer(self):
        gm = GameManager()
        issues = [{'jira_key': 'OPS-1', 'summary': 'a'}, {'jira_key': 'OPS-2', 'summary': 'b'}]
        game_id = gm.create('Sprint', 'FIBONACCI', issues, source='paste')
        gm.select_issue(game_id, 1)
        backlog = gm.add_issues(game_id, 'OPS-3  late', 'paste')
        self.assertEqual(backlog['currentIndex'], 1)   # pointer untouched by append

    def test_add_issues_preserves_inflight_vote(self):
        gm = GameManager()
        issues = [{'jira_key': 'OPS-1', 'summary': 'a'}, {'jira_key': 'OPS-2', 'summary': 'b'}]
        game_id = gm.create('Sprint', 'FIBONACCI', issues, source='paste')
        gm.select_issue(game_id, 0)
        game = gm.get(game_id)
        p = Player('Ann', False)
        game.player_joins('p1', p)
        game.player_picks('p1', 5)
        gm.add_issues(game_id, 'OPS-3  late', 'paste')
        # The append must not clear hands or flip revealed for the in-flight round.
        self.assertEqual(game.get_player('p1').get_hand(), 5)
        self.assertFalse(game.get_revealed())

    def test_add_issues_to_empty_backlog_leaves_current_none(self):
        gm = GameManager()
        game_id = gm.create('No backlog', 'FIBONACCI')   # classic game, no issues
        backlog = gm.add_issues(game_id, 'OPS-1  one\nOPS-2  two', 'paste')
        self.assertEqual([i['key'] for i in backlog['issues']], ['OPS-1', 'OPS-2'])
        self.assertIsNone(backlog['currentIndex'])       # never auto-selects

    def test_add_issues_persists_rows(self):
        gm = GameManager()
        issues = [{'jira_key': 'OPS-1', 'summary': 'a'}]
        game_id = gm.create('Sprint', 'FIBONACCI', issues, source='paste')
        before = Issue.select().count()
        gm.add_issues(game_id, 'OPS-2  new\nOPS-3  newer', 'paste')
        self.assertEqual(Issue.select().count(), before + 2)
        added = list(Issue.select().where((Issue.game == game_id) &
                                          (Issue.jira_key << ['OPS-2', 'OPS-3'])))
        self.assertEqual(len(added), 2)
        self.assertTrue(all(r.source == 'paste' for r in added))
        self.assertTrue(all(r.status == 'pending' for r in added))

    def test_add_issues_invalid_raises(self):
        from gamestate.exceptions import InvalidBacklogError
        gm = GameManager()
        game_id = gm.create('Sprint', 'FIBONACCI')
        with self.assertRaises(InvalidBacklogError):
            gm.add_issues(game_id, 'OPS-1', 'paste')     # a key with no summary

    # --- S7: rejoin token + scoped resume ---

    def test_join_token_reattaches_same_identity(self):
        gm = GameManager()
        game_id = gm.create('Sprint', 'FIBONACCI')
        _, _, id1, _ = gm.join_game(game_id, 'p1', 'Ann', False, token='tok')
        _, _, id2, _ = gm.join_game(game_id, 'p2', 'Ann', False, token='tok')
        self.assertEqual(id1, id2)                                   # same token → same id
        self.assertEqual(len(gm.get(game_id).list_players_uuid()), 1)  # no ghost

    def test_join_after_restart_flags_resume_for_inflight_issue(self):
        gm = GameManager()
        issues = [{'jira_key': 'OPS-1', 'summary': 'a'}]
        game_id = gm.create('Sprint', 'FIBONACCI', issues, source='paste')
        gm.select_issue(game_id, 0)               # OPS-1 → estimating, persisted
        gm2 = GameManager()                       # fresh process → cache-miss hydrate
        _, _, _, resumed = gm2.join_game(game_id, 'p1', 'Ann', False)
        self.assertTrue(resumed)                  # in-flight issue → resume toast

    def test_join_fresh_backlog_is_not_a_resume(self):
        gm = GameManager()
        issues = [{'jira_key': 'OPS-1', 'summary': 'a'}]
        game_id = gm.create('Sprint', 'FIBONACCI', issues, source='paste')
        _, _, _, resumed = gm.join_game(game_id, 'p1', 'Ann', False)
        self.assertFalse(resumed)                 # nothing selected yet

    def test_resume_flag_clears_once_re_revealed(self):
        gm = GameManager()
        issues = [{'jira_key': 'OPS-1', 'summary': 'a'}]
        game_id = gm.create('Sprint', 'FIBONACCI', issues, source='paste')
        gm.select_issue(game_id, 0)
        gm2 = GameManager()
        game = gm2.get(game_id)
        self.assertTrue(game.is_resumed())
        p = Player('Ann', False)
        game.player_joins('p1', p)
        p.set_hand(5)
        gm2.reveal_cards(game_id)
        self.assertFalse(game.is_resumed())       # re-vote completed the resume

    # --- S8: soft host / driver gate ---

    def test_require_driver_allows_driver_rejects_others(self):
        gm = GameManager()
        game_id = gm.create('Sprint', 'FIBONACCI')
        _, _, driver_id, _ = gm.join_game(game_id, 'p1', 'Ann', False)   # first joiner = driver
        _, _, other_id, _ = gm.join_game(game_id, 'p2', 'Bob', False)
        gm.require_driver(game_id, driver_id)                            # no raise
        with self.assertRaises(NotDriverError):
            gm.require_driver(game_id, other_id)

    def test_claim_driver_takes_over(self):
        gm = GameManager()
        game_id = gm.create('Sprint', 'FIBONACCI')
        _, _, driver_id, _ = gm.join_game(game_id, 'p1', 'Ann', False)
        _, _, other_id, _ = gm.join_game(game_id, 'p2', 'Bob', False)
        gm.claim_driver(game_id, other_id)
        gm.require_driver(game_id, other_id)                             # now Bob drives
        with self.assertRaises(NotDriverError):
            gm.require_driver(game_id, driver_id)


if __name__ == '__main__':
    unittest.main()
