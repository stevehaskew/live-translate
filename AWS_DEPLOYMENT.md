# AWS Deployment Guide

This document provides a comprehensive guide for deploying Live Translation to AWS using the serverless architecture.

## Overview

The AWS deployment uses:
- **API Gateway (WebSocket)** - Real-time bidirectional communication
- **AWS Lambda (Python 3.12)** - Serverless compute for message handling
- **DynamoDB** - Distributed client connection storage
- **S3 + CloudFront** - Global static website hosting
- **Terraform** - Infrastructure as Code

## Prerequisites

Before you begin, ensure you have:

1. **AWS Account** with appropriate permissions
2. **AWS CLI** installed and configured (`aws configure`)
3. **Terraform** >= 1.0 installed
4. **Python 3.12** for building the Lambda package
5. **Git** for cloning the repository

### Required AWS Permissions

Your AWS user/role needs permissions for:
- API Gateway (create, update, delete WebSocket APIs)
- Lambda (create, update, delete functions)
- DynamoDB (create, update, delete tables)
- S3 (create buckets, upload files)
- CloudFront (create distributions)
- IAM (create roles and policies)
- CloudWatch Logs (create log groups)

## Step-by-Step Deployment

### Step 1: Clone and Prepare

```bash
# Clone the repository
git clone https://github.com/stevehaskew/live-translate.git
cd live-translate

# Ensure you have dependencies installed
pip install boto3 python-dotenv
```

### Step 2: Build Lambda Deployment Package

```bash
# Run the build script
./scripts/build_lambda.sh

# Verify the package was created
ls -lh lambda_deployment.zip
```

Expected output:
```
✓ Lambda deployment package created: /path/to/lambda_deployment.zip
Package size: 16M
```

### Step 3: Configure Terraform Variables

```bash
cd terraform

# Copy the example variables file
cp terraform.tfvars.example terraform.tfvars

# Generate a secure API key
openssl rand -base64 32

# Edit terraform.tfvars with your values
nano terraform.tfvars
```

**Required Configuration:**

```hcl
# AWS region
aws_region = "us-east-1"

# Your domain name (CloudFront will use this as an alias)
domain_name = "translate.example.com"

# API key (use the one generated above)
api_key = "your-secure-api-key-here"

# Environment name
environment = "production"

# Project name (used for resource naming)
project_name = "live-translate"
```

**Optional Configuration:**

```hcl
# Custom API domain (defaults to "api.{domain_name}")
api_domain_name = "ws.translate.example.com"
```

### Step 4: Deploy Infrastructure

```bash
# Initialize Terraform (downloads required providers)
terraform init

# Preview the changes
terraform plan

# Review the plan, then apply
terraform apply
```

Terraform will create:
- 1 DynamoDB table
- 1 Lambda function
- 1 API Gateway WebSocket API
- 1 S3 bucket
- 1 CloudFront distribution
- IAM roles and policies
- CloudWatch Log Groups

This process takes approximately 5-10 minutes.

### Step 5: Upload Static Website Files

After Terraform completes, upload the website files to S3:

```bash
# Get the S3 bucket name
BUCKET_NAME=$(terraform output -raw s3_bucket_name)

# Sync static files (excludes .gitignore and .example files)
aws s3 sync ../static/ s3://$BUCKET_NAME/ \
  --exclude ".gitignore" \
  --exclude "*.example"

# Verify files were uploaded
aws s3 ls s3://$BUCKET_NAME/
```

### Step 6: Create Configuration File

Create and upload the `config.json` file:

```bash
# Get the WebSocket endpoint
WS_ENDPOINT=$(terraform output -raw websocket_api_endpoint)

# Create config.json
cat > config.json << EOF
{
  "logoFile": "",
  "pageTitle": "🌍 Live Translation",
  "contactText": "support@example.com",
  "websocketUrl": "$WS_ENDPOINT"
}
EOF

# Upload to S3
aws s3 cp config.json s3://$BUCKET_NAME/

# Verify
aws s3 ls s3://$BUCKET_NAME/config.json
```

### Step 7: (Optional) Upload Custom Logo

If you have a custom logo:

```bash
# Upload logo
aws s3 cp /path/to/your/logo.png s3://$BUCKET_NAME/logo.png

# Update config.json to reference it
cat > config.json << EOF
{
  "logoFile": "logo.png",
  "pageTitle": "🌍 Live Translation",
  "contactText": "support@example.com",
  "websocketUrl": "$WS_ENDPOINT"
}
EOF

aws s3 cp config.json s3://$BUCKET_NAME/
```

### Step 8: Configure DNS

Get the CloudFront and API Gateway endpoints:

```bash
# CloudFront domain for static website
terraform output cloudfront_distribution_url

# API Gateway WebSocket endpoint
terraform output websocket_api_endpoint
```

**Configure DNS Records:**

1. **Static Website (CloudFront)**:
   - Type: CNAME
   - Name: `translate.example.com` (or your domain)
   - Value: `d123456789abcd.cloudfront.net` (from output above)

2. **API Gateway WebSocket** (if using custom domain):
   - Type: CNAME
   - Name: `api.translate.example.com`
   - Value: Extract domain from WebSocket endpoint

**Note**: DNS propagation can take 24-48 hours, but often completes within minutes.

### Step 9: Invalidate CloudFront Cache (Optional)

If you update files in S3, invalidate the CloudFront cache:

```bash
DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id)

aws cloudfront create-invalidation \
  --distribution-id $DISTRIBUTION_ID \
  --paths "/*"
```

### Step 10: Test the Deployment

1. **Access the website**:
   - Via CloudFront: `https://d123456789abcd.cloudfront.net`
   - Via custom domain: `https://translate.example.com` (after DNS propagation)

2. **Check the WebSocket connection**:
   - Open browser DevTools (F12)
   - Go to Console tab
   - Look for: "Connected to server"

3. **Test speech input**:
   - Run the Go client: `./speech_to_text_go wss://your-api-endpoint/production`
   - Speak into microphone
   - Verify translations appear in browser

## Monitoring and Maintenance

### CloudWatch Logs

View Lambda function logs:

```bash
# Get the function name
FUNCTION_NAME=$(terraform output -raw lambda_function_name)

# Tail logs
aws logs tail /aws/lambda/$FUNCTION_NAME --follow
```

### Metrics

Monitor in AWS Console:
- **Lambda**: Invocations, errors, duration, concurrent executions
- **API Gateway**: Connection count, message count, errors
- **DynamoDB**: Read/write capacity, throttled requests
- **CloudFront**: Requests, data transfer, cache hit ratio

### Cost Tracking

Track costs in AWS Cost Explorer or use:

```bash
# Get current month's estimated costs
aws ce get-cost-and-usage \
  --time-period Start=$(date -d "month ago" +%Y-%m-01),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=SERVICE
```

## Updating the Deployment

### Update Lambda Code

```bash
# Make changes to Python files
# (lambda_handler.py, client_map.py, message_handler.py)

# Rebuild package
./scripts/build_lambda.sh

# Apply changes
cd terraform
terraform apply
```

### Update Static Files

```bash
# Make changes to static files
# (static/index.html, static/main.css)

# Get bucket name
BUCKET_NAME=$(terraform output -raw s3_bucket_name)

# Sync changes
aws s3 sync ../static/ s3://$BUCKET_NAME/ \
  --exclude ".gitignore" \
  --exclude "*.example"

# Invalidate CloudFront cache
DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id)
aws cloudfront create-invalidation \
  --distribution-id $DISTRIBUTION_ID \
  --paths "/*"
```

### Update Configuration

```bash
# Edit config.json locally
nano config.json

# Upload to S3
BUCKET_NAME=$(terraform output -raw s3_bucket_name)
aws s3 cp config.json s3://$BUCKET_NAME/

# Invalidate cache
DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id)
aws cloudfront create-invalidation \
  --distribution-id $DISTRIBUTION_ID \
  --paths "/config.json"
```

### Update Infrastructure

```bash
# Edit Terraform files (*.tf)

# Preview changes
terraform plan

# Apply changes
terraform apply
```

## Troubleshooting

### Lambda Function Errors

**Symptom**: Translations not working, WebSocket disconnects

**Check logs**:
```bash
aws logs tail /aws/lambda/$(terraform output -raw lambda_function_name) --follow
```

**Common issues**:
- Missing IAM permissions (check IAM policy)
- DynamoDB throttling (increase capacity or use on-demand)
- Translation API errors (check AWS Translate quotas)

### WebSocket Connection Fails

**Symptom**: "Disconnected from server" in browser console

**Check**:
1. API Gateway endpoint is correct in `config.json`
2. Lambda function is deployed and healthy
3. Lambda has execute-api:ManageConnections permission
4. CORS settings (if using custom domain)

**Test WebSocket manually**:
```bash
# Install wscat
npm install -g wscat

# Connect to WebSocket
wscat -c "$(terraform output -raw websocket_api_endpoint)"
```

### CloudFront Not Serving Files

**Symptom**: 404 errors, old content showing

**Check**:
1. Files uploaded to S3: `aws s3 ls s3://$BUCKET_NAME/`
2. S3 bucket policy allows CloudFront access
3. Origin Access Control (OAC) configured correctly

**Fix**:
```bash
# Re-sync files
aws s3 sync ../static/ s3://$BUCKET_NAME/ --delete

# Invalidate cache
aws cloudfront create-invalidation \
  --distribution-id $(terraform output -raw cloudfront_distribution_id) \
  --paths "/*"
```

### DynamoDB Errors

**Symptom**: "ProvisionedThroughputExceededException" in logs

**Fix**: The table uses on-demand billing, so this shouldn't happen. If it does:
1. Check for burst traffic patterns
2. Consider adding DynamoDB reserved capacity
3. Review Lambda concurrency settings

### High AWS Costs

**Check usage**:
```bash
# Lambda invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=$(terraform output -raw lambda_function_name) \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Sum

# API Gateway messages
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name Count \
  --dimensions Name=ApiId,Value=$(terraform output -raw websocket_api_id) \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Sum
```

**Cost optimization**:
- Reduce Lambda memory if not needed (currently 512MB)
- Reduce CloudWatch log retention (currently 7 days)
- Use CloudFront price class to limit edge locations
- Set up AWS Budgets alerts

## Security Considerations

### API Key Management

The API key in `terraform.tfvars` is sensitive. Never commit it to version control.

**Rotate API key**:
```bash
# Generate new key
NEW_KEY=$(openssl rand -base64 32)

# Update terraform.tfvars
echo "api_key = \"$NEW_KEY\"" >> terraform.tfvars

# Apply changes
terraform apply

# Update speech-to-text client .env file
echo "API_KEY=$NEW_KEY" >> ../.env
```

### IAM Best Practices

The Terraform configuration follows least-privilege principles:
- Lambda can only access its own DynamoDB table
- Lambda can only manage connections on its own API Gateway
- CloudWatch Logs scoped to the Lambda function

**Review IAM policies**:
```bash
# Get Lambda role ARN
aws lambda get-function --function-name $(terraform output -raw lambda_function_name) \
  --query 'Configuration.Role' --output text

# Get attached policies
aws iam list-role-policies --role-name live-translate-lambda-execution-production
```

### Network Security

- All communication uses HTTPS/WSS (TLS 1.2+)
- S3 bucket is private (no public access)
- CloudFront uses Origin Access Control (OAC)
- API Gateway uses IAM authentication for management API

## Cleanup / Teardown

To completely remove the deployment:

```bash
# Delete S3 bucket contents (required before destroying bucket)
BUCKET_NAME=$(terraform output -raw s3_bucket_name)
aws s3 rm s3://$BUCKET_NAME --recursive

# Destroy all Terraform resources
terraform destroy

# Confirm when prompted
```

This will delete:
- All Lambda functions
- API Gateway APIs
- DynamoDB tables
- S3 buckets (if empty)
- CloudFront distributions
- IAM roles and policies
- CloudWatch Log Groups

**Note**: CloudFront distributions take 15-30 minutes to fully delete.

## Support

For issues specific to AWS deployment:
1. Check CloudWatch Logs
2. Review Terraform state: `terraform show`
3. Validate configuration: `terraform validate`
4. Check AWS service health: https://status.aws.amazon.com/

For application issues, see the main [README.md](../README.md).
