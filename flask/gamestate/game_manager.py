import uuid
from typing import Optional

from peewee import DoesNotExist

from gamestate.deck import Deck
from gamestate.exceptions import GameDoesNotExistError, DeckDoesNotExistError, GameNotOngoingError
from gamestate.game import Game
from gamestate.models import StoredGame, Issue, EstimationResult, database_proxy
from gamestate.player import Player


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

    def join_game(self, game_uuid: str, player_id: str, player_name: str, is_spectator: bool) -> tuple[dict, dict]:
        game = self.get(game_uuid)
        player = Player(player_name, is_spectator)
        game.player_joins(player_id, player)
        return game.info(), game.state()

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

    def reveal_cards(self, game_uuid: str) -> tuple[dict, dict]:
        game = self.__get_ongoing_game(game_uuid)
        game.reveal_hands()
        return game.state(), game.info()

    def end_turn(self, game_uuid: str) -> tuple[dict, dict]:
        game = self.__get_ongoing_game(game_uuid)
        game.end_turn()
        return game.state(), game.info()

    def backlog(self, game_uuid: str) -> dict:
        game = self.__get_ongoing_game(game_uuid)
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
    