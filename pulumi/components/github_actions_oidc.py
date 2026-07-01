"""GitHub Actions OIDC IAM Role for Pulumi deployments."""

from __future__ import annotations

import json

import pulumi
import pulumi_aws as aws


class GitHubActionsOIDC(pulumi.ComponentResource):
    def __init__(self, name, *, github_org, github_repo, tags, opts=None):
        super().__init__("valheim:iam:GitHubActionsOIDC", name, None, opts)

        self.oidc_provider = aws.iam.OpenIdConnectProvider(
            f"{name}-github-oidc",
            url="https://token.actions.githubusercontent.com",
            client_id_lists=["sts.amazonaws.com"],
            thumbprint_lists=["6938fd4e98bab03faadb97b34396831e3780aea1"],
            tags={**tags, "Name": f"{name}-github-oidc"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        assume_role_policy = pulumi.Output.all(oidc_arn=self.oidc_provider.arn).apply(
            lambda args: json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Federated": args["oidc_arn"]},
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringEquals": {
                            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                        },
                        "StringLike": {
                            "token.actions.githubusercontent.com:sub": f"repo:{github_org}/{github_repo}:*",
                        },
                    },
                }],
            })
        )

        self.role = aws.iam.Role(
            f"{name}-pulumi-role",
            assume_role_policy=assume_role_policy,
            tags={**tags, "Name": f"{name}-pulumi-role"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        aws.iam.RolePolicyAttachment(
            f"{name}-admin-policy",
            role=self.role.name,
            policy_arn="arn:aws:iam::aws:policy/AdministratorAccess",
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.register_outputs({"role_arn": self.role.arn})
