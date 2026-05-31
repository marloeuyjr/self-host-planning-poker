import { Component, inject } from '@angular/core';
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';
import { TranslocoDirective } from '@ngneat/transloco';

/**
 * The keyboard cheat-sheet (`?`), opened as an NgbModal. Lists the in-game
 * shortcuts with <kbd> keys. Dense, operational, slate + emerald — no decoration.
 */
@Component({
  selector: 'shpp-keyboard-help-modal',
  standalone: true,
  templateUrl: './keyboard-help-modal.component.html',
  styleUrls: ['./keyboard-help-modal.component.scss'],
  imports: [TranslocoDirective]
})
export class KeyboardHelpModalComponent {
  activeModal = inject(NgbActiveModal);
}
