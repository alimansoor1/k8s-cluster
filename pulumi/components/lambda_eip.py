"""Lambda that re-attaches the CP EIP to the ASG's new instance on launch.

Triggered by an ASG lifecycle hook on EC2_INSTANCE_LAUNCHING. The function:
  1. Looks up the EIP by tag (Project + Role=cp)
  2. Waits for the new instance to be in 'running' state
  3. Associates the EIP to the instance
  4. Calls complete-lifecycle-action so the instance enters InService
"""

from __future__ import annotations

from pathlib import Path

import pulumi
import pulumi_aws as aws


class EipReattachLambda(pulumi.ComponentResource):
    def __init__(
        self,
        name: str,
        *,
        tags: dict[str, str],
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        super().__init__("valheim:lambda:EipReattachLambda", name, None, opts)

        # Lambda execution role
        self.role = aws.iam.Role(
            f"{name}-role",
            assume_role_policy="""{
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }]
            }""",
            tags=tags,
            opts=pulumi.ResourceOptions(parent=self),
        )
        aws.iam.RolePolicyAttachment(
            f"{name}-basic-exec",
            role=self.role.name,
            policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Custom policy: describe instances, associate addresses, complete lifecycle
        aws.iam.RolePolicy(
            f"{name}-policy",
            role=self.role.id,
            policy="""{
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "ec2:DescribeInstances",
                            "ec2:DescribeAddresses",
                            "ec2:AssociateAddress",
                            "ec2:DisassociateAddress"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Effect": "Allow",
                        "Action": "autoscaling:CompleteLifecycleAction",
                        "Resource": "*"
                    }
                ]
            }""",
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Resolve path to lambda source (../../lambda/eip-reattach relative to component)
        lambda_src = Path(__file__).resolve().parents[2] / "lambda" / "eip-reattach"

        self.lambda_fn = aws.lambda_.Function(
            f"{name}-fn",
            runtime="python3.12",
            role=self.role.arn,
            handler="handler.lambda_handler",
            code=pulumi.FileArchive(str(lambda_src)),
            timeout=300,
            memory_size=256,
            tags=tags,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Permission for ASG lifecycle hook (via EventBridge) to invoke
        aws.lambda_.Permission(
            f"{name}-invoke",
            action="lambda:InvokeFunction",
            function=self.lambda_fn.name,
            principal="events.amazonaws.com",
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.register_outputs({"lambda_arn": self.lambda_fn.arn})
