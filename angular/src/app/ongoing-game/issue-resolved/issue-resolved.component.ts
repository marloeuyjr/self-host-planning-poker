import { Component, OnDestroy } from '@angular/core';
import { NgIf } from '@angular/common';
import { Subscription } from 'rxjs';
import { CurrentGameService } from '../current-game.service';
import { BacklogState, Issue } from '../../model/events';
import { decksDict, displayCardValue } from '../../model/deck';
import { TranslocoDirective } from '@ngneat/transloco';

/**
 * Bottom-strip panel shown when the selected issue is already resolved — Done
 * (estimated) or parked (refinement / skipped). It replaces the voting deck so a
 * resolved issue can't be voted on, surfaces the recorded estimate / park reason,
 * and offers the driver a one-tap re-open that starts a fresh round (append-only;
 * prior rounds are kept). Renders nothing for an active (votable) issue.
 */
@Component({
  selector: 'shpp-issue-resolved',
  standalone: true,
  templateUrl: './issue-resolved.component.html',
  styleUrls: ['./issue-resolved.component.scss'],
  imports: [NgIf, TranslocoDirective]
})
export class IssueResolvedComponent implements OnDestroy {
  issue: Issue | null = null;
  private backlog: BacklogState | null = null;
  isDriver = true;
  private subs: Subscription[] = [];

  constructor(private currentGame: CurrentGameService) {
    this.subs.push(this.currentGame.currentIssue$.subscribe((i) => this.issue = i));
    this.subs.push(this.currentGame.backlog$.subscribe((b) => this.backlog = b));
    this.subs.push(this.currentGame.isDriver$.subscribe((d) => this.isDriver = d));
  }

  get isEstimated(): boolean {
    return this.issue?.status === 'estimated';
  }

  get isParked(): boolean {
    return this.issue?.status === 'refinement' || this.issue?.status === 'skipped';
  }

  get isSkipped(): boolean {
    return this.issue?.status === 'skipped';
  }

  /** The accepted estimate, mapped to the deck it was voted on. Null if none was
   *  recorded (accepted with no agreed value). Coerced to a string so a 0 shows. */
  get acceptedValue(): string | null {
    if (!this.issue || !this.backlog) {
      return null;
    }
    const rounds = this.backlog.results[this.issue.id] ?? [];
    for (let i = rounds.length - 1; i >= 0; i--) {
      if (rounds[i].finalValue !== null) {
        const deck = decksDict[rounds[i].deck] ?? decksDict['FIBONACCI'];
        const display = displayCardValue(deck, rounds[i].finalValue as number);
        return display === undefined || display === null ? null : String(display);
      }
    }
    return null;
  }

  reopen(): void {
    this.currentGame.reopenIssue();
  }

  // The card table (which normally hosts "Take control") is hidden for a resolved
  // issue, so keep the claim affordance reachable for a non-driver here.
  claimDriver(): void {
    this.currentGame.claimDriver();
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }
}
