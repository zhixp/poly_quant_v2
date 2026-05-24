"""
Market Mapping Service: cross-venue market entity resolution.

Supabase Python client does not support arbitrary raw SQL from this app. This
service therefore uses table queries directly; the old implementation called
placeholder `db.fetch_all()`/`fetch_one()` methods that always returned empty,
which made arbitrage comparisons silently skip mappings.
"""
import logging
from typing import Optional, List
from dataclasses import dataclass
from app.core.database import db

logger = logging.getLogger("MarketMapping")


@dataclass
class MarketMapping:
    """Represents a mapping between Polymarket and an external venue."""
    id: int
    polymarket_event_slug: str
    polymarket_market_slug: Optional[str]
    venue: str
    venue_market_id: str
    normalized_name: str
    status: str
    created_at: str
    updated_at: str


class MarketMappingService:
    """CRUD + lookup utilities for cross-venue mappings."""

    def _row_to_mapping(self, row: dict) -> MarketMapping:
        return MarketMapping(
            id=row["id"],
            polymarket_event_slug=row["polymarket_event_slug"],
            polymarket_market_slug=row.get("polymarket_market_slug"),
            venue=row["venue"],
            venue_market_id=row["venue_market_id"],
            normalized_name=row["normalized_name"],
            status=row.get("status", "active"),
            created_at=str(row.get("created_at", "")),
            updated_at=str(row.get("updated_at", "")),
        )

    async def get_mappings_for_polymarket(
        self,
        event_slug: str,
        venue: Optional[str] = None,
        active_only: bool = True,
        market_slug: Optional[str] = None,
        exact_market_only: bool = False,
    ) -> List[MarketMapping]:
        """Get mappings for a Polymarket event, optionally narrowed to a child market.

        For ladder events, pass `market_slug`; otherwise a May 31 Polymarket
        market can be compared against a May 26 Kalshi ticker.
        """
        if not db.client:
            return []
        try:
            query = db.client.table("market_mappings").select("*").eq(
                "polymarket_event_slug", event_slug
            )
            if venue:
                query = query.eq("venue", venue.lower())
            if active_only:
                query = query.eq("status", "active")
            if market_slug:
                query = query.eq("polymarket_market_slug", market_slug)

            response = query.order("created_at", desc=True).execute()
            rows = response.data or []

            # If no exact child-market mapping exists, allow event-level mapping as fallback
            # for legacy odds context only. Arbitrage callers must set exact_market_only=True.
            if market_slug and not rows and not exact_market_only:
                fallback = db.client.table("market_mappings").select("*").eq(
                    "polymarket_event_slug", event_slug
                ).is_("polymarket_market_slug", "null")
                if venue:
                    fallback = fallback.eq("venue", venue.lower())
                if active_only:
                    fallback = fallback.eq("status", "active")
                rows = (fallback.order("created_at", desc=True).execute().data or [])

            return [self._row_to_mapping(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch mappings for {event_slug}/{market_slug}: {e}")
            return []

    def is_exact_active_mapping(
        self,
        mapping: Optional[MarketMapping],
        event_slug: str,
        market_slug: str,
        venue: Optional[str] = None,
    ) -> bool:
        """True only for exact, active DB mappings eligible for live arb checks."""
        if not mapping or not market_slug:
            return False
        if mapping.status != "active":
            return False
        if mapping.polymarket_event_slug != event_slug:
            return False
        if mapping.polymarket_market_slug != market_slug:
            return False
        if venue and mapping.venue.lower() != venue.lower():
            return False
        return True

    async def get_mapping_by_venue_id(self, venue: str, venue_market_id: str) -> Optional[MarketMapping]:
        if not db.client:
            return None
        try:
            response = db.client.table("market_mappings").select("*").eq(
                "venue", venue.lower()
            ).eq("venue_market_id", venue_market_id).eq("status", "active").limit(1).execute()
            rows = response.data or []
            return self._row_to_mapping(rows[0]) if rows else None
        except Exception as e:
            logger.error(f"Failed to fetch mapping for {venue}/{venue_market_id}: {e}")
            return None

    async def create_mapping(
        self,
        polymarket_event_slug: str,
        venue: str,
        venue_market_id: str,
        normalized_name: str,
        polymarket_market_slug: Optional[str] = None,
    ) -> Optional[int]:
        if not db.client:
            return None
        try:
            payload = {
                "polymarket_event_slug": polymarket_event_slug,
                "polymarket_market_slug": polymarket_market_slug,
                "venue": venue.lower(),
                "venue_market_id": venue_market_id,
                "normalized_name": normalized_name,
            }
            response = db.client.table("market_mappings").insert(payload).execute()
            rows = response.data or []
            mapping_id = rows[0]["id"] if rows else None
            if mapping_id:
                logger.info("Created mapping #%s: %s/%s <-> %s/%s", mapping_id, polymarket_event_slug, polymarket_market_slug, venue, venue_market_id)
            return mapping_id
        except Exception as e:
            logger.error(f"Failed to create mapping: {e}")
            return None

    async def update_mapping(self, mapping_id: int, **kwargs) -> bool:
        if not db.client:
            return False
        allowed_fields = {"polymarket_market_slug", "venue_market_id", "normalized_name", "status"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            logger.warning(f"No valid fields to update for mapping {mapping_id}")
            return False
        try:
            db.client.table("market_mappings").update(updates).eq("id", mapping_id).execute()
            logger.info(f"Updated mapping #{mapping_id}: {updates}")
            return True
        except Exception as e:
            logger.error(f"Failed to update mapping {mapping_id}: {e}")
            return False

    async def disable_mapping(self, mapping_id: int) -> bool:
        return await self.update_mapping(mapping_id, status="disabled")

    async def get_all_active_mappings(self) -> List[MarketMapping]:
        if not db.client:
            return []
        try:
            response = db.client.table("market_mappings").select("*").eq("status", "active").order(
                "polymarket_event_slug"
            ).execute()
            return [self._row_to_mapping(row) for row in (response.data or [])]
        except Exception as e:
            logger.error(f"Failed to fetch all active mappings: {e}")
            return []

    async def search_mappings(self, search_term: str, limit: int = 10) -> List[MarketMapping]:
        if not db.client:
            return []
        try:
            response = db.client.table("market_mappings").select("*").ilike(
                "normalized_name", f"%{search_term}%"
            ).eq("status", "active").order("updated_at", desc=True).limit(limit).execute()
            return [self._row_to_mapping(row) for row in (response.data or [])]
        except Exception as e:
            logger.error(f"Failed to search mappings for '{search_term}': {e}")
            return []


market_mapping_service = MarketMappingService()
