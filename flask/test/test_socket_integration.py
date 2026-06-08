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
from gamestate.models import EstimationResult, Issue, StoredGame, database_proxy, create_tables  # noqa: E402


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

    def test_rename_game_is_gated_to_the_driver(self):
        # rename_game mutates the live session AND the durable record, so it must
        # carry the same soft host gate as the other mutating handlers (4008).
        game_id = self._new_backlog_game()
        driver, _ = self._join(game_id, 'Ann')             # driver
        guest, _ = self._join(game_id, 'Bob')              # non-driver
        driver.get_received(); guest.get_received()

        err = guest.emit('rename_game', {'name': 'Hijacked'}, callback=True)
        self.assertIsInstance(err, dict)
        self.assertEqual(err.get('code'), 4008)
        self.assertEqual(app_module.gm.info(game_id)['name'], 'Sprint')   # unchanged

        driver.emit('rename_game', {'name': 'Renamed'})
        info = _last(driver.get_received(), 'info')
        self.assertEqual(info['name'], 'Renamed')          # driver succeeds + broadcasts

    def test_free_text_is_clamped_server_side(self):
        # Names + park reasons fan out into every full-snapshot broadcast and the DB;
        # the server clamps rather than rejects (a paste should never strand a handler).
        game_id = self._new_backlog_game()
        driver, _ = self._join(game_id, 'Ann')
        driver.get_received()

        driver.emit('rename_game', {'name': 'x' * 500})
        info = _last(driver.get_received(), 'info')
        self.assertLessEqual(len(info['name']), 120)

        driver.emit('select_issue', {'index': 0})
        driver.get_received()
        driver.emit('park_issue', {'status': 'refinement', 'reason': 'y' * 500})
        backlog = _last(driver.get_received(), 'backlog')
        self.assertLessEqual(len(backlog['issues'][0]['parkReason']), 200)

    def test_join_mid_reveal_sends_results_to_the_late_joiner(self):
        # Joining while a reveal is on the table should render that round, not an
        # empty 'no votes' summary — and only the joiner gets it (no room re-confetti).
        game_id = self._new_backlog_game()
        driver, _ = self._join(game_id, 'Ann')
        guest, _ = self._join(game_id, 'Bob')
        driver.emit('select_issue', {'index': 0})
        driver.emit('pick_card', {'card': 5}); guest.emit('pick_card', {'card': 5})
        driver.get_received(); guest.get_received()
        driver.emit('reveal_cards')
        driver.get_received(); guest.get_received()        # drain the reveal broadcast

        late, _ = self._join(game_id, 'Cara', spectator=True)
        results = _last(late.get_received(), 'results')
        self.assertIsNotNone(results)
        self.assertEqual(results['count'], 2)
        # The room is not re-notified (the existing players already saw the reveal).
        self.assertNotIn('results', _names(driver.get_received()))

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

    def test_add_issues_appends_for_driver_and_gates_others(self):
        game_id = self._new_backlog_game()
        driver, _ = self._join(game_id, 'Ann')             # first joiner → driver
        guest, _ = self._join(game_id, 'Bob')              # non-driver

        driver.emit('select_issue', {'index': 0})          # OPS-1 → estimating
        driver.get_received(); guest.get_received()        # drain

        # A non-driver cannot append to the queue (soft host gate, 4008).
        err = guest.emit('add_issues', {'backlog': 'OPS-9  sneaky', 'backlogFormat': 'paste'},
                         callback=True)
        self.assertIsInstance(err, dict)
        self.assertEqual(err.get('code'), 4008)
        self.assertEqual(Issue.select().where(Issue.game == game_id).count(), 2)   # nothing added

        # The driver appends two issues mid-session; they land at the tail and the
        # current pointer is untouched (append never disturbs the active round).
        driver.emit('add_issues', {'backlog': 'OPS-3  late one\nOPS-4  late two',
                                   'backlogFormat': 'paste'})
        backlog = _last(driver.get_received(), 'backlog')
        self.assertEqual([i['key'] for i in backlog['issues']], ['OPS-1', 'OPS-2', 'OPS-3', 'OPS-4'])
        self.assertEqual(backlog['currentIndex'], 0)       # still on OPS-1
        self.assertEqual(backlog['issues'][0]['status'], 'estimating')
        # Persisted at the tail of the order with provenance.
        rows = list(Issue.select().where(Issue.game == game_id).order_by(Issue.order_index))
        self.assertEqual([r.order_index for r in rows], [0, 1, 2, 3])
        added = Issue.get((Issue.game == game_id) & (Issue.jira_key == 'OPS-4'))
        self.assertEqual(added.source, 'paste')
        self.assertEqual(added.status, 'pending')

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

    def test_sessions_endpoint_empty_db_returns_empty_list(self):
        # No games created in this test → the recall list is an empty JSON array.
        StoredGame.delete().execute()                      # clear any rows from prior tests
        client = self.app.test_client()
        resp = client.get('/sessions')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [])

    def test_sessions_endpoint_lists_games_with_counts_newest_first(self):
        StoredGame.delete().execute()                      # isolate from other tests' rows

        # Older game with a backlog; estimate one issue so it has a real estimated count.
        older_id = self._new_backlog_game()                # 2 issues: OPS-1, OPS-2
        driver, _ = self._join(older_id, 'Ann')
        guest, _ = self._join(older_id, 'Bob')
        driver.emit('select_issue', {'index': 0})
        driver.emit('pick_card', {'card': 5}); guest.emit('pick_card', {'card': 5})
        driver.get_received(); guest.get_received()
        driver.emit('reveal_cards')
        driver.emit('accept_estimate', {'value': 5})       # OPS-1 → estimated

        # Newer game with a single issue, none estimated.
        newer_id = self.gm.create('Sprint Next', 'POWERS',
                                  [{'jira_key': 'OPS-9', 'summary': 'solo'}], source='paste')

        client = self.app.test_client()
        resp = client.get('/sessions')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

        # Newest-first ordering: the more recently created game comes first.
        self.assertEqual(data[0]['uuid'], newer_id)
        self.assertEqual(data[1]['uuid'], older_id)

        by_uuid = {s['uuid']: s for s in data}
        older = by_uuid[older_id]
        self.assertEqual(older['name'], 'Sprint')
        self.assertEqual(older['deck'], 'FIBONACCI')
        self.assertEqual(older['total'], 2)
        self.assertEqual(older['estimated'], 1)
        self.assertIsNotNone(older['createdAt'])

        newer = by_uuid[newer_id]
        self.assertEqual(newer['name'], 'Sprint Next')
        self.assertEqual(newer['deck'], 'POWERS')
        self.assertEqual(newer['total'], 1)
        self.assertEqual(newer['estimated'], 0)

    def test_sessions_endpoint_legacy_null_created_at_sorts_last(self):
        StoredGame.delete().execute()

        # A timestamped game and a legacy game whose created_at is NULL (predates B2).
        recent_id = self.gm.create('Recent', 'FIBONACCI')
        legacy_id = str(__import__('uuid').uuid4())
        StoredGame.insert(uuid=legacy_id, name='Legacy', deck='POWERS',
                          created_at=None).execute()

        resp = self.app.test_client().get('/sessions')
        data = resp.get_json()
        self.assertEqual([s['uuid'] for s in data], [recent_id, legacy_id])
        legacy = next(s for s in data if s['uuid'] == legacy_id)
        self.assertIsNone(legacy['createdAt'])
        self.assertEqual(legacy['total'], 0)
        self.assertEqual(legacy['estimated'], 0)

    # --- v2: session export endpoints (CSV / JSON) ---

    def _seed_estimated_game(self, card=5, value=5):
        """A 2-issue game with OPS-1 estimated at `value` (both players voted `card`)."""
        game_id = self._new_backlog_game()                 # OPS-1, OPS-2 (FIBONACCI)
        driver, _ = self._join(game_id, 'Ann')
        guest, _ = self._join(game_id, 'Bob')
        driver.emit('select_issue', {'index': 0})
        driver.emit('pick_card', {'card': card}); guest.emit('pick_card', {'card': card})
        driver.get_received(); guest.get_received()
        driver.emit('reveal_cards')
        driver.emit('accept_estimate', {'value': value})   # OPS-1 → estimated
        return game_id

    def test_export_json_endpoint_returns_full_session(self):
        game_id = self._seed_estimated_game(card=5, value=8)
        resp = self.app.test_client().get(f'/sessions/{game_id}/export.json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.mimetype.startswith('application/json'))
        data = resp.get_json()
        self.assertEqual(data['uuid'], game_id)
        self.assertEqual(data['name'], 'Sprint')
        self.assertEqual(data['deck'], 'FIBONACCI')
        self.assertEqual(data['total'], 2)
        self.assertEqual(data['estimated'], 1)
        self.assertEqual(data['pointsTotal'], 8.0)          # only OPS-1 accepted so far
        by_key = {i['key']: i for i in data['issues']}
        self.assertEqual(by_key['OPS-1']['finalValue'], 8.0)
        self.assertEqual(by_key['OPS-1']['voterCount'], 2)
        self.assertIsNone(by_key['OPS-2']['finalValue'])    # not yet estimated

    def test_export_csv_endpoint_has_attachment_header_and_rows(self):
        game_id = self._seed_estimated_game(card=5, value=5)
        resp = self.app.test_client().get(f'/sessions/{game_id}/export.csv')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.mimetype.startswith('text/csv'))
        disposition = resp.headers.get('Content-Disposition', '')
        self.assertIn('attachment', disposition)
        self.assertIn('sprint-poker.csv', disposition)      # slug from the session name
        lines = [l for l in resp.get_data(as_text=True).splitlines() if l]
        self.assertEqual(lines[0], 'order,key,summary,status,final_value,rounds,'
                                   'average,agreement,voter_count,deck,park_reason')
        ops1 = next(l for l in lines if l.startswith('0,OPS-1,'))
        cells = ops1.split(',')
        self.assertEqual(cells[3], 'estimated')             # status
        self.assertEqual(cells[4], '5.0')                   # final_value
        self.assertEqual(cells[8], '2')                     # voter_count
        self.assertEqual(cells[9], 'FIBONACCI')             # deck

    def test_export_endpoints_unknown_uuid_return_404(self):
        bogus = str(__import__('uuid').uuid4())
        client = self.app.test_client()
        self.assertEqual(client.get(f'/sessions/{bogus}/export.json').status_code, 404)
        self.assertEqual(client.get(f'/sessions/{bogus}/export.csv').status_code, 404)

    # --- v2.3: hardened /create + baseline security/cache headers ---

    def test_create_rejects_a_malformed_body_with_400(self):
        client = self.app.test_client()
        # Missing deck, missing name, and a non-JSON body all 400 instead of 500ing
        # on a KeyError / None dereference.
        self.assertEqual(client.post('/create', json={'name': 'X'}).status_code, 400)
        self.assertEqual(client.post('/create', json={'deck': 'FIBONACCI'}).status_code, 400)
        self.assertEqual(client.post('/create', data='not json',
                                     content_type='text/plain').status_code, 400)

    def test_create_accepts_a_valid_body(self):
        resp = self.app.test_client().post('/create', json={'name': 'Sprint', 'deck': 'FIBONACCI'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_data(as_text=True))   # returns the new game uuid

    def test_security_and_cache_headers_present(self):
        resp = self.app.test_client().get('/sessions')
        self.assertEqual(resp.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(resp.headers.get('X-Frame-Options'), 'DENY')
        csp = resp.headers.get('Content-Security-Policy', '')
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("script-src 'self'", csp)
        # The JSON API must revalidate, not be cached as static.
        self.assertEqual(resp.headers.get('Cache-Control'), 'no-cache')


if __name__ == '__main__':
    unittest.main()
