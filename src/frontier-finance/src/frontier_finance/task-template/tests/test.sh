#!/bin/bash
# Grade /app/report.md against this query's rubrics with the upstream
# FrontierFinance grader. grade.py writes /logs/verifier/reward.json.
mkdir -p /logs/verifier
/opt/ff-grader/bin/python /tests/grade.py
