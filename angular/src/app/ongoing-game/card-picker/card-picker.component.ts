import { Component, OnDestroy } from '@angular/core';
import { CardValue, Deck } from '../../model/deck';
import { Subscription } from 'rxjs';
import { CurrentGameService } from '../current-game.service';
import { UserInformationService } from '../../shared/user-info/user-information.service';
import { PickableCardComponent } from './card/pickable-card.component';
import { NgIf, NgFor } from '@angular/common';
import { TranslocoDirective } from '@ngneat/transloco';

@Component({
    selector: 'shpp-card-picker',
    templateUrl: './card-picker.component.html',
    standalone: true,
    imports: [NgIf, NgFor, PickableCardComponent, TranslocoDirective]
})
export class CardPickerComponent implements OnDestroy {
  deck?: Deck
  selectedCard?: CardValue;
  isSpectator = false;
  isGameRevealed = false;

  private deckSubscription: Subscription;
  private newGameSubscription: Subscription;
  private spectatorSubscription: Subscription;
  private gameRevealedSubscription: Subscription;

  constructor(private currentGame: CurrentGameService,
              private userInfoService: UserInformationService) {
    this.deckSubscription = currentGame.deck$
    .subscribe((deck) => {
      this.deck = deck;
      this.selectedCard = undefined;
    });

    this.newGameSubscription = this.currentGame.newGame$
    .subscribe(() => this.selectedCard = undefined);

    this.spectatorSubscription = this.userInfoService.spectatorObservable()
    .subscribe((spectator: boolean) => {
      this.isSpectator = spectator;
      if (spectator) {
        this.selectedCard = undefined;
      }
    });

    this.gameRevealedSubscription = this.currentGame.revealed$
    .subscribe((revealed: boolean) => this.isGameRevealed = revealed);
  }

  selectCard(card: CardValue): void {
    if (this.isSpectator || this.isGameRevealed) {
      return;
    }
    if (this.selectedCard !== card) {
      this.selectedCard = card;
      this.currentGame.pickCard(card.value);
    } else {
      this.selectedCard = undefined;
      this.currentGame.pickCard(null);
    }
  }

  /** Pick the card at a positional index (keyboard digits). Reuses selectCard,
   *  so toggle-to-unpick and the spectator/revealed guards apply. */
  pickByIndex(index: number): void {
    if (!this.deck) {
      return;
    }
    const card = this.deck.values[index];
    if (!card) {
      return;
    }
    this.selectCard(card);
  }

  /** Digit hint for the i-th card: 1..9 for the first nine, 0 for the tenth,
   *  none beyond (the 11th card on the Fibonacci decks is Tab-reachable). */
  keyHintFor(i: number): string | undefined {
    if (i < 9) {
      return String(i + 1);
    }
    if (i === 9) {
      return '0';
    }
    return undefined;
  }

  ngOnDestroy(): void {
    this.deckSubscription.unsubscribe();
    this.newGameSubscription.unsubscribe();
    this.spectatorSubscription.unsubscribe();
    this.gameRevealedSubscription.unsubscribe();
  }

}
