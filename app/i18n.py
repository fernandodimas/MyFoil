import json
import os
import structlog
from flask import request

logger = structlog.get_logger('i18n')


class I18n:
    def __init__(self, app=None):
        self.translations = {}
        self.default_locale = 'pt_BR'
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
        if cookie_lang:
            if cookie_lang in self.translations:
                return cookie_lang
            if cookie_lang.lower().startswith('pt') and 'pt_BR' in self.translations:
                return 'pt_BR'

        # 2. Try best match from headers (supporting generic 'pt' -> 'pt_BR')
        for lang_code, _ in request.accept_languages:
            norm = (lang_code or '').replace('-', '_')
            if norm in self.translations:
                return norm
            short = norm.split('_')[0].lower()
            if short == 'pt' and 'pt_BR' in self.translations:
                return 'pt_BR'
            if short in self.translations:
                return short

        best_match = request.accept_languages.best_match(self.translations.keys())
        return best_match or self.default_locale

    def t(self, key):
        locale = self.get_locale()
        # Fallback to default locale, then 'en', then key itself
        return (
            self.translations.get(locale, {}).get(
                key,
                self.translations.get(self.default_locale, {}).get(
                    key,
                    self.translations.get('en', {}).get(key, key),
                ),
            )
        )

    def get_translations_dict(self):
        locale = self.get_locale()
        merged = {}
        if 'en' in self.translations:
            merged.update(self.translations['en'])
        if self.default_locale in self.translations:
            merged.update(self.translations[self.default_locale])
        if locale in self.translations:
            merged.update(self.translations[locale])
        return merged

    def get_available_languages(self):
        """Return dict of available languages with friendly names"""
        names = {
            'en': 'English',
            'pt_BR': 'Português (Brasil)',
            'es': 'Español',
        }
        available = {}
        for code in self.translations.keys():
            available[code] = names.get(code, code)

        for code, name in names.items():
            if code not in available and os.path.exists(os.path.join(self.app.root_path, 'translations', f'{code}.json')):
                available[code] = name

        return available

    def context_processor(self):
        from constants import BUILD_VERSION
        try:
            from auth import admin_account_created
            has_admin = admin_account_created()
        except Exception:
            has_admin = True
        return dict(
            t=self.t,
            get_locale=self.get_locale,
            get_translations=self.get_translations_dict,
            get_available_languages=self.get_available_languages,
            build_version=BUILD_VERSION,
            container_tz=os.getenv("TZ", "UTC"),
            admin_account_created=has_admin,
        )
