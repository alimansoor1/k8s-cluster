"""Lambda to auto-update talosconfig in S3 when CP EIP changes."""

from __future__ import annotations

import json

import pulumi
import pulumi_aws as aws


class TalosConfigSync(pulumi.ComponentResource):
    def __init__(self, name, *, bucket_name, talosconfig_key, tags, opts=None):
        super().__init__("valheim:lambda:TalosConfigSync", name, None, opts)

        self.role = aws.iam.Role(
            f"{name}-role",
            assume_role_policy=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }],
            }),
            tags={**tags, "Name": f"{name}-role"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        aws.iam.RolePolicyAttachment(
            f"{name}-lambda-basic",
            role=self.role.name,
            policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            opts=pulumi.ResourceOptions(parent=self),
        )

        aws.iam.RolePolicy(
            f"{name}-s3-policy",
            role=self.role.id,
            policy=pulumi.Output.all(bucket=bucket_name).apply(
                lambda args: json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:PutObject"],
                        "Resource": f"arn:aws:s3:::{args['bucket']}/*",
                    }],
                })
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

        lambda_code = f"""import json
import boto3

s3 = boto3.client("s3")
BUCKET = "{bucket_name}"
KEY = "{talosconfig_key}"

def handler(event, context):
    detail = event.get("detail", {{}})
    eip = detail.get("PublicIp") or detail.get("publicIp")
    if not eip:
        print("No PublicIp in event")\n        return {{"statusCode": 400}}
    try:
        response = s3.get_object(Bucket=BUCKET, Key=KEY)
        config = json.loads(response["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        print("talosconfig not found")\n        return {{"statusCode": 404}}
    context_name = config.get("context", "valheim")\n    if context_name in config.get("contexts", {{}}):
        config["contexts"][context_name]["endpoints"] = [eip]
        config["contexts"][context_name]["nodes"] = [eip]
    s3.put_object(Bucket=BUCKET, Key=KEY, Body=json.dumps(config, indent=4).encode(), ContentType="application/json")\n    print(f"Updated talosconfig to {{eip}}")\n    return {{"statusCode": 200}}"""

        self.function = aws.lambda_.Function(
            f"{name}-function",
            runtime="python3.12",
            handler="index.handler",
            role=self.role.arn,
            code=pulumi.AssetArchive({"index.py": pulumi.StringAsset(lambda_code)}),
            timeout=30,
            tags={**tags, "Name": f"{name}-function"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        event_rule = aws.cloudwatch.EventRule(
            f"{name}-eip-event",
            event_pattern=json.dumps({
                "source": ["aws.ec2"],
                "detail-type": ["AWS API Call via CloudTrail"],
                "detail": {
                    "eventSource": ["ec2.amazonaws.com"],
                    "eventName": ["AssociateAddress"],
                },
            }),
            tags={**tags, "Name": f"{name}-eip-event"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        aws.cloudwatch.EventTarget(
            f"{name}-eip-target",
            rule=event_rule.name,
            arn=self.function.arn,
            opts=pulumi.ResourceOptions(parent=self),
        )

        aws.lambda_.Permission(
            f"{name}-eventbridge-perm",
            action="lambda:InvokeFunction",
            function=self.function.name,
            principal="events.amazonaws.com",
            source_arn=event_rule.arn,
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.register_outputs({"lambda_arn": self.function.arn})
