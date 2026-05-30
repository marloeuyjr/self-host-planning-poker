import { AfterViewInit, Component, ElementRef, OnDestroy, ViewChild } from '@angular/core';
import { combineLatest, filter, Subscription } from 'rxjs';
import { Deck, decksDict, displayCardValue } from '../../model/deck';
import { AsyncPipe, NgClass, NgFor, NgIf } from '@angular/common';
import { CurrentGameService } from '../current-game.service';
import confetti from 'canvas-confetti';
import { TranslocoDecimalPipe } from '@ngneat/transloco-locale';
import { TranslocoDirective } from '@ngneat/transloco';
import { EstimationResultView, Issue, RoundResults } from '../../model/events';

/**
 * Results panel shown on reveal (S5). Renders the stats the SERVER computed — no
 * browser math — keeps the confetti on full agreement, and (for a backlog game)
 * hosts the driver's accept / re-vote controls with a proposed final value (E4).
 */
@Component({
  selector: 'shpp-turn-summary',
  templateUrl: './turn-summary.component.html',
  styleUrls: ['./turn-summary.component.scss'],
  standalone: true,
  imports: [TranslocoDirective, NgFor, NgIf, NgClass, AsyncPipe, TranslocoDecimalPipe]
})
export class TurnSummaryComponent implements AfterViewInit, OnDestroy {
  private subscriptions: Subscription[] = [];

  displayCardValue = displayCardValue;
  Number = Number;
  round = Math.round;

  deck: Deck = decksDict['FIBONACCI'];
  results: RoundResults | null = null;
  currentIssue: Issue | null = null;
  priorRounds: EstimationResultView[] = [];
  finalValueInput: number | null = null;
  isDriver = true;   // only the driver accepts / re-votes (S8)

  @ViewChild('agreementElement')
  private agreementElement?: ElementRef;

  constructor(private currentGameService: CurrentGameService) {
    this.subscriptions.push(this.currentGameService.gameInfo$.subscribe((info) => {
      if (info) {
        this.deck = decksDict[info.deck] ?? this.deck;
      }
    }));

    this.subscriptions.push(this.currentGameService.results$.subscribe((results) => {
      this.results = results;
      this.finalValueInput = results ? results.proposedFinalValue : null;
    }));

    // The current issue's already-recorded rounds, shown only as a muted reference
    // (anti-anchoring — the live numbers come from `results`, the current round).
    this.subscriptions.push(
      combineLatest([this.currentGameService.currentIssue$, this.currentGameService.backlog$])
        .subscribe(([issue, backlog]) => {
          this.currentIssue = issue;
          this.priorRounds = (issue && backlog) ? (backlog.results[issue.id] ?? []) : [];
        }));

    this.subscriptions.push(this.currentGameService.isDriver$.subscribe((d) => this.isDriver = d));
  }

  ngAfterViewInit(): void {
    this.subscriptions.push(this.currentGameService.results$
      .pipe(filter((r): r is RoundResults => !!r && r.unanimous && r.count > 0))
      .subscribe(() => this.fireConfettis()));
  }

  /** Distribution buckets, winner (highest count, then highest value) first. */
  get distributionEntries(): { key: string, value: number }[] {
    if (!this.results) {
      return [];
    }
    return Object.entries(this.results.distribution)
      .map(([key, value]) => ({ key, value }))
      .sort((a, b) => b.value - a.value || Number(b.key) - Number(a.key));
  }

  isBacklogGame(): boolean {
    return this.currentIssue !== null;
  }

  get hasVotes(): boolean {
    return !!this.results && this.results.count > 0;
  }

  get isNumeric(): boolean {
    return !!this.results && this.results.numeric;
  }

  get averageValue(): number | null {
    return this.results?.average ?? null;
  }

  get medianValue(): number | null {
    return this.results?.median ?? null;
  }

  get lowValue(): number | null {
    return this.results?.low ?? null;
  }

  get highValue(): number | null {
    return this.results?.high ?? null;
  }

  get agreementPercent(): number | null {
    return this.results?.agreement != null ? Math.round(this.results.agreement * 100) : null;
  }

  /** "low–high" in the deck's display values, or just "low" when they coincide. */
  get rangeDisplay(): string | null {
    if (this.lowValue === null || this.highValue === null) {
      return null;
    }
    const low = displayCardValue(this.deck, this.lowValue);
    const high = displayCardValue(this.deck, this.highValue);
    return low === high ? `${low}` : `${low}–${high}`;
  }

  /** After two inconclusive rounds the driver should decide or park (E4). */
  showDecideHint(): boolean {
    return this.isBacklogGame() && !!this.results && !this.results.consensus && this.results.round >= 3;
  }

  agreementClass(): string {
    const agreement = this.results?.agreement ?? 0;
    if (!agreement) {
      return '';
    } else if (agreement < .5) {
      return 'text-danger';
    } else if (agreement < .7) {
      return 'text-warning';
    } else {
      return 'text-success';
    }
  }

  setFinalValue(value: number): void {
    this.finalValueInput = value;
  }

  accept(): void {
    this.currentGameService.acceptEstimate(this.finalValueInput);
  }

  revote(): void {
    this.currentGameService.revote();
  }

  ngOnDestroy(): void {
    this.subscriptions.forEach((s) => s.unsubscribe());
  }

  private fireConfettis() {
    const domRect = this.agreementElement?.nativeElement.getBoundingClientRect();
    if (!domRect) {
      return;
    }
    const x = (domRect.left + domRect.width / 2) / window.innerWidth;
    const y = (domRect.top + domRect.height / 2) / window.innerHeight;
    const origin = { x: x, y: y };
    this.fireParticles(0.25, { origin: origin, spread: 26, startVelocity: 55 });
    this.fireParticles(0.2, { origin: origin, spread: 60 });
    this.fireParticles(0.35, { origin: origin, spread: 100, decay: 0.91, scalar: 0.8 });
    this.fireParticles(0.1, { origin: origin, spread: 120, startVelocity: 25, decay: 0.92, scalar: 1.2 });
    this.fireParticles(0.1, { origin: origin, spread: 120, startVelocity: 45 });
  }

  private fireParticles(particleRatio: number, opts: any) {
    confetti({
      ...opts,
      disableForReducedMotion: true,
      particleCount: Math.floor(200 * particleRatio)
    });
  }
}
