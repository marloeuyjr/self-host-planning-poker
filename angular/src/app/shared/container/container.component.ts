import { Component } from '@angular/core';
import { NavigationBarComponent } from '../../navigation-bar/navigation-bar.component';
import { TranslocoDirective } from '@ngneat/transloco';

@Component({
  standalone: true,
  selector: 'shpp-container',
  templateUrl: './container.component.html',
  imports: [ NavigationBarComponent, TranslocoDirective ]
})
export class ContainerComponent {

}
