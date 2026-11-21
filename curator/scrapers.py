from abc import ABC, abstractmethod
import html
import re
from typing import List, Optional
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup

from models import Opportunity, ResearchResource, UserProfile

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def clean_text(raw: Optional[str]) -> str:
    if not raw:
        return ""
    text = BeautifulSoup(html.unescape(raw), "html.parser").get_text(" ", strip=True)
    replacements = {
        "â€™": "'",
        "âs": "'s",
        "â€œ": '"',
        "â€\x9d": '"',
        "â€“": "-",
        "â€”": "-",
        "â¢": "",
        "Â": "",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return re.sub(r"\s+", " ", text).strip()


class BaseOpportunityScraper(ABC):
    name: str = "base"

    @abstractmethod
    def scrape(self, profile: UserProfile, category: str) -> List[Opportunity]:
        """Fetch and parse opportunities matching profile and category."""


class BaseResearchScraper(ABC):
    name: str = "research_base"

    @abstractmethod
    def search(self, topic: str, limit: int = 8) -> List[ResearchResource]:
        """Fetch curated research links and summaries for a topic."""


class LinkedInGuestScraper(BaseOpportunityScraper):
    """Fetches public job and internship listings from LinkedIn's guest search endpoint."""

    name = "LinkedIn"

    def scrape(self, profile: UserProfile, category: str) -> List[Opportunity]:
        cat = category.lower()
        if cat not in {"job", "internship"}:
            return []

        skill_part = " ".join(profile.skills[:2])
        role_hint = "intern" if cat == "internship" else "entry level"
        keywords = f"{profile.qualification} {skill_part} {role_hint}".strip()
        location = profile.location or "India"

        # LinkedIn f_E filter: 1 = Internship, 2 = Entry level
        exp_filter = "1" if cat == "internship" else "2"
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={quote_plus(keywords)}&location={quote_plus(location)}&f_E={exp_filter}&start=0"
        )

        results: List[Opportunity] = []
        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=12.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            for card in soup.select("li")[:15]:
                title_el = card.select_one("h3.base-search-card__title")
                company_el = card.select_one("h4.base-search-card__subtitle")
                loc_el = card.select_one("span.job-search-card__location")
                link_el = card.select_one("a.base-card__full-link")

                if not title_el or not link_el or not link_el.get("href"):
                    continue

                title = clean_text(title_el.get_text())
                company = clean_text(company_el.get_text()) if company_el else "Company on LinkedIn"
                job_loc = clean_text(loc_el.get_text()) if loc_el else location
                href = link_el["href"].split("?")[0].strip()

                actual_cat = "internship" if "intern" in title.lower() or cat == "internship" else "job"
                results.append(
                    Opportunity(
                        title=title,
                        category=actual_cat,
                        organization=company,
                        url=href,
                        summary=f"Listed on LinkedIn · Location: {job_loc} · Tailored for {profile.qualification} ({profile.current_stage}).",
                        eligibility_tags=[profile.qualification, job_loc, "LinkedIn"] + profile.skills[:2],
                        source_name=self.name,
                    )
                )
        except Exception as exc:
            print(f"[{self.name}] Guest search note: {exc}")

        return results


class MultiPortalWebIndexScraper(BaseOpportunityScraper):
    """
    Surfs Wellfound, Internshala, Unstop, and Buddy4Study via search index queries
    so login-walled portals still return live direct links matched to qualification.
    """

    name = "Multi-Portal Index (Wellfound / Internshala / Unstop)"

    PORTALS_BY_CATEGORY = {
        "internship": [
            ("Wellfound", "site:wellfound.com/jobs"),
            ("Internshala", "site:internshala.com/internship"),
            ("Unstop", "site:unstop.com/internships"),
        ],
        "job": [
            ("Wellfound", "site:wellfound.com/jobs"),
            ("LinkedIn", "site:linkedin.com/jobs/view"),
            ("Unstop", "site:unstop.com/jobs"),
        ],
        "scholarship": [
            ("Buddy4Study", "site:buddy4study.com/scholarship"),
            ("Unstop", "site:unstop.com/scholarships"),
        ],
        "course": [
            ("Coursera", "site:coursera.org/learn"),
            ("NPTEL / Swayam", "site:swayam.gov.in"),
        ],
    }

    def scrape(self, profile: UserProfile, category: str) -> List[Opportunity]:
        cat = category.lower()
        portals = self.PORTALS_BY_CATEGORY.get(cat, [])
        if not portals:
            return []

        results: List[Opportunity] = []
        skill_str = " ".join(profile.skills[:2])
        loc_str = profile.location or ""

        for portal_name, site_filter in portals:
            query = f"{site_filter} {profile.qualification} {skill_str} {cat} {loc_str}".strip()
            hits = self._query_bing_rss(query, limit=5)
            for hit in hits:
                results.append(
                    Opportunity(
                        title=hit["title"],
                        category=cat,
                        organization=portal_name,
                        url=hit["url"],
                        summary=hit["summary"] or f"{portal_name} listing matching {profile.qualification}.",
                        eligibility_tags=[portal_name, profile.qualification] + profile.skills[:2],
                        source_name=portal_name,
                    )
                )

        return results

    def _query_bing_rss(self, query: str, limit: int = 5) -> List[dict]:
        """Bing RSS search endpoint reliably returns clean titles, URLs, and snippets without CAPTCHAs."""
        url = f"https://www.bing.com/search?format=rss&q={quote_plus(query)}"
        items: List[dict] = []
        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=12.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "xml")
            for item in soup.find_all("item")[:limit]:
                title = clean_text(item.find("title").text if item.find("title") else "")
                link = (item.find("link").text if item.find("link") else "").strip()
                desc = clean_text(item.find("description").text if item.find("description") else "")
                if title and link.startswith("http"):
                    items.append({"title": title, "url": link, "summary": desc[:260]})
        except Exception as exc:
            print(f"[{self.name}] Search index warning: {exc}")

        return items


class RemoteOKOpportunityScraper(BaseOpportunityScraper):
    """Fetches remote tech jobs and internships from RemoteOK's public JSON API."""

    name = "RemoteOK"

    def scrape(self, profile: UserProfile, category: str) -> List[Opportunity]:
        cat = category.lower()
        if cat not in {"job", "internship"}:
            return []

        url = "https://remoteok.com/api"
        results: List[Opportunity] = []
        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=12.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()

            for item in data[1:45]:
                title = clean_text(item.get("position"))
                company = clean_text(item.get("company")) or "Company"
                apply_url = (item.get("url") or "").strip()
                tags = [clean_text(str(t)) for t in (item.get("tags") or []) if t]
                desc = clean_text(item.get("description"))

                if not title or not apply_url:
                    continue

                is_intern = "intern" in title.lower() or any("intern" in t.lower() for t in tags)
                actual_category = "internship" if is_intern else "job"
                if actual_category != cat:
                    continue

                results.append(
                    Opportunity(
                        title=title,
                        category=actual_category,
                        organization=company,
                        url=apply_url,
                        summary=desc[:260] + ("..." if len(desc) > 260 else ""),
                        eligibility_tags=tags[:6] or ["Remote", "Tech"],
                        source_name=self.name,
                    )
                )
        except Exception as exc:
            print(f"[{self.name}] Error fetching opportunities: {exc}")

        return results


class RemotiveOpportunityScraper(BaseOpportunityScraper):
    """Fetches software & tech roles from Remotive's public API."""

    name = "Remotive"

    def scrape(self, profile: UserProfile, category: str) -> List[Opportunity]:
        cat = category.lower()
        if cat not in {"job", "internship"}:
            return []

        search_term = profile.skills[0] if profile.skills else "software"
        url = f"https://remotive.com/api/remote-jobs?search={quote_plus(search_term)}&limit=20"
        results: List[Opportunity] = []

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=12.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                jobs = resp.json().get("jobs", [])

            for job in jobs:
                title = clean_text(job.get("title"))
                company = clean_text(job.get("company_name")) or "Company"
                apply_url = (job.get("url") or "").strip()
                tags = [clean_text(str(t)) for t in (job.get("tags") or []) if t]
                desc = clean_text(job.get("description"))
                job_type = (job.get("job_type") or "").lower()

                is_intern = "intern" in title.lower() or "intern" in job_type
                actual_category = "internship" if is_intern else "job"
                if actual_category != cat:
                    continue

                results.append(
                    Opportunity(
                        title=title,
                        category=actual_category,
                        organization=company,
                        url=apply_url,
                        summary=desc[:260] + ("..." if len(desc) > 260 else ""),
                        eligibility_tags=tags[:6] or [profile.qualification],
                        source_name=self.name,
                    )
                )
        except Exception as exc:
            print(f"[{self.name}] Error fetching Remotive jobs: {exc}")

        return results


class CourseCatalogScraper(BaseOpportunityScraper):
    """Fetches courses aligned with user qualification/skills from Coursera's catalog endpoint."""

    name = "Coursera Catalog"

    def scrape(self, profile: UserProfile, category: str) -> List[Opportunity]:
        if category.lower() != "course":
            return []

        query_terms = " ".join((profile.skills[:2] + profile.interests[:2]) or [profile.qualification])
        url = (
            "https://api.coursera.org/api/courses.v1"
            f"?q=search&query={quote_plus(query_terms)}&limit=12&fields=slug,name,description"
        )
        results: List[Opportunity] = []

        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=12.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                elements = resp.json().get("elements", [])

            for item in elements:
                name = clean_text(item.get("name"))
                slug = (item.get("slug") or "").strip()
                desc = clean_text(item.get("description"))
                if not name or not slug:
                    continue

                results.append(
                    Opportunity(
                        title=name,
                        category="course",
                        organization="Coursera",
                        url=f"https://www.coursera.org/learn/{slug}",
                        summary=desc[:260] + ("..." if len(desc) > 260 else ""),
                        eligibility_tags=[profile.qualification] + profile.skills[:3],
                        source_name=self.name,
                    )
                )
        except Exception as exc:
            print(f"[{self.name}] Error fetching courses: {exc}")

        return results


class ScholarshipDirectoryScraper(BaseOpportunityScraper):
    """Combines Scholars4Dev RSS feed items with verified student scholarship portals."""

    name = "Scholarships Feed"

    def scrape(self, profile: UserProfile, category: str) -> List[Opportunity]:
        if category.lower() != "scholarship":
            return []

        results: List[Opportunity] = []
        rss_url = "https://www.scholars4dev.com/feed/"
        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=12.0, follow_redirects=True) as client:
                resp = client.get(rss_url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "xml")
            for item in soup.find_all("item")[:12]:
                title = clean_text(item.find("title").text if item.find("title") else "")
                link = (item.find("link").text if item.find("link") else "").strip()
                desc = clean_text(item.find("description").text if item.find("description") else "")
                cats = [clean_text(c.text) for c in item.find_all("category") if c.text]

                if title and link:
                    results.append(
                        Opportunity(
                            title=title,
                            category="scholarship",
                            organization="Scholars4Dev",
                            url=link,
                            summary=desc[:260] + ("..." if len(desc) > 260 else ""),
                            eligibility_tags=cats[:5] or [profile.qualification],
                            source_name=self.name,
                        )
                    )
        except Exception as exc:
            print(f"[{self.name}] RSS fetch note: {exc}")

        verified_portals = [
            Opportunity(
                title="National Scholarship Portal (NSP) – Central & UGC Schemes",
                category="scholarship",
                organization="Government of India",
                url="https://scholarships.gov.in/",
                summary="Official portal for AICTE Pragati, Saksham, Post-Matric, and Merit-cum-Means scholarships for UG/PG students.",
                eligibility_tags=["B.Tech", "Undergraduate", "12th Pass", "India", "AICTE"],
                source_name="Verified Portal",
            ),
            Opportunity(
                title="AICTE Swanath & Pragati Scholarship Schemes",
                category="scholarship",
                organization="AICTE",
                url="https://www.aicte-india.org/schemes/students-development-schemes",
                summary="Financial support scholarships for students enrolled in AICTE-approved technical degree and diploma programs.",
                eligibility_tags=["B.Tech", "Undergraduate", "Engineering", "AICTE", "India"],
                source_name="Verified Portal",
            ),
            Opportunity(
                title="Buddy4Study – Curated Undergraduate & STEM Scholarships",
                category="scholarship",
                organization="Buddy4Study",
                url="https://www.buddy4study.com/scholarships",
                summary="Aggregates corporate CSR, merit-based, and STEM scholarships for school, undergraduate, and postgraduate students.",
                eligibility_tags=["B.Tech", "B.Sc", "12th Pass", "Undergraduate", "Postgraduate", "STEM"],
                source_name="Verified Portal",
            ),
        ]
        results.extend(verified_portals)
        return results


class PlaywrightPageScraper:
    """Optional headless browser scraper for dynamic/JS-rendered web pages."""

    name = "Playwright Headless Browser"

    def fetch_rendered_links(self, page_url: str, keyword: str = "", limit: int = 10) -> List[dict]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return []

        items: List[dict] = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=DEFAULT_HEADERS["User-Agent"])
                page.goto(page_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(1500)

                anchors = page.query_selector_all("a[href]")
                for a in anchors:
                    text = clean_text(a.inner_text())
                    href = (a.get_attribute("href") or "").strip()
                    if not text or len(text) < 8 or not href.startswith("http"):
                        continue
                    if keyword and keyword.lower() not in f"{text} {href}".lower():
                        continue
                    items.append({"title": text, "url": href})
                    if len(items) >= limit:
                        break

                browser.close()
        except Exception as exc:
            print(f"[{self.name}] Headless scrape note: {exc}")

        return items


class MultiSourceResearchScraper(BaseResearchScraper):
    """Fetches academic papers from both arXiv and OpenAlex APIs."""

    name = "arXiv + OpenAlex"

    def search(self, topic: str, limit: int = 8) -> List[ResearchResource]:
        half = max(2, limit // 2)
        arxiv_items = self._fetch_arxiv(topic, max_results=half)
        openalex_items = self._fetch_openalex(topic, max_results=max(1, limit - len(arxiv_items)))
        return (arxiv_items + openalex_items)[:limit]

    def _fetch_arxiv(self, topic: str, max_results: int = 4) -> List[ResearchResource]:
        url = (
            "https://export.arxiv.org/api/query?"
            f"search_query=all:{quote_plus(topic)}&start=0&max_results={max_results}"
        )
        items: List[ResearchResource] = []
        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=12.0) as client:
                resp = client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "xml")
            for entry in soup.find_all("entry"):
                title = clean_text(entry.find("title").text if entry.find("title") else "")
                link_el = entry.find("id")
                href = link_el.text.strip() if link_el else ""
                summary_el = entry.find("summary")
                snippet = clean_text(summary_el.text if summary_el else "")[:320]
                published_el = entry.find("published")
                published = published_el.text[:10] if published_el else None
                year = published[:4] if published else None
                author_names = [
                    clean_text(a.find("name").text)
                    for a in entry.find_all("author")[:4]
                    if a.find("name")
                ]
                arxiv_id = href.split("/abs/")[-1] if "/abs/" in href else None

                if title and href:
                    items.append(
                        ResearchResource(
                            title=title,
                            url=href,
                            snippet=snippet + ("..." if len(snippet) >= 320 else ""),
                            source_name="arXiv",
                            published_info=f"Published: {published}" if published else None,
                            authors=", ".join(author_names) if author_names else None,
                            year=year,
                            venue_or_id=f"arXiv:{arxiv_id}" if arxiv_id else "arXiv",
                        )
                    )
        except Exception as exc:
            print(f"[arXiv] Error fetching feed: {exc}")

        return items

    def _fetch_openalex(self, topic: str, max_results: int = 4) -> List[ResearchResource]:
        url = f"https://api.openalex.org/works?search={quote_plus(topic)}&per-page={max_results}"
        items: List[ResearchResource] = []
        try:
            with httpx.Client(headers=DEFAULT_HEADERS, timeout=12.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                results = resp.json().get("results", [])

            for work in results:
                title = clean_text(work.get("title"))
                doi = work.get("doi")
                landing = (work.get("primary_location") or {}).get("landing_page_url")
                href = doi or landing or work.get("id") or ""
                pub_year = work.get("publication_year")
                cited_by = work.get("cited_by_count", 0)
                authorships = work.get("authorships") or []
                authors = ", ".join(
                    clean_text((a.get("author") or {}).get("display_name"))
                    for a in authorships[:4]
                    if (a.get("author") or {}).get("display_name")
                )

                abstract = self._reconstruct_abstract(work.get("abstract_inverted_index"))
                snippet = (
                    abstract[:320] + ("..." if len(abstract) > 320 else "")
                    if abstract
                    else f"Scholarly work ({pub_year}) with {cited_by} citations."
                )

                if title and href:
                    items.append(
                        ResearchResource(
                            title=title,
                            url=href,
                            snippet=snippet,
                            source_name="OpenAlex",
                            published_info=f"Year: {pub_year} | Citations: {cited_by}" if pub_year else None,
                            authors=authors or None,
                            year=str(pub_year) if pub_year else None,
                            venue_or_id="OpenAlex",
                        )
                    )
        except Exception as exc:
            print(f"[OpenAlex] Error fetching works: {exc}")

        return items

    @staticmethod
    def _reconstruct_abstract(inverted_index: Optional[dict]) -> str:
        if not inverted_index or not isinstance(inverted_index, dict):
            return ""
        pos_map = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                pos_map[pos] = word
        return " ".join(pos_map[i] for i in sorted(pos_map))