import { Component, Inject } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { getBrowserCultureLang, getBrowserLang, TranslocoService } from '@ngneat/transloco';
import { TranslocoLocaleService } from '@ngneat/transloco-locale';
import { RouterOutlet } from '@angular/router';
import { ToastsContainerComponent } from './shared/toast/toast-container.component';

// Shipped languages whose scripts read right-to-left.
const RTL_LANGS = ['ar', 'he'];

@Component({
    selector: 'shpp-root',
    templateUrl: './app.component.html',
    styles: [],
    standalone: true,
    imports: [RouterOutlet, ToastsContainerComponent]
})
export class AppComponent {

  constructor(private transloco: TranslocoService,
              private translocoLocale: TranslocoLocaleService,
              @Inject(DOCUMENT) private document: Document) {
    // Norwegian Bokmål browsers report 'nb'; we ship the translation as 'no'.
    const detected = getBrowserLang() || 'en';
    const lang = detected === 'nb' ? 'no' : detected;
    transloco.setActiveLang(lang);
    translocoLocale.setLocale(getBrowserCultureLang());
    // Keep the document in sync with the active language so assistive tech announces
    // content in the right voice (WCAG 3.1.1) and RTL scripts lay out correctly.
    this.document.documentElement.lang = lang;
    this.document.documentElement.dir = RTL_LANGS.includes(lang) ? 'rtl' : 'ltr';
  }
}
