
import re
from typing import Iterable, List, Optional, Set, Tuple
from models import Opportunity, ResearchResource, UserProfile
from scrapers import BaseOpportunityScraper, BaseResearchScraper


class ScholarScoutEngine:
    SENIOR_KEYWORDS = (
        "senior ",
        "sr.",
        "staff ",
        "principal ",
        "director",
        "vp ",
        "vice president",
        "head of ",
        "lead ",
        "manager",
        "5+ years",
        "7+ years",
        "10+ years",
    )

    POSTGRAD_ONLY_KEYWORDS = (
        "phd only",
        "doctoral fellowship",
        "postdoctoral",
        "postdoc",
        "masters only",
        "m.tech only",
    )

    UNDERGRAD_PLUS_KEYWORDS = (
        "b.tech",
        "b.e",
        "bachelor",
        "undergraduate",
        "m.tech",
        "masters",
        "phd",
        "doctoral",
        "postgraduate",
    )

    def __init__(
        self,
        opportunity_scrapers: List[BaseOpportunityScraper],
        research_scrapers: List[BaseResearchScraper],
    ) -> None:
        self.opportunity_scrapers = opportunity_scrapers
        self.research_scrapers = research_scrapers

    def find_opportunities(
        self,
        profile: UserProfile,
        categories: Optional[Iterable[str]] = None,
    ) -> List[Opportunity]:
        target_categories = (
            [c.lower() for c in categories]
            if categories
            else ["scholarship", "internship", "course", "job"]
        )

        collected: List[Opportunity] = []
        seen_keys: Set[Tuple[str, str]] = set()

        for category in target_categories:
            for scraper in self.opportunity_scrapers:
                raw_opps = scraper.scrape(profile, category)
                for opp in raw_opps:
                    dedup_key = (opp.category.lower(), opp.url.strip())
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    if profile.strict_eligibility and not self._is_eligible(opp, profile):
                        continue

                    score, note = self._score_and_explain(opp, profile)
                    # Exclude completely unrelated listings when strict qualification filtering is enabled
                    if profile.strict_eligibility and score <= 0.0:
                        continue

                    opp.match_score = score
                    opp.eligibility_note = note
                    collected.append(opp)

        collected.sort(key=lambda o: o.match_score, reverse=True)
        return collected

    def curate_research(self, topic: str, limit: int = 8) -> List[ResearchResource]:
        curated: List[ResearchResource] = []
        seen_urls: Set[str] = set()

        for scraper in self.research_scrapers:
            for res in scraper.search(topic, limit=limit):
                clean_url = res.url.strip()
                if clean_url in seen_urls:
                    continue
                seen_urls.add(clean_url)
                curated.append(res)
                if len(curated) >= limit:
                    return curated

        return curated

    def _is_eligible(self, opp: Opportunity, profile: UserProfile) -> bool:
        """Enforce degree-level and seniority eligibility rules based on user qualification."""
        title_lower = opp.title.lower()
        full_text = f"{opp.title} {opp.summary} {' '.join(opp.eligibility_tags)}".lower()
        edu = profile.education_level.lower()
        stage = profile.current_stage.lower()

        # 1. Students / fresh graduates shouldn't be shown Senior/Director roles
        is_student_or_fresher = any(
            k in stage for k in ("1st", "2nd", "3rd", "4th", "final", "student", "fresher")
        )
        if is_student_or_fresher and any(kw in title_lower for kw in self.SENIOR_KEYWORDS):
            return False

        # 2. High school / 12th students shouldn't get degree-required jobs or PG scholarships
        if "12th" in edu or "high school" in edu:
            if opp.category == "job" and any(k in full_text for k in ("b.tech", "bachelor", "graduate required")):
                return False
            if any(kw in full_text for kw in self.POSTGRAD_ONLY_KEYWORDS):
                return False

        # 3. Undergraduate students shouldn't get PhD/Postdoc/Masters-only scholarships
        if "undergraduate" in edu or "b.tech" in profile.qualification.lower():
            if any(kw in full_text for kw in self.POSTGRAD_ONLY_KEYWORDS):
                return False

        return True

    @staticmethod
    def _score_and_explain(opp: Opportunity, profile: UserProfile) -> Tuple[float, str]:
        tags_text = " ".join(opp.eligibility_tags)
        haystack = f"{opp.title} {opp.summary} {tags_text}".lower()
        score = 0.0
        reasons: List[str] = []

        # 1. Qualification & Education Level match
        qual_lower = profile.qualification.strip().lower()
        if qual_lower and qual_lower in haystack:
            score += 4.0
            reasons.append(f"Qualification: {profile.qualification}")
        else:
            q_tokens = [
                tok for tok in re.sub(r"[^a-z0-9\s]", "", qual_lower).split()
                if len(tok) > 2
            ]
            q_hits = [tok for tok in q_tokens if tok in haystack]
            if q_hits:
                score += round(1.2 * len(q_hits), 2)
                reasons.append(f"Qualification match ({', '.join(q_hits)})")

        # Education level keywords (e.g., Undergraduate, B.Tech, 12th)
        edu_tokens = [
            tok for tok in re.sub(r"[^a-z0-9\s]", " ", profile.education_level.lower()).split()
            if len(tok) > 2
        ]
        if any(tok in haystack for tok in edu_tokens):
            score += 1.5
            reasons.append(f"Level: {profile.education_level}")

        # 2. Stage match
        stage_hits = [
            tok for tok in profile.current_stage.lower().split()
            if len(tok) > 2 and tok in haystack
        ]
        if stage_hits:
            score += 0.8
            reasons.append(f"Stage: {profile.current_stage}")

        # 3. Skills match
        matched_skills = [
            s.strip() for s in profile.skills if s.strip() and s.strip().lower() in haystack
        ]
        if matched_skills:
            score += round(2.5 * len(matched_skills), 2)
            reasons.append(f"Skills: {', '.join(matched_skills[:3])}")

        # 4. Interests match
        matched_interests = [
            i.strip() for i in profile.interests if i.strip() and i.strip().lower() in haystack
        ]
        if matched_interests:
            score += round(1.2 * len(matched_interests), 2)
            reasons.append(f"Interests: {', '.join(matched_interests[:3])}")

        # 5. Location match
        if profile.location and profile.location.strip().lower() in haystack:
            score += 1.0
            reasons.append(f"Location: {profile.location}")

        note = " | ".join(reasons) if reasons else "General match"
        return round(score, 2), note