"""Read-only content report queries for the DuckDB analytics layer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.services._duckdb_sql import LATEST_ANALYSIS_CTE
from app.services.scoring_engine import CONFIG as SCORING_CONFIG


class ReportsMixin:
    def query_content_for_report(self, hours: int = 48) -> list[dict[str, Any]]:
        conn = self._get_conn()
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        results = conn.execute(f"""
            WITH {LATEST_ANALYSIS_CTE},
            {self._ignored_content_cte(conn)}
            SELECT c.id, c.title, c.url, c.category, c.source_name, a.summary,
                   a.creator_score, a.viral_score, a.quality_score, a.risk_score,
                   a.recommended_reason
            FROM oltp_db.content_items c
            LEFT JOIN latest_analysis a ON a.content_id = c.id
            LEFT JOIN ignored_content ignored ON ignored.content_id = c.id
            WHERE c.crawled_at >= '{cutoff}'
              AND ignored.content_id IS NULL
              AND a.curation_score IS NOT NULL
            ORDER BY (COALESCE(a.creator_score, 0) + COALESCE(a.viral_score, 0)) DESC
            LIMIT 100
        """).fetchall()
        return [
            {
                "id": row[0],
                "title": row[1],
                "url": row[2],
                "category": row[3],
                "source_name": row[4],
                "summary": row[5] or "",
                "creator_score": float(row[6]) if row[6] else 0,
                "viral_score": float(row[7]) if row[7] else 0,
                "quality_score": float(row[8]) if row[8] else 0,
                "risk_score": float(row[9]) if row[9] else 0,
                "recommended_reason": row[10] or "",
            }
            for row in results
        ]

    def query_content_for_weekly(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        conn = self._get_conn()
        feedback_min = float(SCORING_CONFIG["feedback_score_min"])
        feedback_max = float(SCORING_CONFIG["feedback_score_max"])
        feedback_weight = float(SCORING_CONFIG["w_feedback"])
        results = conn.execute(f"""
            WITH {LATEST_ANALYSIS_CTE},
            {self._feedback_scores_cte(conn)},
            {self._ignored_content_cte(conn)}
            SELECT c.id, c.title, c.url, c.category, c.source_name, c.platform,
                   c.crawled_at, a.summary, a.creator_score, a.viral_score,
                   a.quality_score, a.hot_score, a.freshness_score, a.risk_score,
                   a.curation_score, a.info_density, a.actionability, a.source_weight,
                   a.tags, a.recommendation, a.recommended_reason,
                   COALESCE(s.weight, 3) AS source_weight_db,
                   COALESCE(f.feedback_score, 0) AS feedback_score,
                   COALESCE(a.curation_score, 0)
                       + LEAST({feedback_max}, GREATEST({feedback_min}, COALESCE(f.feedback_score, 0)))
                       * {feedback_weight} AS adjusted_score
            FROM oltp_db.content_items c
            LEFT JOIN latest_analysis a ON a.content_id = c.id
            LEFT JOIN oltp_db.sources s ON s.id = c.source_id
            LEFT JOIN feedback_scores f ON f.content_id = c.id
            LEFT JOIN ignored_content ignored ON ignored.content_id = c.id
            WHERE CAST(c.crawled_at AS DATE) >= DATE '{start_date}'
              AND CAST(c.crawled_at AS DATE) <= DATE '{end_date}'
              AND ignored.content_id IS NULL
              AND a.curation_score IS NOT NULL
            ORDER BY adjusted_score DESC, COALESCE(a.creator_score, 0) DESC
        """).fetchall()
        return [
            {
                "id": row[0],
                "title": row[1],
                "url": row[2] or "",
                "category": row[3] or "未分类",
                "source_name": row[4] or "",
                "platform": row[5] or "",
                "crawled_at": row[6].isoformat() if hasattr(row[6], "isoformat") else row[6],
                "summary": row[7] or "",
                "creator_score": float(row[8]) if row[8] else 0,
                "viral_score": float(row[9]) if row[9] else 0,
                "quality_score": float(row[10]) if row[10] else 0,
                "hot_score": float(row[11]) if row[11] else 0,
                "freshness_score": float(row[12]) if row[12] else 0,
                "risk_score": float(row[13]) if row[13] else 0,
                "curation_score": float(row[14]) if row[14] else 0,
                "info_density": float(row[15]) if row[15] else 50,
                "actionability": float(row[16]) if row[16] else 50,
                "source_weight": float(row[17]) if row[17] else 50,
                "tags": row[18] or [],
                "recommendation": row[19] or "",
                "recommended_reason": row[20] or "",
                "source_weight_db": int(row[21]) if row[21] else 3,
                "feedback_score": float(row[22]) if row[22] else 0,
                "adjusted_score": round(float(row[23] or 0), 1),
            }
            for row in results
        ]
