##
# (c) 2021-2025
#     Cloud Ops Works LLC - https://cloudops.works/
#     Find us on:
#       GitHub: https://github.com/cloudopsworks
#       WebSite: https://cloudops.works
#     Distributed Under Apache v2.0 License
#

resource "aws_sqs_queue" "this" {
  name                    = "${local.function_name}-sqs-queue"
  sqs_managed_sse_enabled = true
  tags                    = local.all_tags
}

resource "aws_lambda_event_source_mapping" "this" {
  event_source_arn  = aws_sqs_queue.this.arn
  function_name     = aws_lambda_function.this.arn
  starting_position = "LATEST"
  batch_size        = 5
  enabled           = true
  scaling_config {
    maximum_concurrency = 10
  }
  tags = local.all_tags
}