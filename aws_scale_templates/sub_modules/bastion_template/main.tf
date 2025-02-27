/*
    This nested module creates;
    1. Bastion log group
    2. Bastion SSH metric filter
    3. Bastion Host Role
    4. Bastion Host Policy
    5. Bastion security group/Rule
    6. Bastion Autoscaling group
*/

module "bastion_log_group" {
  source                = "../../../resources/aws/logs/log_group"
  log_group_name_prefix = format("%s-bastion-log", var.resource_prefix)
}

module "bastion_ssh_metric_filter" {
  source         = "../../../resources/aws/logs/log_metric"
  log_group_name = module.bastion_log_group.log_group_name
}

module "bastion_host_iam_role" {
  source           = "../../../resources/aws/security/iam/iam_role"
  turn_on          = true
  role_name_prefix = format("%s-bastion-", var.resource_prefix)
  role_policy      = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF
}

module "bastion_host_iam_policy" {
  source                  = "../../../resources/aws/security/iam/iam_role_policy"
  turn_on                 = true
  role_policy_name_prefix = format("%s-bastion-", var.resource_prefix)
  iam_role_id             = module.bastion_host_iam_role.iam_role_id
  iam_role_policy         = <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Action": [
                "logs:CreateLogStream",
                "logs:GetLogEvents",
                "logs:PutLogEvents",
                "logs:DescribeLogGroups",
                "logs:DescribeLogStreams",
                "logs:PutRetentionPolicy",
                "logs:PutMetricFilter",
                "logs:CreateLogGroup"
            ],
            "Resource": "${module.bastion_log_group.log_group_arn}",
            "Effect": "Allow"
        },
        {
            "Action": [
                "ec2:AssociateAddress",
                "ec2:DescribeAddresses"
            ],
            "Resource": "*",
            "Effect": "Allow"
        }
    ]
}
EOF
}

module "bastion_instance_iam_profile" {
  source                       = "../../../resources/aws/security/iam/iam_instance_profile"
  turn_on                      = true
  instance_profile_name_prefix = format("%s-bastion-", var.resource_prefix)
  iam_host_role                = module.bastion_host_iam_policy.role_policy_name
}

module "bastion_security_group" {
  source                = "../../../resources/aws/security/security_group"
  turn_on               = true
  sec_group_name        = [format("%s-%s", var.resource_prefix, "bastion-sg")]
  sec_group_description = ["Enable SSH access to the bastion host from external via SSH port"]
  vpc_id                = var.vpc_ref
  sec_group_tag         = ["bastion-sec-group"]
}

module "bastion_security_rule" {
  source      = "../../../resources/aws/security/security_rule_cidr"
  total_rules = 2
  security_group_id = [module.bastion_security_group.sec_group_id,
  module.bastion_security_group.sec_group_id]
  security_rule_description = ["Incoming traffic to bastion",
  "Incoming ICMP traffic to bastion"]
  security_rule_type       = ["ingress", "ingress"]
  traffic_protocol         = ["TCP", "icmp"]
  traffic_from_port        = [var.bastion_public_ssh_port, "-1"]
  traffic_to_port          = [var.bastion_public_ssh_port, "-1"]
  cidr_blocks              = var.remote_cidr_blocks
  security_prefix_list_ids = null
}

module "bastion_egress_security_rule" {
  source                    = "../../../resources/aws/security/security_rule_cidr"
  total_rules               = 1
  security_group_id         = [module.bastion_security_group.sec_group_id]
  security_rule_description = ["Outgoing traffic from bastion to instances"]
  security_rule_type        = ["egress"]
  traffic_protocol          = ["-1"]
  traffic_from_port         = ["0"]
  traffic_to_port           = ["65535"]
  cidr_blocks               = ["0.0.0.0/0"]
  security_prefix_list_ids  = null
}

module "bastion_autoscaling_launch_template" {
  source                      = "../../../resources/aws/asg/launch_template"
  turn_on                     = true
  launch_template_name_prefix = format("%s-%s", var.resource_prefix, "bastion-launch-tmpl")
  image_id                    = var.bastion_image_ref
  instance_type               = var.bastion_instance_type
  instance_iam_profile        = module.bastion_instance_iam_profile.iam_instance_profile_name[0]
  enable_userdata             = false
  meta_private_key            = ""
  meta_public_key             = ""
  enable_public_ip_address    = true
  key_name                    = var.bastion_key_pair
  sec_groups                  = [module.bastion_security_group.sec_group_id]
}

module "bastion_autoscaling_group" {
  source                     = "../../../resources/aws/asg/asg_group"
  turn_on                    = true
  asg_name_prefix            = format("%s-%s", var.resource_prefix, "bastion-asg")
  asg_launch_template_id     = module.bastion_autoscaling_launch_template.asg_launch_template_id
  asg_max_size               = 1
  asg_min_size               = 1
  asg_desired_size           = 1
  auto_scaling_group_subnets = var.vpc_auto_scaling_group_subnets
  asg_suspend_processes      = ["AZRebalance"]
  asg_tags                   = tomap({ "key" = "Name", "value" = format("%s-%s", var.resource_prefix, "bastion-asg") })
}
