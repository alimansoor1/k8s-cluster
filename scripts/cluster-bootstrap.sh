#!/usr/bin/env bash
# One-time cluster bootstrap: install Cilium, then Argo CD root app.
# After this, Argo CD manages everything from the repo.

set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

: "${KUBECONFIG:?KUBECONFIG must be set (see .envrc)}"

echo "→ Installing Cilium via Helm"
helm repo add cilium https://helm.cilium.io --force-update
helm upgrade --install cilium cilium/cilium \
  --namespace kube-system \
  --version 1.16.3 \
  --values infrastructure/cilium/values.yaml \
  --wait

echo "→ Waiting for Cilium DaemonSet to be ready"
kubectl -n kube-system rollout status ds/cilium --timeout=5m

echo "→ Installing Argo CD via Helm"
helm repo add argo https://argoproj.github.io/argo-helm --force-update
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install argocd argo/argo-cd \
  --namespace argocd \
  --version 7.6.12 \
  --values infrastructure/argo-cd/values.yaml \
  --wait

echo "→ Initial admin password:"
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d > argocd-initial-password.txt
echo "  saved to: argocd-initial-password.txt (gitignored)"

echo "→ Applying root Argo CD Application (app-of-apps)"
kubectl apply -f argocd/apps/root.yaml

echo ""
echo "✓ Bootstrap complete."
echo "  just argocd-ui   →   open Argo CD on http://localhost:8080"
echo "                       login: admin / contents of argocd-initial-password.txt"
