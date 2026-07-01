"""Security groups for CP, worker, and NLB."""

from __future__ import annotations

import pulumi
import pulumi_aws as aws


class SecurityGroups(pulumi.ComponentResource):
    def __init__(self, name, *, vpc_id, admin_cidr, udp_start, udp_end, tags, opts=None):
        super().__init__("valheim:network:SecurityGroups", name, None, opts)

        self.nlb = aws.ec2.SecurityGroup(
            f"{name}-nlb", description="Valheim NLB", vpc_id=vpc_id,
            ingress=[aws.ec2.SecurityGroupIngressArgs(protocol="udp", from_port=udp_start, to_port=udp_end, cidr_blocks=["0.0.0.0/0"])],
            egress=[aws.ec2.SecurityGroupEgressArgs(protocol="-1", from_port=0, to_port=0, cidr_blocks=["0.0.0.0/0"])],
            tags={**tags, "Name": f"{name}-nlb"}, opts=pulumi.ResourceOptions(parent=self),
        )

        self.cp = aws.ec2.SecurityGroup(
            f"{name}-cp", description="Talos Control Plane", vpc_id=vpc_id,
            ingress=[
                aws.ec2.SecurityGroupIngressArgs(protocol="tcp", from_port=6443, to_port=6443, cidr_blocks=[admin_cidr]),
                aws.ec2.SecurityGroupIngressArgs(protocol="tcp", from_port=50000, to_port=50000, cidr_blocks=[admin_cidr]),
            ],
            egress=[aws.ec2.SecurityGroupEgressArgs(protocol="-1", from_port=0, to_port=0, cidr_blocks=["0.0.0.0/0"])],
            tags={**tags, "Name": f"{name}-cp"}, opts=pulumi.ResourceOptions(parent=self),
        )

        self.worker = aws.ec2.SecurityGroup(
            f"{name}-worker", description="Talos worker", vpc_id=vpc_id,
            egress=[aws.ec2.SecurityGroupEgressArgs(protocol="-1", from_port=0, to_port=0, cidr_blocks=["0.0.0.0/0"])],
            tags={**tags, "Name": f"{name}-worker"}, opts=pulumi.ResourceOptions(parent=self),
        )

        aws.ec2.SecurityGroupRule(f"{name}-worker-udp", type="ingress", from_port=udp_start, to_port=udp_end, protocol="udp", source_security_group_id=self.nlb.id, security_group_id=self.worker.id, opts=pulumi.ResourceOptions(parent=self))
        aws.ec2.SecurityGroupRule(f"{name}-worker-kubelet", type="ingress", from_port=10250, to_port=10250, protocol="tcp", source_security_group_id=self.cp.id, security_group_id=self.worker.id, opts=pulumi.ResourceOptions(parent=self))
        aws.ec2.SecurityGroupRule(f"{name}-cp-apiserver", type="ingress", from_port=6443, to_port=6443, protocol="tcp", source_security_group_id=self.worker.id, security_group_id=self.cp.id, opts=pulumi.ResourceOptions(parent=self))
        aws.ec2.SecurityGroupRule(f"{name}-cp-vxlan", type="ingress", from_port=8472, to_port=8472, protocol="udp", source_security_group_id=self.worker.id, security_group_id=self.cp.id, opts=pulumi.ResourceOptions(parent=self))
        aws.ec2.SecurityGroupRule(f"{name}-worker-vxlan", type="ingress", from_port=8472, to_port=8472, protocol="udp", source_security_group_id=self.cp.id, security_group_id=self.worker.id, opts=pulumi.ResourceOptions(parent=self))
        aws.ec2.SecurityGroupRule(f"{name}-cp-cilium-health", type="ingress", from_port=4240, to_port=4240, protocol="tcp", source_security_group_id=self.worker.id, security_group_id=self.cp.id, opts=pulumi.ResourceOptions(parent=self))
        aws.ec2.SecurityGroupRule(f"{name}-worker-cilium-health", type="ingress", from_port=4240, to_port=4240, protocol="tcp", source_security_group_id=self.cp.id, security_group_id=self.worker.id, opts=pulumi.ResourceOptions(parent=self))
        aws.ec2.SecurityGroupRule(f"{name}-cp-etcd", type="ingress", from_port=2379, to_port=2380, protocol="tcp", source_security_group_id=self.worker.id, security_group_id=self.cp.id, opts=pulumi.ResourceOptions(parent=self))
        aws.ec2.SecurityGroupRule(f"{name}-cp-nodeport", type="ingress", from_port=30000, to_port=32767, protocol="udp", cidr_blocks=["0.0.0.0/0"], security_group_id=self.cp.id, opts=pulumi.ResourceOptions(parent=self))
        aws.ec2.SecurityGroupRule(f"{name}-worker-nodeport", type="ingress", from_port=30000, to_port=32767, protocol="udp", cidr_blocks=["0.0.0.0/0"], security_group_id=self.worker.id, opts=pulumi.ResourceOptions(parent=self))

        self.register_outputs({"nlb_sg_id": self.nlb.id, "cp_sg_id": self.cp.id, "worker_sg_id": self.worker.id})
