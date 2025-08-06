#!/bin/bash
cd /home/ucadmin/Development/Meeting-Ops/backend
export DATABASE_URL='postgresql://meeting_ops:REMOVED@localhost:5432/meeting_ops'
export REDIS_URL='redis://localhost:6379'
timeout 5 ./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 9050 2>&1 | grep -E "(Meeting|router|ERROR|WARNING|Failed)"