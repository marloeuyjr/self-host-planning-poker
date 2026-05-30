import datetime

from peewee import (Model, UUIDField, CharField, TextField, IntegerField,
                    FloatField, DateTimeField, ForeignKeyField, Proxy)

database_proxy = Proxy()


class StoredGame(Model):
    uuid = UUIDField(primary_key=True)
    name = CharField()
    deck = CharField()

    class Meta:
        database = database_proxy


class Issue(Model):
    """A backlog item to estimate, owned by a game/session and ordered in a queue."""
    game = ForeignKeyField(StoredGame, backref='issues', on_delete='CASCADE')
    jira_key = CharField()
    summary = CharField()
    description = TextField(null=True)
    url = CharField(null=True)             # optional Jira link (CSV import, S3)
    order_index = IntegerField()
    status = CharField(default='pending')  # pending | estimating | estimated | refinement | skipped
    park_reason = TextField(null=True)     # why an issue was parked / skipped (S6)
    source = CharField(null=True)          # provenance, e.g. 'paste' or 'csv'
    imported_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = database_proxy


class EstimationResult(Model):
    """An append-only record of one voting round on an issue (EC2).

    Several rows may exist per issue — one per re-vote round; `final_value` is set
    on the accepted round (E4). The numbers are computed server-side by
    `gamestate.stats.compute_stats` and frozen here before hands are cleared (E5).
    """
    issue = ForeignKeyField(Issue, backref='results', on_delete='CASCADE')
    round_number = IntegerField()
    final_value = FloatField(null=True)
    average = FloatField(null=True)
    median = FloatField(null=True)
    agreement = FloatField(null=True)
    deck_at_vote = CharField()
    voter_count = IntegerField(default=0)
    decided_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = database_proxy
        # Append-only integrity: exactly one row per (issue, round).
        indexes = ((('issue', 'round_number'), True),)


# Columns added to `Issue` after its table first shipped (S1). On a fresh DB peewee
# creates them from the model; on a DB that already has the S1 `issue` table they are
# added by a guarded `ALTER TABLE`. Both paths are idempotent and forward-only.
_ISSUE_ADDED_COLUMNS = {
    'url': 'VARCHAR',
    'park_reason': 'TEXT',
}


def create_tables():
    """Create all tables if missing, then add any columns introduced after S1.

    Forward-only, additive migration: existing `StoredGame` rows are untouched; the
    `Issue` / `EstimationResult` tables are created on boot if absent, and columns
    added to `Issue` in later slices (`url`, `park_reason`) are appended in place on
    an older DB. Idempotent — safe to run on every startup. Replaces the old single
    `StoredGame.create_table()` startup call.
    """
    database_proxy.create_tables([StoredGame, Issue, EstimationResult])
    _add_missing_issue_columns()


def _add_missing_issue_columns():
    existing = {col.name for col in database_proxy.get_columns('issue')}
    for name, sql_type in _ISSUE_ADDED_COLUMNS.items():
        if name not in existing:
            database_proxy.execute_sql(f'ALTER TABLE issue ADD COLUMN {name} {sql_type}')
