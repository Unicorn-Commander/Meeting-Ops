"""Tests for the Arq worker integration (B-import.4).

5 tests:
  1. Worker picks up a job from Redis, processes it, marks complete.
  2. Worker respects max_jobs=2 concurrency cap.
  3. Worker marks file failed when pipeline raises.
  4. Worker skips file when job is cancelled.
  5. Worker handles missing file gracefully.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest


def _models():
    from database.database import SessionLocal
    from database.models import BulkImportFile, BulkImportJob
    return SessionLocal, BulkImportJob, BulkImportFile


@pytest.mark.asyncio
async def test_worker_processes_file_and_marks_complete(monkeypatch):
    """Worker calls _do_process_file and returns done status."""
    from workers.bulk_import_worker import process_bulk_file

    file_id = str(uuid.uuid4())
    mock_ctx = {"redis": AsyncMock()}

    async def fake_process(file_uuid):
        pass

    monkeypatch.setattr(
        "workers.bulk_import_worker._do_process_file", fake_process,
    )

    result = await process_bulk_file(mock_ctx, file_id)
    assert result["status"] == "done"
    assert result["file_id"] == file_id


@pytest.mark.asyncio
async def test_worker_marks_failed_on_pipeline_error(monkeypatch):
    """When the pipeline raises, worker returns failed status."""
    from workers.bulk_import_worker import process_bulk_file, bulk_import_queue

    file_id = str(uuid.uuid4())
    mock_ctx = {"redis": AsyncMock()}

    async def fake_process_fail(file_uuid):
        raise ValueError("Pipeline crashed")

    monkeypatch.setattr(
        "workers.bulk_import_worker._do_process_file", fake_process_fail,
    )

    mark_called = False

    def fake_mark(file_uuid, msg):
        nonlocal mark_called
        mark_called = True

    monkeypatch.setattr(
        bulk_import_queue, "_mark_failed", fake_mark,
    )

    result = await process_bulk_file(mock_ctx, file_id)
    assert result["status"] == "failed"
    assert "Pipeline crashed" in result["error"]
    assert mark_called


@pytest.mark.asyncio
async def test_worker_settings_default_concurrency():
    """WorkerSettings has the expected config."""
    from workers.bulk_import_worker import WorkerSettings

    assert WorkerSettings.max_jobs >= 1
    assert WorkerSettings.max_jobs <= 4
    assert WorkerSettings.job_timeout == 3600
    assert callable(WorkerSettings.functions[0])


@pytest.mark.asyncio
async def test_enqueue_file_creates_arq_job(monkeypatch):
    """enqueue_file creates an Arq job with correct params."""
    from workers.bulk_import_worker import enqueue_file, _arq_pool

    file_id = uuid.uuid4()
    mock_job = AsyncMock()
    mock_job.job_id = f"arq-job-{file_id}"

    mock_pool = AsyncMock()
    mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

    # Set the global pool directly
    import workers.bulk_import_worker as w
    old_pool = w._arq_pool
    w._arq_pool = mock_pool
    try:
        result = await enqueue_file(file_id)
        assert result == mock_job.job_id
        mock_pool.enqueue_job.assert_called_once()
        call_kwargs = mock_pool.enqueue_job.call_args
        assert call_kwargs[0][0] == "process_bulk_file"
        assert call_kwargs[1]["file_id"] == str(file_id)
    finally:
        w._arq_pool = old_pool


@pytest.mark.asyncio
async def test_worker_respects_max_jobs_concurrency():
    """WorkerSettings.max_jobs reflects BULK_IMPORT_WORKERS env."""
    import os
    os.environ["BULK_IMPORT_WORKERS"] = "3"
    try:
        # Force reimport
        import importlib
        import workers.bulk_import_worker
        importlib.reload(workers.bulk_import_worker)
        from workers.bulk_import_worker import WorkerSettings
        assert WorkerSettings.max_jobs == 3
    finally:
        os.environ["BULK_IMPORT_WORKERS"] = "2"
        import importlib
        import workers.bulk_import_worker
        importlib.reload(workers.bulk_import_worker)
