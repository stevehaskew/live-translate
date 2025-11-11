output "cloudfront_distribution_url" {
  description = "CloudFront distribution URL for the static website"
  value       = aws_cloudfront_distribution.website.domain_name
}

output "cloudfront_custom_domain" {
  description = "Custom domain name for the static website"
  value       = var.domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.website.id
}

output "s3_bucket_name" {
  description = "S3 bucket name for static website files"
  value       = aws_s3_bucket.website.id
}

output "websocket_api_endpoint" {
  description = "WebSocket API Gateway endpoint URL"
  value       = "wss://${local.api_domain_name}/${var.environment}"
}

output "websocket_api_default_endpoint" {
  description = "WebSocket API Gateway default endpoint URL"
  value       = aws_apigatewayv2_stage.websocket.invoke_url
}

output "websocket_api_id" {
  description = "WebSocket API Gateway ID"
  value       = aws_apigatewayv2_api.websocket.id
}

output "dynamodb_table_name" {
  description = "DynamoDB table name for client connections"
  value       = aws_dynamodb_table.connections.name
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.websocket_handler.function_name
}

output "api_domain" {
  description = "The API domain name configured"
  value       = local.api_domain_name
}

output "route53_zone_id" {
  description = "Route53 hosted zone ID"
  value       = data.aws_route53_zone.main.zone_id
}

output "acm_certificate_arn_cloudfront" {
  description = "ACM certificate ARN for CloudFront"
  value       = aws_acm_certificate.cloudfront.arn
}

output "acm_certificate_arn_api_gateway" {
  description = "ACM certificate ARN for API Gateway"
  value       = aws_acm_certificate.api_gateway.arn
}
