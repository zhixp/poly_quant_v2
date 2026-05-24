# app/ai/agents.py
import asyncio
import json
import logging
from app.ai.hydra import HydraEngine
from app.Prompts.bull import get_bull_prompt
from app.Prompts.bear import get_bear_prompt
from app.Prompts.lawyer import get_lawyer_prompt
from app.Prompts.journalist import get_journalist_prompt
from app.Prompts.judge import get_judge_prompt

logger = logging.getLogger("AgentCouncil")

class AgentCouncil:
    """
    The War Room: 5 Parallel Agents using strict Hydra rotation.
    Per poly.md Section 4: Bull + Bear + Lawyer + Journalist → Judge
    """
    def __init__(self):
        self.hydra = HydraEngine()

    async def deliberate(self, question: str, context_data: str):
        """
        Executes the 5-Agent Parallel Swarm with fail-safe error handling.
        Returns: (verdict_text, opinions_dict)
        
        NOTE: context_data should include current market prices from search results.
        Judge will extract and use them for multi-candidate market analysis.
        """
        logger.info("⚡ War Room: Deploying 4 Specialist Agents...")
        
        # 1. Fire the Specialist Agents in Parallel (AsyncIO)
        tasks = [
            self._safe_generate(get_bull_prompt(question, context_data), "BULL 🐂"),
            self._safe_generate(get_bear_prompt(question, context_data), "BEAR 🐻"),
            self._safe_generate(get_lawyer_prompt(context_data, context_data), "LAWYER ⚖️"),
            self._safe_generate(get_journalist_prompt(question, context_data), "SKEPTIC 🕵️")
        ]
        
        # Wait for all 4 to finish (with timeout protection)
        try:
            responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=30.0)
        except asyncio.TimeoutError:
            logger.error("⏱️ Agent Council Timeout!")
            return "ERROR: Analysis Timeout", {}
        
        # 2. Parse Results into dictionary
        opinions = {
            "BULL 🐂": responses[0],
            "BEAR 🐻": responses[1],
            "LAWYER ⚖️": responses[2],
            "SKEPTIC 🕵️": responses[3]
        }

        # 3. The Judge (Synthesis Phase)
        logger.info("⚖️ War Room: Judge is Deliberating...")
        judge_prompt = get_judge_prompt(
            opinions["BULL 🐂"], 
            opinions["BEAR 🐻"], 
            opinions["LAWYER ⚖️"], 
            opinions["SKEPTIC 🕵️"],
            authoritative_context=context_data,
        )
        
        final_verdict = await self._safe_generate(judge_prompt, "JUDGE")
        
        return final_verdict, opinions

    async def _safe_generate(self, prompt: str, agent_name: str):
        """Wrapper with error handling for individual agent failures."""
        try:
            result = await self.hydra.generate(prompt)
            if result.startswith("ERROR"):
                logger.warning(f"⚠️ {agent_name} returned error: {result}")
            return result
        except Exception as e:
            logger.error(f"❌ {agent_name} crashed: {e}")
            return f"ERROR: {agent_name} unavailable."