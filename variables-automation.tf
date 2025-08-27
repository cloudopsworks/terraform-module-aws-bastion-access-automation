##
# (c) 2021-2025
#     Cloud Ops Works LLC - https://cloudops.works/
#     Find us on:
#       GitHub: https://github.com/cloudopsworks
#       WebSite: https://cloudops.works
#     Distributed Under Apache v2.0 License
#

## Input Variable - Yaml Format
# settings:
#   access_security_group_id: "sg-xxxxxxxx" # Required - Security Group ID for access
#   access_acl_id: "acl-xxxxxxxx"   # Required - Network ACL ID for
#   bastion_ssm_parameter: "/path/to/ssm/parameter" # Required - SSM Parameter for the bastion host
#   environment:
#     variables:
#       KEY: "value"                 # Optional - Environment variables for the Lambda function
#   memory_size: 128                # Optional - Memory size for the Lambda function
#   timeout: 60                     # Optional - Timeout for the Lambda function
#   logging:                       # Optional - Logging configuration
#     log_format: JSON | TEXT       # Optional - Log format, defaults to JSON
#     application_log_level: INFO | DEBUG | ERROR # Optional - Application log level, defaults
#     system_log_level: INFO | DEBUG | ERROR      # Optional - System log level, defaults
#   description: "<description>"    # Optional - Description of the Lambda function
#   bastion_shutdown:
#     cron: "0 18 * * ? *"          # Required - Cron expression
#     timezone: "America/New_York"   # Optional - Timezone for the cron
variable "settings" {
  description = "Settings for the module"
  type        = any
  default     = {}
}
