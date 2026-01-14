import logging
import json
import requests
from plugin_system import MyFoilPlugin

logger = logging.getLogger('main')

class DiscordNotifyPlugin(MyFoilPlugin):
    def __init__(self, app=None):
        super().__init__(app)
        self.name = "Discord Notify"
        self.description = "Envia notificações para um Webhook do Discord quando a biblioteca é atualizada."
        self.version = "1.0.0"
        self.webhook_url = None
        
    def on_load(self):
        logger.info(f"Plugin {self.name} carregado!")
        # In a real scenario, we'd load the webhook URL from a config file
        # For this example, we'll look for a file named discord_config.json in the plugin folder
        import os
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.webhook_url = config.get('webhook_url')
                    logger.info(f"{self.name}: Webhook URL carregada.")
            except Exception as e:
                logger.error(f"{self.name}: Erro ao carregar config: {e}")

    def on_library_updated(self, data):
        if not self.webhook_url:
            return

        # Prepare Discord message
        added = data.get('added', [])
        if not added:
            return

        embeds = []
        for item in added[:5]: # Limit to 5 items to avoid spam
            embeds.append({
                "title": f"🎮 Novo Jogo Adicionado: {item.get('title', 'Desconhecido')}",
                "description": f"**ID:** {item.get('id')}\n**Tamanho:** {self._format_size(item.get('size', 0))}",
                "color": 5814783, # MyFoil Purple-ish
                "thumbnail": {
                    "url": item.get('iconUrl', '')
                }
            })

        payload = {
            "content": "🚀 **A biblioteca MyFoil foi atualizada!**",
            "embeds": embeds
        }

        try:
            requests.post(self.webhook_url, json=payload, timeout=5)
            logger.info(f"{self.name}: Notificação enviada para o Discord.")
        except Exception as e:
            logger.error(f"{self.name}: Erro ao enviar para o Discord: {e}")

    def _format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"
