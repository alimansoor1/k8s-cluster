"""Network Load Balancer forwarding Valheim UDP traffic to the worker ASG."""

from __future__ import annotations

import pulumi
import pulumi_aws as aws


class GameNlb(pulumi.ComponentResource):
    def __init__(
        self,
        name: str,
        *,
        subnet_id: pulumi.Input[str],
        vpc_id: pulumi.Input[str],
        udp_start: int,
        udp_end: int,
        worker_asg_arn: pulumi.Input[str],
        tags: dict[str, str],
        opts: pulumi.ResourceOptions | None = None,
    ) -> None:
        super().__init__("valheim:nlb:GameNlb", name, None, opts)

        self.lb = aws.lb.LoadBalancer(
            f"{name}-lb",
            load_balancer_type="network",
            subnets=[subnet_id],
            internal=False,
            tags={**tags, "Name": f"{name}-lb"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # One target group per UDP port — NLB UDP listeners are single-port,
        # so we register a TG and listener per game port.
        self.target_groups: list[aws.lb.TargetGroup] = []
        self.listeners: list[aws.lb.Listener] = []
        for port in range(udp_start, udp_end + 1):
            tg = aws.lb.TargetGroup(
                f"{name}-tg-{port}",
                port=port,
                protocol="UDP",
                vpc_id=vpc_id,
                target_type="instance",
                health_check=aws.lb.TargetGroupHealthCheckArgs(
                    protocol="TCP",
                    port="10250",  # kubelet — proxy for "is the node up"
                    healthy_threshold=2,
                    unhealthy_threshold=2,
                    interval=30,
                ),
                tags={**tags, "Name": f"{name}-tg-{port}"},
                opts=pulumi.ResourceOptions(parent=self),
            )
            listener = aws.lb.Listener(
                f"{name}-listener-{port}",
                load_balancer_arn=self.lb.arn,
                port=port,
                protocol="UDP",
                default_actions=[
                    aws.lb.ListenerDefaultActionArgs(
                        type="forward",
                        target_group_arn=tg.arn,
                    ),
                ],
                opts=pulumi.ResourceOptions(parent=self),
            )
            # Attach the worker ASG to this target group
            aws.autoscaling.Attachment(
                f"{name}-asg-attach-{port}",
                autoscaling_group_name=worker_asg_arn,
                lb_target_group_arn=tg.arn,
                opts=pulumi.ResourceOptions(parent=self),
            )

            self.target_groups.append(tg)
            self.listeners.append(listener)

        self.register_outputs({"dns_name": self.lb.dns_name, "arn": self.lb.arn})
