"""Valheim K8s infrastructure on AWS."""

from __future__ import annotations

import sys
from pathlib import Path

import pulumi

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from components.iam import EC2InstanceRoles
from components.lambda_eip import EipReattachLambda
from components.network import Network
from components.nodes import ControlPlane, Worker
from components.security_groups import SecurityGroups
from components.dlm_snapshot import DlmSnapshotPolicy
# from components.nlb import GameNlb

config = pulumi.Config()

PROJECT = config.require("project_name")
ENV = config.require("env")
AZ = config.require("az")
ADMIN_CIDR = config.require("admin_cidr")

VPC_CIDR = config.require("vpc_cidr")
PUBLIC_CIDR = config.require("public_subnet_cidr")
PRIVATE_CIDR = config.require("private_subnet_cidr")

CP_TYPE = config.require("cp_instance_type")
WORKER_TYPE = config.require("worker_instance_type")
TALOS_AMI = config.require("talos_ami_id")

UDP_START = int(config.require("valheim_udp_start"))
UDP_END = int(config.require("valheim_udp_end"))

if ADMIN_CIDR.startswith("REPLACE_ME"):
    raise pulumi.RunError(
        "admin_cidr is not set. Run: pulumi config set admin_cidr <your-ip>/32"
    )
if TALOS_AMI.startswith("REPLACE_ME"):
    raise pulumi.RunError(
        "talos_ami_id is not set. See talos/scripts/import-ami.sh, then run: "
        "pulumi config set talos_ami_id <ami-id>"
    )

tags = {
    "Project": PROJECT,
    "Env": ENV,
    "ManagedBy": "pulumi",
}

# === 1. Network ===
network = Network(
    "network",
    vpc_cidr=VPC_CIDR,
    public_cidr=PUBLIC_CIDR,
    private_cidr=PRIVATE_CIDR,
    az=AZ,
    tags=tags,
)

# === 2. Security groups ===
sgs = SecurityGroups(
    "sgs",
    vpc_id=network.vpc.id,
    admin_cidr=ADMIN_CIDR,
    udp_start=UDP_START,
    udp_end=UDP_END,
    tags=tags,
)

# === 3. IAM roles for EC2 instances ===
iam = EC2InstanceRoles("iam", tags=tags)

# === 4. EIP re-attach Lambda ===
eip_lambda = EipReattachLambda("eip-lambda", tags=tags)

# === 5. Control Plane (public subnet, with EIP) ===
control_plane = ControlPlane(
    "cp",
    subnet_id=network.public_subnet.id,
    security_group_ids=[sgs.cp.id],
    ami_id=TALOS_AMI,
    instance_type=CP_TYPE,
    instance_profile_name=iam.cp_instance_profile.name,
    eip_reattach_arn=eip_lambda.lambda_fn.arn,
    tags=tags,
)

# === 6. Worker (private subnet, no public IP) ===
worker = Worker(
    "worker",
    subnet_id=network.private_subnet.id,
    security_group_ids=[sgs.worker.id],
    ami_id=TALOS_AMI,
    instance_type=WORKER_TYPE,
    instance_profile_name=iam.worker_instance_profile.name,
    cp_endpoint=control_plane.eip.public_ip,
    tags=tags,
)

# === 7. NLB - DISABLED until AWS enables ELBv2 ===
# Uncomment this section and add "# from components.nlb import GameNlb"
# to the imports at the top when AWS Support enables ELBv2,
# then run: pulumi up --yes
#
# nlb = GameNlb(
#     "valheim-nlb",
#     subnet_id=network.public_subnet.id,
#     vpc_id=network.vpc.id,
#     udp_start=UDP_START,
#     udp_end=UDP_END,
#     worker_asg_arn=worker.asg.arn,
#     tags=tags,
# )


# === 8. DLM Snapshot Policy ===
dlm = DlmSnapshotPolicy(
    "valheim-dlm",
    tags=tags,
)

# === Outputs ===
pulumi.export("vpc_id", network.vpc.id)
pulumi.export("public_subnet_id", network.public_subnet.id)
pulumi.export("private_subnet_id", network.private_subnet.id)
pulumi.export("cp_eip_public_ip", control_plane.eip.public_ip)
pulumi.export("cp_asg_name", control_plane.asg.name)
pulumi.export("worker_asg_name", worker.asg.name)
# pulumi.export("nlb_dns_name", nlb.lb.dns_name)
# pulumi.export("nlb_arn", nlb.lb.arn)
