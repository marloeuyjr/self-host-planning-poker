import { Component, Input } from '@angular/core';
import { CardValue } from '../../../model/deck';
import { NgIf } from '@angular/common';

@Component({
    selector: 'shpp-pickable-card',
    templateUrl: './pickable-card.component.html',
    styleUrls: ['./pickable-card.component.scss'],
    standalone: true,
    imports: [NgIf]
})
export class PickableCardComponent {
  @Input() cardValue?: CardValue;
  @Input() selected = false;
  @Input() disabled = false;
  @Input() keyHint?: string;

}
