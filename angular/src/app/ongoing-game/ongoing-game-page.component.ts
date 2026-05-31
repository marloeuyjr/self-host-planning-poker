import { Component, OnDestroy } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { TranslocoService } from '@ngneat/transloco';
import { Subscription, switchMap } from 'rxjs';
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

  constructor(private currentGameService: CurrentGameService,
              private titleService: Title,
              private transloco: TranslocoService) {
    this.subscriptions.push(this.currentGameService.gameInfo$
      .pipe(
        switchMap((gameInfo) => this.transloco.selectTranslate('ongoingGame.page-title', { gameName: gameInfo?.name })))
      .subscribe((translatedPageTitle) => this.titleService.setTitle(translatedPageTitle)));
    this.subscriptions.push(this.currentGameService.revealed$.subscribe((revealed) => this.showSummary = revealed));
    this.subscriptions.push(this.currentGameService.hasBacklog$.subscribe((has) => this.isBacklogGame = has));
    this.subscriptions.push(this.currentGameService.currentIssue$
      .subscribe((issue) => this.currentStatus = issue ? issue.status : null));
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
    this.currentGameService.leave();
  }

}
