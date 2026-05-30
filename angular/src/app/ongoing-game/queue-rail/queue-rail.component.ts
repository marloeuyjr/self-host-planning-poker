import { Component, OnDestroy } from '@angular/core';
import { AsyncPipe, NgClass, NgFor, NgIf } from '@angular/common';
import { Observable, Subscription } from 'rxjs';
import { CurrentGameService } from '../current-game.service';
import { BacklogState, Issue } from '../../model/events';
import { TranslocoDirective } from '@ngneat/transloco';

/**
 * The left queue rail (S4): every issue with a status chip, an X-of-N progress
 * count + bar, and click-to-jump. Collapsible to protect the dense ops-room
 * layout. Renders nothing without a backlog.
 */
@Component({
  selector: 'shpp-queue-rail',
  standalone: true,
  templateUrl: './queue-rail.component.html',
  styleUrls: ['./queue-rail.component.scss'],
  imports: [NgIf, NgFor, NgClass, AsyncPipe, TranslocoDirective]
})
export class QueueRailComponent implements OnDestroy {
  backlog$: Observable<BacklogState | null>;
  collapsed = false;
  isDriver = true;   // only the driver may jump the queue (S8)

  private driverSubscription: Subscription;

  constructor(private currentGame: CurrentGameService) {
    this.backlog$ = this.currentGame.backlog$;
    this.driverSubscription = this.currentGame.isDriver$.subscribe((d) => this.isDriver = d);
  }

  ngOnDestroy(): void {
    this.driverSubscription.unsubscribe();
  }

  estimatedCount(backlog: BacklogState): number {
    return backlog.issues.filter((i) => i.status === 'estimated').length;
  }

  progressPercent(backlog: BacklogState): number {
    return backlog.issues.length ? this.estimatedCount(backlog) / backlog.issues.length * 100 : 0;
  }

  select(index: number): void {
    if (this.isDriver) {
      this.currentGame.selectIssue(index);
    }
  }

  toggle(): void {
    this.collapsed = !this.collapsed;
  }

  trackById(_: number, issue: Issue): number {
    return issue.id;
  }
}
