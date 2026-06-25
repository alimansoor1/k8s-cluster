"""VPC with one public + one private subnet, IGW, NAT GW."""

from __future__ import annotations

import pulumi
import pulumi_aws as aws


class Network(pulumi.ComponentResource):
    """VPC topology.

    Public subnet hosts: NLB, Control Plane (with EIP), NAT GW.
    Private subnet hosts: Worker node (no public IP, NAT-egress only).
    """

    def __init__(
        self,
        name: str,
        *,
        vpc_cidr: str,
        public_cidr: str,
        private_cidr: str,
        az: str,
        tags: dict[str, str],
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        super().__init__("valheim:network:Network", name, None, opts)

        self.vpc = aws.ec2.Vpc(
            f"{name}-vpc",
            cidr_block=vpc_cidr,
            enable_dns_hostnames=True,
            enable_dns_support=True,
            tags={**tags, "Name": f"{name}-vpc"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.igw = aws.ec2.InternetGateway(
            f"{name}-igw",
            vpc_id=self.vpc.id,
            tags={**tags, "Name": f"{name}-igw"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Public subnet
        self.public_subnet = aws.ec2.Subnet(
            f"{name}-public",
            vpc_id=self.vpc.id,
            cidr_block=public_cidr,
            availability_zone=az,
            map_public_ip_on_launch=True,
            tags={**tags, "Name": f"{name}-public", "Tier": "public"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Private subnet
        self.private_subnet = aws.ec2.Subnet(
            f"{name}-private",
            vpc_id=self.vpc.id,
            cidr_block=private_cidr,
            availability_zone=az,
            map_public_ip_on_launch=False,
            tags={**tags, "Name": f"{name}-private", "Tier": "private"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # NAT GW for private subnet outbound
        self.nat_eip = aws.ec2.Eip(
            f"{name}-nat-eip",
            domain="vpc",
            tags={**tags, "Name": f"{name}-nat-eip"},
            opts=pulumi.ResourceOptions(parent=self),
        )
        self.nat_gw = aws.ec2.NatGateway(
            f"{name}-nat",
            allocation_id=self.nat_eip.id,
            subnet_id=self.public_subnet.id,
            tags={**tags, "Name": f"{name}-nat"},
            opts=pulumi.ResourceOptions(parent=self, depends_on=[self.igw]),
        )

        # Public route table → IGW
        self.public_rt = aws.ec2.RouteTable(
            f"{name}-public-rt",
            vpc_id=self.vpc.id,
            routes=[
                aws.ec2.RouteTableRouteArgs(
                    cidr_block="0.0.0.0/0",
                    gateway_id=self.igw.id,
                ),
            ],
            tags={**tags, "Name": f"{name}-public-rt"},
            opts=pulumi.ResourceOptions(parent=self),
        )
        aws.ec2.RouteTableAssociation(
            f"{name}-public-rta",
            route_table_id=self.public_rt.id,
            subnet_id=self.public_subnet.id,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # Private route table → NAT GW
        self.private_rt = aws.ec2.RouteTable(
            f"{name}-private-rt",
            vpc_id=self.vpc.id,
            routes=[
                aws.ec2.RouteTableRouteArgs(
                    cidr_block="0.0.0.0/0",
                    nat_gateway_id=self.nat_gw.id,
                ),
            ],
            tags={**tags, "Name": f"{name}-private-rt"},
            opts=pulumi.ResourceOptions(parent=self),
        )
        aws.ec2.RouteTableAssociation(
            f"{name}-private-rta",
            route_table_id=self.private_rt.id,
            subnet_id=self.private_subnet.id,
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.register_outputs(
            {
                "vpc_id": self.vpc.id,
                "public_subnet_id": self.public_subnet.id,
                "private_subnet_id": self.private_subnet.id,
            }
        )
