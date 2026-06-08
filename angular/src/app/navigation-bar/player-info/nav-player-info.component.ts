import { Component } from '@angular/core';
import { NgbOffcanvas, NgbTooltip } from '@ng-bootstrap/ng-bootstrap';
import { UserInformationService } from '../../shared/user-info/user-information.service';
import { PlayerNameFormComponent } from '../../shared/player-name-form/player-name-form.component';
import { CurrentGameService } from '../../ongoing-game/current-game.service';
import { TranslocoDirective } from '@ngneat/transloco';
import { AsyncPipe, NgIf } from '@angular/common';

@Component({
    selector: 'shpp-nav-player-info',
    templateUrl: './nav-player-info.component.html',
    styleUrls: ['./nav-player-info.component.scss'],
    standalone: true,
    imports: [TranslocoDirective, PlayerNameFormComponent, NgbTooltip, AsyncPipe, NgIf]
})
export class NavPlayerInfoComponent {
  constructor(public userInformation: UserInformationService,
              public currentGame: CurrentGameService,
              private offcanvaseService: NgbOffcanvas) {
  }

  toggleSpectator(): void {
    this.userInformation.setSpectator(!this.userInformation.isSpectator());
  }

  openEdit(content: any): void {
    this.offcanvaseService.open(content, { ariaLabelledBy: 'offcanvas-basic-title', position: 'end' });
  }

}
