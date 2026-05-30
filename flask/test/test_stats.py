import unittest

from gamestate.deck import Deck
from gamestate.stats import compute_stats, ABSTAIN


class StatsTestCase(unittest.TestCase):
    def test_empty_round_has_no_average_and_no_consensus(self):
        s = compute_stats([], Deck.FIBONACCI)
        self.assertEqual(s['count'], 0)
        self.assertIsNone(s['average'])
        self.assertIsNone(s['median'])
        self.assertIsNone(s['agreement'])
        self.assertEqual(s['distribution'], {})
        self.assertEqual(s['mode'], [])
        self.assertFalse(s['consensus'])
        self.assertFalse(s['unanimous'])

    def test_single_vote(self):
        s = compute_stats([5], Deck.FIBONACCI)
        self.assertEqual(s['count'], 1)
        self.assertEqual(s['average'], 5.0)
        self.assertEqual(s['median'], 5)
        self.assertEqual(s['mode'], [5])
        self.assertEqual(s['low'], 5)
        self.assertEqual(s['high'], 5)
        self.assertEqual(s['agreement'], 1.0)
        self.assertTrue(s['consensus'])
        self.assertTrue(s['unanimous'])

    def test_unanimous(self):
        s = compute_stats([3, 3, 3], Deck.FIBONACCI)
        self.assertEqual(s['average'], 3.0)
        self.assertEqual(s['mode'], [3])
        self.assertEqual(s['agreement'], 1.0)
        self.assertTrue(s['unanimous'])
        self.assertTrue(s['consensus'])

    def test_adjacent_single_mode_is_consensus(self):
        # 3 @ idx3, 5 @ idx4 on FIBONACCI -> adjacent; single mode (3)
        s = compute_stats([3, 3, 5], Deck.FIBONACCI)
        self.assertEqual(s['average'], round(11 / 3, 2))
        self.assertEqual(s['mode'], [3])
        self.assertTrue(s['consensus'])
        self.assertFalse(s['unanimous'])

    def test_multi_step_spread_is_not_consensus(self):
        # 2 @ idx2, 13 @ idx6 -> 4 steps apart
        s = compute_stats([2, 13], Deck.FIBONACCI)
        self.assertFalse(s['consensus'])
        self.assertEqual(s['average'], 7.5)
        self.assertEqual(s['low'], 2)
        self.assertEqual(s['high'], 13)

    def test_multimodal_tie_is_not_consensus(self):
        # adjacent cards but a bimodal tie -> no-consensus (E3)
        s = compute_stats([3, 3, 5, 5], Deck.FIBONACCI)
        self.assertEqual(s['mode'], [3, 5])
        self.assertFalse(s['consensus'])

    def test_abstain_only(self):
        s = compute_stats([ABSTAIN, ABSTAIN], Deck.FIBONACCI)
        self.assertEqual(s['count'], 0)
        self.assertEqual(s['abstains'], 2)
        self.assertIsNone(s['average'])
        self.assertFalse(s['consensus'])

    def test_abstain_excluded_from_average(self):
        s = compute_stats([ABSTAIN, 8], Deck.FIBONACCI)
        self.assertEqual(s['count'], 1)
        self.assertEqual(s['abstains'], 1)
        self.assertEqual(s['average'], 8.0)
        self.assertEqual(s['mode'], [8])
        self.assertEqual(s['agreement'], 1.0)
        self.assertTrue(s['consensus'])

    def test_zero_is_counted_in_average(self):
        # the old client-side math dropped/0-divided here; 0 is a real vote
        s = compute_stats([0, 0, 1], Deck.FIBONACCI)
        self.assertEqual(s['average'], round(1 / 3, 2))
        self.assertEqual(s['mode'], [0])
        self.assertEqual(s['low'], 0)
        self.assertTrue(s['consensus'])  # 0 @ idx0, 1 @ idx1 adjacent, single mode

    def test_non_numeric_deck_is_distribution_only(self):
        s = compute_stats([2, 2, 3], Deck.T_SHIRTS)
        self.assertFalse(s['numeric'])
        self.assertIsNone(s['average'])
        self.assertIsNone(s['median'])
        self.assertEqual(s['distribution'], {2: 2, 3: 1})
        self.assertEqual(s['mode'], [2])
        self.assertEqual(s['agreement'], round(2 / 3, 2))
        self.assertTrue(s['consensus'])

    def test_trust_vote_deck_is_distribution_only(self):
        s = compute_stats([4, 5], Deck.TRUST_VOTE)
        self.assertFalse(s['numeric'])
        self.assertIsNone(s['average'])

    def test_powers_deck_adjacency(self):
        # POWERS = [0,1,2,4,8,16,32,64]
        consensus = compute_stats([4, 4, 8], Deck.POWERS)  # idx3, idx4 adjacent, mode [4]
        self.assertTrue(consensus['consensus'])
        spread = compute_stats([4, 64], Deck.POWERS)  # idx3 vs idx7
        self.assertFalse(spread['consensus'])


if __name__ == '__main__':
    unittest.main()
