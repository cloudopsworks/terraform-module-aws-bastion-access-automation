##
# (c) 2021-2025
#     Cloud Ops Works LLC - https://cloudops.works/
#     Find us on:
#       GitHub: https://github.com/cloudopsworks
#       WebSite: https://cloudops.works
#     Distributed Under Apache v2.0 License
#
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = [
      "sts:AssumeRole"
    ]
    principals {
      type = "Service"
      identifiers = [
        "lambda.amazonaws.com",
        "scheduler.amazonaws.com",
      ]
    }
  }
}

data "aws_iam_policy_document" "lambda_exec" {
  statement {
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction",
      "lambda:InvokeAsync"
    ]
    resources = [
      aws_lambda_function.this.arn,
      "${aws_lambda_function.this.arn}:*"
    ]
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${local.function_name_short}-exec-role"
  path               = "/"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role[0].json
  tags               = local.all_tags
}

resource "aws_iam_role_policy" "lambda_exec" {
  name   = "${local.function_name_short}-exec-policy"
  policy = data.aws_iam_policy_document.lambda_exec.json
  role   = aws_iam_role.lambda_exec[0].id
}
