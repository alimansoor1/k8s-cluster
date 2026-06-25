"""Re-attach the CP EIP to a newly launched ASG instance.

Trigger: EventBridge rule on ASG lifecycle action "EC2_INSTANCE_LAUNCHING"
        for the CP ASG.

Flow:
    1. Read instance_id + lifecycle action info from event detail
    2. Find the EIP tagged Role=cp + Project=valheim
    3. Wait until instance state == 'running'
    4. Associate the EIP
    5. Complete the lifecycle action so the instance enters InService

If anything fails, complete with result=ABANDON so ASG retries.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(logging.INFO)

ec2 = boto3.client("ec2")
asg = boto3.client("autoscaling")

PROJECT_TAG = os.environ.get("PROJECT_TAG", "valheim")
ROLE_TAG = os.environ.get("ROLE_TAG", "cp")
WAIT_SECONDS = int(os.environ.get("WAIT_SECONDS", "240"))


def _find_eip() -> str:
    """Return AllocationId of the EIP matching tags Project + Role."""
    resp = ec2.describe_addresses(
        Filters=[
            {"Name": "tag:Project", "Values": [PROJECT_TAG]},
            {"Name": "tag:Role", "Values": [ROLE_TAG]},
        ]
    )
    addrs = resp.get("Addresses", [])
    if not addrs:
        raise RuntimeError(f"No EIP found with tags Project={PROJECT_TAG} Role={ROLE_TAG}")
    if len(addrs) > 1:
        raise RuntimeError(f"Multiple EIPs found, expected one: {[a['AllocationId'] for a in addrs]}")
    return addrs[0]["AllocationId"]


def _wait_running(instance_id: str) -> None:
    """Block until the instance is in 'running' state, or timeout."""
    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:
        r = ec2.describe_instances(InstanceIds=[instance_id])
        state = r["Reservations"][0]["Instances"][0]["State"]["Name"]
        log.info("Instance %s state=%s", instance_id, state)
        if state == "running":
            return
        time.sleep(10)
    raise TimeoutError(f"Instance {instance_id} did not reach running within {WAIT_SECONDS}s")


def lambda_handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    log.info("Event: %s", event)
    detail = event.get("detail", {})
    instance_id = detail.get("EC2InstanceId")
    hook_name = detail.get("LifecycleHookName")
    asg_name = detail.get("AutoScalingGroupName")
    token = detail.get("LifecycleActionToken")

    if not all([instance_id, hook_name, asg_name, token]):
        log.error("Missing required fields in event detail: %s", detail)
        return {"status": "skipped", "reason": "missing-fields"}

    result = "ABANDON"
    try:
        allocation_id = _find_eip()
        log.info("Found EIP allocation %s", allocation_id)

        _wait_running(instance_id)

        ec2.associate_address(
            AllocationId=allocation_id,
            InstanceId=instance_id,
            AllowReassociation=True,
        )
        log.info("Associated EIP %s with instance %s", allocation_id, instance_id)
        result = "CONTINUE"
    except (ClientError, RuntimeError, TimeoutError) as e:
        log.exception("EIP re-attach failed: %s", e)
    finally:
        asg.complete_lifecycle_action(
            LifecycleHookName=hook_name,
            AutoScalingGroupName=asg_name,
            LifecycleActionToken=token,
            LifecycleActionResult=result,
            InstanceId=instance_id,
        )
        log.info("Completed lifecycle action with result=%s", result)

    return {"status": "ok", "result": result, "instance_id": instance_id}
