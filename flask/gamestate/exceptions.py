class PlanningPokerException(Exception):
    code = 0


class DeckDoesNotExistError(PlanningPokerException):
    code = 4001


class GameNotOngoingError(PlanningPokerException):
    code = 4002


class PlayerNotInGameError(PlanningPokerException):
    code = 4003


class GameDoesNotExistError(PlanningPokerException):
    code = 4004


class InvalidCardValueError(PlanningPokerException):
    code = 4005


class SpectatorCannotPlayError(PlanningPokerException):
    code = 4006


class InvalidBacklogError(PlanningPokerException):
    code = 4007


class NotDriverError(PlanningPokerException):
    code = 4008


class IssueNotInBacklogError(PlanningPokerException):
    code = 4009


class NoCurrentIssueError(PlanningPokerException):
    code = 4010
