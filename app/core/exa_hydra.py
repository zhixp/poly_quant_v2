from exa_py import Exa
from app.config import Config

class ExaHydra:
    def __init__(self):
        self.keys = Config.EXA_KEYS
        if not self.keys:
            self.clients = []
        else:
            self.clients = [Exa(key) for key in self.keys]
        self.current_index = 0

    def search(self, query):
        if not self.clients: return []
        
        # Rotate client
        client = self.clients[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.clients)
        
        try:
            # Neural Search for documents/news
            return client.search_and_contents(
                query,
                type="neural",
                use_autoprompt=True,
                num_results=3,
                text=True,
                include_domains=["sec.gov", "courtlistener.com", "reuters.com", "bloomberg.com", "nytimes.com"]
            ).results
        except Exception as e:
            print(f"Exa Error: {e}")
            return []