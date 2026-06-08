import { Component, EventEmitter, Input, OnDestroy, Output } from '@angular/core';
import { AbstractControl, FormBuilder, FormGroup, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { UserInformationService } from '../user-info/user-information.service';
import { TranslocoDirective } from '@ngneat/transloco';
import { NgIf } from '@angular/common';
import { Subject, Subscription, throttleTime } from "rxjs";

@Component({
    selector: 'shpp-player-name-form',
    templateUrl: './player-name-form.component.html',
    standalone: true,
    imports: [TranslocoDirective, ReactiveFormsModule, NgIf]
})
export class PlayerNameFormComponent implements OnDestroy {
  formGroup: FormGroup;

  @Input()
  join = false;
  @Output() validated = new EventEmitter<void>();

  private subscription?: Subscription;
  private subject: Subject<void>

  constructor(private fb: FormBuilder,
              private userInformation: UserInformationService) {
    this.formGroup = this.fb.group({
      username: [ this.userInformation.getName(), [Validators.required, PlayerNameFormComponent.nonBlank]]
    });

    this.subject = new Subject<void>();
    // Leading-edge throttle: join/update fires immediately on the first click (the
    // 1s debounce made the primary CTA feel dead) while still coalescing an
    // accidental double-submit within the window.
    this.subscription = this.subject
    .pipe(throttleTime(1000))
    .subscribe(() => {
      // Trim before persisting/broadcasting so a whitespace-padded name never shows
      // up as a blank or mis-aligned player card; a blank-after-trim name never submits.
      const username = (this.formGroup.get('username')?.value ?? '').trim();
      if (!username) {
        return;
      }
      this.userInformation.setName(username);
      this.validated.emit();
    });
  }

  /** Reject a whitespace-only name (Validators.required alone treats "   " as set). */
  private static nonBlank(control: AbstractControl): ValidationErrors | null {
    return (control.value ?? '').trim().length > 0 ? null : { required: true };
  }

  ngOnDestroy(): void {
        this.subscription?.unsubscribe();
    }

  setUsername(): void {
    this.subject.next();
  }

}
