"""DLM Lifecycle Policy for EBS snapshots of Valheim world saves.

Creates daily snapshots of the Valheim PVC with 7-day retention.
"""

import pulumi
import pulumi_aws as aws


class DlmSnapshotPolicy(pulumi.ComponentResource):
    def __init__(self, name, *, tags, opts=None):
        super().__init__("valheim:storage:DlmSnapshotPolicy", name, None, opts)

        self.policy = aws.dlm.LifecyclePolicy(
            f"{name}-dlm-policy",
            description="Daily snapshots of Valheim world saves",
            execution_role_arn=aws.iam.get_role(name="AWSDataLifecycleManagerDefaultRole").arn,
            state="ENABLED",
            policy_details=[aws.dlm.LifecyclePolicyPolicyDetailsArgs(
                resource_types=["VOLUME"],
                target_tags={"Role": "worker"},
                schedules=[
                    aws.dlm.LifecyclePolicyPolicyDetailsScheduleArgs(
                        name="Daily Valheim Backup",
                        create_rule=aws.dlm.LifecyclePolicyPolicyDetailsScheduleCreateRuleArgs(
                            interval=24,
                            interval_unit="HOURS",
                            times=["03:00"],
                        ),
                        retain_rule=aws.dlm.LifecyclePolicyPolicyDetailsScheduleRetainRuleArgs(
                            count=7,
                        ),
                        tags_to_add={**tags, "Name": f"{name}-valheim-snapshot"},
                        copy_tags=True,
                    ),
                ],
            )],
            tags={**tags, "Name": f"{name}-dlm-policy"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.register_outputs({"policy_id": self.policy.id})
