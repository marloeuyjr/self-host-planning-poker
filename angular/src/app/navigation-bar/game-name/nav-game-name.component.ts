import { Component, OnDestroy } from '@angular/core';
import { CurrentGameService } from '../../ongoing-game/current-game.service';
import { GameInfo } from '../../model/events';
import { Subscription } from 'rxjs';
import { ToastService } from '../../shared/toast/toast.service';
import { Clipboard } from '@angular/cdk/clipboard';
import { TranslocoDirective, TranslocoService } from '@ngneat/transloco';
import { NgbModal, NgbTooltip } from '@ng-bootstrap/ng-bootstrap';
import { NgIf } from '@angular/common';
import { SessionExportService } from '../../shared/session-export.service';

@Component({
    selector: 'shpp-game-name',
    templateUrl: './nav-game-name.component.html',
    standalone: true,
    imports: [TranslocoDirective, NgIf, NgbTooltip]
})
export class NavGameNameComponent implements OnDestroy {

  currentGameInfo: GameInfo | null | undefined;
  private gameInfoSubscription: Subscription;

  constructor(private currentGameService: CurrentGameService,
              private toastService:  ToastService,
              private clipboard: Clipboard,
              private modalService: NgbModal,
              private transloco: TranslocoService,
              private exportService: SessionExportService) {
    this.gameInfoSubscription = this.currentGameService.gameInfo$
    .subscribe((gameInfo) => this.currentGameInfo = gameInfo);
  }

  ngOnDestroy(): void {
    this.gameInfoSubscription.unsubscribe();
  }

  /** Download URL for this session's CSV export, or null before the game id is known.
   *  A string getter (not a fresh object) so it stays value-stable across change
   *  detection — `*ngIf="...as url"` then never trips ExpressionChangedAfterChecked. */
  get exportCsvUrl(): string | null {
    const id = this.currentGameService.gameId;
    return id ? this.exportService.csvUrl(id) : null;
  }

  get exportJsonUrl(): string | null {
    const id = this.currentGameService.gameId;
    return id ? this.exportService.jsonUrl(id) : null;
  }

  copyLink(): void {
    this.clipboard.copy(this.getUrl());
    this.toastService.show(
      this.transloco.translate('navbar.gameName.copy-toast')
    )
  }

  /** Open the QR modal. The component and its (~CommonJS) `qrcode` dependency are
   *  dynamically imported so they split into an on-demand chunk rather than weighing
   *  down the main game bundle — most sessions never open the QR. */
  async displayQrCode(): Promise<void> {
    const { QrCodeModalContentComponent } =
      await import('./qr-code-modal-content/qr-code-modal-content.component');
    const modalRef = this.modalService.open(QrCodeModalContentComponent);
    modalRef.componentInstance.url = this.getUrl();
  }

  private getUrl(): string {
    return window.location.toString();
  }
}
