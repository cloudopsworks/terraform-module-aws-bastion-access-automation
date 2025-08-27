##
# (c) 2021-2025
#     Cloud Ops Works LLC - https://cloudops.works/
#     Find us on:
#       GitHub: https://github.com/cloudopsworks
#       WebSite: https://cloudops.works
#     Distributed Under Apache v2.0 License
#

locals {
  function_name       = "access-automation-${local.system_name}"
  function_name_short = "access-automation-${local.system_name_short}"
  variables = concat(try(var.settings.environment.variables, []),
    [
      {
        name  = "ACCESS_SG_ID"
        value = var.settings.access_security_group_id
      },
      {
        name  = "ACCESS_ACL_ID"
        value = var.settings.access_acl_id
      },
      {
        name  = "BASTION_SSM_PARAMETER"
        value = var.settings.bastion_ssm_parameter
      },
      {
        name  = "SCHEDULER_ROLE_ARN"
        value = aws_iam_role.lambda_exec.arn
      },
      {
        name = "RESPONSE_QUEUE_SSM_PARAMETER"
        value = aws_ssm_parameter.sqs_response_queue_url.name
      }
    ],
    try(var.settings.max_lease_hours, null) != null ? [
      {
        name  = "ACCESS_MAX_LEASE_HOURS"
        value = var.settings.max_lease_hours
      }
    ] : []
  )
}

resource "archive_file" "lambda_code" {
  output_path = "${path.module}/.archive/${local.function_name_short}.zip"
  type        = "zip"
  source_dir  = "${path.module}/lambda_code/"
}

resource "aws_lambda_function" "this" {
  function_name    = local.function_name
  description      = try(var.settings.description, "Bastion Access Control Lambda - Region: ${data.aws_region.current.id}")
  role             = aws_iam_role.default_lambda_function.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  package_type     = "Zip"
  filename         = archive_file.lambda_code.output_path
  source_code_hash = archive_file.lambda_code.output_base64sha256
  memory_size      = try(var.settings.memory_size, 128)
  timeout          = try(var.settings.timeout, 60)
  publish          = true
  environment {
    variables = {
      for item in local.variables :
      item.name => item.value
    }
  }
  logging_config {
    application_log_level = try(var.settings.logging.application_log_level, null)
    log_format            = try(var.settings.logging.log_format, "JSON")
    log_group             = aws_cloudwatch_log_group.logs.name
    system_log_level      = try(var.settings.logging.system_log_level, null)
  }
  tags = local.all_tags
  depends_on = [
    aws_cloudwatch_log_group.logs,
    archive_file.lambda_code
  ]
}