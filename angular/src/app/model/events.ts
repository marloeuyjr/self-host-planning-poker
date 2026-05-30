export interface GameInfo {
  name: string;
  deck: string;
  revealed: boolean;
  playerId?: string;
}

export interface Player {
  name: string;
  spectator: boolean;
}

export interface PlayerState extends Player {
  hasPicked?: boolean;
  hand?: number;
}

export type GameState = Record<string, PlayerState>;

export interface ErrorMessage {
  error: true;
  message: string;
  code: number;
}

export type IssueStatus = 'pending' | 'estimating' | 'estimated' | 'refinement' | 'skipped';

export interface Issue {
  id: number;
  key: string;
  summary: string;
  description: string | null;
  url: string | null;
  status: IssueStatus;
  orderIndex: number;
}

export interface EstimationResultView {
  round: number;
  finalValue: number | null;
  average: number | null;
  median: number | null;
  agreement: number | null;
  deck: string;
  voterCount: number;
}

export interface BacklogState {
  issues: Issue[];
  currentIndex: number | null;
  results: Record<number, EstimationResultView[]>;
}
