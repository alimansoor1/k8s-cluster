"""IAM roles and instance profiles for EC2 nodes.

CP and worker each get an instance profile so they can:
  - Pull EBS CSI volumes
  - Read tags (used by Talos node discovery)
  - Send logs to CloudWatch (optional)
"""

from __future__ import annotations

import json

import pulumi
import pulumi_aws as aws

EC2_ASSUME_ROLE = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
)


class EC2InstanceRoles(pulumi.ComponentResource):
    def __init__(
        self,
        name: str,
        *,
        tags: dict[str, str],
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        super().__init__("valheim:iam:EC2InstanceRoles", name, None, opts)

        # Shared inline policy: EBS, EC2 describe, CW logs
        node_policy_doc = aws.iam.get_policy_document_output(
            statements=[
                aws.iam.GetPolicyDocumentStatementArgs(
                    actions=[
                        "ec2:DescribeInstances",
                        "ec2:DescribeTags",
                        "ec2:DescribeRegions",
                        "ec2:DescribeAvailabilityZones",
                        "ec2:DescribeVolumes",
                        "ec2:DescribeVolumesModifications",
                        "ec2:AttachVolume",
                        "ec2:DetachVolume",
                        "ec2:ModifyVolume",
                        "ec2:CreateVolume",
                        "ec2:DeleteVolume",
                        "ec2:CreateTags",
                        "ec2:CreateSnapshot",
                        "ec2:DeleteSnapshot",
                        "ec2:DescribeSnapshots",
                    ],
                    resources=["*"],
                ),
                aws.iam.GetPolicyDocumentStatementArgs(
                    actions=[
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                        "logs:DescribeLogStreams",
                    ],
                    resources=["arn:aws:logs:*:*:*"],
                ),
            ]
        )

        # === Control Plane role ===
        self.cp_role = aws.iam.Role(
            f"{name}-cp",
            assume_role_policy=EC2_ASSUME_ROLE,
            tags={**tags, "Name": f"{name}-cp"},
            opts=pulumi.ResourceOptions(parent=self),
        )
        aws.iam.RolePolicy(
            f"{name}-cp-policy",
            role=self.cp_role.id,
            policy=node_policy_doc.json,
            opts=pulumi.ResourceOptions(parent=self),
        )
        # SSM allows nothing beyond what we explicitly grant — useful for break-glass
        aws.iam.RolePolicyAttachment(
            f"{name}-cp-ssm",
            role=self.cp_role.name,
            policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
            opts=pulumi.ResourceOptions(parent=self),
        )
        self.cp_instance_profile = aws.iam.InstanceProfile(
            f"{name}-cp-profile",
            role=self.cp_role.name,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # === Worker role ===
        self.worker_role = aws.iam.Role(
            f"{name}-worker",
            assume_role_policy=EC2_ASSUME_ROLE,
            tags={**tags, "Name": f"{name}-worker"},
            opts=pulumi.ResourceOptions(parent=self),
        )
        aws.iam.RolePolicy(
            f"{name}-worker-policy",
            role=self.worker_role.id,
            policy=node_policy_doc.json,
            opts=pulumi.ResourceOptions(parent=self),
        )
        aws.iam.RolePolicyAttachment(
            f"{name}-worker-ssm",
            role=self.worker_role.name,
            policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
            opts=pulumi.ResourceOptions(parent=self),
        )
        self.worker_instance_profile = aws.iam.InstanceProfile(
            f"{name}-worker-profile",
            role=self.worker_role.name,
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.register_outputs(
            {
                "cp_role_arn": self.cp_role.arn,
                "worker_role_arn": self.worker_role.arn,
            }
        )
