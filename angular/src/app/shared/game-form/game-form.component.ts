import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { AbstractControl, FormBuilder, FormGroup, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { Deck, decks, decksDict, displayDeckValues } from '../../model/deck';
import { NgFor, NgIf } from '@angular/common';
import { TranslocoDirective } from '@ngneat/transloco';

@Component({
  standalone: true,
  selector: 'shpp-game-form',
  templateUrl: './game-form.component.html',
  imports: [TranslocoDirective, NgFor, NgIf, ReactiveFormsModule]
})
export class GameFormComponent implements OnInit{

  formGroup: FormGroup;
  decks = decks
  displayDeckValues = displayDeckValues

  @Input()
  name?: string;
  @Input()
  deck?: string;
  @Output() gameOutput = new EventEmitter<{name: string, deck: Deck, backlog?: string, backlogFormat?: string}>();

  constructor(private fb: FormBuilder) {
    this.formGroup = this.fb.group({
      name: [ '', [ Validators.required, GameFormComponent.nonBlank ]],
      deck: [ decksDict['FIBONACCI'], Validators.required ],
      // Optional starting backlog — only shown / sent when creating a game (S3).
      backlog: [ '' ],
      backlogFormat: [ 'paste' ]
    });
  }

  ngOnInit(): void {
    if (this.name) {
      this.formGroup.get('name')?.patchValue(this.name);
    }
    if (this.deck) {
      this.formGroup.get('deck')?.patchValue(decksDict[this.deck]);
    }
  }

  validate(): void {
    // Trim so a padded name never reaches the broadcast/DB (the server also clamps
    // length); a blank-after-trim name is already blocked by the nonBlank validator.
    const raw = this.formGroup.getRawValue();
    this.gameOutput.emit({ ...raw, name: (raw.name ?? '').trim() });
  }

  /** Reject a whitespace-only name (Validators.required alone treats "   " as set). */
  private static nonBlank(control: AbstractControl): ValidationErrors | null {
    return (control.value ?? '').trim().length > 0 ? null : { required: true };
  }

  isNewGame(): boolean {
    return !this.name && !this.deck;
  }

}
