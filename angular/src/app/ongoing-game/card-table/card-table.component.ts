import { Component, OnDestroy } from '@angular/core';
import { GameState } from '../../model/events';
import { Subscription } from 'rxjs';
import { Deck } from '../../model/deck';
import { CurrentGameService } from '../current-game.service';
import { PlayerHandComponent } from './player-hand/player-hand.component';
import { KeyValuePipe, NgFor, NgIf } from '@angular/common';
import { TranslocoDirective } from '@ngneat/transloco';

@Component({
    selector: 'shpp-card-table',
    templateUrl: './card-table.component.html',
    styleUrls: ['./card-table.component.scss'],
    standalone: true,
    imports: [TranslocoDirective, NgFor, NgIf, PlayerHandComponent, KeyValuePipe]
})
export class CardTableComponent implements OnDestroy {
  state: GameState = {}
  canReveal = true;
  deck?: Deck;
  // In a backlog game, advancing happens via accept / re-vote in the results panel,
  // so the classic "New turn" button is hidden (S5).
  isBacklogGame = false;

  private stateSubscription: Subscription;
  private revealedSubscription: Subscription;
  private deckSubscription: Subscription;
  private backlogSubscription: Subscription;

  constructor(private currentGameService: CurrentGameService) {
    this.stateSubscription = this.currentGameService.state$
    .subscribe((state: GameState) => {
      this.state = state;
    });

    this.deckSubscription = currentGameService.deck$
    .subscribe((deck: Deck) => this.deck = deck);

    this.revealedSubscription = currentGameService.revealed$
    .subscribe((revealed: boolean) => this.canReveal = !revealed)

    this.backlogSubscription = currentGameService.hasBacklog$
    .subscribe((hasBacklog: boolean) => this.isBacklogGame = hasBacklog);
  }

  revealCards(): void {
    this.currentGameService.revealCards();
  }

  endTurn(): void {
    this.currentGameService.endTurn();
  }

  ngOnDestroy(): void {
    this.stateSubscription.unsubscribe();
    this.revealedSubscription.unsubscribe();
    this.deckSubscription.unsubscribe();
    this.backlogSubscription.unsubscribe();
  }

  getId(item: any): string {
    return item.key;
  }
}
