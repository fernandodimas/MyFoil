import json
import os
import structlog
from flask import request

logger = structlog.get_logger('i18n')


def get_build_version():
    """Get build version from file or git"""
    try:
        version_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'BUILD_VERSION')
        if os.path.exists(version_file):
            with open(version_file, 'r') as f:
                version = f.read().strip()
                if version:
                    return version
    except:
        pass
    try:
        import subprocess
        version = subprocess.check_output(['git', 'describe', '--tags', '--always'], 
                                          cwd=os.path.dirname(os.path.dirname(__file__)), 
                                          stderr=subprocess.DEVNULL).decode().strip()
        if version:
            return version
    except:
        pass
    return 'Unknown'


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

    def context_processor(self):
        return dict(
            t=self.t, 
            get_locale=self.get_locale, 
            get_translations=self.get_translations_dict,
            build_version=get_build_version()
        )
