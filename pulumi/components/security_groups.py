"""Security groups for CP, worker, and NLB.

Trust model:
  - admin (your IP)  → CP:6443 (kubectl), CP:50000 (talosctl), CP:22 NOT OPEN
  - NLB SG           → worker:UDP 2456-2458 (game)
  - CP SG            → worker:10250 (kubelet)
  - worker SG        → CP:6443 (kubelet → apiserver), CP:2379-2380 (etcd peer if needed)
  - All egress       → 0.0.0.0/0 (Talos needs to reach kube image registries, GitHub, etc.)
"""

from __future__ import annotations

import pulumi
import pulumi_aws as aws


class SecurityGroups(pulumi.ComponentResource):
    def __init__(
        self,
        name: str,
        *,
        vpc_id: pulumi.Input[str],
        admin_cidr: str,
        udp_start: int,
        udp_end: int,
        tags: dict[str, str],
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        super().__init__("valheim:network:SecurityGroups", name, None, opts)

        # NLB SG — receives UDP from the world, forwards to worker
        self.nlb = aws.ec2.SecurityGroup(
            f"{name}-nlb",
            description="Valheim NLB — public UDP ingress",
            vpc_id=vpc_id,
            ingress=[
                aws.ec2.SecurityGroupIngressArgs(
                    description="Valheim game UDP from anywhere",
                    protocol="udp",
                    from_port=udp_start,
                    to_port=udp_end,
                    cidr_blocks=["0.0.0.0/0"],
                ),
            ],
            egress=[
                aws.ec2.SecurityGroupEgressArgs(
                    protocol="-1",
                    from_port=0,
                    to_port=0,
                    cidr_blocks=["0.0.0.0/0"],
                ),
            ],
            tags={**tags, "Name": f"{name}-nlb"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # CP SG — kubectl + talosctl from admin only; no SSH
        self.cp = aws.ec2.SecurityGroup(
            f"{name}-cp",
            description="Talos Control Plane",
            vpc_id=vpc_id,
            ingress=[
                aws.ec2.SecurityGroupIngressArgs(
                    description="kube-apiserver from admin",
                    protocol="tcp",
                    from_port=6443,
                    to_port=6443,
                    cidr_blocks=[admin_cidr],
                ),
                aws.ec2.SecurityGroupIngressArgs(
                    description="talosctl from admin",
                    protocol="tcp",
                    from_port=50000,
                    to_port=50000,
                    cidr_blocks=[admin_cidr],
                ),
            ],
            egress=[
                aws.ec2.SecurityGroupEgressArgs(
                    protocol="-1",
                    from_port=0,
                    to_port=0,
                    cidr_blocks=["0.0.0.0/0"],
                ),
            ],
            tags={**tags, "Name": f"{name}-cp"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Worker SG
        # - UDP game ports from NLB SG (not from world directly)
        # - kubelet (10250) from CP SG
        # - All egress (Talos pulls images, joins cluster, etc.)
        self.worker = aws.ec2.SecurityGroup(
            f"{name}-worker",
            description="Talos worker — private",
            vpc_id=vpc_id,
            egress=[
                aws.ec2.SecurityGroupEgressArgs(
                    protocol="-1",
                    from_port=0,
                    to_port=0,
                    cidr_blocks=["0.0.0.0/0"],
                ),
            ],
            tags={**tags, "Name": f"{name}-worker"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Worker ingress rules (separated so SG references resolve cleanly)
        aws.ec2.SecurityGroupRule(
            f"{name}-worker-udp-from-nlb",
            type="ingress",
            from_port=udp_start,
            to_port=udp_end,
            protocol="udp",
            source_security_group_id=self.nlb.id,
            security_group_id=self.worker.id,
            description="Valheim UDP from NLB only",
            opts=pulumi.ResourceOptions(parent=self),
        )

        aws.ec2.SecurityGroupRule(
            f"{name}-worker-kubelet-from-cp",
            type="ingress",
            from_port=10250,
            to_port=10250,
            protocol="tcp",
            source_security_group_id=self.cp.id,
            security_group_id=self.worker.id,
            description="kubelet from CP",
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Allow worker → CP for kubelet/apiserver communication
        aws.ec2.SecurityGroupRule(
            f"{name}-cp-from-worker-apiserver",
            type="ingress",
            from_port=6443,
            to_port=6443,
            protocol="tcp",
            source_security_group_id=self.worker.id,
            security_group_id=self.cp.id,
            description="apiserver from worker",
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.register_outputs(
            {
                "nlb_sg_id": self.nlb.id,
                "cp_sg_id": self.cp.id,
                "worker_sg_id": self.worker.id,
            }
        )
