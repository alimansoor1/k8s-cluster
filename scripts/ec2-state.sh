#!/usr/bin/env bash
# Start or stop both EC2 instances (CP + worker) using ASG suspend/resume.
#
# Pulumi outputs give us the ASG names. Suspending the Launch process keeps
# the instances stopped without ASG re-launching replacements.

set -euo pipefail

ACTION="${1:-status}"

cd "$(dirname "$0")/.."

CP_ASG="$(cd pulumi/stacks/prod && uv run pulumi stack output cp_asg_name 2>/dev/null || true)"
WORKER_ASG="$(cd pulumi/stacks/prod && uv run pulumi stack output worker_asg_name 2>/dev/null || true)"

if [[ -z "${CP_ASG}" || -z "${WORKER_ASG}" ]]; then
  echo "ERROR: Could not read ASG names from Pulumi stack outputs."
  exit 1
fi

case "${ACTION}" in
  start)
    echo "→ Resuming ASG processes + setting desired=1"
    aws autoscaling resume-processes --auto-scaling-group-name "${CP_ASG}"
    aws autoscaling resume-processes --auto-scaling-group-name "${WORKER_ASG}"
    aws autoscaling set-desired-capacity --auto-scaling-group-name "${CP_ASG}" --desired-capacity 1
    aws autoscaling set-desired-capacity --auto-scaling-group-name "${WORKER_ASG}" --desired-capacity 1
    echo "✓ EC2 instances starting. Allow 2-3 min for Talos boot + cluster ready."
    ;;
  stop)
    echo "→ Setting desired=0 + suspending ASG processes"
    aws autoscaling set-desired-capacity --auto-scaling-group-name "${CP_ASG}" --desired-capacity 0
    aws autoscaling set-desired-capacity --auto-scaling-group-name "${WORKER_ASG}" --desired-capacity 0
    aws autoscaling suspend-processes --auto-scaling-group-name "${CP_ASG}" --scaling-processes Launch
    aws autoscaling suspend-processes --auto-scaling-group-name "${WORKER_ASG}" --scaling-processes Launch
    echo "✓ EC2 instances stopping. ASG won't re-launch until 'just up'."
    ;;
  status)
    aws autoscaling describe-auto-scaling-groups \
      --auto-scaling-group-names "${CP_ASG}" "${WORKER_ASG}" \
      --query 'AutoScalingGroups[*].{Name:AutoScalingGroupName,Desired:DesiredCapacity,Instances:length(Instances),Suspended:SuspendedProcesses[*].ProcessName}' \
      --output table
    ;;
  *)
    echo "Usage: $0 {start|stop|status}"
    exit 1
    ;;
esac
