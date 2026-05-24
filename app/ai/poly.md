# 🧠 PolyQuant Sentinel: System Architecture & Logic

> **Version:** 1.0 (Genesis)
> **Role:** Autonomous Market Intelligence Agency
> **Core Philosophy:** "Math > Hype" | "Accuracy > Speed"

---

## 1. The "Zero Trust" Security Protocol
Before any logic runs, the system enforces strict security boundaries.

### **A. Permission Lockdown**
* **Discord Side:** The bot has **Zero Administrative Power**. It cannot ban users, delete channels, or view audit logs. It can only:
    * Read Messages (to see `/ask`)
    * Send Messages (to reply)
    * Embed Links (to show data)
* **Code Side (`main.py`):** We explicitly disable `intents.members` and `intents.presences`. The bot does not know who is in the server. This prevents "User Scraping" attacks.

### **B. Input Sanitization**
* **Attack Vector:** Users trying to inject commands or spam via the bot.
* **Defense:** `main.py` strips `@everyone`, `@here`, and limits queries to 200 characters before processing.
* **Fail-Safe:** The `Watchdog` catches crashes and routes the error stack trace to a **Private Webhook**, ensuring the public channel never sees internal code errors.

---

## 2. The "Hydra" Brain (Rate Limits & IP Protection)
**File:** `app/ai/hydra.py` | `app/config.py`

The system acts as a "Load Balancer" for Intelligence. It treats API keys as "Ammo" that must be conserved and rotated.

* **The Logic:**
    * The bot holds a pool of Gemini Keys (e.g., 7-20 keys).
    * **IP Protection (`MAX_RPM_PER_KEY`):** We hard-code a limit (e.g., 12 requests per minute). This prevents Google from flagging your IP address for spamming.
    * **Round Robin:** Request 1 -> Key A, Request 2 -> Key B, etc.
* **The Safety Net (429 Assassin):**
    * If a key fails with `ResourceExhausted` (429), the Hydra **Quarantines** it for 60 seconds.
    * It **Instantly Retries** with the next healthy key.
    * **Result:** The user experiences 0 seconds of downtime.

---

## 3. The "Invincible Router" (Search Logic)
**File:** `app/core/router.py`

The bot never relies on a single source of truth. It uses a **Waterfall Logic** to find data, skipping broken or missing tools automatically.

### **The Waterfall Flow:**
1.  **Tier 1: DuckDuckGo (Free)**
    * *Action:* Attempts to fetch general news.
    * *Status:* Always Active.
2.  **Tier 2: Tavily (AI Optimized)**
    * *Logic:* Checks `.env` for `TAVILY_API_KEY`.
    * *Switch:* If Key exists -> Fetch high-quality context. If Key is missing -> **SKIP silently.**
3.  **Tier 3: Brave Search (Huge Index)**
    * *Logic:* Checks `.env` for `BRAVE_API_KEY`.
    * *Switch:* **If Key is missing -> SKIP.** (This handles your current situation where you don't have a Brave key yet. The code won't crash).
4.  **Tier 4: Exa (God Mode)**
    * *Action:* Fires only if previous steps didn't provide enough "Hard Data" (PDFs, Filings).
    * *Safety:* Uses `ExaHydra` to rotate Exa keys if you have multiple.

**Result:** The bot *always* finds data, even if 2 out of 4 services are down.

---

## 4. The "Sync" Workflow (How It All Connects)

When a user types `/ask Will Bitcoin hit 100k?`, the entire system synchronizes in 4 phases:

### **Phase 1: The Memory Check (0.1s)**
* **Component:** `app/core/database.py`
* **Action:** Checks Supabase: "Have we answered this specific question in the last 6 hours?"
* **Result:** If YES -> Returns cached answer instantly (Free cost). If NO -> Proceed to Phase 2.

### **Phase 2: The Eye Scan (3s)**
* **Component:** `app/core/router.py`
* **Action:** The Router executes the Waterfall search (DDG -> Tavily -> Brave -> Exa).
* **Output:** Collects raw text, news snippets, and URLs.

### **Phase 3: The War Room (5s)**
* **Component:** `app/ai/agents.py`
* **Action:** The `AgentCouncil` spins up 5 parallel threads using the `Hydra`:
    1.  **The Bull:** Looks for positive momentum.
    2.  **The Bear:** Looks for risks.
    3.  **The Lawyer:** Audits resolution rules.
    4.  **The Journalist:** Fact-checks sources.
    5.  **The Judge:** Reads the outputs of the first 4 and renders a verdict.
* **Sync:** All 5 agents run at the exact same time (AsyncIO) to save time.

### **Phase 4: The Save & Serve (0.5s)**
* **Component:** `main.py`
* **Action:**
    1.  Posts the formatted "Judge's Verdict" to Discord.
    2.  Saves the result to `app/core/database.py` (Supabase) to fuel the Cache for the next user.

---

## 5. The "Lag Hunter" (Background Sync)
**File:** `app/scanners/lag_hunter.py`

While the bot answers questions, this script runs in a separate parallel loop.

* **Logic:**
    1.  **Polls RSS:** Checks SEC.gov, CoinDesk, FiveThirtyEight every 60s.
    2.  **Checks Price:** If "Breaking News" is found, it checks the Polymarket API.
    3.  **The Calculation:** `IF (News_Age < 15m) AND (Price_Change < 1%) THEN ALERT.`
    4.  **The Sync:** It injects a message directly into the `#news-lag` channel without user input.

---

## 6. Troubleshooting & Fixes

### **Issue: `ModuleNotFoundError: No module named 'app.config'`**
**Why:** Python doesn't know that the `app` folder is a package when running from the root.
**Fix:** You must run the bot using the module flag OR fix the path in code.
* **Command:** `python -m main` (Try this first)
* **Code Fix:** Add this to the very top of `main.py`:
    ```python
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    ```

### **Issue: `pip` not found**
**Fix:** Use the direct python module execution:
`python -m pip install -r requirements.txt`