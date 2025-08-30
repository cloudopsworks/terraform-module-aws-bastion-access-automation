##
# (c) 2021-2025
#     Cloud Ops Works LLC - https://cloudops.works/
#     Find us on:
#       GitHub: https://github.com/cloudopsworks
#       WebSite: https://cloudops.works
#     Distributed Under Apache v2.0 License
#

resource "aws_scheduler_schedule" "this" {
  name        = "${local.function_name_short}-bastion-shutdown"
  description = "Schedule to trigger Lambda function ${aws_lambda_function.this.function_name} for bastion host shutdown"
  flexible_time_window {
    mode = "OFF"
  }
  schedule_expression          = "cron(${var.settings.bastion_shutdown.cron})"
  schedule_expression_timezone = try(var.settings.bastion_shutdown.timezone, null)
  target {
    arn      = aws_sqs_queue.this.arn
    role_arn = aws_iam_role.scheduler_sqs.arn
    input = jsonencode({
      action = "shutdown_bastion"
    })
  }
}