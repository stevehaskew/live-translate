# Local variables
locals {
  api_domain_name = var.api_domain_name != "" ? var.api_domain_name : "api.${var.domain_name}"
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# DynamoDB table for WebSocket connections
resource "aws_dynamodb_table" "connections" {
  name           = "${var.project_name}-connections-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "client_id"

  attribute {
    name = "client_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-connections-${var.environment}"
  })
}

# S3 bucket for static website hosting
resource "aws_s3_bucket" "website" {
  bucket = "${var.project_name}-website-${var.environment}"

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-website-${var.environment}"
  })
}

resource "aws_s3_bucket_public_access_block" "website" {
  bucket = aws_s3_bucket.website.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 bucket policy for CloudFront access
resource "aws_s3_bucket_policy" "website" {
  bucket = aws_s3_bucket.website.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontAccess"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.website.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.website.arn
          }
        }
      }
    ]
  })
}

# CloudFront Origin Access Control
resource "aws_cloudfront_origin_access_control" "website" {
  name                              = "${var.project_name}-website-oac-${var.environment}"
  description                       = "OAC for ${var.project_name} website"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# CloudFront distribution for static website
resource "aws_cloudfront_distribution" "website" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  aliases             = [var.domain_name]

  origin {
    domain_name              = aws_s3_bucket.website.bucket_regional_domain_name
    origin_id                = "S3-${aws_s3_bucket.website.id}"
    origin_access_control_id = aws_cloudfront_origin_access_control.website.id
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.website.id}"

    forwarded_values {
      query_string = false

      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
    compress               = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.cloudfront.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-website-${var.environment}"
  })
}

# IAM role for Lambda function
resource "aws_iam_role" "lambda_execution" {
  name = "${var.project_name}-lambda-execution-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = local.common_tags
}

# IAM role for Transcribe service (to be assumed by Lambda for token generation)
resource "aws_iam_role" "transcribe_client" {
  count = var.enable_token_generation ? 1 : 0
  name  = "${var.project_name}-transcribe-client-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowLambdaExecutionRoleToAssume"
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.lambda_execution.arn
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-transcribe-client-${var.environment}"
  })
}

# IAM policy for Transcribe client role
resource "aws_iam_role_policy" "transcribe_client" {
  count = var.enable_token_generation ? 1 : 0
  name  = "${var.project_name}-transcribe-policy-${var.environment}"
  role  = aws_iam_role.transcribe_client[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "transcribe:StartStreamTranscription"
        ]
        Resource = "*"
      }
    ]
  })
}

# IAM policy for Lambda execution
resource "aws_iam_role_policy" "lambda_execution" {
  name = "${var.project_name}-lambda-policy-${var.environment}"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:DeleteItem",
          "dynamodb:UpdateItem",
          "dynamodb:Scan"
        ]
        Resource = aws_dynamodb_table.connections.arn
      },
      {
        Effect = "Allow"
        Action = [
          "execute-api:ManageConnections"
        ]
        Resource = "arn:aws:execute-api:${var.aws_region}:*:${aws_apigatewayv2_api.websocket.id}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "execute-api:Invoke"
        ]
        # Allow invoking the PostToConnection management endpoint for any connection id on any stage
        Resource = [
          "arn:aws:execute-api:${var.aws_region}:*:${aws_apigatewayv2_api.websocket.id}/*/POST/@connections/*",
          "arn:aws:execute-api:${var.aws_region}:*:${aws_apigatewayv2_api.websocket.id}/*/POST/*/@connections/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "translate:TranslateText",
          "comprehend:DetectDominantLanguage"
        ]
        Resource = "*"
      }
    ]
  })
}

# Additional IAM policy for Lambda to assume Transcribe role
resource "aws_iam_role_policy" "lambda_assume_transcribe" {
  count = var.enable_token_generation ? 1 : 0
  name  = "${var.project_name}-lambda-assume-transcribe-${var.environment}"
  role  = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowAssumeTranscribeClientRole"
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Resource = aws_iam_role.transcribe_client[0].arn
      }
    ]
  })
}

# Lambda function
resource "aws_lambda_function" "websocket_handler" {
  filename         = var.lambda_zip_path
  function_name    = "${var.project_name}-websocket-handler-${var.environment}"
  role             = aws_iam_role.lambda_execution.arn
  handler          = "lambda_handler.lambda_handler"
  source_code_hash = filebase64sha256(var.lambda_zip_path)
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 512

  environment {
    variables = merge(
      {
        DYNAMODB_TABLE_NAME = aws_dynamodb_table.connections.name
        API_KEY             = var.api_key
      },
      var.enable_token_generation ? {
        TRANSCRIBE_ROLE_ARN = aws_iam_role.transcribe_client[0].arn
      } : {}
    )
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-websocket-handler-${var.environment}"
  })
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.websocket_handler.function_name}"
  retention_in_days = 7

  tags = local.common_tags
}

# WebSocket API Gateway
resource "aws_apigatewayv2_api" "websocket" {
  name                       = "${var.project_name}-websocket-${var.environment}"
  protocol_type              = "WEBSOCKET"
  route_selection_expression = "$request.body.action"

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-websocket-${var.environment}"
  })
}

# Lambda permissions for API Gateway
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.websocket_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket.execution_arn}/*"
}

# API Gateway Integration
resource "aws_apigatewayv2_integration" "lambda" {
  api_id           = aws_apigatewayv2_api.websocket.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.websocket_handler.invoke_arn
}

# API Gateway Routes
resource "aws_apigatewayv2_route" "connect" {
  api_id    = aws_apigatewayv2_api.websocket.id
  route_key = "$connect"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "disconnect" {
  api_id    = aws_apigatewayv2_api.websocket.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.websocket.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# API Gateway Stage
resource "aws_apigatewayv2_stage" "websocket" {
  api_id      = aws_apigatewayv2_api.websocket.id
  name        = var.environment
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 5000
    throttling_rate_limit  = 2000
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-websocket-stage-${var.environment}"
  })
}
