import pandas as pd
import streamlit as st

from citations import format_apa, format_bibtex, format_ieee
from database import ScholarScoutDB
from engine import ScholarScoutEngine
from models import UserProfile
from scrapers import (
    CourseCatalogScraper,
    LinkedInGuestScraper,
    MultiPortalWebIndexScraper,
    MultiSourceResearchScraper,
    PlaywrightPageScraper,
    RemoteOKOpportunityScraper,
    RemotiveOpportunityScraper,
    ScholarshipDirectoryScraper,
)

st.set_page_config(
    page_title="ScholarScout AI",
    page_icon="🎓",
    layout="wide",
)

st.markdown(
    """
    <style>
    .opp-card {
        padding: 1.05rem 1.2rem;
        border-radius: 10px;
        border: 1px solid rgba(128, 128, 128, 0.25);
        margin-bottom: 0.85rem;
        background-color: rgba(255, 255, 255, 0.02);
    }
    .badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        font-size: 0.74rem;
        font-weight: 600;
        border-radius: 999px;
        margin-right: 0.4rem;
        text-transform: uppercase;
    }
    .badge-internship { background: #1e3a8a; color: #dbeafe; }
    .badge-job { background: #065f46; color: #d1fae5; }
    .badge-scholarship { background: #78350f; color: #fef3c7; }
    .badge-course { background: #4c1d95; color: #ede9fe; }
    .badge-score { background: #374151; color: #f9fafb; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_engine() -> ScholarScoutEngine:
    return ScholarScoutEngine(
        opportunity_scrapers=[
            LinkedInGuestScraper(),
            MultiPortalWebIndexScraper(),
            ScholarshipDirectoryScraper(),
            RemotiveOpportunityScraper(),
            RemoteOKOpportunityScraper(),
            CourseCatalogScraper(),
        ],
        research_scrapers=[MultiSourceResearchScraper()],
    )


@st.cache_resource
def get_db() -> ScholarScoutDB:
    return ScholarScoutDB()


@st.cache_data(ttl=600, show_spinner=False)
def cached_opportunities(
    qualification: str,
    education_level: str,
    current_stage: str,
    grad_year: int | None,
    skills_tuple: tuple,
    interests_tuple: tuple,
    location: str,
    categories_tuple: tuple,
    strict_eligibility: bool,
):
    profile = UserProfile(
        qualification=qualification,
        education_level=education_level,
        current_stage=current_stage,
        graduation_year=grad_year,
        skills=list(skills_tuple),
        interests=list(interests_tuple),
        location=location or None,
        strict_eligibility=strict_eligibility,
    )
    return get_engine().find_opportunities(profile=profile, categories=list(categories_tuple))


@st.cache_data(ttl=600, show_spinner=False)
def cached_research(topic: str, limit: int):
    return get_engine().curate_research(topic=topic, limit=limit)


db = get_db()

# --- Header ---
st.title("🎓 ScholarScout AI")
st.caption(
    "Surfs LinkedIn, Wellfound, Internshala, Unstop, Coursera & academic repositories to match opportunities to your exact qualification."
)

# --- Sidebar: User Qualification & Profile ---
with st.sidebar:
    st.header("👤 Your Qualification & Profile")
    education_level = st.selectbox(
        "Education Level",
        options=[
            "High School / 12th",
            "Undergraduate (B.Tech/B.Sc/B.A)",
            "Postgraduate (M.Tech/M.Sc/MBA)",
            "PhD / Doctoral",
        ],
        index=1,
    )
    qualification = st.text_input(
        "Specific Qualification / Branch",
        value="B.Tech Computer Science",
        placeholder="e.g., B.Tech CSE, B.Com, 12th Science, MBA",
    )
    current_stage = st.selectbox(
        "Current Stage",
        options=["1st Year", "2nd Year", "3rd Year", "4th Year", "Final Year", "Fresher / Graduate"],
        index=3,
    )
    grad_year = st.number_input(
        "Graduation Year",
        min_value=2020,
        max_value=2035,
        value=2027,
        step=1,
    )
    skills_raw = st.text_input(
        "Skills (comma-separated)",
        value="Python, React, Machine Learning",
    )
    interests_raw = st.text_input(
        "Interests (comma-separated)",
        value="Software Engineering, AI, Web Development",
    )
    location = st.text_input("Location", value="India")

    strict_eligibility = st.toggle(
        "Strict Qualification & Seniority Filter",
        value=True,
        help="Automatically hides senior/executive roles and degree-ineligible listings.",
    )

    selected_categories = st.multiselect(
        "Opportunity Categories",
        options=["scholarship", "internship", "course", "job"],
        default=["scholarship", "internship", "course", "job"],
        format_func=lambda x: x.capitalize(),
    )

    scout_clicked = st.button("🚀 Scout Eligible Opportunities", type="primary", use_container_width=True)

skills_list = [s.strip() for s in skills_raw.split(",") if s.strip()]
interests_list = [i.strip() for i in interests_raw.split(",") if i.strip()]

saved_opp_urls = {row["url"] for row in db.list_saved_opportunities()}
saved_paper_urls = {row["url"] for row in db.list_saved_papers()}

tab_opps, tab_research, tab_saved, tab_history = st.tabs(
    [
        "🎯 Eligible Opportunities",
        "📚 Research Paper Curator",
        "⭐ Saved Items",
        "🕒 Search History",
    ]
)

# ==========================================
# TAB 1: OPPORTUNITY DISCOVERY
# ==========================================
with tab_opps:
    if not selected_categories:
        st.warning("Select at least one category in the sidebar.")
    else:
        with st.spinner(
            f"Surfing LinkedIn, Wellfound, Internshala, Unstop & scholarship feeds for {qualification}..."
        ):
            opportunities = cached_opportunities(
                qualification=qualification,
                education_level=education_level,
                current_stage=current_stage,
                grad_year=int(grad_year),
                skills_tuple=tuple(skills_list),
                interests_tuple=tuple(interests_list),
                location=location,
                categories_tuple=tuple(selected_categories),
                strict_eligibility=strict_eligibility,
            )

        if scout_clicked:
            db.log_search(
                search_type="opportunities",
                query_text=f"{education_level} | {qualification} ({current_stage})",
                result_count=len(opportunities),
            )

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Eligible Matches", len(opportunities))
        c2.metric("Scholarships", sum(1 for o in opportunities if o.category == "scholarship"))
        c3.metric("Internships", sum(1 for o in opportunities if o.category == "internship"))
        c4.metric("Courses", sum(1 for o in opportunities if o.category == "course"))
        c5.metric("Jobs", sum(1 for o in opportunities if o.category == "job"))

        st.divider()

        all_sources = sorted({o.source_name for o in opportunities})
        f1, f2, f3, f4 = st.columns([2, 2, 2, 1])
        with f1:
            cat_filter = st.selectbox(
                "Category",
                options=["all"] + selected_categories,
                format_func=lambda x: "All Categories" if x == "all" else x.capitalize(),
            )
        with f2:
            source_filter = st.selectbox(
                "Portal / Source",
                options=["all"] + all_sources,
                format_func=lambda x: "All Portals" if x == "all" else x,
            )
        with f3:
            kw_filter = st.text_input("Keyword Filter", placeholder="e.g., Wellfound, React, AICTE...")
        with f4:
            min_score = st.number_input("Min Score", min_value=0.0, value=0.0, step=0.5)

        filtered = [
            o
            for o in opportunities
            if (cat_filter == "all" or o.category == cat_filter)
            and (source_filter == "all" or o.source_name == source_filter)
            and o.match_score >= min_score
            and (
                not kw_filter
                or kw_filter.lower() in f"{o.title} {o.organization} {o.summary} {o.source_name}".lower()
            )
        ]

        if not filtered:
            st.info(
                "No opportunities matched your current filters. Try unchecking 'Strict Qualification & Seniority Filter' or broadening your skills."
            )
        else:
            df_export = pd.DataFrame(
                [
                    {
                        "Category": o.category.capitalize(),
                        "Title": o.title,
                        "Organization": o.organization,
                        "Portal": o.source_name,
                        "Match Score": o.match_score,
                        "Eligibility Match": o.eligibility_note,
                        "URL": o.url,
                    }
                    for o in filtered
                ]
            )
            st.download_button(
                "⬇️ Export Filtered Opportunities (CSV)",
                data=df_export.to_csv(index=False).encode("utf-8"),
                file_name="scholarscout_eligible_opportunities.csv",
                mime="text/csv",
            )

            for idx, opp in enumerate(filtered):
                badge_class = f"badge-{opp.category.lower()}"
                tags_display = " · ".join(opp.eligibility_tags[:5]) if opp.eligibility_tags else "General"
                is_saved = opp.url in saved_opp_urls

                col_card, col_act = st.columns([6, 1])
                with col_card:
                    st.markdown(
                        f"""
                        <div class="opp-card">
                            <div>
                                <span class="badge {badge_class}">{opp.category}</span>
                                <span class="badge badge-score">Score: {opp.match_score}</span>
                                <small style="opacity:0.85;"><strong>Portal:</strong> {opp.source_name}</small>
                            </div>
                            <h4 style="margin: 0.45rem 0 0.25rem 0;">
                                <a href="{opp.url}" target="_blank" style="text-decoration:none;">{opp.title}</a>
                            </h4>
                            <div style="font-size:0.88rem; opacity:0.9; margin-bottom:0.35rem;">
                                <strong>{opp.organization}</strong> &nbsp;|&nbsp; <em>{opp.eligibility_note}</em>
                            </div>
                            <div style="font-size:0.82rem; opacity:0.75; margin-bottom:0.45rem;">
                                Tags: {tags_display}
                            </div>
                            <p style="font-size:0.92rem; margin-bottom:0.4rem;">{opp.summary}</p>
                            <a href="{opp.url}" target="_blank">Open on {opp.source_name} ↗</a>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with col_act:
                    if is_saved:
                        if st.button("Saved ✓", key=f"unsave_opp_{idx}_{opp.category}"):
                            db.remove_opportunity(opp.url)
                            st.rerun()
                    else:
                        if st.button("Bookmark", key=f"save_opp_{idx}_{opp.category}"):
                            db.save_opportunity(
                                {
                                    "title": opp.title,
                                    "category": opp.category,
                                    "organization": opp.organization,
                                    "url": opp.url,
                                    "summary": opp.summary,
                                    "source_name": opp.source_name,
                                    "match_score": opp.match_score,
                                }
                            )
                            st.rerun()

        with st.expander("🌐 Custom / Dynamic Page Link Extractor (Playwright Headless Browser)"):
            custom_url = st.text_input("Target Webpage URL", placeholder="https://wellfound.com/jobs")
            custom_kw = st.text_input("Optional Keyword", placeholder="e.g., intern, python, frontend")
            if st.button("Extract Links") and custom_url.strip():
                pw = PlaywrightPageScraper()
                links = pw.fetch_rendered_links(custom_url.strip(), keyword=custom_kw.strip(), limit=15)
                if not links:
                    st.info(
                        "No links returned (site may require login or Playwright Chromium isn't installed yet). "
                        "Install headless Chromium via: `pip install playwright && playwright install chromium`."
                    )
                else:
                    for item in links:
                        st.markdown(f"- [{item['title']}]({item['url']})")

# ==========================================
# TAB 2: RESEARCH PAPER CURATOR
# ==========================================
with tab_research:
    st.subheader("Research Paper & Literature Curator")
    r1, r2 = st.columns([4, 1])
    with r1:
        topic_input = st.text_input(
            "Research Topic / Keywords",
            value="automated web scraping and information retrieval for academic search",
        )
    with r2:
        paper_limit = st.slider("Papers to Fetch", min_value=4, max_value=20, value=8, step=2)

    curate_clicked = st.button("📖 Curate Research Content", type="primary")

    if topic_input.strip():
        with st.spinner("Querying arXiv and OpenAlex repositories..."):
            papers = cached_research(topic=topic_input.strip(), limit=paper_limit)

        if curate_clicked:
            db.log_search(
                search_type="research",
                query_text=topic_input.strip(),
                result_count=len(papers),
            )

        if not papers:
            st.warning("No research papers found. Try broader or different keywords.")
        else:
            st.success(f"Curated {len(papers)} academic resources for your topic.")

            md_lines = [f"# Curated Research References: {topic_input.strip()}\n"]
            for i, p in enumerate(papers, start=1):
                md_lines.append(
                    f"{i}. **{p.title}** ({p.source_name})\n"
                    f"   - Authors: {p.authors or 'N/A'}\n"
                    f"   - Info: {p.published_info or 'N/A'}\n"
                    f"   - URL: {p.url}\n"
                    f"   - Summary: {p.snippet}\n"
                )
            st.download_button(
                "⬇️ Download Literature Notes (.md)",
                data="\n".join(md_lines).encode("utf-8"),
                file_name="scholarscout_literature_review.md",
                mime="text/markdown",
            )

            for idx, paper in enumerate(papers):
                is_paper_saved = paper.url in saved_paper_urls
                with st.container(border=True):
                    top_l, top_r = st.columns([6, 1])
                    with top_l:
                        st.markdown(f"### {idx + 1}. [{paper.title}]({paper.url})")
                        meta = [f"**Source:** {paper.source_name}"]
                        if paper.authors:
                            meta.append(f"**Authors:** {paper.authors}")
                        if paper.published_info:
                            meta.append(f"**{paper.published_info}**")
                        st.caption("  |  ".join(meta))
                    with top_r:
                        if is_paper_saved:
                            if st.button("Saved ✓", key=f"unsave_paper_{idx}"):
                                db.remove_paper(paper.url)
                                st.rerun()
                        else:
                            if st.button("Save Paper", key=f"save_paper_{idx}"):
                                db.save_paper(
                                    {
                                        "title": paper.title,
                                        "url": paper.url,
                                        "snippet": paper.snippet,
                                        "source_name": paper.source_name,
                                        "authors": paper.authors or "",
                                        "published_info": paper.published_info or "",
                                        "year": paper.year or "",
                                    }
                                )
                                st.rerun()

                    st.write(paper.snippet)
                    st.markdown(f"[Open Full Paper / Source ↗]({paper.url})")

                    with st.expander("📋 Citations (APA / IEEE / BibTeX)"):
                        c_apa, c_ieee, c_bib = st.tabs(["APA", "IEEE", "BibTeX"])
                        with c_apa:
                            st.code(format_apa(paper), language="text")
                        with c_ieee:
                            st.code(format_ieee(paper), language="text")
                        with c_bib:
                            st.code(format_bibtex(paper), language="bibtex")

# ==========================================
# TAB 3: SAVED ITEMS
# ==========================================
with tab_saved:
    s_left, s_right = st.columns(2)
    with s_left:
        st.subheader("⭐ Bookmarked Opportunities")
        saved_opps = db.list_saved_opportunities()
        if not saved_opps:
            st.info("No bookmarked opportunities yet.")
        else:
            for i, row in enumerate(saved_opps):
                with st.container(border=True):
                    st.markdown(f"**[{row['title']}]({row['url']})**")
                    st.caption(
                        f"{row['category'].upper()} · {row['organization']} · Score: {row['match_score']}"
                    )
                    st.write(row["summary"])
                    if st.button("Remove Bookmark", key=f"del_saved_opp_{i}"):
                        db.remove_opportunity(row["url"])
                        st.rerun()

    with s_right:
        st.subheader("📚 Saved Research Papers")
        saved_papers = db.list_saved_papers()
        if not saved_papers:
            st.info("No saved research papers yet.")
        else:
            for i, row in enumerate(saved_papers):
                with st.container(border=True):
                    st.markdown(f"**[{row['title']}]({row['url']})**")
                    st.caption(f"{row['source_name']} · {row['authors'] or 'N/A'}")
                    st.write(row["snippet"])
                    if st.button("Remove Paper", key=f"del_saved_paper_{i}"):
                        db.remove_paper(row["url"])
                        st.rerun()

# ==========================================
# TAB 4: SEARCH HISTORY
# ==========================================
with tab_history:
    st.subheader("🕒 Recent Scout & Research Queries")
    history_rows = db.list_history(limit=30)
    if not history_rows:
        st.info("Click 'Scout Eligible Opportunities' or 'Curate Research Content' to log searches.")
    else:
        st.dataframe(pd.DataFrame(history_rows), use_container_width=True, hide_index=True)