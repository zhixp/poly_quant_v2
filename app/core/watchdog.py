import aiohttp
import logging
from datetime import datetime
from app.config import Config

logger = logging.getLogger("Watchdog")

class Watchdog:
    def __init__(self):
        self.webhook_url = Config.ADMIN_WEBHOOK_URL

    async def alert(self, source: str, message: str, severity: str = "WARNING"):
        """
        Sends a private alert to the Admin Channel via Webhook.
        Severity: "INFO" (green), "WARNING" (yellow), "ERROR" (red)
        """
        if not self.webhook_url:
            logger.info(f"Watchdog: {message}")
            return

        # Color mapping: INFO=green, WARNING=yellow, ERROR=red
        color_map = {
            "INFO": 5763719,    # Green
            "WARNING": 16776960, # Yellow
            "ERROR": 15548997   # Red
        }
        color = color_map.get(severity, 16776960)
        
        # Label mapping
        label = "Status" if severity == "INFO" else "Error"
        
        # Sanitize Keys (Don't leak API keys in error logs)
        safe_message = str(message)
        if Config.GEMINI_KEYS:
            for key in Config.GEMINI_KEYS:
                safe_message = safe_message.replace(key, "[REDACTED]")

        embed = {
            "title": f"🛡️ PolyQuant Alert: {source}",
            "description": f"**{label}:** `{safe_message[:1000]}`\n**Time:** {datetime.now()}",
            "color": color,
            "footer": {"text": "PolyQuant Security Module"}
        }
        
        payload = {"username": "PolyQuant Watchdog", "embeds": [embed]}

        try:
            async with aiohttp.ClientSession() as session:
                await session.post(self.webhook_url, json=payload)
        except Exception as e:
            logger.critical(f"Watchdog Failed to send alert: {e}")

# Create a global instance
watchdog = Watchdog()