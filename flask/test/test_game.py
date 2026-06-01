import unittest
from unittest.mock import Mock

from gamestate.deck import Deck
from gamestate.exceptions import PlayerNotInGameError, InvalidCardValueError
from gamestate.game import Game


class GameTestCase(unittest.TestCase):
    def test_empty_state(self):
        game = Game('PBR Team Pizza')
        self.assertEqual(game.list_players_uuid(), [])
        self.assertEqual(game.get_deck(), Deck.FIBONACCI)
        self.assertEqual(game.name, 'PBR Team Pizza')
        game2 = Game('PBR Team Pasta', Deck.T_SHIRTS)
        self.assertEqual(game2.get_deck(), Deck.T_SHIRTS)
        self.assertEqual(game2.name, 'PBR Team Pasta')

    def test_set_name(self):
        game = Game('PBR Team Pizza')
        game.name = 'PBR Team Pasta'
        self.assertEqual(game.name, 'PBR Team Pasta')

    def test_set_deck(self):
        game = Game('PBR Team Pizza')
        game.set_deck(Deck.POWERS)
        self.assertEqual(game.get_deck(), Deck.POWERS)

    def test_add_player(self):
        uuid = '47b71b00-e060-47ba-8fae-029f5473794b'
        game = Game('PBR Team Pizza')
        player = Mock()
        game.player_joins(uuid, player)
        self.assertTrue(uuid in game.list_players_uuid())

    def test_remove_player(self):
        uuid = '47b71b00-e060-47ba-8fae-029f5473794b'
        game = Game('PBR Team Pizza')
        player = Mock()
        game.player_joins(uuid, player)
        self.assertTrue(uuid in game.list_players_uuid())
        game.player_leaves(uuid)
        self.assertTrue(uuid not in game.list_players_uuid())

    def test_list_players(self):
        game = Game('PBR Team Pizza')
        uuid1 = '2c6f0ffa-ad57-47b7-bb34-2275d05018cf'
        player1 = Mock()
        game.player_joins(uuid1, player1)
        uuid2 = '1499d88f-7841-47f1-a734-10a638bd4884'
        player2 = Mock()
        game.player_joins(uuid2, player2)
        self.assertEqual(game.list_players(), [(uuid1, player1), (uuid2, player2)])

    def test_list_players_uuid(self):
        game = Game('PBR Team Pizza')
        uuid1 = '2c6f0ffa-ad57-47b7-bb34-2275d05018cf'
        player1 = Mock()
        game.player_joins(uuid1, player1)
        uuid2 = '1499d88f-7841-47f1-a734-10a638bd4884'
        player2 = Mock()
        game.player_joins(uuid2, player2)
        self.assertEqual(game.list_players_uuid(), [uuid1, uuid2])

    def test_get_player(self):
        game = Game('PBR Team Pizza')
        uuid1 = '2c6f0ffa-ad57-47b7-bb34-2275d05018cf'
        player1 = Mock()
        game.player_joins(uuid1, player1)
        self.assertEqual(game.get_player(uuid1), player1)

        uuid2 = '0f6b59d5-6765-4be1-b196-760c654729a6'
        with self.assertRaises(PlayerNotInGameError) as ex:
            game.get_player(uuid2)
        self.assertEqual(str(ex.exception), f'Player with UUID {uuid2} is not in this game')

    def test_player_picks(self):
        game = Game('PBR Team Pizza', Deck.POWERS)
        uuid1 = '2c6f0ffa-ad57-47b7-bb34-2275d05018cf'
        uuid2 = '0f6b59d5-6765-4be1-b196-760c654729a6'
        player_mock = Mock()
        game.player_joins(uuid1, player_mock)
        game.player_picks(uuid1, 8)
        player_mock.set_hand.assert_called_with(8)

        game.player_picks(uuid1, None)
        player_mock.set_hand.assert_called_with(None)

        with self.assertRaises(PlayerNotInGameError) as ex1:
            game.player_picks(uuid2, 8)
        self.assertEqual(str(ex1.exception), f'Player with UUID {uuid2} is not in this game')

        with self.assertRaises(InvalidCardValueError) as ex2:
            game.player_picks(uuid1, 13)
        self.assertEqual(str(ex2.exception), 'Card value 13 is not valid. Current deck is POWERS')

    def test_player_picks_abstain(self):
        """'?' (abstain) is a valid pick on Fibonacci; the dropped high cards are not."""
        game = Game('PBR Team Pizza', Deck.FIBONACCI)
        uuid = '2c6f0ffa-ad57-47b7-bb34-2275d05018cf'
        player_mock = Mock()
        game.player_joins(uuid, player_mock)

        game.player_picks(uuid, '?')
        player_mock.set_hand.assert_called_with('?')

        # 34/55/89 were removed when Fibonacci was capped at 21 — no longer valid.
        with self.assertRaises(InvalidCardValueError):
            game.player_picks(uuid, 34)

    def test_end_turn(self):
        game = Game('PBR Team Pizza')
        player_1 = Mock()
        game.player_joins('j', player_1)
        player_2 = Mock()
        game.player_joins('p', player_2)
        spectator_1 = Mock()
        game.player_joins('d', spectator_1)
        game.end_turn()
        player_1.clear_hand.assert_called()
        player_2.clear_hand.assert_called()
        spectator_1.clear_hand.assert_called()

    def test_end_turn_should_set_revealed_as_false(self):
        game = Game('PBR Team Pizza')
        self.assertFalse(game.get_revealed())
        game.reveal_hands()
        self.assertTrue(game.get_revealed())
        game.end_turn()
        self.assertFalse(game.get_revealed())


    def test_setting_deck_should_clear_hands(self):
        game = Game('PBR Team Pizza')
        player_1 = Mock()
        game.player_joins('j', player_1)
        player_2 = Mock()
        game.player_joins('p', player_2)
        spectator_1 = Mock()
        game.player_joins('d', spectator_1)
        game.set_deck(Deck.POWERS)
        player_1.clear_hand.assert_called()
        player_2.clear_hand.assert_called()
        spectator_1.clear_hand.assert_called()

    def test_setting_deck_should_set_revealed_as_false(self):
        game = Game('PBR Team Pizza')
        game.reveal_hands()
        self.assertTrue(game.get_revealed())
        game.set_deck(Deck.POWERS)
        self.assertFalse(game.get_revealed())

    def test_setting_deck_should_not_clear_hands_when_deck_is_the_same(self):
        game = Game('PBR Team Pizza', Deck.POWERS)
        player_1 = Mock()
        game.player_joins('j', player_1)
        player_2 = Mock()
        game.player_joins('p', player_2)
        spectator_1 = Mock()
        game.player_joins('d', spectator_1)
        game.set_deck(Deck.POWERS)
        player_1.clear_hand.assert_not_called()
        player_2.clear_hand.assert_not_called()
        spectator_1.clear_hand.assert_not_called()

    def test_setting_deck_should_no_set_revealed_as_false_if_deck_is_the_same(self):
        game = Game('PBR Team Pizza', Deck.POWERS)
        game.reveal_hands()
        self.assertTrue(game.get_revealed())
        game.set_deck(Deck.POWERS)
        self.assertTrue(game.get_revealed())

    def test_is_game_empty(self):
        uuid = '47b71b00-e060-47ba-8fae-029f5473794b'
        game = Game('PBR Team Pizza')
        self.assertTrue(game.is_game_empty())
        player = Mock()
        game.player_joins(uuid, player)
        self.assertFalse(game.is_game_empty())
        game.player_leaves(uuid)
        self.assertTrue(game.is_game_empty())

    def test_get_non_spectator_players(self):
        game = Game('PBR Team Pizza')
        player_1 = Mock()
        player1_conf = {'spectator': False}
        player_1.configure_mock(**player1_conf)
        game.player_joins('j', player_1)
        player_2 = Mock()
        player2_conf = {'spectator': False}
        player_2.configure_mock(**player2_conf)
        game.player_joins('p', player_2)
        spectator_1 = Mock()
        spectator_conf = {'spectator': True}
        spectator_1.configure_mock(**spectator_conf)
        game.player_joins('d', spectator_1)
        self.assertEqual(game.get_non_spectator_players(), [player_1, player_2])

    def test_all_players_have_picked_card(self):
        game = Game('PBR Team Pizza')
        player_1 = Mock()
        player1_conf = {'spectator': False, 'has_picked_card.return_value': True}
        player_1.configure_mock(**player1_conf)
        game.player_joins('j', player_1)

        player_2 = Mock()
        player2_conf = {'spectator': False, 'has_picked_card.return_value': False}
        player_2.configure_mock(**player2_conf)
        game.player_joins('p', player_2)

        spectator_1 = Mock()
        spectator_conf = {'spectator': True, 'has_picked_card.return_value': False}
        spectator_1.configure_mock(**spectator_conf)
        game.player_joins('d', spectator_1)
        self.assertFalse(game.has_all_players_picked_card())

        player2_conf['has_picked_card.return_value'] = True
        player_2.configure_mock(**player2_conf)
        self.assertTrue(game.has_all_players_picked_card())

    def test_state_when_revealed_is_false(self):
        game = Game('PBR Team Pizza')
        player_1 = Mock()
        player1_state = {'name': 'John', 'spectator': False, 'hasPicked': True}
        player_1.configure_mock(**{'state.return_value': player1_state})
        game.player_joins('j', player_1)
        player_2 = Mock()
        player2_state = {'name': 'Peter', 'spectator': False, 'hasPicked': False}
        player_2.configure_mock(**{'state.return_value': player2_state})
        game.player_joins('p', player_2)
        spectator_1 = Mock()
        spectator1_state = {'name': 'Daisy', 'spectator': True, 'hasPicked': False}
        spectator_1.configure_mock(**{'state.return_value': spectator1_state})
        game.player_joins('d', spectator_1)

        self.assertEqual(game.state(), {
            'j': player1_state,
            'p': player2_state,
            'd': spectator1_state,
        })

    def test_state_when_revealed_is_true(self):
        game = Game('PBR Team Pizza')
        player_1 = Mock()
        player1_state = {'name': 'John', 'spectator': False, 'hand': 3, 'hasPicked': True}
        player_1.configure_mock(**{'state_with_hand.return_value': player1_state})
        game.player_joins('j', player_1)
        player_2 = Mock()
        player2_state = {'name': 'Peter', 'spectator': False, 'hand': None, 'hasPicked': False}
        player_2.configure_mock(**{'state_with_hand.return_value': player2_state})
        game.player_joins('p', player_2)
        spectator_1 = Mock()
        spectator1_state = {'name': 'Daisy', 'spectator': True, 'hand': None, 'hasPicked': False}
        spectator_1.configure_mock(**{'state_with_hand.return_value': spectator1_state})
        game.player_joins('d', spectator_1)

        game.reveal_hands()
        self.assertEqual(game.state(), {
            'j': player1_state,
            'p': player2_state,
            'd': spectator1_state,
        })

    def test_state_when_revealed_is_true_then_false(self):
        game = Game('PBR Team Pizza')
        player_1 = Mock()
        player1_state = {'name': 'John', 'spectator': False, 'hasPicked': True}
        player1_state_with_hand = {'name': 'John', 'spectator': False, 'hand': 3}
        player_1.configure_mock(**{'state.return_value': player1_state,
                                   'state_with_hand.return_value': player1_state_with_hand})
        game.player_joins('j', player_1)
        player_2 = Mock()
        player2_state = {'name': 'Peter', 'spectator': False, 'hasPicked': False}
        player2_state_with_hand = {'name': 'Peter', 'spectator': False, 'hand': None}
        player_2.configure_mock(**{'state.return_value': player2_state,
                                   'state_with_hand.return_value': player2_state_with_hand})
        game.player_joins('p', player_2)
        spectator_1 = Mock()
        spectator1_state = {'name': 'Daisy', 'spectator': True, 'hasPicked': False}
        spectator1_state_with_hand = {'name': 'Daisy', 'spectator': True, 'hand': None}
        spectator_1.configure_mock(**{'state.return_value': spectator1_state,
                                      'state_with_hand.return_value': spectator1_state_with_hand})
        game.player_joins('d', spectator_1)

        self.assertEqual(game.state(), {
            'j': player1_state,
            'p': player2_state,
            'd': spectator1_state,
        })

        game.reveal_hands()
        self.assertEqual(game.state(), {
            'j': player1_state_with_hand,
            'p': player2_state_with_hand,
            'd': spectator1_state_with_hand,
        })

        game.end_turn()
        self.assertEqual(game.state(), {
            'j': player1_state,
            'p': player2_state,
            'd': spectator1_state,
        })

    def test_reveal_hand(self):
        game = Game('PBR Team Pizza')
        self.assertFalse(game.get_revealed())
        game.reveal_hands()
        self.assertTrue(game.get_revealed())

    def test_game_info(self):
        game_name1 = 'Fizz'
        game1 = Game(game_name1)
        self.assertEqual(game1.info(), {'name': game_name1, 'deck': 'FIBONACCI', 'revealed': False, 'driverId': None})

        game_name2 = 'Buzz'
        game2 = Game(game_name2, Deck.POWERS)
        self.assertEqual(game2.info(), {'name': game_name2, 'deck': 'POWERS', 'revealed': False, 'driverId': None})
        game2.reveal_hands()
        self.assertEqual(game2.info(), {'name': game_name2, 'deck': 'POWERS', 'revealed': True, 'driverId': None})
        game2.end_turn()
        self.assertEqual(game2.info(), {'name': game_name2, 'deck': 'POWERS', 'revealed': False, 'driverId': None})

    def test_first_joiner_becomes_driver_and_hands_off_on_leave(self):
        game = Game('Sprint')
        game.player_joins('a', Mock())
        self.assertTrue(game.is_driver('a'))
        game.player_joins('b', Mock())
        self.assertTrue(game.is_driver('a'))      # still the first joiner
        self.assertFalse(game.is_driver('b'))
        game.player_leaves('a')                   # driver leaves
        self.assertTrue(game.is_driver('b'))      # auto-handoff to whoever remains
        self.assertEqual(game.info()['driverId'], 'b')

    def test_claim_driver_takes_over(self):
        game = Game('Sprint')
        game.player_joins('a', Mock())
        game.player_joins('b', Mock())
        game.claim_driver('b')
        self.assertTrue(game.is_driver('b'))
        self.assertFalse(game.is_driver('a'))
        game.claim_driver('ghost')                # not a present player → ignored
        self.assertTrue(game.is_driver('b'))

    def test_set_and_expose_backlog(self):
        game = Game('Sprint')
        self.assertFalse(game.has_backlog())
        issues = [{'id': 1, 'key': 'OPS-1', 'summary': 's', 'status': 'pending', 'orderIndex': 0}]
        game.set_backlog(issues, current=0, results={1: [{'round': 1}]})
        self.assertTrue(game.has_backlog())
        payload = game.backlog()
        self.assertEqual(payload['issues'], issues)
        self.assertEqual(payload['currentIndex'], 0)
        self.assertEqual(payload['results'], {1: [{'round': 1}]})

    @staticmethod
    def _backlog():
        return [
            {'id': 1, 'key': 'OPS-1', 'summary': 'a', 'status': 'pending', 'orderIndex': 0},
            {'id': 2, 'key': 'OPS-2', 'summary': 'b', 'status': 'pending', 'orderIndex': 1},
            {'id': 3, 'key': 'OPS-3', 'summary': 'c', 'status': 'pending', 'orderIndex': 2},
        ]

    def test_select_issue_moves_pointer_and_flips_status(self):
        game = Game('Sprint')
        issues = self._backlog()
        game.set_backlog(issues, current=None)
        changed = game.select_issue(1)
        self.assertEqual(game.backlog()['currentIndex'], 1)
        self.assertEqual(issues[1]['status'], 'estimating')
        self.assertIn(issues[1], changed)
        self.assertEqual(game.current_issue()['key'], 'OPS-2')

    def test_select_issue_reverts_unfinished_previous(self):
        game = Game('Sprint')
        issues = self._backlog()
        issues[0]['status'] = 'estimating'
        game.set_backlog(issues, current=0)
        changed = game.select_issue(1)
        self.assertEqual(issues[0]['status'], 'pending')   # never completed → reverted
        self.assertEqual(issues[1]['status'], 'estimating')
        self.assertIn(issues[0], changed)

    def test_select_issue_preserves_a_completed_estimate(self):
        game = Game('Sprint')
        issues = self._backlog()
        issues[0]['status'] = 'estimated'
        game.set_backlog(issues, current=0)
        game.select_issue(1)
        self.assertEqual(issues[0]['status'], 'estimated')  # terminal status preserved

    def test_select_issue_views_parked_without_reopening(self):
        # Behaviour change (see decisions): selecting a parked issue VIEWS it; it must
        # not silently re-open for voting. The host re-opens explicitly (reopen_current).
        game = Game('Sprint')
        issues = self._backlog()
        issues[2]['status'] = 'refinement'
        game.set_backlog(issues, current=0)
        changed = game.select_issue(2)
        self.assertEqual(game.backlog()['currentIndex'], 2)  # pointer moved (view)
        self.assertEqual(issues[2]['status'], 'refinement')  # NOT re-opened
        self.assertNotIn(issues[2], changed)                 # nothing to persist for it

    def test_select_issue_views_estimated_without_reopening(self):
        game = Game('Sprint')
        issues = self._backlog()
        issues[2]['status'] = 'estimated'
        game.set_backlog(issues, current=0)
        game.select_issue(2)
        self.assertEqual(game.backlog()['currentIndex'], 2)
        self.assertEqual(issues[2]['status'], 'estimated')   # preserved, view-only

    def test_reopen_current_reopens_an_estimated_issue(self):
        game = Game('Sprint')
        issues = self._backlog()
        issues[1]['status'] = 'estimated'
        game.set_backlog(issues, current=1)
        changed = game.reopen_current()
        self.assertEqual(issues[1]['status'], 'estimating')  # explicit host re-open
        self.assertIs(changed, issues[1])

    def test_reopen_current_clears_park_reason(self):
        game = Game('Sprint')
        issues = self._backlog()
        issues[0]['status'] = 'refinement'
        issues[0]['parkReason'] = 'missing AC'
        game.set_backlog(issues, current=0)
        game.reopen_current()
        self.assertEqual(issues[0]['status'], 'estimating')
        self.assertIsNone(issues[0]['parkReason'])           # no longer parked

    def test_reopen_current_clears_table(self):
        game = Game('Sprint')
        issues = self._backlog()
        issues[0]['status'] = 'estimated'
        game.set_backlog(issues, current=0)
        player = Mock()
        player.configure_mock(**{'spectator': False})
        game.player_joins('p', player)
        game.reveal_hands()
        game.reopen_current()
        self.assertFalse(game.get_revealed())
        player.clear_hand.assert_called()

    def test_reopen_current_without_issue_returns_none(self):
        game = Game('Sprint')
        game.set_backlog(self._backlog(), current=None)
        self.assertIsNone(game.reopen_current())

    def test_select_issue_clears_table(self):
        game = Game('Sprint')
        game.set_backlog(self._backlog(), current=0)
        player = Mock()
        player.configure_mock(**{'spectator': False})
        game.player_joins('p', player)
        game.reveal_hands()
        game.select_issue(1)
        self.assertFalse(game.get_revealed())
        player.clear_hand.assert_called()

    def test_select_issue_out_of_range_raises(self):
        from gamestate.exceptions import IssueNotInBacklogError
        game = Game('Sprint')
        game.set_backlog(self._backlog(), current=0)
        with self.assertRaises(IssueNotInBacklogError):
            game.select_issue(9)

    def test_rejoin_token_reattaches_same_slot(self):
        game = Game('Sprint')
        p1 = Mock()
        p1.configure_mock(**{'spectator': False})
        eff1 = game.player_joins('id-1', p1, token='tok')
        self.assertEqual(eff1, 'id-1')
        # Same human rejoins (same token) while still present → reuse id, no duplicate.
        p1b = Mock()
        p1b.configure_mock(**{'spectator': False})
        eff2 = game.player_joins('id-2', p1b, token='tok')
        self.assertEqual(eff2, 'id-1')
        self.assertEqual(game.list_players_uuid(), ['id-1'])

    def test_join_without_token_keeps_distinct_players(self):
        game = Game('Sprint')
        game.player_joins('id-1', Mock())
        game.player_joins('id-2', Mock())
        self.assertEqual(len(game.list_players_uuid()), 2)


if __name__ == '__main__':
    unittest.main()
