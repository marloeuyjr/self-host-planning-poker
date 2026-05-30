import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
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
      name: [ '', [ Validators.required, Validators.minLength(1) ]],
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
    this.gameOutput.emit(this.formGroup?.getRawValue());
  }

  isNewGame(): boolean {
    return !this.name && !this.deck;
  }

}
