import { Component, HostListener, OnDestroy, ViewChild } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { TranslocoService } from '@ngneat/transloco';
import { Subscription, switchMap } from 'rxjs';
import { NgbModal, NgbModalRef } from '@ng-bootstrap/ng-bootstrap';
import { CurrentGameService } from './current-game.service';
import { CardPickerComponent } from './card-picker/card-picker.component';
import { TurnSummaryComponent } from './turn-summary/turn-summary.component';
import { NgIf } from '@angular/common';
import { CardTableComponent } from './card-table/card-table.component';
import { NavPlayerInfoComponent } from '../navigation-bar/player-info/nav-player-info.component';
import { NavGameInfoComponent } from '../navigation-bar/game-info/nav-game-info.component';
import { NavGameNameComponent } from '../navigation-bar/game-name/nav-game-name.component';
import { ContainerComponent } from '../shared/container/container.component';
import { CurrentIssueComponent } from './current-issue/current-issue.component';
import { QueueRailComponent } from './queue-rail/queue-rail.component';
import { IssueResolvedComponent } from './issue-resolved/issue-resolved.component';
import { KeyboardHelpModalComponent } from './keyboard-help/keyboard-help-modal.component';

@Component({
    selector: 'shpp-ongoing-game-page',
    templateUrl: './ongoing-game-page.component.html',
    styleUrls: ['./ongoing-game-page.component.scss'],
    standalone: true,
    imports: [
      ContainerComponent,
      NavGameNameComponent,
      NavGameInfoComponent,
      NavPlayerInfoComponent,
      CardTableComponent,
      NgIf,
      TurnSummaryComponent,
      CardPickerComponent,
      CurrentIssueComponent,
      QueueRailComponent,
      IssueResolvedComponent
    ]
})
export default class OngoingGamePageComponent implements OnDestroy {
  private subscriptions: Subscription[] = [];

  showSummary = false;
  private isBacklogGame = false;
  private currentStatus: string | null = null;

  // Child components driven by the global keyboard handler. The picker and the
  // summary are each *ngIf'd in/out (only one is present at a time), so these
  // are optional — the handler null-checks before use.
  @ViewChild(CardPickerComponent) private cardPicker?: CardPickerComponent;
  @ViewChild(CardTableComponent) private cardTable?: CardTableComponent;
  @ViewChild(TurnSummaryComponent) private turnSummary?: TurnSummaryComponent;
  @ViewChild(CurrentIssueComponent) private currentIssue?: CurrentIssueComponent;

  // Backlog navigation state, tracked from the service for the n/p handlers.
  private currentIndex: number | null = null;
  private issuesLength = 0;
  private isDriver = false;

  private helpRef?: NgbModalRef;

  constructor(private currentGameService: CurrentGameService,
              private titleService: Title,
              private transloco: TranslocoService,
              private modalService: NgbModal) {
    this.subscriptions.push(this.currentGameService.gameInfo$
      .pipe(
        switchMap((gameInfo) => this.transloco.selectTranslate('ongoingGame.page-title', { gameName: gameInfo?.name })))
      .subscribe((translatedPageTitle) => this.titleService.setTitle(translatedPageTitle)));
    this.subscriptions.push(this.currentGameService.revealed$.subscribe((revealed) => this.showSummary = revealed));
    this.subscriptions.push(this.currentGameService.hasBacklog$.subscribe((has) => this.isBacklogGame = has));
    this.subscriptions.push(this.currentGameService.currentIssue$
      .subscribe((issue) => this.currentStatus = issue ? issue.status : null));
    this.subscriptions.push(this.currentGameService.backlog$.subscribe((backlog) => {
      this.currentIndex = backlog ? backlog.currentIndex : null;
      this.issuesLength = backlog ? backlog.issues.length : 0;
    }));
    this.subscriptions.push(this.currentGameService.isDriver$.subscribe((isDriver) => this.isDriver = isDriver));
  }

  @HostListener('document:keydown', ['$event'])
  onKeydown(event: KeyboardEvent): void {
    const key = event.key;
    // Ignore auto-repeat from a held key — avoids spamming pick_card and a held
    // Enter racing two accept_estimate before the round-trip clears the round.
    if (event.repeat) {
      return;
    }
    // Ignore keys typed into editable targets (rename, park reason, create form).
    const el = event.target as HTMLElement | null;
    const tag = el?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el?.isContentEditable) {
      return;
    }
    // A modal is open: only let `?` close our own help (ng-bootstrap handles Esc).
    if (document.body.classList.contains('modal-open')) {
      if (this.helpRef && key === '?') {
        this.helpRef.close();
      }
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey) {
      return;
    }
    // Let focused interactive elements handle Enter/Space themselves (avoids
    // double-firing with the Tab-focusable cards and the action buttons).
    if ((key === 'Enter' || key === ' ') && (tag === 'BUTTON' || tag === 'A' || el?.getAttribute('role') === 'button')) {
      return;
    }

    if (key === '?') {
      this.toggleHelp();
      event.preventDefault();
      return;
    }
    if (key === 'd') {
      this.currentIssue?.toggleDescription();
      event.preventDefault();
      return;
    }
    if (key === 'n') {
      this.navigateIssue(1);
      return;
    }
    if (key === 'p') {
      this.navigateIssue(-1);
      return;
    }
    if (key === 'Enter') {
      this.onEnter(event);
      return;
    }
    if (/^[0-9]$/.test(key)) {
      const idx = key === '0' ? 9 : Number(key) - 1;
      this.cardPicker?.pickByIndex(idx);
      event.preventDefault();
    }
  }

  /** Enter: driver-gated reveal → advance/accept, reusing the card-table's gating.
   *  CardTable exposes `canReveal` (= not yet revealed), so revealed === !canReveal. */
  private onEnter(event: KeyboardEvent): void {
    const ct = this.cardTable;
    if (!ct || !ct.isDriver) {
      return;
    }
    if (ct.canReveal) {
      ct.revealCards();
      event.preventDefault();
    } else if (!ct.isBacklogGame) {
      ct.endTurn();
      event.preventDefault();
    } else {
      this.turnSummary?.acceptDefault();
      event.preventDefault();
    }
  }

  private navigateIssue(delta: number): void {
    if (!this.isDriver || this.currentIndex === null) {
      return;
    }
    const next = this.currentIndex + delta;
    if (next >= 0 && next < this.issuesLength) {
      this.currentGameService.selectIssue(next);
    }
  }

  private toggleHelp(): void {
    if (this.helpRef) {
      this.helpRef.close();
      this.helpRef = undefined;
      return;
    }
    this.helpRef = this.modalService.open(KeyboardHelpModalComponent);
    this.helpRef.result.finally(() => this.helpRef = undefined);
  }

  /** Voting is available for a classic game, or a backlog issue still being
   *  estimated (pending or estimating). Resolved/parked issues replace the deck
   *  with the read-only panel below. */
  get votingActive(): boolean {
    return !this.isBacklogGame || this.currentStatus === 'pending' || this.currentStatus === 'estimating';
  }

  /** The selected backlog issue is Done or parked — show the resolved panel. */
  get isResolved(): boolean {
    return this.isBacklogGame &&
      (this.currentStatus === 'estimated' || this.currentStatus === 'refinement' || this.currentStatus === 'skipped');
  }

  ngOnDestroy(): void {
    this.subscriptions.forEach((s) => s.unsubscribe());
    this.helpRef?.close();
    this.currentGameService.leave();
  }

}
