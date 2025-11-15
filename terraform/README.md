# Terraform Infrastructure for Live Translation (AWS)

This directory contains Terraform configuration for deploying Live Translation on AWS using:
- API Gateway (WebSocket) with custom domain
- Lambda functions
- DynamoDB for client connection storage
- S3 + CloudFront for static website hosting
- ACM certificates for HTTPS/WSS
- Route53 DNS records

## Prerequisites

1. **Terraform** >= 1.0 installed
2. **AWS CLI** configured with appropriate credentials
3. **Route53 Hosted Zone** - Your domain must already be hosted in Route53
4. **AWS Account** with permissions to create:
   - API Gateway
   - Lambda functions
   - DynamoDB tables
   - S3 buckets
   - CloudFront distributions
   - ACM certificates
   - Route53 records
   - IAM roles and policies
   - CloudWatch Logs

## DNS and Certificate Setup

**Important**: Before running Terraform, ensure your domain is already hosted in Route53. Terraform will:
1. Look up the existing Route53 hosted zone for your domain
2. Create ACM certificates for both the static website and API Gateway
3. Add DNS validation records to Route53
4. Wait for certificate validation to complete
5. Configure CloudFront and API Gateway to use the certificates
6. Create A and AAAA records pointing to CloudFront and API Gateway

**Certificate Locations**:
- CloudFront certificate: `us-east-1` (required by CloudFront)
- API Gateway certificate: Your configured region (e.g., `us-east-1`)

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
domain_name  = "translate.example.com"  # Must be hosted in Route53
api_key      = "your-secure-api-key-here"
environment  = "production"
project_name = "live-translate"
```

**Note**: The `domain_name` must already exist as a hosted zone in Route53. The API Gateway will automatically use `api.translate.example.com`.

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

# Create and upload config.json with the custom domain
WS_ENDPOINT=$(terraform output -raw websocket_api_endpoint)
cat > config.json << EOF
{
  "logoFile": "",
  "pageTitle": "🌍 Live Translation",
  "contactText": "your support team",
  "websocketUrl": "$WS_ENDPOINT"
}
EOF

aws s3 cp config.json s3://$BUCKET_NAME/config.json

# Optional: Upload custom logo
# aws s3 cp /path/to/logo.png s3://$BUCKET_NAME/logo.png
```

**Note**: After Terraform completes, DNS records will be automatically created and the custom domains will be ready to use. Certificate validation typically takes 5-10 minutes.

### 5. Verify Deployment

Check that everything is working:

```bash
# Get the custom domain URLs
terraform output cloudfront_custom_domain
terraform output websocket_api_endpoint

# Test the website
curl -I https://$(terraform output -raw cloudfront_custom_domain)

# The WebSocket endpoint will be: wss://api.YOUR-DOMAIN/production
```

### 6. Invalidate CloudFront Cache (After Updates)

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
- **Custom Domain**: Configured with ACM certificate
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
  - `TRANSCRIBE_ROLE_ARN`: ARN of IAM role to assume for token generation (when enabled)

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
- **Custom Domain**: Configured with ACM certificate
- **Features**:
  - HTTPS redirect with custom domain
  - SNI SSL/TLS 1.2+
  - Gzip compression
  - Caching (1 hour default)
  - Origin Access Control (OAC) for S3

### ACM Certificates
- **CloudFront Certificate**: Created in `us-east-1` (required by CloudFront)
- **API Gateway Certificate**: Created in configured region
- **Validation**: Automatic via DNS (Route53)
- **Renewal**: Automatic by AWS

### Route53 DNS Records
- **A Record**: `domain_name` → CloudFront distribution
- **AAAA Record**: `domain_name` → CloudFront distribution (IPv6)
- **A Record**: `api.domain_name` → API Gateway custom domain
- **AAAA Record**: `api.domain_name` → API Gateway custom domain (IPv6)
- **Validation Records**: Automatic certificate validation

### IAM Role & Policies

#### Lambda Execution Role
The Lambda function's execution role includes permissions to:
- Write CloudWatch Logs
- Read/Write DynamoDB table
- Call API Gateway Management API (PostToConnection)
- Call AWS Translate and Comprehend services
- Assume the Transcribe client role (for token generation)

#### Transcribe Client Role (Token Generation)
When `enable_token_generation` is true, Terraform creates:

- **Transcribe Client Role**: IAM role that grants access to AWS Transcribe Streaming
  - Can be assumed by the Lambda execution role
  - Scoped to `transcribe:StartStreamTranscription` permission only
  - Uses ExternalId condition for additional security
  
- **AssumeRole Permission**: Lambda execution role can assume the Transcribe client role
  - Required for the `/generate_token` endpoint to work
  - Allows Lambda to generate temporary session credentials for speech clients
  
**How it works:**
1. Speech client requests token via `/generate_token` endpoint (with API key)
2. Lambda assumes the Transcribe client role using STS AssumeRole
3. Lambda returns temporary credentials (valid for 1 hour) to the client
4. Client uses temporary credentials to access AWS Transcribe
5. Credentials are automatically refreshed by client every 20 minutes

**Security benefits:**
- Speech clients never need permanent AWS credentials
- Temporary credentials are scoped to Transcribe service only
- Credentials expire after 1 hour
- ExternalId prevents confused deputy attacks

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
| `enable_token_generation` | Enable AWS token generation for Transcribe | No | `true` |

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

## DNS and SSL Configuration

**DNS is automatically configured by Terraform!** When you run `terraform apply`:

1. **ACM Certificates** are automatically created:
   - CloudFront certificate (in us-east-1)
   - API Gateway certificate (in your configured region)

2. **DNS Validation** records are automatically added to Route53

3. **Certificate Validation** waits for DNS propagation (usually 5-10 minutes)

4. **A and AAAA Records** are created:
   - `translate.example.com` → CloudFront distribution
   - `api.translate.example.com` → API Gateway custom domain

5. **Custom Domains** are configured with SSL/TLS:
   - CloudFront uses SNI with TLS 1.2+
   - API Gateway uses regional endpoint with TLS 1.2+

**No manual DNS configuration required!** Just ensure your domain is already hosted in Route53 before running Terraform.

### Accessing Your Deployment

After Terraform completes (and certificate validation finishes):

- **Static Website**: `https://translate.example.com`
- **WebSocket API**: `wss://api.translate.example.com/production`

Get the exact URLs from Terraform outputs:
```bash
terraform output cloudfront_custom_domain
terraform output websocket_api_endpoint
```

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

## Terraform Outputs

After deployment, Terraform provides the following outputs:

| Output | Description |
|--------|-------------|
| `cloudfront_distribution_url` | CloudFront distribution URL |
| `cloudfront_custom_domain` | Custom domain for static website |
| `cloudfront_distribution_id` | CloudFront distribution ID (for cache invalidation) |
| `s3_bucket_name` | S3 bucket name for static files |
| `websocket_api_endpoint` | WebSocket API custom domain endpoint |
| `websocket_api_default_endpoint` | WebSocket API default AWS endpoint |
| `websocket_api_id` | API Gateway WebSocket API ID |
| `dynamodb_table_name` | DynamoDB table name for connections |
| `lambda_function_name` | Lambda function name |
| `api_domain` | Configured API domain name |
| `transcribe_role_arn` | ARN of Transcribe IAM role (for token generation) |
| `transcribe_role_name` | Name of Transcribe IAM role |

View all outputs:
```bash
terraform output
```

Get a specific output:
```bash
terraform output -raw websocket_api_endpoint
```

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

### Token Generation Not Working

1. Verify `enable_token_generation` is set to `true` in `terraform.tfvars`
2. Check that `TRANSCRIBE_ROLE_ARN` environment variable is set in Lambda
3. Verify Lambda execution role has `sts:AssumeRole` permission
4. Check Transcribe client role trust policy allows Lambda to assume it
5. Review CloudWatch Logs for AssumeRole errors

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
