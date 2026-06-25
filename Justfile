# Justfile — common commands for Valheim K8s cluster
# Run `just` to list all commands.

set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load := true

# === Default ===
default:
    @just --list

# === Setup ===

# Install required local tooling (uv, pulumi, talosctl, kubectl, helm, argocd)
setup:
    @echo "→ Installing local tooling. Re-run safe."
    ./scripts/setup-tools.sh

# Sync Python deps
deps:
    cd pulumi/stacks/prod && uv sync

# === Infrastructure (Pulumi) ===

# Preview AWS infra changes
infra-preview:
    cd pulumi/stacks/prod && uv run pulumi preview

# Apply AWS infra changes
infra-up:
    cd pulumi/stacks/prod && uv run pulumi up

# Destroy AWS infra (use with care)
infra-down:
    cd pulumi/stacks/prod && uv run pulumi destroy

# Show all Pulumi stack outputs
infra-outputs:
    cd pulumi/stacks/prod && uv run pulumi stack output --json | jq

# === Talos ===

# Generate Talos machine configs from talconfig.yaml
talos-gen:
    cd talos && talhelper genconfig

# Apply machine configs to CP + worker (bootstrap)
talos-bootstrap:
    ./talos/scripts/bootstrap.sh

# talosctl shortcuts
talos-health:
    talosctl health --talosconfig $TALOSCONFIG

talos-dashboard:
    talosctl dashboard --talosconfig $TALOSCONFIG

# === Cluster bootstrap (one-time before Argo takes over) ===

# Install Cilium + Argo CD root app
cluster-bootstrap:
    ./scripts/cluster-bootstrap.sh

# Open Argo CD UI on localhost
argocd-ui:
    @echo "→ http://localhost:8080  (admin / see argocd/initial-password.txt)"
    kubectl -n argocd port-forward svc/argocd-server 8080:443

# === Daily ops ===

# Start EC2 instances
up:
    ./scripts/ec2-state.sh start

# Stop EC2 instances
down:
    ./scripts/ec2-state.sh stop

# Cluster + pod status
status:
    @echo "=== Nodes ===" && kubectl get nodes -o wide
    @echo "" && echo "=== Pods (all namespaces) ===" && kubectl get pods -A
    @echo "" && echo "=== Valheim ===" && kubectl -n valheim get pods,svc,pvc

# Tail Valheim pod logs
logs:
    kubectl -n valheim logs -f -l app=valheim-world-1

# Show recent AWS cost (rough estimate, requires aws ce permissions)
costs:
    ./scripts/show-costs.sh

# === Lint + format ===
lint:
    cd pulumi/stacks/prod && uv run ruff check .
    cd pulumi/stacks/prod && uv run pyright .

fmt:
    cd pulumi/stacks/prod && uv run ruff format .
