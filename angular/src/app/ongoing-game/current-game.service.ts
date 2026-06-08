import { Injectable } from '@angular/core';
import { Manager, Socket } from 'socket.io-client';
import { environment } from '../../environments/environment';
import { BehaviorSubject, combineLatest, filter, map, Observable, Subject, take } from 'rxjs';
import { BacklogState, ErrorMessage, GameInfo, GameState, Issue, RoundResults } from '../model/events';
import { Deck, decksDict } from '../model/deck';
import { ActivatedRouteSnapshot, Router, UrlTree } from '@angular/router';
import { HashMap, TranslocoService } from '@ngneat/transloco';
import { UserInformationService } from '../shared/user-info/user-information.service';
import { ToastService } from '../shared/toast/toast.service';
import { PathLocationStrategy } from '@angular/common';

@Injectable({
  providedIn: 'root'
})
export class CurrentGameService {
  private readonly totalAttempts = 10;
  private readonly reconnectDelaySeconds = 5;
  private readonly retries = 5;
  private readonly ackTimeoutMs = 10000;

  private manager: Manager;
  private socket: Socket;

  private stateSubject = new BehaviorSubject<GameState>({});
  private infoSubject = new BehaviorSubject<GameInfo | null>(null);
  private newGameSubject = new Subject<void>();
  private backlogSubject = new BehaviorSubject<BacklogState | null>(null);
  private resultsSubject = new BehaviorSubject<RoundResults | null>(null);
  // Live socket connectivity, surfaced so the page can show a persistent offline
  // banner while reconnection runs (the disconnect toast alone auto-hides in 5s but
  // reconnection takes up to ~50s). Seeded true: the route guard only loads the page
  // after a successful join, so the socket is already connected by first render.
  private connectedSubject = new BehaviorSubject<boolean>(true);
  private currentGameId: string | null = null;

  constructor(private router: Router,
              private userInformation: UserInformationService,
              private transloco: TranslocoService,
              private toastService: ToastService,
              private pls: PathLocationStrategy) {
    this.manager = new Manager(environment.backendRootOverride ?? window.location.origin,
      {
        path: `${this.pls.getBaseHref()}socket.io/`,
        autoConnect: false,
        reconnection: true,
        reconnectionDelay: this.reconnectDelaySeconds * 1000,
        reconnectionAttempts: this.totalAttempts
      });
    this.socket = this.manager.socket('/', {
      retries: this.retries,
      ackTimeout: this.ackTimeoutMs
    });

    this.socket.on('state', (state: GameState) => this.stateSubject.next(state));
    this.socket.on('info', (info: GameInfo) => this.infoSubject.next(info));
    this.socket.on('new_game', () => {
      this.newGameSubject.next();
      this.resultsSubject.next(null);   // a new round starts — drop the stale summary
    });
    this.socket.on('backlog', (backlog: BacklogState) => this.backlogSubject.next(backlog));
    this.socket.on('results', (results: RoundResults) => this.resultsSubject.next(results));

    this.socket.on('connect', () => this.connectedSubject.next(true));
    this.socket.on('disconnect', (reason) => {
      // The persistent offline banner (connected$ === false) is the calm, operational
      // signal while reconnection runs — don't also stack a toast, and never surface
      // the raw socket.io reason code to users. The reason stays in the console.
      if (reason !== 'io client disconnect') {
        this.connectedSubject.next(false);
      }
      console.info(`Socket disconnected. Reason is "${reason}"`);
    });
    // Per-attempt reconnect chatter (up to ~10 events) belongs in the console — the
    // offline banner already narrates "reconnecting…". Only the terminal outcomes
    // (reconnected, or gave up) are worth a one-shot toast.
    this.manager.on('reconnect_attempt', (attempt: number) => {
      console.info(`Reconnection attempt ${attempt}/${this.totalAttempts}`);
    });
    this.manager.on('reconnect_error', (err: Error) => {
      console.warn(`Reconnection error: ${err.message}`);
    });
    this.manager.on('reconnect_failed', () => {
      this.error('reconnect.failed', { attempts: this.totalAttempts });
    });
    this.manager.on('reconnect', (attempt: number) => {
      this.connectedSubject.next(true);
      this.success('reconnect.success', { attempts: attempt });
    });

    this.userInformation.nameObservable().subscribe((name: string) => {
      if (this.socket.connected) {
        this.socket.emit('set_player_name', {name: name});
      }
    });
    this.userInformation.spectatorObservable().subscribe((spectator: boolean) => {
      if (this.socket.connected) {
        this.socket.emit('set_spectator', {spectator: spectator})
      }
    });
  }

  public get state$(): Observable<GameState> {
    return this.stateSubject.asObservable();
  }

  public get gameInfo$(): Observable<GameInfo | null> {
    return this.infoSubject.asObservable();
  }

  /** Live socket connectivity — false while a reconnection is in progress. */
  public get connected$(): Observable<boolean> {
    return this.connectedSubject.asObservable();
  }

  /** The current session driver's id (the soft host), or null. */
  public get driverId$(): Observable<string | null> {
    return this.infoSubject.asObservable().pipe(map((info) => info?.driverId ?? null));
  }

  /** The uuid of the game currently joined, or null when not in a game. Captured on
   *  join so the nav can build the session-export download URLs (the route param is
   *  the authoritative id; GameInfo deliberately doesn't carry it). */
  public get gameId(): string | null {
    return this.currentGameId;
  }

  public get newGame$(): Observable<void>{
    return this.newGameSubject.asObservable();
  }

  public get backlog$(): Observable<BacklogState | null> {
    return this.backlogSubject.asObservable();
  }

  /** The issue currently under the pointer, or null when there is no backlog. */
  public get currentIssue$(): Observable<Issue | null> {
    return this.backlogSubject.asObservable().pipe(
      map((backlog: BacklogState | null) =>
        backlog && backlog.currentIndex !== null ? backlog.issues[backlog.currentIndex] ?? null : null)
    );
  }

  public get hasBacklog$(): Observable<boolean> {
    return this.backlogSubject.asObservable().pipe(
      map((backlog: BacklogState | null) => !!backlog && backlog.issues.length > 0)
    );
  }

  public get results$(): Observable<RoundResults | null> {
    return this.resultsSubject.asObservable();
  }

  /** Whether the local player holds the soft driver role (S8). */
  public get isDriver$(): Observable<boolean> {
    return combineLatest([this.infoSubject.asObservable(), this.userInformation.playerIdObservable()]).pipe(
      map(([info, playerId]) => !!info && !!info.driverId && info.driverId === playerId)
    );
  }

  public get revealed$(): Observable<boolean> {
    return this.gameInfo$.pipe(
      map((info: GameInfo | null) => info !== null ? info.revealed : false)
    );
  }

  public get deck$(): Observable<Deck> {
    return this.infoSubject.asObservable()
    .pipe(
      filter((gameInfo: GameInfo | null): gameInfo is GameInfo => gameInfo !== null),
      map((gameInfo: GameInfo) => decksDict[gameInfo?.deck])
    );
  }

  canActivate(route: ActivatedRouteSnapshot): Promise<boolean | UrlTree> {
    const gameId = route.params['gameId'];
    this.currentGameId = gameId;
    return this.socket.connect()
    .emitWithAck('join', {
      game: gameId,
      name: this.userInformation.getName(),
      spectator: this.userInformation.isSpectator(),
      token: this.getOrCreateRejoinToken(gameId)
    })
    .then((response: GameInfo | ErrorMessage) => {
        if ('error' in response) {
          this.socket.disconnect();
          this.handleError(response);
          return this.router.parseUrl('/');
        } else {
          this.infoSubject.next(response);
          this.userInformation.setPlayerIdSubject(response.playerId);
          if (response.resumed) {
            this.info('resume.notice');   // "session resumed — re-vote the current issue"
          }
          return true;
        }
      },
      (reason: any) => {
        this.handleError(reason);
        return this.router.parseUrl('/');
      });
  }

  public leave(): void {
    this.socket.disconnect();
    this.stateSubject.next({});
    this.infoSubject.next(null);
    this.backlogSubject.next(null);
    this.resultsSubject.next(null);
    this.currentGameId = null;
  }

  public selectIssue(index: number): void {
    this.socket.emit('select_issue', { index: index }, (response?: ErrorMessage) => this.handleError(response));
  }

  public acceptEstimate(value: number | null): void {
    this.socket.emit('accept_estimate', { value: value }, (response?: ErrorMessage) => this.handleError(response));
  }

  public revote(): void {
    this.socket.emit('revote', (response?: ErrorMessage) => this.handleError(response));
  }

  /** Host re-opens an already-resolved or parked issue for a fresh round (S4). */
  public reopenIssue(): void {
    this.socket.emit('reopen_issue', (response?: ErrorMessage) => this.handleError(response));
  }

  public parkIssue(status: 'refinement' | 'skipped', reason: string | null): void {
    this.socket.emit('park_issue', { status: status, reason: reason }, (response?: ErrorMessage) => this.handleError(response));
  }

  /** Append parsed issues to the live session's queue mid-session (B1). The driver
   *  pastes / imports more rows; the server appends them without disturbing the
   *  pointer or the in-flight round. */
  public addIssues(text: string, fmt: string): void {
    this.socket.emit('add_issues', { backlog: text, backlogFormat: fmt }, (response?: ErrorMessage) => this.handleError(response));
  }

  public claimDriver(): void {
    this.socket.emit('claim_driver', (response?: ErrorMessage) => this.handleError(response));
  }

  public renameGame(newName: string): void {
    this.socket.emit('rename_game', { name: newName }, (response?: ErrorMessage) => this.handleError(response));
  }

  public setDeck(deck: Deck): void {
    this.socket.emit('set_deck', { deck: deck.name }, (response?: ErrorMessage) => this.handleError(response));
  }

  public pickCard(cardValue: number | string | null): void {
    this.socket.emit('pick_card', { card: cardValue }, (response?: ErrorMessage) => this.handleError(response));
  }

  public revealCards(): void {
    this.socket.emit('reveal_cards', (response?: ErrorMessage) => this.handleError(response));
  }

  public endTurn(): void {
    this.socket.emit('end_turn', (response?: ErrorMessage) => this.handleError(response));
  }

  /**
   * A stable per-session rejoin token kept in localStorage (S7, EC3). Sent on join
   * so a reconnect / reload reattaches to the same player identity instead of
   * minting a fresh one. This is continuity, NOT authentication.
   */
  private getOrCreateRejoinToken(gameId: string): string {
    const key = `shpp-rejoin-${gameId}`;
    try {
      let token = localStorage.getItem(key);
      if (!token) {
        token = (typeof crypto !== 'undefined' && crypto.randomUUID)
          ? crypto.randomUUID()
          : `${gameId}-${Date.now()}`;
        localStorage.setItem(key, token);
      }
      return token;
    } catch {
      // localStorage unavailable (private mode / blocked) — fall back to a volatile id.
      return `${gameId}-${Date.now()}`;
    }
  }

  private handleError(error?: ErrorMessage | any): void {
    if (!!error) {
      if ('error' in error) {
        this.error(`errors.${error.code}`, { message: error.message });
      } else {
        // An unstructured, unexpected failure: the raw payload is for the console,
        // never the toast (it would render "[object Object]"). Show the actionable
        // fallback instead.
        console.error('Unexpected socket error', error);
        this.error('errors.0');
      }
    }
  }

  // selectTranslate re-emits on every language change; these are fire-and-forget
  // toasts, so take(1) completes the subscription instead of leaking one per toast.
  private info(key: string, translateParams?: HashMap): void {
    this.transloco.selectTranslate(key, translateParams).pipe(take(1)).subscribe((text) => {
      console.info(text);
      this.toastService.show(text, { className: 'bg-info' });
    })
  }

  private success(key: string, translateParams?: HashMap): void {
    this.transloco.selectTranslate(key, translateParams).pipe(take(1)).subscribe((text) => {
      console.info(text);
      this.toastService.show(text, { className: 'bg-success text-light' });
    });
  }

  private error(key: string, translateParams?: HashMap): void {
    this.transloco.selectTranslate(key, translateParams).pipe(take(1)).subscribe((text) => {
      console.error(text);
      this.toastService.show(text, { className: 'bg-danger text-light' });
    })
  }

}
