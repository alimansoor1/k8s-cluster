#!/bin/bash
# Worker userdata — placeholder. See userdata-cp.sh for the explanation.
# The __CP_ENDPOINT__ token is substituted at Pulumi deploy time with the
# CP EIP, available here for any custom logic that needs it.
#
#   Substituted CP endpoint: __CP_ENDPOINT__

#cloud-config
echo "Talos worker booting. CP endpoint: __CP_ENDPOINT__"
echo "Apply machine config via talosctl from your workstation."
