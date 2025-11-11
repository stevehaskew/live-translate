# DNS and Certificate Configuration
# This file contains Route53 and ACM certificate resources for custom domains

# Data source to fetch the Route53 hosted zone
data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# ACM Certificate for CloudFront (must be in us-east-1)
resource "aws_acm_certificate" "cloudfront" {
  provider          = aws.us_east_1
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-cloudfront-cert-${var.environment}"
  })
}

# DNS validation record for CloudFront certificate
resource "aws_route53_record" "cloudfront_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.cloudfront.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.main.zone_id
}

# Certificate validation for CloudFront
resource "aws_acm_certificate_validation" "cloudfront" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.cloudfront.arn
  validation_record_fqdns = [for record in aws_route53_record.cloudfront_cert_validation : record.fqdn]
}

# ACM Certificate for API Gateway (in the configured region)
resource "aws_acm_certificate" "api_gateway" {
  domain_name       = local.api_domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-api-gateway-cert-${var.environment}"
  })
}

# DNS validation record for API Gateway certificate
resource "aws_route53_record" "api_gateway_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.api_gateway.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.main.zone_id
}

# Certificate validation for API Gateway
resource "aws_acm_certificate_validation" "api_gateway" {
  certificate_arn         = aws_acm_certificate.api_gateway.arn
  validation_record_fqdns = [for record in aws_route53_record.api_gateway_cert_validation : record.fqdn]
}

# Route53 A record for CloudFront distribution
resource "aws_route53_record" "cloudfront" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.website.domain_name
    zone_id                = aws_cloudfront_distribution.website.hosted_zone_id
    evaluate_target_health = false
  }
}

# Route53 AAAA record for CloudFront distribution (IPv6)
resource "aws_route53_record" "cloudfront_ipv6" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.website.domain_name
    zone_id                = aws_cloudfront_distribution.website.hosted_zone_id
    evaluate_target_health = false
  }
}

# Custom domain for API Gateway
resource "aws_apigatewayv2_domain_name" "websocket" {
  domain_name = local.api_domain_name

  domain_name_configuration {
    certificate_arn = aws_acm_certificate_validation.api_gateway.certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-api-domain-${var.environment}"
  })
}

# API Gateway domain mapping
resource "aws_apigatewayv2_api_mapping" "websocket" {
  api_id      = aws_apigatewayv2_api.websocket.id
  domain_name = aws_apigatewayv2_domain_name.websocket.id
  stage       = aws_apigatewayv2_stage.websocket.id
}

# Route53 A record for API Gateway custom domain
resource "aws_route53_record" "api_gateway" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = local.api_domain_name
  type    = "A"

  alias {
    name                   = aws_apigatewayv2_domain_name.websocket.domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.websocket.domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}

# Route53 AAAA record for API Gateway custom domain (IPv6)
resource "aws_route53_record" "api_gateway_ipv6" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = local.api_domain_name
  type    = "AAAA"

  alias {
    name                   = aws_apigatewayv2_domain_name.websocket.domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.websocket.domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}
