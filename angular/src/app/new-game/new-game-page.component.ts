import { Component } from '@angular/core';
import { Deck } from '../model/deck';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { environment } from '../../environments/environment';
import { Router } from '@angular/router';
import { GameFormComponent } from '../shared/game-form/game-form.component';
import { ContainerComponent } from '../shared/container/container.component';
import { NavAppTitleComponent } from '../navigation-bar/app-title/nav-app-title.component';
import { FooterComponent } from '../shared/footer/footer.component';
import { PathLocationStrategy } from '@angular/common';
import { ToastService } from '../shared/toast/toast.service';

@Component({
  standalone: true,
  selector: 'shpp-new-game-page',
  templateUrl: './new-game-page.component.html',
  styleUrls: [ './new-game-page.component.scss' ],
  imports: [
    GameFormComponent,
    ContainerComponent,
    NavAppTitleComponent,
    FooterComponent
  ]
})
export default class NewGamePageComponent {

  constructor(private http: HttpClient,
              private router: Router,
              private pls: PathLocationStrategy,
              private toastService: ToastService) { }

  onNewGame(newGame: {name: string, deck: Deck, backlog?: string, backlogFormat?: string}): void {
    const body: { name: string, deck: string, backlog?: string, backlogFormat?: string } = {
      name: newGame.name,
      deck: newGame.deck.name
    }
    if (newGame.backlog && newGame.backlog.trim()) {
      body.backlog = newGame.backlog;
      body.backlogFormat = newGame.backlogFormat ?? 'paste';
    }
    this.http.post(`${ environment.backendRootOverride ?? this.pls.getBaseHref() }create`, body, { responseType: 'text' })
      .subscribe({
        next: (gameId) => this.router.navigate(['game', gameId]),
        error: (err: HttpErrorResponse) =>
          this.toastService.show(err.error || 'Could not create the game.', { className: 'bg-danger text-light' })
      });
  }

}
