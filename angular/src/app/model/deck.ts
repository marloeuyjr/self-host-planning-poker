export interface CardValue {
  // Usually a number, but the abstain card carries the string '?' so the value
  // sent on `pick_card` matches the server's abstain sentinel (stats.ABSTAIN).
  value: number | string;
  display: number | string;
}

export interface Deck {
  name: string;
  textValues: boolean;
  values: CardValue[];
}

export const decks: Deck[] = [
  {
    name: 'FIBONACCI',
    textValues: false,
    values: [
      { value: 0, display: 0 },
      { value: 1, display: 1 },
      { value: 2, display: 2 },
      { value: 3, display: 3 },
      { value: 5, display: 5 },
      { value: 8, display: 8 },
      { value: 13, display: 13 },
      { value: 21, display: 21 },
      // Abstain: "voted, but I don't understand the issue". Excluded from the mean
      // server-side (stats.ABSTAIN). Last so the numeric keyboard digits don't shift.
      { value: '?', display: '?' },
    ]
  },
  {
    name: 'MODIFIED_FIBONACCI',
    textValues: false,
    values: [
      { value: 0, display: 0 },
      { value: 0.5, display: 0.5 },
      { value: 1, display: 1 },
      { value: 2, display: 2 },
      { value: 3, display: 3 },
      { value: 5, display: 5 },
      { value: 8, display: 8 },
      { value: 13, display: 13 },
      { value: 20, display: 20 },
      { value: 40, display: 40 },
      { value: 100, display: 100 },
    ]
  },
  {
    name: 'POWERS',
    textValues: false,
    values: [
      { value: 0, display: 0 },
      { value: 1, display: 1 },
      { value: 2, display: 2 },
      { value: 4, display: 4 },
      { value: 8, display: 8 },
      { value: 16, display: 16 },
      { value: 32, display: 32 },
      { value: 64, display: 64 },
    ]
  },
  {
    name: 'TRUST_VOTE',
    textValues: false,
    values: [
      { value: 0, display: 0 },
      { value: 1, display: 1 },
      { value: 2, display: 2 },
      { value: 3, display: 3 },
      { value: 4, display: 4 },
      { value: 5, display: 5 },
    ]
  },
  {
    name: 'T_SHIRTS',
    textValues: true,
    values: [
      { value: 1, display: 'XXS' },
      { value: 2, display: 'XS' },
      { value: 3, display: 'S' },
      { value: 4, display: 'M' },
      { value: 5, display: 'L' },
      { value: 6, display: 'XL' },
      { value: 7, display: 'XXL' },
    ]
  }
]

export const decksDict: { [key: string]: Deck } = decks.reduce((result: { [key: string]: Deck }, deck: Deck) => {
  result[deck.name] = deck;
  return result;
}, {});

export function displayDeckValues(deck: Deck): string {
  return deck.values.map(v => v.display).join(', ');
}

export function displayCardValue(deck: Deck, cardValue: number | string): string | number | undefined {
  return deck.values.find(c => c.value === cardValue)?.display;
}
