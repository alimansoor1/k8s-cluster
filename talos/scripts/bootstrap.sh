#!/usr/bin/env bash
# Bootstrap the Talos cluster after Pulumi has provisioned EC2 instances.
#
# Prereqs:
#   - pulumi up succeeded
#   - talhelper genconfig succeeded (see talos/talconfig.yaml)
#   - $TALOSCONFIG and $KUBECONFIG are set (via .envrc)
#
# This script is idempotent: re-running after a partial failure is safe.

set -euo pipefail

cd "$(dirname "$0")/.."   # cd to talos/

CP_IP="$(cd ../pulumi/stacks/prod && uv run pulumi stack output cp_eip_public_ip 2>/dev/null || true)"
WORKER_IP="$(cd ../pulumi/stacks/prod && uv run pulumi stack output --json 2>/dev/null | jq -r '.worker_asg_name')"

if [[ -z "${CP_IP}" ]]; then
  echo "ERROR: cp_eip_public_ip not found in Pulumi outputs. Run 'pulumi up' first."
  exit 1
fi

echo "→ CP IP: ${CP_IP}"
echo "→ Waiting for Talos API on ${CP_IP}:50000 ..."
for i in {1..30}; do
  if nc -zv -w 3 "${CP_IP}" 50000 2>/dev/null; then
    echo "✓ Talos API reachable"
    break
  fi
  echo "  ... attempt $i/30, sleeping 10s"
  sleep 10
done

# Step 1 — apply CP config
echo "→ Applying control plane config"
talosctl apply-config \
  --insecure \
  --nodes "${CP_IP}" \
  --file _out/cp-1.yaml

# Step 2 — bootstrap etcd (only on first ever boot)
echo "→ Bootstrapping etcd"
talosctl --talosconfig _out/talosconfig \
  --nodes "${CP_IP}" \
  bootstrap || echo "(bootstrap may have already run — continuing)"

# Step 3 — wait for kube-apiserver
echo "→ Waiting for kube-apiserver"
sleep 30
talosctl --talosconfig _out/talosconfig \
  --nodes "${CP_IP}" \
  kubeconfig _out/kubeconfig

# Step 4 — apply worker config (worker reaches CP via private routing,
#                                we need its private IP from the worker ASG)
WORKER_PRIV_IP="$(aws ec2 describe-instances \
  --filters "Name=tag:Role,Values=worker" "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].PrivateIpAddress' --output text)"
if [[ -z "${WORKER_PRIV_IP}" ]]; then
  echo "ERROR: could not resolve worker private IP. Is the worker EC2 running?"
  exit 1
fi
echo "→ Worker private IP: ${WORKER_PRIV_IP}"

# To reach the worker on its private IP, you need to be inside the VPC
# (or via the CP as a jump host using talosctl --endpoints CP --nodes WORKER).
echo "→ Applying worker config (via CP as endpoint)"
talosctl --talosconfig _out/talosconfig \
  --endpoints "${CP_IP}" \
  --nodes "${WORKER_PRIV_IP}" \
  apply-config \
  --insecure \
  --file _out/worker-1.yaml

echo "✓ Talos bootstrap complete."
echo "  kubeconfig: talos/_out/kubeconfig"
echo "  talosconfig: talos/_out/talosconfig"
echo ""
echo "Next: just cluster-bootstrap   (installs Cilium + Argo CD)"
