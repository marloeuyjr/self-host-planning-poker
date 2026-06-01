import { inject, Injectable } from '@angular/core';
import { PathLocationStrategy } from '@angular/common';
import { environment } from '../../environments/environment';

/**
 * Builds the download URLs for a session's CSV / JSON export (v2). Centralises the
 * base-href resolution that `saved-sessions` inlined so both the home-page recall list
 * and the in-game nav point at the same backend routes. Downloads are plain
 * `<a [href] download>` links — the server's `Content-Disposition` header drives the
 * save, so no blob / fetch / JS plumbing is needed here.
 */
@Injectable({ providedIn: 'root' })
export class SessionExportService {
  private pls = inject(PathLocationStrategy);

  /** `backendRootOverride` (dev, points at the Flask port) or the deployed base href;
   *  both already end in a slash, matching the `${base}sessions` convention. */
  private base(): string {
    return environment.backendRootOverride ?? this.pls.getBaseHref();
  }

  csvUrl(uuid: string): string {
    return `${this.base()}sessions/${uuid}/export.csv`;
  }

  jsonUrl(uuid: string): string {
    return `${this.base()}sessions/${uuid}/export.json`;
  }
}
