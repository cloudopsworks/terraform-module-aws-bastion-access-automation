##
# (c) 2021-2025
#     Cloud Ops Works LLC - https://cloudops.works/
#     Find us on:
#       GitHub: https://github.com/cloudopsworks
#       WebSite: https://cloudops.works
#     Distributed Under Apache v2.0 License
#

import boto3
import os
import json
import logging
from datetime import datetime, timedelta, timezone
import time

logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', logging.INFO))

def lambda_handler(event, context):
    """
    Lambda function to handle Bastion Access Automation requests.

    Events are received from SQS and processed to manage user access.
    Events from EventBridge to perform shutdown Bastion Host after a timeout and for access removal on SG and ACLs.
    It will manage the following upon event:
    - Start Bastion Host if not running, bastion host information is configured in SSM Parameter Store
    - Allow user access via Security Group modification for a limited time, will modify ACLs if configured
    - Remove user access via Security Group modification and ACLs upon event from EventBridge
    """
    logger.debug(f"Received event: {json.dumps(event)}")

    # Process SQS events
    if 'Records' in event:
        for record in event['Records']:
            try:
                message = json.loads(record['body'])
                message_id = record.get('MessageId')
                process_access_request(context, message, message_id)
            except Exception as e:
                logger.error(f"Error processing record: {e}")

    # Process EventBridge events
    elif 'detail-type' in event:
        try:
            process_eventbridge_event(context, event)
        except Exception as e:
            logger.error(f"Error processing EventBridge event: {e}")

    else:
        logger.warning("Received unknown event format.")

    return {
        'statusCode': 200,
        'body': json.dumps('Processing complete')
    }


def _permission_exists(target_permission, existing_permissions):
    """
    Check if a target permission already exists in the list of existing permissions.
    Compares only the essential fields: IpProtocol, FromPort, ToPort, and CIDR blocks.
    """
    target_protocol = target_permission.get('IpProtocol')
    target_from_port = target_permission.get('FromPort')
    target_to_port = target_permission.get('ToPort')
    target_cidrs = {ip_range.get('CidrIp') for ip_range in target_permission.get('IpRanges', [])}

    for existing_perm in existing_permissions:
        # Check if protocol and ports match
        if (existing_perm.get('IpProtocol') == target_protocol and
                existing_perm.get('FromPort') == target_from_port and
                existing_perm.get('ToPort') == target_to_port):

            # Check if any of the target CIDR blocks already exist
            existing_cidrs = {ip_range.get('CidrIp') for ip_range in existing_perm.get('IpRanges', [])}
            if target_cidrs.intersection(existing_cidrs):
                return True

    return False


def process_access_request(context, message, message_id):
    """
    Process access request messages from SQS.
    message will contain following fields:
    - ip_address: The IP address of the user requesting access
    - service: ssh or rdp
    bastion host information is configured in SSM Parameter Store
    """
    lease_period = int(os.environ.get('ACCESS_MAX_LEASE_HOURS', '8'))

    ip_address = message.get('ip_address')
    service = message.get('service')
    lease_request = message.get('lease_request', lease_period)
    if lease_request > lease_period:
        lease_request = lease_period

    if not ip_address or not service:
        logger.error("Invalid access request message format.")
        return

    logger.info(f"Processing access request for IP: {ip_address}, Service: {service}")

    # Retrieve Bastion Host details from SSM Parameter Store
    ssm = boto3.client('ssm')
    ec2 = boto3.client('ec2')
    scheduler = boto3.client('scheduler')

    try:
        bastion_instance_id = ssm.get_parameter(Name=os.environ['BASTION_SSM_PARAMETER'])['Parameter']['Value']
    except Exception as e:
        logger.error(f"Error retrieving Bastion Host details from SSM: {e}")
        return

    security_group_id = os.environ['ACCESS_SG_ID']
    vpc_acl_id = os.environ['ACCESS_ACL_ID']

    # Modify Security Group to allow access ensuring no duplicate rules
    try:
        existing_permissions = ec2.describe_security_groups(GroupIds=[security_group_id])['SecurityGroups'][0]['IpPermissions']
        port = 22 if service.lower() == 'ssh' else 3389
        ip_permission = {
            'IpProtocol': 'tcp',
            'FromPort': port,
            'ToPort': port,
            'IpRanges': [{'CidrIp': f'{ip_address}/32'}]
        }
        if not _permission_exists(ip_permission, existing_permissions):
            logger.info(f"Adding access rule to Security Group {security_group_id} for IP {ip_address}")
            ec2.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[ip_permission]
            )
        else:
            logger.info(f"Access rule for IP {ip_address} already exists in Security Group {security_group_id}")
    except Exception as e:
        logger.error(f"Error modifying Security Group: {e}")
        return

    # Modify Network ACL to allow access, if configured ensure no duplicate rules and use reserved rule numbers from 1400 to 1499, vpc_acl_id is required precondition
    try:
        nacl = ec2.describe_network_acls(NetworkAclIds=[vpc_acl_id])['NetworkAcls'][0]
        port = 22 if service.lower() == 'ssh' else 3389
        # rule number between 1400 and 1499 to avoid conflicts check existing rules
        # scrub existing rules to find an available rule number and if currently cidr block exists within the range
        existing_rule_numbers = {entry['RuleNumber'] for entry in nacl['Entries']}
        existing_cidrs = {entry['CidrBlock'] for entry in nacl['Entries'] if entry['RuleAction'] == 'allow' and entry['Protocol'] == '6' and entry['PortRange']['From'] == port}
        rule_number = None
        permanent_access = False
        for rn in range(9400, 9500):
            if rn not in existing_rule_numbers:
                rule_number = rn
                break
        if not rule_number:
            logger.error("No available rule number in the reserved range 1400-1499 for Network ACL.")
            return
        if f'{ip_address}/32' not in existing_cidrs:
            logger.info(f"Adding access rule to Network ACL {vpc_acl_id} for IP {ip_address}")
            ec2.create_network_acl_entry(
                NetworkAclId=vpc_acl_id,
                RuleNumber=rule_number,
                Protocol='6',
                RuleAction='allow',
                Egress=False,
                CidrBlock=f'{ip_address}/32',
                PortRange={
                    'From': port,
                    'To': port
                }
            )
        else:
            logger.info(f"Access rule for IP {ip_address} already exists in Network ACL {vpc_acl_id}, Retrieving existing rule number.")
            for entry in nacl['Entries']:
                if (entry['RuleAction'] == 'allow' and entry['Protocol'] == '6' and
                        entry['PortRange']['From'] == port and entry['CidrBlock'] == f'{ip_address}/32'):
                    rule_number = entry['RuleNumber']
                    if rule_number < 9400 or rule_number > 9499:
                        logger.warning(f"Existing rule number {rule_number} for IP {ip_address} is outside the reserved range 1400-1499. Access is Permanent or Consider manual cleanup.")
                        permanent_access = True
                    logger.info(f"Found existing rule number {rule_number} for IP {ip_address} in Network ACL {vpc_acl_id}.")
                    break
    except Exception as e:
        logger.error(f"Error modifying Network ACL: {e}")
        return

    logger.info(f"Access granted to IP {ip_address} for service {service}.")

    # Start Bastion Host if not running
    try:
        instance_status = ec2.describe_instance_status(InstanceIds=[bastion_instance_id])
        if not instance_status['InstanceStatuses']:
            logger.info(f"Starting Bastion Host: {bastion_instance_id}")
            ec2.start_instances(InstanceIds=[bastion_instance_id])
            waiter = ec2.get_waiter('instance_running')
            waiter.wait(InstanceIds=[bastion_instance_id])
            logger.info(f"Bastion Host {bastion_instance_id} is now running.")
        else:
            logger.info(f"Bastion Host {bastion_instance_id} is already running.")
    except Exception as e:
        logger.error(f"Error starting Bastion Host: {e}")
        return

    # Wait until the instance is fully registered in SSM before proceeding, timeout after 50 seconds
    try:
        logger.info(f"Waiting for Bastion Host {bastion_instance_id} to be registered in SSM.")
        ssm_available = False
        for i in range(1, 100):
            response = ssm.describe_instance_information(
                Filters=[{'Key': 'InstanceIds', 'Values': [bastion_instance_id]}])
            if len(response["InstanceInformationList"]) > 0 and \
                    response["InstanceInformationList"][0]["PingStatus"] == "Online" and \
                    response["InstanceInformationList"][0]["InstanceId"] == bastion_instance_id:
                ssm_available = True
                break
            time.sleep(5)
        if ssm_available:
            logger.info(f"Bastion Host {bastion_instance_id} is now registered in SSM.")
        else:
            logger.warning(f"Bastion Host {bastion_instance_id} is not registered in SSM after waiting.")
    except Exception as e:
        logger.error(f"Error waiting for Bastion Host to register in SSM: {e}")
        return

    # Save a single EventBridge Scheduler to remove access after timeout of 8 hours
    # as part of the event payload include ip_address, service and acl rule_number
    # the event will be ephemeral and auto delete after execution
    try:
        if not permanent_access:
            schedule_name = f"remove-access-{ip_address.replace('.', '-')}-{service}"
            # calculate lease end time from currenti time plus lease period in hours and convert to format required by EventBridge Scheduler
            lease_end_time = (datetime.now(timezone.utc) + timedelta(hours=lease_request)).strftime('%Y-%m-%dT%H:%M:%S')
            schedule_expression = f"at({lease_end_time})"
            target = {
                'Arn': context.invoked_function_arn,
                'RoleArn': os.environ['SCHEDULER_ROLE_ARN'],  # IAM Role ARN with permissions to invoke this Lambda
                'Input': json.dumps({
                    'detail-type': 'BastionAccessRemoval',
                    'detail': {
                        'action': 'remove_access',
                        'ip_address': ip_address,
                        'service': service,
                        'rule_number': rule_number
                    }
                })
            }
            logger.info(f"Creating EventBridge Scheduler {schedule_name} to remove access after ${lease_request} hours.")
            scheduler.create_schedule(
                Name=schedule_name,
                ScheduleExpression=schedule_expression,
                State='ENABLED',
                FlexibleTimeWindow={'Mode': 'OFF'},
                Target=target,
                Description='Schedule to remove Bastion access after timeout',
                ActionAfterCompletion='DELETE'
            )
            logger.info(f"EventBridge Scheduler {schedule_name} created successfully.")
        else:
            logger.info("Permanent access detected, skipping EventBridge Scheduler creation.")
    except Exception as e:
        logger.error(f"Error creating EventBridge Scheduler: {e}")
        return


def process_eventbridge_event(context, event):
    """
    Process EventBridge events for access removal and Bastion Host shutdown.
    EventBridge events will contain an 'action' field to determine the type of event:
    - action: 'remove_access' or 'shutdown_bastion'
    """
    action = event.get('detail', {}).get('action')

    ssm = boto3.client('ssm')
    ec2 = boto3.client('ec2')

    if action == 'remove_access':
        ip_address = event['detail'].get('ip_address')
        service = event['detail'].get('service')
        rule_number = event['detail'].get('rule_number')

        if not ip_address or not service or rule_number is None:
            logger.error("Invalid remove access event format.")
            return

        logger.info(f"Processing access removal for IP: {ip_address}, Service: {service}")

        security_group_id = os.environ['ACCESS_SG_ID']
        vpc_acl_id = os.environ['ACCESS_ACL_ID']

        # Remove access from Security Group
        try:
            port = 22 if service.lower() == 'ssh' else 3389
            ip_permission = {
                'IpProtocol': 'tcp',
                'FromPort': port,
                'ToPort': port,
                'IpRanges': [{'CidrIp': f'{ip_address}/32'}]
            }
            logger.info(f"Removing access rule from Security Group {security_group_id} for IP {ip_address}")
            ec2.revoke_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[ip_permission]
            )
        except Exception as e:
            logger.error(f"Error removing access from Security Group: {e}")

        # Remove access from Network ACL, if configured
        try:
            logger.info(f"Removing access rule from Network ACL {vpc_acl_id} for IP {ip_address}")
            ec2.delete_network_acl_entry(
                NetworkAclId=vpc_acl_id,
                RuleNumber=rule_number,
                Egress=False
            )
        except Exception as e:
            logger.error(f"Error removing access from Network ACL: {e}")

    if action == 'shutdown_bastion':
        logger.info("Processing Bastion Host shutdown event.")

        # Retrieve Bastion Host details from SSM Parameter Store
        try:
            bastion_instance_id = ssm.get_parameter(Name=os.environ['BASTION_SSM_PARAMETER'])['Parameter']['Value']
        except Exception as e:
            logger.error(f"Error retrieving Bastion Host details from SSM: {e}")
            return

        # Stop Bastion Host if running
        try:
            instance_status = ec2.describe_instance_status(InstanceIds=[bastion_instance_id])
            if instance_status['InstanceStatuses']:
                logger.info(f"Stopping Bastion Host: {bastion_instance_id}")
                ec2.stop_instances(InstanceIds=[bastion_instance_id])
                waiter = ec2.get_waiter('instance_stopped')
                waiter.wait(InstanceIds=[bastion_instance_id])
                logger.info(f"Bastion Host {bastion_instance_id} is now stopped.")
            else:
                logger.info(f"Bastion Host {bastion_instance_id} is already stopped.")
        except Exception as e:
            logger.error(f"Error stopping Bastion Host: {e}")
            return