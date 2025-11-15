#!/bin/bash
cd terraform
BUCKET_NAME=$(terraform output -raw s3_bucket_name)
aws s3 sync ../static/ s3://$BUCKET_NAME/ --exclude ".gitignore" --exclude "*.example"
DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id); \
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths '/*'
cd ..
