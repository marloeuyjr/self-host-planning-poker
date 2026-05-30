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
    order_index = IntegerField()
    status = CharField(default='pending')  # pending | estimating | estimated | refinement | skipped
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


def create_tables():
    """Create all tables if missing.

    Forward-only, additive migration (S1): existing `StoredGame` rows are untouched;
    the new `Issue` / `EstimationResult` tables are added on boot. Replaces the old
    single `StoredGame.create_table()` startup call.
    """
    database_proxy.create_tables([StoredGame, Issue, EstimationResult])
