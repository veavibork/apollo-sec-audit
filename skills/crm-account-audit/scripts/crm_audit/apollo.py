import re
from typing import Any

import requests

from crm_audit.cache import JsonCache
from crm_audit.coerce import as_float, as_int, as_str, as_str_tuple
from crm_audit.errors import LiveCallLimitReached, SourceError
from crm_audit.fetch import get_json
from crm_audit.models import ApolloOrg

ENRICH_URL = "https://api.apollo.io/api/v1/organizations/enrich"
DOMAIN_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
)


def normalize_domain(raw: str) -> str:
    """'https://www.HubSpot.com/about' -> 'hubspot.com'. Raises ValueError if not a domain."""
    text = raw.strip().lower()
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text)
    text = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    text = text.split(":", 1)[0].rstrip(".").removeprefix("www.")
    if not DOMAIN_PATTERN.fullmatch(text):
        raise ValueError(f"not a domain: {raw!r}")
    return text


def trim(raw: Any) -> ApolloOrg | None:
    if not isinstance(raw, dict):
        raise SourceError("apollo: response is not a JSON object")
    if "organization" not in raw:
        raise SourceError("apollo: response has no 'organization' key")
    org = raw["organization"]
    if not isinstance(org, dict) or not org:
        return None
    return ApolloOrg(
        name=as_str(org.get("name")),
        domain=as_str(org.get("primary_domain")),
        annual_revenue=as_float(org.get("annual_revenue")),
        estimated_num_employees=as_int(org.get("estimated_num_employees")),
        founded_year=as_int(org.get("founded_year")),
        publicly_traded_symbol=as_str(org.get("publicly_traded_symbol")),
        publicly_traded_exchange=as_str(org.get("publicly_traded_exchange")),
        city=as_str(org.get("city")),
        state=as_str(org.get("state")),
        country=as_str(org.get("country")),
        industry=as_str(org.get("industry")),
        sic_codes=as_str_tuple(org.get("sic_codes")),
        naics_codes=as_str_tuple(org.get("naics_codes")),
        total_funding=as_float(org.get("total_funding")),
        latest_funding_stage=as_str(org.get("latest_funding_stage")),
    )


class ApolloClient:
    def __init__(
        self,
        cache: JsonCache,
        api_key: str | None,
        max_live_calls: int,
        session: requests.Session | None = None,
    ) -> None:
        if max_live_calls < 0:
            raise ValueError("max_live_calls must be >= 0")
        self._cache = cache
        self._api_key = api_key or None
        self._max_live_calls = max_live_calls
        self._session = session or requests.Session()
        self.live_calls = 0

    def enrich(self, domain: str) -> ApolloOrg | None:
        """Cache first. Live calls count toward the cap before they are sent."""
        domain = normalize_domain(domain)
        key = f"apollo/{domain}.json"
        raw = self._cache.get(key)
        if raw is None:
            if self._api_key is None:
                raise SourceError(f"apollo: APOLLO_API_KEY is not set and {domain} is not cached")
            if self.live_calls >= self._max_live_calls:
                raise LiveCallLimitReached(
                    f"apollo: live call limit ({self._max_live_calls}) reached before {domain}"
                )
            self.live_calls += 1
            raw = get_json(
                self._session,
                "apollo",
                ENRICH_URL,
                headers={
                    "x-api-key": self._api_key,
                    "Cache-Control": "no-cache",
                    "accept": "application/json",
                },
                params={"domain": domain},
            )
            org = trim(raw)
            self._cache.put(key, raw)
            return org
        return trim(raw)
