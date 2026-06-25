# Decisions

The reasoning behind each major choice. Read this before changing anything substantial.

## OS: Talos Linux

**Chosen over:** Ubuntu, Amazon Linux 2023, Bottlerocket.

**Why:** Talos is immutable and API-only — no SSH, no shell, no package manager, no users. The attack surface is fundamentally smaller than a general-purpose Linux. For a server exposed to the internet, this matters.

**Tradeoff:** You can't `ssh` and `tail -f /var/log/...`. Everything is `talosctl` over its API. Once you accept that, you stop missing SSH within a week.

## IaC: Pulumi (Python)

**Chosen over:** Terraform/OpenTofu, CDK, Pulumi-YAML, Pulumi-Go.

**Why Python:** Already in your toolchain (bug bounty agent), excellent Neovim integration via pyright, fits the AWS ecosystem.

**Why Pulumi over Terraform:** Real loops, real conditionals, real functions, a real type system. The Talos userdata injection alone makes the case — that's 4 lines in Python vs an unreadable `templatefile()` call in HCL.

**Why not Pulumi-YAML:** Cross-resource wiring (e.g., the SG rule that references the NLB SG ID) is genuinely awkward in YAML. The Lambda code injection is the killer issue.

## K8s distribution: self-managed via Talos (not EKS)

**Chosen over:** EKS, k3s, kubeadm.

**Why not EKS:** EKS control plane costs $0.10/hr = $72/month even when idle. For a personal cluster this dominates the bill. Talos's control plane runs on a t3.medium at $0.046/hr = ~$33/month, and you can stop it when not playing.

**Why not k3s:** k3s is fine, but Talos's security model is stricter and you wanted to learn it.

## CNI: Cilium with kube-proxy replacement

**Chosen over:** Flannel, Calico, AWS VPC CNI.

**Why Cilium:** eBPF dataplane, Hubble observability, network policies via L4/L7, and replacing kube-proxy reduces one moving part. It's the modern default for new clusters.

**Why not AWS VPC CNI:** Ties you to AWS subnets for pod IPs, which complicates things if you ever migrate. Cilium uses overlay or native routing as you prefer.

## Gateway: Envoy Gateway (in-cluster)

**Chosen over:** Ingress-NGINX, Traefik, Istio.

**Why Envoy Gateway:** Implements the Kubernetes Gateway API spec (the successor to Ingress), handles UDP natively, and is the reference implementation. For a setup that's mostly UDP traffic, ingress-nginx is the wrong tool.

**Tradeoff:** Newer than ingress-nginx; smaller community. For your use (UDP routing to one pod), the maturity gap doesn't matter.

## Load balancer: NLB (not ALB)

**Why NLB:** ALB doesn't support UDP. Valheim is UDP-only. End of decision tree.

## Worker placement: private subnet (no public IP)

**Chosen over:** Public subnet with security group restrictions.

**Why:** Defense in depth. Even if you misconfigure a security group, a worker with no public IP cannot be reached from the internet. NLB cross-subnet routing means game traffic still works.

**Cost:** NAT Gateway (~$32/month) for the worker's outbound traffic. This is the largest single cost in the stack.

**Alternative for cost savings:** Replace NAT GW with VPC endpoints (ECR, S3, STS). For Valheim's needs, this is feasible — the worker mainly pulls container images. Save this for a future optimization.

## ASG: min=1 max=1 desired=1 (self-healing, not autoscaling)

**Why:** Valheim doesn't shard. Adding a second worker doesn't add capacity to one world. ASG here is purely for "EC2 died → ASG launches a replacement."

**Why not no ASG (just a raw EC2):** Without ASG, a hardware failure means a dead game server until you intervene. The ASG turns that into a 5-minute auto-recovery.

## CP gets an EIP, worker does not

**Why CP:** kubectl/talosctl needs a stable IP. ASG replacements would change the IP without the EIP + lifecycle hook trick.

**Why not worker:** The worker is unreachable from the internet directly. The NLB resolves the worker's current ENI IP via its target group; no EIP needed.

## Single AZ (ap-southeast-1a)

**Why:** EBS volumes are AZ-scoped. Multi-AZ implies either replicated storage (not practical for Valheim's save format) or a complex restore-in-another-AZ procedure. For a personal cluster, single-AZ is the right call.

## Argo CD over Flux

**Why Argo CD:** UI is better for someone learning K8s. Flux's CLI-first model is great for teams, but a UI helps you see what's syncing and why.

**Tradeoff:** Argo CD's resource footprint is slightly larger (~400 MB RAM total across its pods vs ~150 MB for Flux). On a t3.medium worker, this is fine.

## Helm + Kustomize (not pure Helm or pure Kustomize)

**Pattern:** Helm for cluster infrastructure (Cilium, Argo CD, Envoy Gateway, EBS CSI). Kustomize for application manifests (Valheim).

**Why:** Helm is unbeatable for installing complex third-party charts with hundreds of templates. Kustomize is cleaner for your own apps where the manifest structure is simple and you want plain YAML you can read in 10 seconds.

## uv over pip/poetry/pdm

**Why uv:** Single binary, 10x faster than pip, handles venvs and lockfiles in one tool. Modern Python toolchain.

**Tradeoff:** Newer (released 2024). If something breaks in uv, you might be on the bleeding edge.

## just over make

**Why just:** Recipes are easier to read than Makefiles, no tab/space landmines, supports `.env` files natively.

**Tradeoff:** One more tool to install. Worth it.

## Lambda for EIP re-attach (not a daemon on the CP)

**Why Lambda:** The CP is the very thing being replaced. A daemon on the CP can't re-attach the CP's EIP because the daemon doesn't exist yet when the new instance is launching.

**Alternative:** EventBridge → SSM Automation. Equivalent, slightly more verbose to configure. Lambda is more flexible for adding logic later.

## EBS gp3 (not io2 or st1)

**Why gp3:** Best price/performance for small volumes. The 8 GiB world save file doesn't need io2's IOPS.

## ServerSideApply in Argo

**Why:** Better field management for CRDs and shared resources. The K8s default merge strategy can lose fields silently on updates.

## No Vault / no Sealed Secrets (yet)

**Why:** One secret. Adding Vault for one secret is engineering theater. Revisit when you have 5+ secrets.

## Why this repo isn't a Helm umbrella chart

**Considered:** Packaging everything as a single Helm chart with sub-charts.

**Rejected:** Helm umbrella charts are painful to debug. Argo CD's ApplicationSet pattern is cleaner — each component is its own Application, syncs independently, easier to see what broke.
