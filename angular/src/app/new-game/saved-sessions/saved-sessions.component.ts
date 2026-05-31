import { Component, OnInit } from '@angular/core';
import { DatePipe, NgFor, NgIf, PathLocationStrategy } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { TranslocoDirective } from '@ngneat/transloco';
import { environment } from '../../../environments/environment';
import { SavedSession } from '../../model/events';

/**
 * Home-page recall list (B2): the most-recent saved sessions, newest-first, each a
 * dense two-line row (name + deck/created, then a mono estimated-progress line) that
 * navigates back into the game. Mirrors the queue-rail's flat slate+emerald styling —
 * no nested cards. Quiet empty + error states; this is an internal ops tool, so a
 * failed fetch logs and shows nothing rather than shouting.
 */
@Component({
  standalone: true,
  selector: 'shpp-saved-sessions',
  templateUrl: './saved-sessions.component.html',
  styleUrls: ['./saved-sessions.component.scss'],
  imports: [NgIf, NgFor, DatePipe, TranslocoDirective]
})
export class SavedSessionsComponent implements OnInit {
  sessions: SavedSession[] = [];
  loaded = false;

  constructor(private http: HttpClient,
              private pls: PathLocationStrategy,
              private router: Router) { }

  ngOnInit(): void {
    const url = `${ environment.backendRootOverride ?? this.pls.getBaseHref() }sessions`;
    this.http.get<SavedSession[]>(url).subscribe({
      next: (sessions) => {
        this.sessions = sessions;
        this.loaded = true;
      },
      error: (err) => {
        console.error('Could not load saved sessions.', err);
        this.sessions = [];
        this.loaded = true;
      }
    });
  }

  open(session: SavedSession): void {
    this.router.navigate(['game', session.uuid]);
  }
}
