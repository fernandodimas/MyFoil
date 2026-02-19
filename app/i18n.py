import json
import os
import structlog
from flask import request

logger = structlog.get_logger('i18n')


class I18n:
    def __init__(self, app=None):
        self.translations = {}
        self.default_locale = 'en'
        if app:
            self.init_app(app)

    def init_app(self, app):
        self.app = app
        self.load_translations()
        app.context_processor(self.context_processor)

    def load_translations(self):
        translations_dir = os.path.join(self.app.root_path, 'translations')
        if not os.path.exists(translations_dir):
            return
            
        for filename in os.listdir(translations_dir):
            if filename.endswith('.json'):
                locale = filename[:-5]
                try:
                    with open(os.path.join(translations_dir, filename), 'r', encoding='utf-8') as f:
                        self.translations[locale] = json.load(f)
                except Exception as e:
                    logger.error(f"Error loading translation {filename}: {e}")

    def get_locale(self):
        # 1. Check for language cookie
        cookie_lang = request.cookies.get('language')
        if cookie_lang and cookie_lang in self.translations:
            return cookie_lang
            
        # 2. Try best match from headers
        best_match = request.accept_languages.best_match(self.translations.keys())
        return best_match or self.default_locale

    def t(self, key):
        locale = self.get_locale()
        # Fallback to default if key missing in locale
        return self.translations.get(locale, {}).get(key, self.translations.get(self.default_locale, {}).get(key, key))

    def get_translations_dict(self):
        locale = self.get_locale()
        return self.translations.get(locale, self.translations.get(self.default_locale, {}))

    def get_available_languages(self):
        """Return dict of available languages with friendly names"""
        names = {
            'en': 'English',
            'pt_BR': 'Português (Brasil)',
            'es': 'Español'
        }
        available = {}
        # Ensure loaded translations are included
        for code in self.translations.keys():
            available[code] = names.get(code, code)
            
        # Ensure default hardcoded ones exist even if file load failed
        for code, name in names.items():
            if code not in available and os.path.exists(os.path.join(self.app.root_path, 'translations', f'{code}.json')):
                 available[code] = name
                 
        return available

    def context_processor(self):
        from constants import BUILD_VERSION
        return dict(
            t=self.t, 
            get_locale=self.get_locale, 
            get_translations=self.get_translations_dict,
            get_available_languages=self.get_available_languages,
            build_version=BUILD_VERSION
        )
