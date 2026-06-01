import { Component, OnDestroy } from '@angular/core';
import { AsyncPipe, NgClass, NgFor, NgIf, NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Observable, Subscription } from 'rxjs';
import { CurrentGameService } from '../current-game.service';
import { BacklogState, Issue } from '../../model/events';
import { decksDict, displayCardValue } from '../../model/deck';
import { TranslocoDirective } from '@ngneat/transloco';

const PARKED_STATUSES = ['refinement', 'skipped'];

/**
 * The left queue rail (S4): every issue with a status chip, an X-of-N progress
 * count + bar, and click-to-jump. Collapsible to protect the dense ops-room
 * layout. Renders nothing without a backlog.
 *
 * Each item is two lines (key + chip, then the summary) so a real Jira key never
 * crushes the summary the way a single-line layout did. Estimated issues surface
 * their accepted value; parked issues drop into their own zone below the queue.
 */
@Component({
  selector: 'shpp-queue-rail',
  standalone: true,
  templateUrl: './queue-rail.component.html',
  styleUrls: ['./queue-rail.component.scss'],
  imports: [NgIf, NgFor, NgClass, NgTemplateOutlet, AsyncPipe, FormsModule, TranslocoDirective]
})
export class QueueRailComponent implements OnDestroy {
  backlog$: Observable<BacklogState | null>;
  collapsed = false;
  isDriver = true;   // only the driver may jump the queue (S8)

  // Collapsible "add issues" mini-form at the rail footer (B1) — driver-only,
  // mirrors the current-issue park form. Paste/CSV toggle reuses the create UX.
  addExpanded = false;
  addText = '';
  addFormat = 'paste';

  private driverSubscription: Subscription;

  constructor(private currentGame: CurrentGameService) {
    this.backlog$ = this.currentGame.backlog$;
    this.driverSubscription = this.currentGame.isDriver$.subscribe((d) => this.isDriver = d);
  }

  ngOnDestroy(): void {
    this.driverSubscription.unsubscribe();
  }

  /** Issues still in the estimation queue (parked ones live in their own zone). */
  queued(backlog: BacklogState): Issue[] {
    return backlog.issues.filter((i) => !PARKED_STATUSES.includes(i.status));
  }

  /** Parked issues (needs-refinement / skipped), surfaced separately (S6). */
  parked(backlog: BacklogState): Issue[] {
    return backlog.issues.filter((i) => PARKED_STATUSES.includes(i.status));
  }

  estimatedCount(backlog: BacklogState): number {
    return backlog.issues.filter((i) => i.status === 'estimated').length;
  }

  /** Denominator excludes parked issues — they will never be estimated, so the
   *  bar reflects progress through the issues we are actually voting on. */
  toEstimateCount(backlog: BacklogState): number {
    return backlog.issues.length - this.parked(backlog).length;
  }

  progressPercent(backlog: BacklogState): number {
    const total = this.toEstimateCount(backlog);
    return total ? this.estimatedCount(backlog) / total * 100 : 0;
  }

  /** The accepted estimate to show on a Done issue, mapped to the deck it was
   *  voted on (so a T-shirt size shows "M", not its ordinal). Null if none. */
  acceptedValue(backlog: BacklogState, issue: Issue): string | null {
    const rounds = backlog.results[issue.id] ?? [];
    for (let i = rounds.length - 1; i >= 0; i--) {
      if (rounds[i].finalValue !== null) {
        const deck = decksDict[rounds[i].deck] ?? decksDict['FIBONACCI'];
        const display = displayCardValue(deck, rounds[i].finalValue as number);
        // Coerce to string so a valid 0-point estimate isn't treated as falsy.
        return display === undefined || display === null ? null : String(display);
      }
    }
    return null;
  }

  /** Original-order index, so click-to-jump targets the right backlog position. */
  indexOf(backlog: BacklogState, issue: Issue): number {
    return backlog.issues.indexOf(issue);
  }

  select(index: number): void {
    if (this.isDriver) {
      this.currentGame.selectIssue(index);
    }
  }

  toggle(): void {
    this.collapsed = !this.collapsed;
  }

  toggleAdd(): void {
    this.addExpanded = !this.addExpanded;
  }

  submitAdd(): void {
    const text = this.addText.trim();
    if (!text) {
      return;
    }
    this.currentGame.addIssues(text, this.addFormat);
    this.addText = '';
    this.addExpanded = false;
  }

  cancelAdd(): void {
    this.addText = '';
    this.addExpanded = false;
  }

  trackById(_: number, issue: Issue): number {
    return issue.id;
  }
}
