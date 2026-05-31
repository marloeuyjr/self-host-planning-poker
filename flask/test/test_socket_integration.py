"""End-to-end integration test of the Socket.IO handlers in app.py.

The unit suites cover GameManager / Game / stats / intake. This drives the real
handlers through flask-socketio's in-process test client, so it catches wiring and
emit-shape bugs (event names, payload keys, the driver gate, persistence) that the
unit tests can't — the layer the operator's live session actually exercises.

A scratch DB is selected via DATABASE_PATH before app is imported (the override added
to app.py for testability); prod behaviour is unchanged.
"""
import os
import tempfile
import unittest

os.environ['DATABASE_PATH'] = os.path.join(tempfile.gettempdir(), 'poker_socket_it.db')
if os.path.exists(os.environ['DATABASE_PATH']):
    os.remove(os.environ['DATABASE_PATH'])

import app as app_module  # noqa: E402  (env must be set first)
from gamestate.models import EstimationResult, Issue, database_proxy, create_tables  # noqa: E402


def _last(received, name):
    """The args[0] payload of the most recent event called `name`, or None."""
    matches = [e for e in received if e['name'] == name]
    return matches[-1]['args'][0] if matches and matches[-1]['args'] else (matches[-1] if matches else None)


def _names(received):
    return [e['name'] for e in received]


class SocketIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        # Other suites re-point the shared database_proxy at their own in-memory DBs;
        # re-assert app's scratch DB (created at import) so these tests are order-proof.
        database_proxy.initialize(app_module.real_db)
        if database_proxy.is_closed():
            database_proxy.connect()
        create_tables()
        self.app = app_module.app
        self.socketio = app_module.socketio
        self.gm = app_module.gm
        self.gm.games.clear()   # don't inherit cached games from a prior test

    def _new_backlog_game(self):
        return self.gm.create('Sprint', 'FIBONACCI',
                              [{'jira_key': 'OPS-1', 'summary': 'first'},
                               {'jira_key': 'OPS-2', 'summary': 'second'}], source='paste')

    def _join(self, game_id, name='Ann', spectator=False, token=None):
        client = self.socketio.test_client(self.app)
        ack = client.emit('join', {'game': game_id, 'name': name,
                                   'spectator': spectator, 'token': token}, callback=True)
        return client, ack

    def test_join_emits_backlog_and_full_loop_persists(self):
        game_id = self._new_backlog_game()

        driver, ack = self._join(game_id, 'Ann')          # first joiner → driver
        self.assertIn('playerId', ack)
        backlog = _last(driver.get_received(), 'backlog')
        self.assertEqual([i['key'] for i in backlog['issues']], ['OPS-1', 'OPS-2'])

        guest, _ = self._join(game_id, 'Bob')              # second non-spectator

        driver.emit('select_issue', {'index': 0})
        backlog = _last(driver.get_received(), 'backlog')
        self.assertEqual(backlog['currentIndex'], 0)
        self.assertEqual(backlog['issues'][0]['status'], 'estimating')

        driver.emit('pick_card', {'card': 5})
        guest.emit('pick_card', {'card': 8})
        driver.get_received(); guest.get_received()        # drain

        driver.emit('reveal_cards')
        results = _last(driver.get_received(), 'results')
        self.assertEqual(results['count'], 2)
        self.assertEqual(results['average'], 6.5)
        self.assertEqual(results['distribution'], {'5': 1, '8': 1})   # JSON keys are strings
        # 5 and 8 are adjacent, but each has one vote → multi-modal tie → no consensus (E3).
        self.assertFalse(results['consensus'])
        self.assertIsNone(results['proposedFinalValue'])
        self.assertEqual(results['round'], 1)

        issue0_id = backlog['issues'][0]['id']
        driver.emit('accept_estimate', {'value': 8})
        adv = _last(driver.get_received(), 'backlog')
        self.assertEqual(adv['currentIndex'], 1)           # advanced to OPS-2
        self.assertEqual(adv['issues'][0]['status'], 'estimated')

        row = EstimationResult.get(EstimationResult.issue == issue0_id)
        self.assertEqual(row.final_value, 8.0)             # persisted, before clear
        self.assertEqual(row.round_number, 1)
        self.assertEqual(row.voter_count, 2)

    def test_driver_gate_rejects_non_driver(self):
        game_id = self._new_backlog_game()
        driver, _ = self._join(game_id, 'Ann')             # driver
        guest, _ = self._join(game_id, 'Bob')              # non-driver

        driver.emit('select_issue', {'index': 0})
        guest.get_received()

        # Non-driver reveal is rejected server-side with the 4008 error in the ack.
        err = guest.emit('reveal_cards', callback=True)
        self.assertIsInstance(err, dict)
        self.assertTrue(err.get('error'))
        self.assertEqual(err.get('code'), 4008)

        # The driver succeeds: no error ack, and a results event is broadcast.
        ok = driver.emit('reveal_cards', callback=True)
        self.assertFalse(isinstance(ok, dict) and ok.get('error'))
        self.assertIsNotNone(_last(driver.get_received(), 'results'))

    def test_park_advances_and_persists(self):
        game_id = self._new_backlog_game()
        driver, _ = self._join(game_id, 'Ann')
        driver.emit('select_issue', {'index': 0})
        backlog = _last(driver.get_received(), 'backlog')
        parked_id = backlog['issues'][0]['id']

        driver.emit('park_issue', {'status': 'refinement', 'reason': 'missing AC'})
        adv = _last(driver.get_received(), 'backlog')
        self.assertEqual(adv['currentIndex'], 1)
        self.assertEqual(Issue.get(Issue.id == parked_id).status, 'refinement')
        self.assertEqual(Issue.get(Issue.id == parked_id).park_reason, 'missing AC')

    def test_select_is_view_only_and_reopen_revotes_a_done_issue(self):
        game_id = self._new_backlog_game()
        driver, _ = self._join(game_id, 'Ann')
        guest, _ = self._join(game_id, 'Bob')
        issue0_id = _last(driver.get_received(), 'backlog')['issues'][0]['id']

        driver.emit('select_issue', {'index': 0})
        driver.emit('pick_card', {'card': 5}); guest.emit('pick_card', {'card': 5})
        driver.get_received(); guest.get_received()
        driver.emit('reveal_cards')
        driver.emit('accept_estimate', {'value': 5})       # round 1 → estimated, advances
        driver.get_received()

        # Selecting the Done issue VIEWS it — it stays estimated, not re-opened.
        driver.emit('select_issue', {'index': 0})
        viewed = _last(driver.get_received(), 'backlog')
        self.assertEqual(viewed['issues'][0]['status'], 'estimated')

        # A non-driver cannot re-open (soft host gate, 4008).
        err = guest.emit('reopen_issue', callback=True)
        self.assertEqual(err.get('code'), 4008)

        # The driver re-opens for a fresh round; the prior result is untouched.
        driver.emit('reopen_issue')
        reopened = _last(driver.get_received(), 'backlog')
        self.assertEqual(reopened['currentIndex'], 0)
        self.assertEqual(reopened['issues'][0]['status'], 'estimating')
        self.assertEqual(len(reopened['results'][str(issue0_id)]), 1)   # round 1 preserved

    def test_resume_after_restart_flags_resumed(self):
        game_id = self._new_backlog_game()
        driver, _ = self._join(game_id, 'Ann')
        driver.emit('select_issue', {'index': 0})          # OPS-1 → estimating (persisted)

        self.gm.games.clear()                              # simulate a worker restart

        _, ack = self._join(game_id, 'Cara')               # rejoin → cache-miss rehydrate
        self.assertTrue(ack.get('resumed'))


if __name__ == '__main__':
    unittest.main()
