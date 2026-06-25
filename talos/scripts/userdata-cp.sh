#!/bin/bash
# CP userdata — runs on Talos EC2 boot.
#
# Talos doesn't use traditional cloud-init userdata for shell — instead it
# expects a YAML machine config. The way to deliver it on AWS is via the
# EC2 userdata as a base64-encoded YAML. This file is a placeholder that the
# `nodes.py` component substitutes; in production you would:
#
#   1. Generate talos/_out/cp-1.yaml via `talhelper genconfig`
#   2. Upload it to a private S3 bucket
#   3. Replace this script with a small fetch-and-apply (see commented version)
#
# OR — the more common path — apply machine configs OUT-OF-BAND via talosctl
# after the EC2 instance boots into Talos's installer/maintenance mode.
# The `talos/scripts/bootstrap.sh` script does exactly that. In that case,
# this userdata can be a no-op.

#cloud-config
# Talos ignores this — but AWS requires *some* valid userdata format.
echo "Talos node booting. Apply machine config via talosctl from your workstation."
