from citations import format_apa
from database import ScholarScoutDB
from engine import ScholarScoutEngine
from models import UserProfile
from scrapers import (
    CourseCatalogScraper,
    MultiSourceResearchScraper,
    RemoteOKOpportunityScraper,
    RemotiveOpportunityScraper,
    ScholarshipDirectoryScraper,
)


def main() -> None:
    profile = UserProfile(
        qualification="B.Tech Computer Science",
        current_stage="4th Year",
        graduation_year=2027,
        skills=["Python", "React", "Machine Learning"],
        interests=["AI", "Information Retrieval", "Web Scraping"],
        location="India",
    )

    engine = ScholarScoutEngine(
        opportunity_scrapers=[
            ScholarshipDirectoryScraper(),
            RemotiveOpportunityScraper(),
            RemoteOKOpportunityScraper(),
            CourseCatalogScraper(),
        ],
        research_scrapers=[MultiSourceResearchScraper()],
    )
    db = ScholarScoutDB()

    opps = engine.find_opportunities(profile)
    db.log_search("opportunities", profile.qualification, len(opps))
    print(f"Found {len(opps)} opportunities. Top 5:")
    for o in opps[:5]:
        print(f"  [{o.category.upper()}] {o.title} ({o.match_score}) -> {o.url}")

    topic = "automated web scraping and information retrieval for academic search"
    papers = engine.curate_research(topic, limit=4)
    db.log_search("research", topic, len(papers))
    print(f"\nCurated {len(papers)} research papers:")
    for p in papers:
        print(f"  - {p.title} ({p.source_name})")
        print(f"    APA: {format_apa(p)}")


if __name__ == "__main__":
    main()