import unittest
import uuid

from peewee import SqliteDatabase, IntegrityError

from gamestate.models import (database_proxy, StoredGame, Issue,
                              EstimationResult, create_tables)


class ModelsTestCase(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDatabase(':memory:')
        database_proxy.initialize(self.db)
        self.db.connect()
        create_tables()

    def tearDown(self):
        self.db.drop_tables([EstimationResult, Issue, StoredGame])
        self.db.close()

    def _game(self, name='Sprint 42', deck='FIBONACCI'):
        return StoredGame.create(uuid=str(uuid.uuid4()), name=name, deck=deck)

    def test_new_tables_created_alongside_stored_game(self):
        tables = set(self.db.get_tables())
        self.assertTrue({'storedgame', 'issue', 'estimationresult'}.issubset(tables))

    def test_issues_keep_their_queue_order(self):
        game = self._game()
        for i, key in enumerate(['OPS-1', 'OPS-2', 'OPS-3']):
            Issue.create(game=game, jira_key=key, summary=f'summary {key}', order_index=i)
        keys = [iss.jira_key for iss in game.issues.order_by(Issue.order_index)]
        self.assertEqual(keys, ['OPS-1', 'OPS-2', 'OPS-3'])

    def test_issue_defaults_to_pending(self):
        game = self._game()
        issue = Issue.create(game=game, jira_key='OPS-1', summary='x', order_index=0)
        self.assertEqual(issue.status, 'pending')

    def test_estimation_results_are_append_only_across_rounds(self):
        game = self._game()
        issue = Issue.create(game=game, jira_key='OPS-1', summary='x', order_index=0)
        EstimationResult.create(issue=issue, round_number=1, average=5.0,
                                agreement=0.6, deck_at_vote='FIBONACCI', voter_count=4)
        EstimationResult.create(issue=issue, round_number=2, final_value=8.0, average=8.0,
                                agreement=1.0, deck_at_vote='FIBONACCI', voter_count=4)
        rounds = [r.round_number for r in issue.results.order_by(EstimationResult.round_number)]
        self.assertEqual(rounds, [1, 2])
        self.assertIsNone(issue.results.where(EstimationResult.round_number == 1).get().final_value)
        self.assertEqual(issue.results.where(EstimationResult.round_number == 2).get().final_value, 8.0)

    def test_duplicate_round_for_same_issue_is_rejected(self):
        game = self._game()
        issue = Issue.create(game=game, jira_key='OPS-1', summary='x', order_index=0)
        EstimationResult.create(issue=issue, round_number=1, deck_at_vote='FIBONACCI')
        with self.assertRaises(IntegrityError):
            EstimationResult.create(issue=issue, round_number=1, deck_at_vote='FIBONACCI')

    def test_create_tables_is_idempotent_and_preserves_data(self):
        game = self._game()
        Issue.create(game=game, jira_key='OPS-1', summary='x', order_index=0)
        create_tables()  # re-run on an existing DB must not error or wipe rows
        self.assertEqual(StoredGame.select().count(), 1)
        self.assertEqual(Issue.select().count(), 1)

    def test_existing_storedgame_only_db_upgrades_cleanly(self):
        # The migration path: a DB that predates this feature has only StoredGame.
        legacy = SqliteDatabase(':memory:')
        database_proxy.initialize(legacy)
        legacy.connect()
        StoredGame.create_table()  # old schema, tables-wise
        g = StoredGame.create(uuid=str(uuid.uuid4()), name='Legacy', deck='POWERS')
        create_tables()  # boot with the new code: additive migration
        self.assertEqual(StoredGame.get(StoredGame.uuid == g.uuid).name, 'Legacy')
        self.assertIn('issue', legacy.get_tables())
        Issue.create(game=g, jira_key='OPS-9', summary='new', order_index=0)
        self.assertEqual(g.issues.count(), 1)
        legacy.close()

    def test_storedgame_has_created_at_after_create_tables(self):
        # The B2 additive column is present and queryable on a fresh DB, and a new
        # row gets a real timestamp from the field default.
        cols = {col.name for col in self.db.get_columns('storedgame')}
        self.assertIn('created_at', cols)
        game = self._game()
        self.assertIsNotNone(StoredGame.get(StoredGame.uuid == game.uuid).created_at)

    def test_legacy_storedgame_without_created_at_migrates_and_rows_survive(self):
        # A DB whose `storedgame` table predates `created_at` (B2). We simulate the
        # old schema by creating the table from a column-less model definition, then
        # boot with the real code: the guarded ALTER must add the column, existing
        # rows must survive (with NULL created_at — SQLite can't backfill now()), and
        # the column must be queryable afterwards.
        from peewee import Model, UUIDField, CharField

        class _LegacyStoredGame(Model):
            uuid = UUIDField(primary_key=True)
            name = CharField()
            deck = CharField()

            class Meta:
                database = database_proxy
                table_name = 'storedgame'

        legacy = SqliteDatabase(':memory:')
        database_proxy.initialize(legacy)
        legacy.connect()
        _LegacyStoredGame.create_table()  # old schema: no created_at column
        self.assertNotIn('created_at', {c.name for c in legacy.get_columns('storedgame')})
        old = _LegacyStoredGame.create(uuid=str(uuid.uuid4()), name='Legacy', deck='POWERS')

        create_tables()  # boot with the new code: additive migration runs the ALTER

        self.assertIn('created_at', {c.name for c in legacy.get_columns('storedgame')})
        survivor = StoredGame.get(StoredGame.uuid == old.uuid)
        self.assertEqual(survivor.name, 'Legacy')
        self.assertIsNone(survivor.created_at)   # legacy rows sort last
        # A row created after the migration still gets a timestamp.
        fresh = StoredGame.create(uuid=str(uuid.uuid4()), name='Fresh', deck='FIBONACCI')
        self.assertIsNotNone(StoredGame.get(StoredGame.uuid == fresh.uuid).created_at)
        create_tables()  # idempotent: re-running must not error or re-add the column
        self.assertEqual(StoredGame.select().count(), 2)
        legacy.close()


if __name__ == '__main__':
    unittest.main()
