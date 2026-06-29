# Known limitations

What this repo does **not** yet automate, and why. Each item is a deliberate v1 scope cut, not a bug.

## 1. Talos machine config re-application on ASG replacement

**Status:** Manual.

When the ASG launches a replacement EC2 instance, the new Talos node boots into **maintenance mode** waiting for a machine config. The lifecycle hook re-attaches the EIP, but it does **not** apply the Talos machine config — that still requires running `talosctl apply-config` from your workstation.

**Why not automated yet:** Two safe options exist:

1. **S3-fetched config in userdata** — bake a small script into the AMI (or userdata) that fetches `cp-1.yaml` / `worker-1.yaml` from a private S3 bucket on boot. Requires the EC2 IAM role to have read access to that bucket and the config files to be uploaded outside git.
2. **Lambda apply-config** — extend the EIP re-attach Lambda to also call the Talos API with the right machine config. Requires bundling `talosctl` (or the Go API client) in the Lambda layer.

Both work; option 1 is simpler. I'm leaving this as a v2 task because the manual `talosctl apply-config` step is fast (30 seconds) and gives you a chance to verify the cluster state before the new node joins.

**Workaround:** Keep `talos/_out/cp-1.yaml` and `talos/_out/worker-1.yaml` somewhere accessible. If the ASG replaces an instance, run:

```bash
NEW_IP=$(aws ec2 describe-instances --filters "Name=tag:Role,Values=cp" \
  "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].PrivateIpAddress' --output text)

talosctl apply-config --insecure --nodes "$NEW_IP" --file talos/_out/cp-1.yaml
```

## 2. Talos / K8s version upgrades

**Status:** Manual via `talosctl upgrade`.

Argo CD manages the Kubernetes manifests but **not** the Talos OS or kubelet version. To upgrade, you bump versions in `talos/talconfig.yaml`, regenerate configs, and run `talosctl upgrade` per node.

**Why not automated:** Talos upgrades are intentionally a manual operation. Auto-upgrading the OS on a personal cluster is asking for a 3 AM page.

## 3. Secrets management

**Status:** `kubectl create secret` manually.

The Valheim server password and any future secrets are created out-of-band. No SealedSecrets, external-secrets, or sops integration.

**Why:** For a single-user cluster with one secret, the added complexity isn't worth it. If you grow this to multiple environments or worlds, install [sealed-secrets](https://github.com/bitnami-labs/sealed-secrets) and convert.

## 4. EBS snapshot lifecycle

**Status:** No automatic snapshots.

Your world saves can be lost if the EBS volume is corrupted or accidentally deleted.

**Fix in 5 min:**

```bash
aws dlm create-lifecycle-policy \
  --description "Daily Valheim world snapshots, 7-day retention" \
  --state ENABLED \
  --execution-role-arn arn:aws:iam::ACCOUNT:role/AWSDataLifecycleManagerDefaultRole \
  --policy-details file://dlm-policy.json
```

I haven't added this to Pulumi because the DLM service role setup is finicky and I'd rather you set it up consciously than have a "wait, what created this?" moment later.

## 5. Cost monitoring / budgets

**Status:** Manual via `just costs`.

No AWS Budget alerts configured. You can blow past your expected monthly cost if you forget to `just down`.

**Recommended:** Add a Pulumi resource for `aws.budgets.Budget` with a $20/month threshold and SNS email notification.

## 6. Argo CD UI exposure

**Status:** Port-forward only.

The Argo CD UI is `ClusterIP` and reachable only via `kubectl port-forward`. No public ingress, no TLS cert, no SSO.

**Why:** For one operator, port-forward is fine and safer than exposing it. If you want public access later, add an Envoy Gateway HTTPRoute + cert-manager + a domain.

## 7. Hubble UI

**Status:** Installed but disabled.

Cilium Hubble is installed (`hubble.enabled: true`) but the UI is disabled. Enable in `infrastructure/cilium/values.yaml` and port-forward when you want network observability.

## 8. Single-AZ blast radius

**Status:** Intentional.

The entire cluster lives in ``AWS_AZ``. If AWS loses that AZ, the cluster is down until the AZ recovers.

**Why:** Multi-AZ requires multi-AZ EBS (impossible — EBS is AZ-scoped), so either a distributed filesystem (EFS, complex with Valheim's flat file format) or accepting that "DR" means restoring from a snapshot in another AZ. For a personal game server, single-AZ is correct.

## 9. No staging environment

**Status:** Only `prod` stack.

`pulumi/stacks/prod` is the only stack. If you want to test infra changes before rolling them to "prod", you'd need to:

```bash
cd pulumi/stacks
cp -r prod staging
cd staging && pulumi stack init staging
```

Then set different CIDR ranges and a different region.

For a personal cluster this is overkill. Documented here so you remember the option exists.

## 10. Worker can only be reached via CP (talosctl)

**Status:** By design.

The worker is in a private subnet with no public IP. `talosctl` reaches it indirectly via the CP as a proxy:

```bash
talosctl --endpoints <CP_EIP> --nodes <WORKER_PRIVATE_IP> ...
```

This is correct — it's exactly what "private worker" means. But if the CP is down, you can't reach the worker via talosctl either. Don't lose the CP.
