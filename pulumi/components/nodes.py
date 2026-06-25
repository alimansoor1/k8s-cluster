"""Control Plane and Worker — each a Launch Template + ASG.

Both ASGs run with min=1 max=1 desired=1 for self-healing only.
The CP ASG has a lifecycle hook + EIP re-attach Lambda.
The Worker has no public IP and no EIP (NLB reaches it via internal VPC routing).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pulumi
import pulumi_aws as aws


def _userdata_for(role: str, extra_vars: dict[str, str] | None = None) -> str:
    """Load talos/userdata-<role>.sh and base64-encode for the Launch Template.

    The userdata script fetches the Talos machine config from S3 (or a pre-baked
    location) and applies it via talosctl. See talos/scripts/userdata-*.sh for
    the actual contents.
    """
    path = (
        Path(__file__).resolve().parents[2]
        / "talos"
        / "scripts"
        / f"userdata-{role}.sh"
    )
    if not path.exists():
        # Fallback: emit a minimal placeholder so Pulumi doesn't fail at preview
        # time. Replace with real talos config fetch before applying.
        body = f"#!/bin/bash\n# TODO: implement userdata for {role}\necho 'placeholder' >> /var/log/userdata.log\n"
    else:
        body = path.read_text()
    if extra_vars:
        for k, v in extra_vars.items():
            body = body.replace(f"__{k}__", str(v))
    return base64.b64encode(body.encode()).decode()


class ControlPlane(pulumi.ComponentResource):
    def __init__(
        self,
        name: str,
        *,
        subnet_id: pulumi.Input[str],
        security_group_ids: list[pulumi.Input[str]],
        ami_id: str,
        instance_type: str,
        instance_profile_name: pulumi.Input[str],
        eip_reattach_arn: pulumi.Input[str],
        tags: dict[str, str],
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        super().__init__("valheim:nodes:ControlPlane", name, None, opts)

        # EIP allocated once, re-attached on ASG instance replacement
        self.eip = aws.ec2.Eip(
            f"{name}-eip",
            domain="vpc",
            tags={**tags, "Name": f"{name}-eip", "Role": "cp"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.launch_template = aws.ec2.LaunchTemplate(
            f"{name}-lt",
            image_id=ami_id,
            instance_type=instance_type,
            iam_instance_profile=aws.ec2.LaunchTemplateIamInstanceProfileArgs(
                name=instance_profile_name,
            ),
            vpc_security_group_ids=security_group_ids,
            user_data=_userdata_for("cp"),
            metadata_options=aws.ec2.LaunchTemplateMetadataOptionsArgs(
                http_endpoint="enabled",
                http_tokens="required",  # IMDSv2 only
                http_put_response_hop_limit=2,
            ),
            tag_specifications=[
                aws.ec2.LaunchTemplateTagSpecificationArgs(
                    resource_type="instance",
                    tags={**tags, "Role": "cp", "Name": f"{name}"},
                ),
                aws.ec2.LaunchTemplateTagSpecificationArgs(
                    resource_type="volume",
                    tags={**tags, "Role": "cp"},
                ),
            ],
            tags={**tags, "Name": f"{name}-lt"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.asg = aws.autoscaling.Group(
            f"{name}-asg",
            min_size=1,
            max_size=1,
            desired_capacity=1,
            vpc_zone_identifiers=[subnet_id],
            launch_template=aws.autoscaling.GroupLaunchTemplateArgs(
                id=self.launch_template.id,
                version="$Latest",
            ),
            health_check_type="EC2",
            health_check_grace_period=300,
            tags=[
                aws.autoscaling.GroupTagArgs(key=k, value=v, propagate_at_launch=True)
                for k, v in {**tags, "Name": f"{name}-asg", "Role": "cp"}.items()
            ],
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Lifecycle hook → EIP re-attach Lambda (via EventBridge)
        self.lifecycle_hook = aws.autoscaling.LifecycleHook(
            f"{name}-launching-hook",
            autoscaling_group_name=self.asg.name,
            lifecycle_transition="autoscaling:EC2_INSTANCE_LAUNCHING",
            default_result="ABANDON",
            heartbeat_timeout=600,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # EventBridge rule → Lambda
        evt_rule = aws.cloudwatch.EventRule(
            f"{name}-launching-rule",
            event_pattern=pulumi.Output.all(asg_name=self.asg.name).apply(
                lambda args: json.dumps(
                    {
                        "source": ["aws.autoscaling"],
                        "detail-type": ["EC2 Instance-launch Lifecycle Action"],
                        "detail": {"AutoScalingGroupName": [args["asg_name"]]},
                    }
                )
            ),
            tags=tags,
            opts=pulumi.ResourceOptions(parent=self),
        )
        aws.cloudwatch.EventTarget(
            f"{name}-launching-target",
            rule=evt_rule.name,
            arn=eip_reattach_arn,
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.register_outputs(
            {
                "asg_name": self.asg.name,
                "eip_public_ip": self.eip.public_ip,
            }
        )


class Worker(pulumi.ComponentResource):
    def __init__(
        self,
        name: str,
        *,
        subnet_id: pulumi.Input[str],
        security_group_ids: list[pulumi.Input[str]],
        ami_id: str,
        instance_type: str,
        instance_profile_name: pulumi.Input[str],
        cp_endpoint: pulumi.Input[str],
        tags: dict[str, str],
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        super().__init__("valheim:nodes:Worker", name, None, opts)

        self.launch_template = aws.ec2.LaunchTemplate(
            f"{name}-lt",
            image_id=ami_id,
            instance_type=instance_type,
            iam_instance_profile=aws.ec2.LaunchTemplateIamInstanceProfileArgs(
                name=instance_profile_name,
            ),
            vpc_security_group_ids=security_group_ids,
            # Worker userdata receives CP endpoint via __CP_ENDPOINT__ substitution
            user_data=cp_endpoint.apply(
                lambda ep: _userdata_for("worker", {"CP_ENDPOINT": ep})
            ),
            metadata_options=aws.ec2.LaunchTemplateMetadataOptionsArgs(
                http_endpoint="enabled",
                http_tokens="required",
                http_put_response_hop_limit=2,
            ),
            tag_specifications=[
                aws.ec2.LaunchTemplateTagSpecificationArgs(
                    resource_type="instance",
                    tags={**tags, "Role": "worker", "Name": name},
                ),
                aws.ec2.LaunchTemplateTagSpecificationArgs(
                    resource_type="volume",
                    tags={**tags, "Role": "worker"},
                ),
            ],
            tags={**tags, "Name": f"{name}-lt"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.asg = aws.autoscaling.Group(
            f"{name}-asg",
            min_size=1,
            max_size=1,
            desired_capacity=1,
            vpc_zone_identifiers=[subnet_id],
            launch_template=aws.autoscaling.GroupLaunchTemplateArgs(
                id=self.launch_template.id,
                version="$Latest",
            ),
            health_check_type="EC2",
            health_check_grace_period=300,
            tags=[
                aws.autoscaling.GroupTagArgs(key=k, value=v, propagate_at_launch=True)
                for k, v in {**tags, "Name": f"{name}-asg", "Role": "worker"}.items()
            ],
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.register_outputs({"asg_name": self.asg.name})
