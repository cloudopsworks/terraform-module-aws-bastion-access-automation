##
# (c) 2021-2025
#     Cloud Ops Works LLC - https://cloudops.works/
#     Find us on:
#       GitHub: https://github.com/cloudopsworks
#       WebSite: https://cloudops.works
#     Distributed Under Apache v2.0 License
#

locals {
  sqs_queue_name      = "${local.function_name}-request-queue"
  response_queue_name = "${local.function_name}-response-queue"
}
resource "aws_sqs_queue" "this" {
  name                       = local.sqs_queue_name
  sqs_managed_sse_enabled    = true
  visibility_timeout_seconds = try(var.settings.timeout, 120) + 30
  tags                       = local.all_tags
}

resource "aws_sqs_queue" "response" {
  name                       = local.response_queue_name
  sqs_managed_sse_enabled    = true
  visibility_timeout_seconds = try(var.settings.timeout, 120) + 30
  tags                       = local.all_tags
}

resource "aws_lambda_event_source_mapping" "this" {
  event_source_arn = aws_sqs_queue.this.arn
  function_name    = aws_lambda_function.this.arn
  batch_size       = 5
  enabled          = true
  scaling_config {
    maximum_concurrency = 10
  }
  tags = local.all_tags
}

resource "aws_ssm_parameter" "sqs_queue_url" {
  name        = "/cloudopsworks/tronador/access-automation/request-queue"
  description = "Tronador Access Automation SQS Request Queue URL - ${local.system_name}"
  type        = "String"
  value       = aws_sqs_queue.this.url
  tags        = local.all_tags
}

resource "aws_ssm_parameter" "sqs_response_queue_url" {
  name        = "/cloudopsworks/tronador/access-automation/response-queue"
  description = "Tronador Access Automation SQS Response Queue URL - ${local.system_name}"
  type        = "String"
  value       = aws_sqs_queue.response.url
  tags        = local.all_tags
}