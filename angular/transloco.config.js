module.exports = {
  rootTranslationsPath: 'src/assets/i18n/',
  // Mirror the runtime availableLangs in main.ts so the keys-manager audits every
  // shipped locale, not just two. 'en' is the source of truth / fallback; 'no' (and
  // 'nb', normalised to 'no' at runtime) is the team's own locale.
  langs: ['af', 'ar', 'ca', 'cs', 'da', 'de', 'el', 'en', 'es', 'fi', 'fr', 'he', 'hu',
    'it', 'ja', 'ko', 'nl', 'no', 'pl', 'pt', 'ro', 'ru', 'sr', 'sv', 'tr', 'uk', 'vi', 'zh'],
  defaultLang: 'en',
  keysManager: {}
};