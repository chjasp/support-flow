from __future__ import annotations

from typing import Any, Dict, List

import logging
from google.cloud import bigquery
from pydantic import BaseModel, Field

from .base import ToolNode

logger = logging.getLogger(__name__)


class _BigQueryArgs(BaseModel):
    sql: str = Field(..., description="Valid BigQuery StandardSQL statement to execute.")
    max_rows: int = Field(
        default=1000,
        description="Maximum number of rows to return (server-side LIMIT).",
    )


class BigQueryNode(ToolNode):
    """PocketFlow-compatible node that executes BigQuery StandardSQL."""

    tool_name = "run_bigquery_sql"
    tool_desc = (
        "Execute StandardSQL against BigQuery and return the first N rows as a list of dicts."
    )
    openai_schema: Dict[str, Any] = _BigQueryArgs.model_json_schema()

    def __init__(self, project: str | None = None):
        self._client = bigquery.Client(project=project)

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def exec(self, sql: str, max_rows: int | None = 1000) -> List[Dict[str, Any]]:  # type: ignore[override]
        query_job = self._client.query(sql)
        # Convert iterator to list of dicts; limit rows to not blow up memory
        rows_iter = query_job.result(max_results=max_rows)
        logger.info("Executing BigQuery SQL via BigQueryNode")
        return [dict(row) for row in rows_iter] 