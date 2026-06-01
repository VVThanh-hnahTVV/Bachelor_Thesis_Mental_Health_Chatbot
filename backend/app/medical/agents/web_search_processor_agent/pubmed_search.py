import logging
import time
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
DEFAULT_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
EUROPE_PMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

# NCBI: max 3 requests/s without API key; stay under with a small gap.
_NCBI_MIN_INTERVAL_SEC = 0.34
_last_ncbi_request_at = 0.0
# Set True after first "blocked" response — avoids hammering NCBI on every chat turn.
_ncbi_ip_blocked = False


def _throttle_ncbi() -> None:
    global _last_ncbi_request_at
    now = time.monotonic()
    wait = _NCBI_MIN_INTERVAL_SEC - (now - _last_ncbi_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_ncbi_request_at = time.monotonic()


def _is_ncbi_blocked_body(text: str) -> bool:
    lower = text.lower()
    return (
        "blocked diagnostic" in lower
        or "misuse.ncbi.nlm.nih.gov" in lower
        or "error blocked" in lower
        or "<!doctype html" in lower[:200]
    )


class PubmedSearchAgent:
    """Search medical literature via NCBI E-utilities, with Europe PMC fallback."""

    def __init__(
        self,
        esearch_url: str = DEFAULT_ESEARCH_URL,
        efetch_url: str = DEFAULT_EFETCH_URL,
        max_results: int = 5,
        tool: str = "MultiAgentMedicalAssistant",
        email: Optional[str] = None,
        api_key: Optional[str] = None,
        enable_europepmc_fallback: bool = True,
        use_ncbi: bool = True,
    ):
        self.esearch_url = esearch_url
        self.efetch_url = efetch_url
        self.max_results = max_results
        self.tool = tool
        self.email = email
        self.api_key = api_key
        self.enable_europepmc_fallback = enable_europepmc_fallback
        self.use_ncbi = use_ncbi

    def _base_params(self) -> dict:
        params = {"tool": self.tool}
        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def search_pubmed(self, query: str) -> str:
        """Return formatted PubMed hits with title, metadata, abstract, and URL."""
        query = query.strip().strip("\"'")
        if not query:
            return "No PubMed query provided."

        global _ncbi_ip_blocked
        ncbi_error: Optional[str] = None
        try_ncbi = (
            self.use_ncbi
            and not _ncbi_ip_blocked
            and (self.email or self.api_key)
        )
        if try_ncbi:
            try:
                article_ids = self._search_ids_ncbi(query)
                if article_ids:
                    summaries = self._fetch_summaries_ncbi(article_ids)
                    return "\n\n---\n\n".join(summaries)
                return "No relevant PubMed articles found."
            except Exception as e:
                ncbi_error = str(e)
                if "blocked" in str(e).lower() or "rate-limit" in str(e).lower():
                    _ncbi_ip_blocked = True
                    logger.info(
                        "NCBI E-utilities blocked for this process; "
                        "using Europe PMC only until server restart."
                    )
                else:
                    logger.warning("NCBI PubMed search failed: %s", e)
        elif _ncbi_ip_blocked:
            ncbi_error = "NCBI skipped (IP blocked earlier in this server session)"
        elif not self.use_ncbi:
            ncbi_error = "NCBI disabled (PUBMED_USE_NCBI=false)"
        elif not (self.email or self.api_key):
            ncbi_error = "PUBMED_EMAIL or PUBMED_API_KEY not configured"

        if self.enable_europepmc_fallback:
            try:
                epmc = self._search_europepmc(query)
                if epmc:
                    note = ""
                    if ncbi_error:
                        note = (
                            f"(NCBI unavailable: {ncbi_error}. "
                            "Showing Europe PMC results instead.)\n\n"
                        )
                    return note + epmc
            except Exception as e:
                logger.warning("Europe PMC fallback failed: %s", e)
                if ncbi_error:
                    return (
                        f"PubMed search unavailable. NCBI: {ncbi_error}. "
                        f"Europe PMC: {e}"
                    )

        if ncbi_error:
            return (
                f"PubMed search unavailable: {ncbi_error}. "
                "Set PUBMED_EMAIL and optional PUBMED_API_KEY (from "
                "https://www.ncbi.nlm.nih.gov/account/settings/ ), or enable "
                "Europe PMC fallback."
            )
        return "PubMed search skipped: configure PUBMED_EMAIL or PUBMED_API_KEY."

    def _search_ids_ncbi(self, query: str) -> List[str]:
        params = {
            **self._base_params(),
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": self.max_results,
        }
        _throttle_ncbi()
        response = requests.get(
            self.esearch_url,
            params=params,
            timeout=30,
            allow_redirects=True,
            headers={"User-Agent": f"{self.tool}/1.0 (medical-assistant)"},
        )
        response.raise_for_status()
        text = (response.text or "").strip()
        if not text.startswith("{") or _is_ncbi_blocked_body(text):
            snippet = text[:200].replace("\n", " ")
            raise ValueError(
                "NCBI blocked or rate-limited this IP. "
                f"Response: {snippet}"
            )
        data = response.json()
        if "error" in data:
            raise ValueError(data.get("error", "NCBI API error"))
        return data.get("esearchresult", {}).get("idlist", [])

    def _fetch_summaries_ncbi(self, article_ids: List[str]) -> List[str]:
        params = {
            **self._base_params(),
            "db": "pubmed",
            "id": ",".join(article_ids),
            "rettype": "abstract",
            "retmode": "text",
        }
        _throttle_ncbi()
        response = requests.get(
            self.efetch_url,
            params=params,
            timeout=30,
            headers={"User-Agent": f"{self.tool}/1.0 (medical-assistant)"},
        )
        response.raise_for_status()
        raw_text = response.text.strip()
        if _is_ncbi_blocked_body(raw_text):
            raise ValueError("NCBI blocked efetch request")

        blocks = [b.strip() for b in raw_text.split("\n\n") if b.strip()]
        formatted: List[str] = []

        for idx, article_id in enumerate(article_ids):
            abstract_block = blocks[idx] if idx < len(blocks) else "Abstract not available."
            url = f"https://pubmed.ncbi.nlm.nih.gov/{article_id}/"
            formatted.append(
                f"PMID: {article_id}\n"
                f"URL: {url}\n"
                f"Abstract:\n{abstract_block}"
            )

        return formatted

    def _search_europepmc(self, query: str) -> str:
        """Europe PMC REST API — no NCBI API key; good fallback when E-utilities block IP."""
        params = {
            "query": query,
            "format": "json",
            "pageSize": self.max_results,
            "resultType": "core",
        }
        response = requests.get(
            EUROPE_PMC_SEARCH_URL,
            params=params,
            timeout=30,
            headers={"User-Agent": f"{self.tool}/1.0 (medical-assistant)"},
        )
        response.raise_for_status()
        data = response.json()
        hits = data.get("resultList", {}).get("result", [])
        if not hits:
            return ""

        formatted: List[str] = []
        for hit in hits:
            pmid = hit.get("pmid") or hit.get("id", "N/A")
            title = hit.get("title", "N/A")
            abstract = (hit.get("abstractText") or "").strip() or "Abstract not available."
            journal = hit.get("journalTitle", "")
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid != "N/A" else ""
            block = (
                f"PMID: {pmid}\n"
                f"title: {title}\n"
                f"journal: {journal}\n"
            )
            if url:
                block += f"URL: {url}\n"
            block += f"Abstract:\n{abstract}"
            formatted.append(block)

        return "\n\n---\n\n".join(formatted)
