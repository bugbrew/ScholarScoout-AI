import re
from models import ResearchResource


def _slug_id(title: str, year: str) -> str:
    first_word = re.sub(r"[^a-zA-Z0-9]", "", (title.split()[0] if title else "paper")).lower()
    return f"{first_word or 'paper'}{year or '2026'}"


def format_apa(paper: ResearchResource) -> str:
    authors = paper.authors or "Unknown Author"
    year = f"({paper.year})." if paper.year else "(n.d.)."
    return f"{authors} {year} {paper.title}. {paper.source_name}. {paper.url}"


def format_ieee(paper: ResearchResource) -> str:
    authors = paper.authors or "Unknown Author"
    year_part = f", {paper.year}" if paper.year else ""
    return f'{authors}, "{paper.title}," {paper.source_name}{year_part}. [Online]. Available: {paper.url}'


def format_bibtex(paper: ResearchResource) -> str:
    key = _slug_id(paper.title, paper.year or "")
    lines = [
        f"@article{{{key},",
        f"  title   = {{{paper.title}}},",
    ]
    if paper.authors:
        lines.append(f"  author  = {{{paper.authors}}},")
    if paper.year:
        lines.append(f"  year    = {{{paper.year}}},")
    lines.append(f"  note    = {{Source: {paper.source_name}}},")
    lines.append(f"  url     = {{{paper.url}}}")
    lines.append("}")
    return "\n".join(lines)