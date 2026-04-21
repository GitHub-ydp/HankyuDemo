import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import zh from './zh.json';
import ja from './ja.json';
import en from './en.json';

const LANGUAGE_STORAGE_KEY = 'appLanguage';
const SUPPORTED_LANGUAGES = ['zh', 'ja', 'en'] as const;

const detectLanguage = () => {
  const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY);
  if (saved && SUPPORTED_LANGUAGES.includes(saved as typeof SUPPORTED_LANGUAGES[number])) {
    return saved;
  }

  const browserLanguage = navigator.language.toLowerCase();
  if (browserLanguage.startsWith('ja')) return 'ja';
  if (browserLanguage.startsWith('en')) return 'en';
  return 'zh';
};

i18n.use(initReactI18next).init({
  resources: {
    zh: { translation: zh },
    ja: { translation: ja },
    en: { translation: en },
  },
  lng: detectLanguage(),
  fallbackLng: 'zh',
  interpolation: { escapeValue: false },
});

i18n.on('languageChanged', (language) => {
  localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
});

export default i18n;
