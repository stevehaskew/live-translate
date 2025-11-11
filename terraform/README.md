# Terraform Infrastructure for Live Translation (AWS)

This directory contains Terraform configuration for deploying Live Translation on AWS using:
- API Gateway (WebSocket)
- Lambda functions
- DynamoDB for client connection storage
- S3 + CloudFront for static website hosting

## Prerequisites

1. **Terraform** >= 1.0 installed
2. **AWS CLI** configured with appropriate credentials
3. **AWS Account** with permissions to create:
   - API Gateway
   - Lambda functions
   - DynamoDB tables
   - S3 buckets
   - CloudFront distributions
   - IAM roles and policies
   - CloudWatch Logs

## Quick Start

### 1. Build the Lambda Deployment Package

From the repository root:

```bash
# Create deployment package with dependencies
cd /path/to/live-translate
./scripts/build_lambda.sh
```

This will create `lambda_deployment.zip` containing:
- `lambda_handler.py`
- `client_map.py`
- `message_handler.py`
- Python dependencies (boto3, etc.)

### 2. Configure Terraform Variables

Create a `terraform.tfvars` file:

```hcl
aws_region   = "us-east-1"
domain_name  = "translate.example.com"
api_key      = "your-secure-api-key-here"
environment  = "production"
project_name = "live-translate"
```

**Generate a secure API key:**
```bash
openssl rand -base64 32
```

### 3. Initialize and Deploy

```bash
cd terraform

# Initialize Terraform
terraform init

# Preview changes
terraform plan

# Apply infrastructure
terraform apply
```

### 4. Upload Static Files to S3

After Terraform creates the infrastructure, upload the static website files:

```bash
# Get the bucket name from Terraform output
BUCKET_NAME=$(terraform output -raw s3_bucket_name)

# Upload static files
aws s3 sync ../static/ s3://$BUCKET_NAME/ \
  --exclude ".gitignore" \
  --exclude "*.example"

# Create and upload config.json
cat > config.json << EOF
{
  "logoFile": "",
  "pageTitle": "🌍 Live Translation",
  "contactText": "your support team",
  "websocketUrl": "wss://api.translate.example.com/production"
}
EOF

aws s3 cp config.json s3://$BUCKET_NAME/config.json

# Optional: Upload custom logo
# aws s3 cp /path/to/logo.png s3://$BUCKET_NAME/logo.png
```

### 5. Invalidate CloudFront Cache (After Updates)

When you update files in S3, invalidate CloudFront cache:

```bash
DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id)
aws cloudfront create-invalidation \
  --distribution-id $DISTRIBUTION_ID \
  --paths "/*"
```

## Architecture

```
┌─────────────────┐
│   Microphone    │
└────────┬────────┘
         │ Audio
         ▼
┌─────────────────┐      WebSocket     ┌──────────────────┐
│  Speech-to-Text │ ──────────────────▶│  API Gateway     │
│   (Go Client)   │   (with API Key)   │   (WebSocket)    │
└─────────────────┘                    └────────┬─────────┘
                                                 │
                                                 ▼
                                       ┌─────────────────┐
                                       │ Lambda Function │
                                       │  (Python 3.12)  │
                                       └────────┬────────┘
                                                │
                         ┌──────────────────────┼──────────────────────┐
                         │                      │                      │
                         ▼                      ▼                      ▼
                  ┌────────────┐        ┌─────────────┐       ┌──────────────┐
                  │  DynamoDB  │        │AWS Translate│       │API Gateway   │
                  │(Connection │        │   Service   │       │Management API│
                  │   Table)   │        └─────────────┘       └──────────────┘
                  └────────────┘                                      │
                                                                      │
                                                                      ▼
                                                             ┌─────────────────┐
                                                             │ Web Clients     │
                                                             │ (via CloudFront)│
                                                             └─────────────────┘
```

## Resources Created

### API Gateway
- **WebSocket API**: Handles real-time bidirectional communication
- **Routes**: `$connect`, `$disconnect`, `$default`
- **Stage**: Deployment stage (e.g., `production`)

### Lambda Function
- **Runtime**: Python 3.12
- **Memory**: 512 MB
- **Timeout**: 30 seconds
- **Environment Variables**:
  - `DYNAMODB_TABLE_NAME`: Connection table name
  - `AWS_REGION`: AWS region
  - `API_KEY`: Authentication key for speech client

### DynamoDB Table
- **Name**: `live-translate-connections-{environment}`
- **Primary Key**: `client_id` (String)
- **Billing**: Pay-per-request
- **TTL**: Enabled (for automatic cleanup of stale connections)

### S3 Bucket
- **Purpose**: Static website hosting
- **Access**: Private (accessed via CloudFront only)
- **Contents**: HTML, CSS, JavaScript, config.json, logo (optional)

### CloudFront Distribution
- **Purpose**: CDN for static website
- **Features**:
  - HTTPS redirect
  - Gzip compression
  - Caching (1 hour default)
  - Origin Access Control (OAC) for S3

### IAM Role & Policies
- **Lambda Execution Role**: Allows Lambda to:
  - Write CloudWatch Logs
  - Read/Write DynamoDB
  - Call API Gateway Management API
  - Call AWS Translate and Comprehend

## Configuration

### Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `aws_region` | AWS region | No | `us-east-1` |
| `domain_name` | Domain for static site | Yes | - |
| `api_domain_name` | API domain (auto: api.{domain_name}) | No | `""` |
| `api_key` | Speech client API key | Yes | - |
| `environment` | Environment name | No | `production` |
| `project_name` | Project name prefix | No | `live-translate` |
| `lambda_zip_path` | Path to Lambda zip | No | `../lambda_deployment.zip` |

### config.json Format

The `config.json` file in S3 configures the static website:

```json
{
  "logoFile": "logo.png",
  "pageTitle": "🌍 Live Translation",
  "contactText": "support@example.com",
  "websocketUrl": "wss://api.translate.example.com/production"
}
```

**Fields:**
- `logoFile`: URL or path to logo image (empty string for no logo)
- `pageTitle`: Page title and header text
- `contactText`: Contact information for support
- `websocketUrl`: Full WebSocket URL (get from Terraform output)

## DNS Configuration

After deployment, configure DNS records:

1. **Static Website (CloudFront)**:
   ```
   translate.example.com → CNAME → d123456789abcd.cloudfront.net
   ```
   
2. **API Gateway WebSocket**:
   ```
   api.translate.example.com → CNAME → xyz123.execute-api.us-east-1.amazonaws.com
   ```

Get CloudFront domain from:
```bash
terraform output cloudfront_distribution_url
```

Get API Gateway domain from:
```bash
terraform output websocket_api_endpoint
```

## Custom Domain Setup (Optional)

For production, use custom domains with SSL:

1. **Request ACM Certificate** (in `us-east-1` for CloudFront):
   ```bash
   aws acm request-certificate \
     --domain-name translate.example.com \
     --domain-name api.translate.example.com \
     --validation-method DNS \
     --region us-east-1
   ```

2. **Update Terraform**: Uncomment ACM certificate section in `resources.tf`

3. **Configure API Gateway Custom Domain**: Add custom domain mapping

## Updating the Deployment

### Update Lambda Code

1. Make changes to Python files
2. Rebuild deployment package: `./scripts/build_lambda.sh`
3. Apply Terraform: `terraform apply`

### Update Static Files

1. Update files in `static/` directory
2. Sync to S3 (see step 4 above)
3. Invalidate CloudFront cache

### Update Configuration

1. Edit `config.json`
2. Upload to S3: `aws s3 cp config.json s3://$BUCKET_NAME/`
3. Invalidate CloudFront cache

## Monitoring

### CloudWatch Logs

Lambda logs are in: `/aws/lambda/live-translate-websocket-handler-{environment}`

View logs:
```bash
aws logs tail /aws/lambda/live-translate-websocket-handler-production --follow
```

### Metrics

Monitor in CloudWatch:
- Lambda invocations, errors, duration
- API Gateway connections, messages, errors
- DynamoDB read/write capacity

## Costs

Estimated monthly costs (light usage):

- **API Gateway**: ~$1 per 1M messages
- **Lambda**: ~$0.20 per 1M requests (512MB memory)
- **DynamoDB**: ~$1.25 per 1M writes (on-demand)
- **S3**: ~$0.023 per GB storage
- **CloudFront**: ~$0.085 per GB transfer (first 10TB)
- **AWS Translate**: ~$15 per 1M characters

Total for moderate usage: **~$20-50/month**

Use [AWS Pricing Calculator](https://calculator.aws/) for detailed estimates.

## Cleanup

To destroy all resources:

```bash
# Delete S3 bucket contents first
aws s3 rm s3://$BUCKET_NAME --recursive

# Destroy infrastructure
terraform destroy
```

## Troubleshooting

### Lambda Function Errors

Check CloudWatch Logs:
```bash
aws logs tail /aws/lambda/live-translate-websocket-handler-production --follow
```

### WebSocket Connection Issues

1. Verify API Gateway endpoint URL in `config.json`
2. Check Lambda execution role has API Gateway Management permissions
3. Verify DynamoDB table exists and is accessible

### Translation Not Working

1. Check Lambda has Translate IAM permissions
2. Verify AWS region supports Translate service
3. Check CloudWatch Logs for errors

### CloudFront Not Serving Files

1. Verify files uploaded to S3
2. Check S3 bucket policy allows CloudFront access
3. Invalidate CloudFront cache

## Security Notes

- **API Key**: Use a strong random key, rotate periodically
- **IAM Roles**: Follow least-privilege principle
- **HTTPS**: Always use HTTPS/WSS in production
- **Secrets**: Never commit `terraform.tfvars` with secrets to version control
- **S3**: Keep bucket private, serve only via CloudFront
- **Lambda**: Keep dependencies updated, scan for vulnerabilities

## Support

For issues or questions:
1. Check CloudWatch Logs
2. Review [AWS Documentation](https://docs.aws.amazon.com/)
3. File an issue on the project repository
