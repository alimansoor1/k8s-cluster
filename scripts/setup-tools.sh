#!/usr/bin/env bash
# Install / verify the local toolchain.
# Idempotent: skips anything already installed.

set -euo pipefail

need() { command -v "$1" >/dev/null 2>&1; }

# 1. uv (fast Python package manager)
if ! need uv; then
  echo "→ Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
else
  echo "✓ uv $(uv --version)"
fi

# 2. Pulumi CLI
if ! need pulumi; then
  echo "→ Installing Pulumi"
  curl -fsSL https://get.pulumi.com | sh
else
  echo "✓ pulumi $(pulumi version)"
fi

# 3. talosctl
if ! need talosctl; then
  echo "→ Installing talosctl"
  curl -sL https://talos.dev/install | sh
else
  echo "✓ talosctl $(talosctl version --client --short 2>/dev/null || talosctl version --client)"
fi

# 4. talhelper
if ! need talhelper; then
  echo "→ Installing talhelper"
  if need brew; then
    brew install budimanjojo/tap/talhelper
  else
    echo "  Install talhelper from: https://github.com/budimanjojo/talhelper/releases"
  fi
else
  echo "✓ talhelper $(talhelper --version)"
fi

# 5. kubectl
if ! need kubectl; then
  echo "→ Install kubectl from https://kubernetes.io/docs/tasks/tools/"
  echo "  e.g.: brew install kubectl"
else
  echo "✓ kubectl $(kubectl version --client -o yaml | grep gitVersion | head -1)"
fi

# 6. helm
if ! need helm; then
  echo "→ Install helm from https://helm.sh/docs/intro/install/"
  echo "  e.g.: brew install helm"
else
  echo "✓ helm $(helm version --short)"
fi

# 7. just
if ! need just; then
  echo "→ Install just from https://github.com/casey/just"
  echo "  e.g.: brew install just"
else
  echo "✓ just $(just --version)"
fi

# 8. jq
if ! need jq; then
  echo "→ Install jq (brew install jq | apt install jq)"
else
  echo "✓ jq $(jq --version)"
fi

# 9. AWS CLI
if ! need aws; then
  echo "→ Install AWS CLI v2 from https://aws.amazon.com/cli/"
else
  echo "✓ aws $(aws --version)"
fi

echo ""
echo "✓ Setup complete. Run 'just deps' to install Python deps for Pulumi."
