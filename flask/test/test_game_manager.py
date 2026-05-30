import unittest
import uuid
from unittest.mock import Mock

from peewee import SqliteDatabase

from gamestate.deck import Deck
from gamestate.exceptions import GameDoesNotExistError, DeckDoesNotExistError, \
    GameNotOngoingError
from gamestate.game_manager import GameManager
from gamestate.models import StoredGame, Issue, EstimationResult, database_proxy, create_tables


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
        game_mock = Mock(**{'state.return_value': "{'foo': 'bar'}", 'info.return_value': "{'fizz': 'buzz'}"})
        gm.games = {'uuid1': game_mock}

        player_name = 'Peter'
        player_id = 'p1'
        is_spectator = True

        info, state = gm.join_game('uuid1', player_id, player_name, is_spectator)
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

    def test_reveal_cards(self):
        gm = GameManager()
        game_mock = Mock(**{'state.return_value': "{'foo': 'bar'}", 'info.return_value': "{'fizz': 'buzz'}"})
        gm.games = {'uuid1': game_mock}

        state, info = gm.reveal_cards("uuid1")
        game_mock.reveal_hands.assert_called()
        game_mock.state.assert_called()
        game_mock.info.assert_called()
        self.assertEqual(state, "{'foo': 'bar'}")
        self.assertEqual(info, "{'fizz': 'buzz'}")
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


if __name__ == '__main__':
    unittest.main()
