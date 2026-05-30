import { Component } from '@angular/core';
import { AsyncPipe, NgIf } from '@angular/common';
import { Observable } from 'rxjs';
import { CurrentGameService } from '../current-game.service';
import { Issue } from '../../model/events';
import { TranslocoDirective } from '@ngneat/transloco';

/**
 * The current-issue header band shown above the card table (S4): mono emerald key,
 * summary, and a collapsible description so nobody has to alt-tab to Jira (EC6).
 * Renders nothing for a classic contextless game (no backlog), so that mode is
 * untouched.
 */
@Component({
  selector: 'shpp-current-issue',
  standalone: true,
  templateUrl: './current-issue.component.html',
  styleUrls: ['./current-issue.component.scss'],
  imports: [NgIf, AsyncPipe, TranslocoDirective]
})
export class CurrentIssueComponent {
  currentIssue$: Observable<Issue | null>;
  hasBacklog$: Observable<boolean>;
  descriptionExpanded = false;

  constructor(private currentGame: CurrentGameService) {
    this.currentIssue$ = this.currentGame.currentIssue$;
    this.hasBacklog$ = this.currentGame.hasBacklog$;
  }

  toggleDescription(): void {
    this.descriptionExpanded = !this.descriptionExpanded;
  }
}
