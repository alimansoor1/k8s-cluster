# Architecture

## Overview

Self-hosted Valheim server on a 2-node Talos Linux Kubernetes cluster in AWS Singapore (`ap-southeast-1`).

## Network topology

```
                    Internet
                       │
                       ▼
              ┌────────────────┐
              │   AWS NLB      │  UDP 2456-2458 (public subnet)
              │   (public IP)  │
              └────────┬───────┘
                       │ VPC internal routing (cross-subnet)
                       ▼
        ┌──────────────────────────────────────────┐
        │              AWS VPC                     │
        │ ┌─────────────────┐  ┌────────────────┐  │
        │ │ PUBLIC subnet   │  │ PRIVATE subnet │  │
        │ │ 10.0.1.0/24     │  │ 10.0.2.0/24    │  │
        │ │                 │  │                │  │
        │ │ ┌─────────────┐ │  │ ┌────────────┐ │  │
        │ │ │ Control     │ │  │ │  Worker    │ │  │
        │ │ │ Plane       │◀┼──┼─│  Node      │ │  │
        │ │ │ (EIP)       │ │  │ │ (no public │ │  │
        │ │ │             │ │  │ │   IP)      │ │  │
        │ │ └─────────────┘ │  │ └────────────┘ │  │
        │ │      ▲          │  │     ▲          │  │
        │ │      │          │  │     │          │  │
        │ └──────┼──────────┘  └─────┼──────────┘  │
        │        │                   │             │
        │        └─── ASG min=1 ─────┘             │
        │             (each)                       │
        └──────────────────────────────────────────┘
                       ▲
                       │ talosctl (CP direct, worker indirect)
                       │ kubectl (CP only)
                       │
                  ┌────┴────┐
                  │   You   │
                  └─────────┘
```

## Key design decisions

| Decision | Rationale |
|---|---|
| Single AZ (`ap-southeast-1a`) | Personal cluster, no HA needed; EBS volumes are AZ-scoped anyway |
| Talos Linux on both nodes | Immutable, no SSH, API-only — significantly smaller attack surface than Ubuntu |
| Cilium CNI + kube-proxy replacement | eBPF dataplane, better observability, modern K8s standard |
| Envoy Gateway (in-cluster) | UDP routing inside K8s; sits between NLB and the Valheim pod |
| NLB for ingress (not ALB) | ALB doesn't support UDP. NLB at L4 forwards game traffic untouched |
| Worker in private subnet | No public IP minimizes attack surface; NLB cross-subnet routes traffic in |
| EIP on CP only | Stable IP for kubectl/talosctl admin access; survives ASG instance replacement via lifecycle hook |
| ASG min=1 max=1 | Self-healing only (not horizontal scaling) — Valheim doesn't shard |
| Argo CD GitOps | All K8s manifests reconcile from this repo automatically |
| EBS gp3, retain policy | World saves persist even if PVC is deleted accidentally |
| t3.medium x2 | Small enough for personal use, large enough for Valheim + system pods |

## Self-healing mechanism

1. EC2 instance fails or is terminated.
2. ASG detects health check failure → launches replacement.
3. For the **CP**: EventBridge rule fires on `EC2_INSTANCE_LAUNCHING` lifecycle hook → invokes the EIP re-attach Lambda → Lambda waits for instance running → associates the same EIP → completes lifecycle action.
4. New instance boots Talos.
5. Talos machine config is re-applied by the operator (via `talosctl apply-config` from your workstation) — **this is not yet fully automated**; see `docs/known-limitations.md`.
6. Talos rejoins the cluster (or bootstraps if it's the only CP).
7. Cilium/Argo CD/Envoy/Valheim pods reconcile automatically.

## Cost model

| Component | Hourly (24/7) | Notes |
|---|---|---|
| CP t3.medium | ~$0.0464/hr | $33/month if always on |
| Worker t3.medium | ~$0.0464/hr | Stop with `just down` when not playing |
| NLB | ~$0.0225/hr + LCU | ~$16/month continuous |
| NAT GW | ~$0.045/hr + data | ~$32/month — biggest single cost |
| EBS gp3 8 GiB | ~$0.0011/hr | <$1/month |
| EIPs (attached) | $0 | Only $0.005/hr when *detached* from a running instance |
| Data transfer (out) | $0.09/GB | Minimal for game UDP traffic |

**Hot tip:** the NAT Gateway is your biggest cost. If you don't need outbound internet from the worker (e.g., for image pulls after the cluster is steady-state), you can replace it with a VPC endpoint for ECR/S3 and delete the NAT GW, saving ~$32/month.

## See also

- `docs/runbook.md` — step-by-step setup
- `docs/decisions.md` — extended rationale per component
- `docs/known-limitations.md` — what's not yet automated
