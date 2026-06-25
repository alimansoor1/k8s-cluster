#!/usr/bin/env bash
# Rough current-month spend for the valheim project, via Cost Explorer.
# Requires ce:GetCostAndUsage IAM permission on your admin user.

set -euo pipefail

START="$(date -u +%Y-%m-01)"
END="$(date -u +%Y-%m-%d)"

aws ce get-cost-and-usage \
  --time-period "Start=${START},End=${END}" \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --filter '{"Tags":{"Key":"Project","Values":["valheim"]}}' \
  --group-by Type=DIMENSION,Key=SERVICE \
  --output table
