##
# (c) 2022-2024 - Cloud Ops Works LLC - https://cloudops.works/
#            On GitHub: https://github.com/cloudopsworks
#            Distributed Under Apache v2.0 License
#
resource "aws_lambda_permission" "allow_scheduler_call_Lambda" {
  statement_id   = "EventBridgeSchedulerCallLambda"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.this.function_name
  principal      = "scheduler.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_lambda_permission" "allow_sqs_call_Lambda" {
  statement_id   = "SQSCallLambda"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.this.function_name
  principal      = "sqs.amazonaws.com"
  source_account = data.aws_caller_identity.current.account_id
}