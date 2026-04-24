"""Normalization worker — converts pending ingested_reports into runs + run_metrics.

Loop behaviour:
  Each iteration claims pending records AND reclaims timed-out processing records,
  then normalizes each one via the adapter REGISTRY.

Claim protocol (atomic via single UPDATE):
  1. SELECT id WHERE status='pending' OR (status='processing' AND claimed_at < now-lease)
  2. UPDATE SET status='processing', claimed_at=now WHERE id=? AND status IN (...)
     Only proceed if rowcount==1 (another worker may have raced us).
  3. On success  → status='processed', processed_at=now
  4. On error, attempt_count < MAX_RETRIES → status='pending', attempt_count+=1
  5. On error, attempt_count >= MAX_RETRIES → status='failed'
  6. No adapter found → status='unsupported'
"""

from __future__ import annotations

import json
import logging
import time

from llm_evalops_platform.adapters import REGISTRY
from llm_evalops_platform.config import settings
from llm_evalops_platform.storage.db import db

logger = logging.getLogger(__name__)


def _claim_next(conn) -> dict | None:
    now = time.time()
    lease_cutoff = now - settings.worker_lease_timeout_secs

    rows = conn.execute(
        """
        SELECT id, app_type, schema_version, run_id, raw_payload, attempt_count, status
        FROM ingested_reports
        WHERE status = 'pending'
           OR (status = 'processing' AND claimed_at < ?)
        ORDER BY received_at ASC
        LIMIT 1
        """,
        (lease_cutoff,),
    ).fetchall()

    for row in rows:
        cursor = conn.execute(
            """
            UPDATE ingested_reports
            SET status = 'processing', claimed_at = ?
            WHERE id = ? AND status IN ('pending', 'processing')
            """,
            (now, row["id"]),
        )
        conn.commit()
        if cursor.rowcount == 1:
            return dict(row)
    return None


def _mark(conn, record_id: int, status: str, **kwargs) -> None:
    sets = ["status = ?"]
    params: list = [status]
    for k, v in kwargs.items():
        sets.append(f"{k} = ?")
        params.append(v)
    params.append(record_id)
    conn.execute(
        f"UPDATE ingested_reports SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    conn.commit()


def _write_normalized(conn, record_id: int, output) -> None:
    now = time.time()
    cursor = conn.execute(
        """
        INSERT INTO runs
            (app_type, run_id, ingest_report_id, schema_version, task_set_id,
             dataset_version, config_version, model_version, source_commit,
             primary_artifact_path, status, wall_duration_ms, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            output.app_type, output.run_id, record_id, output.schema_version,
            output.task_set_id, output.dataset_version, output.config_version,
            output.model_version, output.source_commit, output.primary_artifact_path,
            output.status, output.wall_duration_ms, now,
        ),
    )
    run_pk = cursor.lastrowid
    conn.executemany(
        "INSERT INTO run_metrics (run_pk, metric_name, metric_value, created_at) VALUES (?, ?, ?, ?)",
        [(run_pk, name, value, now) for name, value in output.metrics],
    )
    conn.commit()


def process_one() -> bool:
    """Claim and process one record. Returns True if a record was processed."""
    with db.connection() as conn:
        record = _claim_next(conn)
        if record is None:
            return False

        rid = record["id"]
        schema_version = record["schema_version"]
        attempt = record["attempt_count"]

        adapter = REGISTRY.get(schema_version)
        if adapter is None:
            logger.info(
                '{"event":"unsupported","schema_version":"%s","ingest_id":%d}',
                schema_version, rid,
            )
            _mark(conn, rid, "unsupported")
            return True

        try:
            payload = json.loads(record["raw_payload"])
            output = adapter.normalize(payload)
            _write_normalized(conn, rid, output)
            _mark(conn, rid, "processed", processed_at=time.time())
            logger.info(
                '{"event":"processed","schema_version":"%s","run_id":"%s","ingest_id":%d}',
                schema_version, record["run_id"], rid,
            )
        except Exception as exc:
            new_attempt = attempt + 1
            if new_attempt >= settings.worker_max_retries:
                _mark(conn, rid, "failed", attempt_count=new_attempt, last_error=str(exc))
                logger.warning(
                    '{"event":"failed","schema_version":"%s","ingest_id":%d,"error":"%s"}',
                    schema_version, rid, exc,
                )
            else:
                _mark(conn, rid, "pending", attempt_count=new_attempt, last_error=str(exc))
                logger.warning(
                    '{"event":"retry","schema_version":"%s","ingest_id":%d,"attempt":%d,"error":"%s"}',
                    schema_version, rid, new_attempt, exc,
                )

    return True


def run_loop() -> None:
    logger.info('{"event":"worker_started","poll_interval":%d}', settings.worker_poll_interval_secs)
    while True:
        try:
            processed = process_one()
        except Exception as exc:
            logger.error('{"event":"worker_error","error":"%s"}', exc)
            processed = False
        if not processed:
            time.sleep(settings.worker_poll_interval_secs)
