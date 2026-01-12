import json
import os
from flask import request, g

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
                    print(f"Error loading translation {filename}: {e}")

    def get_locale(self):
        # Try to get from URL parameter usually, but user asked for "default english, translatable via json"
        # Since we don't have a user selector yet, let's use browser Accept-Language
        # or fallback to en. 
        # For this specific request, "maintains english by default" suggests we stick to en unless forced?
        # A simple approach: Check 'lang' cookie or query param, else 'en'.
        # But 'pt_BR' file exists for when we want to switch.
        
        # Let's try best match from headers
        best_match = request.accept_languages.best_match(self.translations.keys())
        return best_match or self.default_locale

    def t(self, key):
        locale = self.get_locale()
        # Fallback to default if key missing in locale
        return self.translations.get(locale, {}).get(key, self.translations.get(self.default_locale, {}).get(key, key))

    def context_processor(self):
        return dict(t=self.t)
