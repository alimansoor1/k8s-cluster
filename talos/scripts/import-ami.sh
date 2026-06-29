#!/usr/bin/env bash
# Download a Talos AWS AMI and import it into your account as a private AMI.
#
# Talos publishes per-region AMI IDs at https://factory.talos.dev/.
# For `AWS_REGION`, easiest path is to use the official Talos image factory:
#
#   1. Visit https://factory.talos.dev/
#   2. Pick AWS / amd64 / your desired version
#   3. Copy the AMI ID for `AWS_REGION`
#   4. Run: pulumi config set talos_ami_id <ami-id>
#
# This script is here for completeness if you want to roll a custom AMI.

set -euo pipefail

TALOS_VERSION="${TALOS_VERSION:-v1.8.2}"
REGION="${AWS_REGION:-`AWS_REGION`}"
BUCKET="${BUCKET:-}"   # set to an S3 bucket you own

if [[ -z "${BUCKET}" ]]; then
  echo "Set BUCKET=<your-s3-bucket> to use this script."
  echo "Otherwise, grab a published AMI ID from https://factory.talos.dev/"
  exit 1
fi

URL="https://github.com/siderolabs/talos/releases/download/${TALOS_VERSION}/aws-amd64.raw.xz"
TMP=$(mktemp -d)
trap "rm -rf ${TMP}" EXIT

echo "→ Downloading ${URL}"
curl -fsSL -o "${TMP}/talos.raw.xz" "${URL}"
xz -d "${TMP}/talos.raw.xz"

echo "→ Uploading to s3://${BUCKET}/talos/${TALOS_VERSION}.raw"
aws s3 cp "${TMP}/talos.raw" "s3://${BUCKET}/talos/${TALOS_VERSION}.raw"

echo "→ Importing as EBS snapshot"
TASK_ID=$(aws ec2 import-snapshot \
  --region "${REGION}" \
  --description "Talos ${TALOS_VERSION}" \
  --disk-container "Format=raw,UserBucket={S3Bucket=${BUCKET},S3Key=talos/${TALOS_VERSION}.raw}" \
  --query 'ImportTaskId' --output text)
echo "  ImportTaskId: ${TASK_ID}"

echo "→ Polling import status (this takes 5-10 min)…"
while true; do
  STATUS=$(aws ec2 describe-import-snapshot-tasks --region "${REGION}" \
    --import-task-ids "${TASK_ID}" \
    --query 'ImportSnapshotTasks[0].SnapshotTaskDetail.Status' --output text)
  echo "  status=${STATUS}"
  if [[ "${STATUS}" == "completed" ]]; then break; fi
  if [[ "${STATUS}" == "deleted" || "${STATUS}" == "deleting" ]]; then
    echo "Import failed."; exit 1
  fi
  sleep 30
done

SNAP_ID=$(aws ec2 describe-import-snapshot-tasks --region "${REGION}" \
  --import-task-ids "${TASK_ID}" \
  --query 'ImportSnapshotTasks[0].SnapshotTaskDetail.SnapshotId' --output text)
echo "  SnapshotId: ${SNAP_ID}"

echo "→ Registering AMI"
AMI_ID=$(aws ec2 register-image \
  --region "${REGION}" \
  --name "talos-${TALOS_VERSION}-$(date +%s)" \
  --architecture x86_64 \
  --root-device-name /dev/xvda \
  --virtualization-type hvm \
  --ena-support \
  --block-device-mappings "[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"SnapshotId\":\"${SNAP_ID}\",\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" \
  --query 'ImageId' --output text)

echo ""
echo "✓ Done. AMI: ${AMI_ID}"
echo "Next: pulumi config set talos_ami_id ${AMI_ID}"
