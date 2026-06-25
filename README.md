# k8s-cluster — Valheim on Talos + Kubernetes

Self-hosted Valheim game server on a 2-node Talos Linux Kubernetes cluster in AWS `ap-southeast-1` (Singapore).

## Architecture

- **Control Plane** — t3.medium, public subnet, EIP, kube-apiserver/etcd/scheduler/controller-manager
- **Worker** — t3.medium, private subnet (no public IP), runs Valheim World 1 + Envoy Gateway + Cilium + system pods
- **NLB** — public, forwards UDP 2456-2458 to worker via VPC internal routing
- **ASG** — `min=1 max=1 desired=1` on both nodes for self-healing (not horizontal scaling)
- **GitOps** — Argo CD watches this repo and syncs all Kubernetes manifests
- **OS** — Talos Linux (immutable, API-only, no SSH) on both nodes
- **CNI** — Cilium (eBPF)
- **IaC** — Pulumi (Python)

See `docs/architecture.md` for the full design.

## Repository layout

```
k8s-cluster/
├── pulumi/              # AWS infrastructure as code (Python)
│   ├── components/      # Reusable Pulumi components (VPC, ASG, NLB)
│   └── stacks/prod/     # The prod stack (__main__.py + Pulumi.prod.yaml)
├── lambda/              # Source code for the EIP re-attach Lambda
├── talos/               # Talos machine config templates + bootstrap scripts
├── bootstrap/           # One-time install (Cilium, Argo CD root app)
├── argocd/              # Argo CD Application definitions (app-of-apps)
├── infrastructure/      # Helm-based cluster infra (Cilium, Envoy GW, EBS CSI)
├── apps/                # Kustomize manifests (Valheim)
├── scripts/             # Helper shell scripts
├── docs/                # Architecture + runbooks
└── Justfile             # Common commands
```

## Quickstart

```bash
# 1. Bootstrap your local toolchain (see docs/setup.md)
just setup

# 2. Provision AWS infrastructure
just infra-up

# 3. Bootstrap Talos cluster
just talos-bootstrap

# 4. Install Cilium + Argo CD (one-time, before Argo takes over)
just cluster-bootstrap

# 5. Argo CD syncs everything else from this repo
just argocd-ui
```

Full procedure in `docs/runbook.md`.

## Daily ops

```bash
just up          # start both EC2 instances
just down        # stop both EC2 instances (saves cost when not playing)
just status      # show cluster + pod status
just logs        # tail Valheim pod logs
just costs       # show current AWS spend estimate
```

## Cost

~$5–10/month if you stop instances when not playing. ~$35/month if 24/7.

## Security

- **No SSH** anywhere — Talos is API-only via `talosctl`
- **Worker is private** — no public IP, reached only via NLB or CP
- **kubectl** — TCP 6443 on CP, your IP only
- **talosctl** — TCP 50000 on CP, your IP only; worker reached indirectly via CP
- **Argo CD** — pulls from public GitHub repo, no inbound exposure

## Editor

This repo is designed for **Neovim + Zellij**. See `docs/neovim-setup.md` for the recommended plugin and LSP config (`pyright`, `ruff`, `yamlls`, `helm-ls`, `terraform-ls`-equivalent for Pulumi).
