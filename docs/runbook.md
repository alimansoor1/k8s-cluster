# Runbook — first-time setup and common operations

## First-time setup

### Prereqs

- AWS account with admin or scoped IAM user
- AWS CLI v2 configured (`aws configure`)
- A custom domain (optional, for Argo CD ingress later)
- Roughly $0.20/hr willingness to burn during testing

### Step 1 — Install local tools

```bash
just setup
```

Installs: `uv`, `pulumi`, `talosctl`, `talhelper`, `kubectl`, `helm`, `just`, `jq`, `aws`.

### Step 2 — Configure environment

```bash
cp .envrc.example .envrc
$EDITOR .envrc
direnv allow
```

Set:
- `AWS_REGION=<AWS_REGION>`
- `AWS_PROFILE` to your admin profile
- `MY_IP` to your home/office IP (automatically detected by default)

### Step 3 — Get a Talos AMI

Easiest: visit https://factory.talos.dev/ → AWS / amd64 → copy the AMI ID for <AWS_REGION>.

Then:

```bash
cd pulumi/stacks/prod
pulumi config set talos_ami_id AMI_ID_HERE
pulumi config set admin_cidr "$(curl -s https://checkip.amazonaws.com)/32"
```

### Step 4 — Sync Python deps

```bash
just deps
```

### Step 5 — Provision AWS infra

```bash
just infra-preview     # see what will happen
just infra-up          # do it
```

Takes ~3–4 minutes. Outputs include `cp_eip_public_ip` and `nlb_dns_name`.

### Step 6 — Edit Talos endpoint, then generate configs

```bash
# Copy the EIP into talos/talconfig.yaml + talos/patches/cp-common.yaml + infrastructure/cilium/values.yaml
sed -i.bak "s|REPLACE_WITH_CP_EIP|$(pulumi -C pulumi/stacks/prod stack output cp_eip_public_ip)|g" \
  talos/talconfig.yaml talos/patches/cp-common.yaml infrastructure/cilium/values.yaml

just talos-gen
```

### Step 7 — Bootstrap Talos

```bash
just talos-bootstrap
```

This applies the CP config, bootstraps etcd, downloads the kubeconfig, then applies the worker config (reaching the private worker via the CP).

Verify:

```bash
kubectl get nodes
```

Both nodes should show `Ready` (the CP after Cilium installs, ~2 min later).

### Step 8 — Cluster bootstrap

```bash
just cluster-bootstrap
```

Installs Cilium + Argo CD. Saves the Argo CD initial admin password to `argocd-initial-password.txt` (gitignored). Applies the root Application.

### Step 9 — Push to GitHub

Create a public or private GitHub repo, then:

```bash
git init
git add .
git commit -m "Initial valheim k8s-cluster"
git remote add origin git@github.com:YOUR_GH_USER/k8s-cluster.git
git push -u origin main
```

Then update the placeholder repo URLs in:
- `argocd/apps/root.yaml`
- `argocd/apps/projects.yaml`
- `argocd/apps/infrastructure.yaml`
- `argocd/apps/valheim.yaml`

Commit + push. Argo CD will pick up the change and start syncing.

### Step 10 — Set the Valheim server password

```bash
kubectl -n valheim create secret generic valheim-server-pass \
  --from-literal=password='YourStrongPasswordHere'
```

The Valheim Deployment references this secret. Argo CD won't manage it (intentional — secrets should not live in git).

### Step 11 — Play

```bash
just status
just logs
```

Connect from Valheim client via `Add Server by IP`:
- IP: the `nlb_dns_name` from Pulumi outputs (resolves to NLB public IP)
- Port: <GAME_UDP_START>

## Daily ops

| Goal | Command |
|---|---|
| Start cluster | `just up` (~2 min boot) |
| Stop cluster | `just down` |
| See status | `just status` |
| Tail logs | `just logs` |
| Open Argo CD | `just argocd-ui` then http://localhost:8080 |
| Talos dashboard | `just talos-dashboard` |
| Check costs | `just costs` |

## Update Valheim

1. Edit `apps/valheim-world-1/base/deployment.yaml` (change image tag).
2. `git commit && git push`
3. Argo CD reconciles within ~3 minutes (or click "Sync" in the UI).

## Update Talos / K8s version

1. Edit `talos/talconfig.yaml` → bump `talosVersion` or `kubernetesVersion`
2. `just talos-gen`
3. `talosctl upgrade --image ghcr.io/siderolabs/installer:v1.x.x --nodes <CP-IP>`
4. Same for worker

## Disaster recovery

**CP instance dies:** ASG auto-replaces. Lifecycle hook re-attaches EIP. You must `talosctl apply-config` the new node from your workstation (not yet automated).

**Worker instance dies:** ASG auto-replaces. Same manual step. EBS volume re-attaches (same AZ enforced).

**EBS volume corruption:** Restore from a recent snapshot (manual — set up `dlm` lifecycle for automated snapshots).

**Lost kubeconfig:** `talosctl --talosconfig ... --nodes CP_IP kubeconfig ./kubeconfig`

**Lost talosconfig:** Re-run `talhelper genconfig` — but **this will rotate cluster secrets**. If you've lost the talosconfig and have no backup, your only path is to destroy and rebuild.

**ALWAYS** back up `talos/_out/talosconfig` somewhere safe (1Password, encrypted USB) — it's the master key.
