import time
import asyncio
import logging
import google.generativeai as genai
from google.api_core import exceptions
from app.config import Config

logger = logging.getLogger("Hydra")

class HydraEngine:
    """
    Strict Round-Robin Key Manager with 429 Quarantine.
    Per poly.md Section 2: "Request 1 -> Key A, Request 2 -> Key B"
    """
    def __init__(self):
        self.keys = Config.GEMINI_KEYS
        if not self.keys:
            raise ValueError("❌ No Gemini Keys found in .env!")
        
        # Track the last usage time for each key
        self.last_used = {key: 0.0 for key in self.keys}
        # Quarantine tracker (keys that hit 429 errors)
        self.quarantined_until = {key: 0.0 for key in self.keys}
        self.model_name = Config.GEMINI_MODEL
        
        # STRICT ROUND-ROBIN: Sequential index rotation
        self.current_index = 0
        logger.info(f"✅ Hydra initialized with {len(self.keys)} keys")

    def _get_next_key(self):
        """
        Strict Round-Robin rotation with quarantine enforcement.
        Returns: (key, wait_time_seconds)
        """
        now = time.time()
        attempts = 0
        max_attempts = len(self.keys)
        
        while attempts < max_attempts:
            # Get next key in rotation
            key = self.keys[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.keys)
            attempts += 1
            
            # Check if key is quarantined (429 recovery)
            if now < self.quarantined_until[key]:
                logger.debug(f"⛔ Key {key[:5]}... still in quarantine")
                continue
            
            # Check rate limit cooldown
            time_since_used = now - self.last_used[key]
            wait_time = Config.COOLDOWN_SECONDS - time_since_used
            
            if wait_time <= 0:
                # Key is ready to fire
                self.last_used[key] = now
                return key, 0
            else:
                # Need to wait (but this is the next key in rotation)
                self.last_used[key] = now + wait_time
                return key, wait_time
        
        # All keys are either quarantined or busy - return first key and wait
        fallback_key = self.keys[0]
        wait_time = max(
            self.quarantined_until[fallback_key] - now,
            Config.COOLDOWN_SECONDS - (now - self.last_used[fallback_key])
        )
        logger.warning(f"⚠️ All keys busy/quarantined. Waiting {wait_time:.1f}s")
        return fallback_key, max(wait_time, 0)

    async def generate(self, prompt):
        """
        Generates content with auto-retry and strict key rotation.
        Per poly.md: 60s quarantine on 429, instant retry with next key.
        """
        retries = len(self.keys) * 2  # Allow 2 full rotation cycles
        
        for attempt in range(retries):
            active_key, wait_time = self._get_next_key()
            
            if wait_time > 0:
                logger.debug(f"⏳ Rate limit: waiting {wait_time:.2f}s for key {active_key[:5]}...")
                await asyncio.sleep(wait_time)

            genai.configure(api_key=active_key)
            model = genai.GenerativeModel(self.model_name)
            
            try:
                response = await model.generate_content_async(prompt)
                return response.text
            
            except exceptions.ResourceExhausted:
                # 429 Error: Quarantine for 60 seconds per poly.md
                logger.warning(f"⛔ Key {active_key[:5]}... hit 429. Quarantined for 60s")
                self.quarantined_until[active_key] = time.time() + 60
                # Instant retry with next key
                continue
            
            except Exception as e:
                logger.error(f"Hydra Error on key {active_key[:5]}...: {e}")
                # For non-429 errors, try next key immediately
                if attempt < retries - 1:
                    continue
                return f"ERROR: Analysis Failed - {str(e)[:100]}"

        return "ERROR: All keys exhausted or rate limited."