from pathlib import Path
import sqlite3
from typing import Any, Dict, List

DB_PATH = Path(__file__).resolve().parent / "scholarscout.db"


class ScholarScoutDB:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL,
                    organization TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    summary TEXT,
                    source_name TEXT,
                    match_score REAL DEFAULT 0.0,
                    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_papers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    snippet TEXT,
                    source_name TEXT,
                    authors TEXT,
                    published_info TEXT,
                    year TEXT,
                    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_type TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    result_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save_opportunity(self, opp: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO saved_opportunities
                    (title, category, organization, url, summary, source_name, match_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    opp["title"],
                    opp["category"],
                    opp["organization"],
                    opp["url"],
                    opp.get("summary", ""),
                    opp.get("source_name", ""),
                    float(opp.get("match_score", 0.0)),
                ),
            )

    def remove_opportunity(self, url: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM saved_opportunities WHERE url = ?", (url,))

    def list_saved_opportunities(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM saved_opportunities ORDER BY saved_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def save_paper(self, paper: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO saved_papers
                    (title, url, snippet, source_name, authors, published_info, year)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    paper["title"],
                    paper["url"],
                    paper.get("snippet", ""),
                    paper.get("source_name", ""),
                    paper.get("authors", ""),
                    paper.get("published_info", ""),
                    paper.get("year", ""),
                ),
            )

    def remove_paper(self, url: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM saved_papers WHERE url = ?", (url,))

    def list_saved_papers(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM saved_papers ORDER BY saved_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def log_search(self, search_type: str, query_text: str, result_count: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO search_history (search_type, query_text, result_count)
                VALUES (?, ?, ?)
                """,
                (search_type, query_text, result_count),
            )

    def list_history(self, limit: int = 25) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM search_history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]