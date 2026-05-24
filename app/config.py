import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- IDENTITY ---
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    OWNER_ID = os.getenv("OWNER_ID")  # Your Discord User ID for admin commands
    
    # --- BRAIN ---
    # Splits the comma-separated keys into a list
    GEMINI_KEYS = [k.strip() for k in os.getenv("GEMINI_KEYS", "").split(",") if k]
    GEMINI_MODEL = "models/gemini-2.0-flash"  # Stable version (2.0)
    
    # --- EYES (SEARCH) ---
    SERPER_KEYS = [k.strip() for k in os.getenv("SERPER_KEYS", "").split(",") if k]
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
    EXA_KEYS = [k.strip() for k in os.getenv("EXA_KEYS", "").split(",") if k]
    BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
    
    # --- EYES (SPECIALIST) ---
    COURT_LISTENER_TOKEN = os.getenv("COURT_LISTENER_TOKEN")
    CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY")
    FMP_API_KEY = os.getenv("FMP_API_KEY")
    
    # --- MEMORY ---
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    
    # --- SECURITY ---
    ADMIN_WEBHOOK_URL = os.getenv("ADMIN_WEBHOOK_URL")

    # --- LIMITS ---
    # 15 RPM is safe for Gemini Flash. We go 12 to be safer.
    MAX_RPM_PER_KEY = 12
    COOLDOWN_SECONDS = 60 / MAX_RPM_PER_KEY

