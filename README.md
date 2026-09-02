# AWS Cloud Resource Management Dashboard

## Overview

A serverless web application built on AWS that monitors real-time cloud resource usage, billing data, and account activity. The dashboard displays EC2 instances, S3 buckets, IAM summary, monthly cost trends, and recent AWS activities with smart tips all fetched live from AWS APIs and rendered in a browser.

**Live URL:**
```
http://cloud-dashboard-sivam-2026.s3-website.ap-south-1.amazonaws.com
```

---

## Architecture

```
Browser
  │
  ├── Loads dashboard from S3 Static Website Hosting
  │
  └── Calls API Gateway (HTTPS)
            │
            └── Triggers Lambda Function (Python)
                      │
                      ├── EC2 API        → instance list and status
                      ├── S3 API         → bucket list
                      ├── Cost Explorer  → monthly billing data
                      ├── IAM API        → users, roles, MFA status
                      └── CloudTrail API → recent account activities
```

---

## AWS Services Used

| Service | Purpose |
|---|---|
| AWS Lambda | Serverless Python function that fetches all AWS data |
| API Gateway | Exposes Lambda as a public HTTPS REST endpoint |
| S3 | Hosts the frontend HTML as a static website |
| IAM | Execution role with least-privilege ReadOnlyAccess for Lambda |
| Cost Explorer | Fetches monthly billing data for the cost chart |
| CloudTrail | Logs and retrieves recent AWS account activities |
| CloudWatch | Monitors Lambda execution and billing alarm |
| SNS | Sends email notification when monthly cost exceeds $5 |
| EC2 | Monitored resource — instance list and running/stopped status |

---

## Project Structure

```
cloud-dashboard/
├── lambda/
│   ├── lambda_function.py     # Python backend — fetches all AWS data
│   └── lambda_function.zip    # Deployment package
├── frontend/
│   ├── index.html             # Dashboard UI — HTML, CSS, JavaScript
│   └── chart.min.js           # Chart.js served locally (CDN blocked fix)
├── bucket-policy.json         # S3 public read policy
└── README.md
```

---

## Features

**Resource Monitoring**
- EC2 instances — name, instance ID, type, and running/stopped state
- S3 buckets — bucket name and creation date
- IAM summary — user count, role count, policy count, MFA status

**Cost Tracking**
- Current month estimated cost
- Monthly cost bar chart for last 6 months
- Powered by AWS Cost Explorer API

**Recent Activities**
- Last 15 meaningful AWS actions from CloudTrail
- Filters out background noise — only shows real infrastructure actions
- Smart tips below each action — color coded by type

| Color | Meaning | Example |
|---|---|---|
| 🟡 Yellow | Warning — action costs money | EC2 instance started |
| 🟢 Green | Good — cost saving action | EC2 instance stopped |
| 🔵 Blue | Info — neutral action | Lambda code updated |
| 🔴 Red | Critical — security concern | Access key created |

**Billing Protection**
- CloudWatch alarm triggers when monthly cost exceeds $5
- SNS sends email notification immediately

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, boto3, AWS Lambda |
| API | AWS API Gateway (REST) |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Charting | Chart.js |
| Hosting | AWS S3 Static Website Hosting |
| IaC | AWS CLI, Bash Shell Scripts |
| Version Control | Git, GitHub |

---

## Setup and Deployment

### Prerequisites

- AWS account (free tier eligible)
- AWS CLI installed and configured
- Python 3.x installed
- Git installed

### Step 1 — Configure AWS CLI

```bash
aws configure
# Enter your Access Key ID, Secret Access Key, region (ap-south-1), output (json)
```

### Step 2 — Create IAM Role for Lambda

```bash
# Create role
aws iam create-role \
  --role-name cloud-dashboard-lambda-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": { "Service": "lambda.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach permissions
aws iam attach-role-policy \
  --role-name cloud-dashboard-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess

aws iam attach-role-policy \
  --role-name cloud-dashboard-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

### Step 3 — Deploy Lambda Function

```bash
cd lambda
zip lambda_function.zip lambda_function.py
cd ..

aws lambda create-function \
  --function-name cloud-dashboard \
  --runtime python3.12 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/cloud-dashboard-lambda-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda/lambda_function.zip \
  --timeout 30 \
  --region ap-south-1
```

### Step 4 — Create API Gateway

```bash
# Create API
aws apigateway create-rest-api \
  --name cloud-dashboard-api \
  --region ap-south-1
```

Then in AWS Console:
1. API Gateway → cloud-dashboard-api → Resources
2. Create Resource → /data
3. Create Method → GET → Lambda integration → cloud-dashboard
4. Actions → Deploy API → Stage: prod

### Step 5 — Update Frontend API URL

Open `frontend/index.html` → find this line → replace with your actual API Gateway URL:

```javascript
const API_URL = "https://YOUR_ID.execute-api.ap-south-1.amazonaws.com/prod/data";
```

### Step 6 — Host Frontend on S3

```bash
# Create bucket
aws s3 mb s3://YOUR_BUCKET_NAME --region ap-south-1

# Enable static website hosting
aws s3 website s3://YOUR_BUCKET_NAME \
  --index-document index.html \
  --error-document index.html

# Remove public access block
aws s3api put-public-access-block \
  --bucket YOUR_BUCKET_NAME \
  --public-access-block-configuration \
  "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"

# Apply bucket policy
aws s3api put-bucket-policy \
  --bucket YOUR_BUCKET_NAME \
  --policy file://bucket-policy.json

# Upload files
aws s3 cp frontend/index.html s3://YOUR_BUCKET_NAME/index.html --content-type "text/html"
aws s3 cp frontend/chart.min.js s3://YOUR_BUCKET_NAME/chart.min.js --content-type "application/javascript"
```

### Step 7 — Set Up Billing Alarm

```bash
# Create SNS topic
aws sns create-topic --name billing-alert --region us-east-1

# Subscribe your email
aws sns subscribe \
  --topic-arn YOUR_TOPIC_ARN \
  --protocol email \
  --notification-endpoint your@email.com \
  --region us-east-1

# Create CloudWatch alarm
aws cloudwatch put-metric-alarm \
  --alarm-name MonthlyBillingAlert \
  --metric-name EstimatedCharges \
  --namespace AWS/Billing \
  --statistic Maximum \
  --dimensions Name=Currency,Value=USD \
  --period 86400 \
  --evaluation-periods 1 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions YOUR_TOPIC_ARN \
  --region us-east-1
```

### Step 8 — Enable CloudTrail

```bash
aws cloudtrail create-trail \
  --name dashboard-trail-mumbai \
  --s3-bucket-name YOUR_CLOUDTRAIL_BUCKET \
  --region ap-south-1

aws cloudtrail start-logging \
  --name dashboard-trail-mumbai \
  --region ap-south-1
```

---

## Updating the Project

**When Lambda code changes:**
```bash
cd lambda
zip lambda_function.zip lambda_function.py -Force
cd ..
aws lambda update-function-code \
  --function-name cloud-dashboard \
  --zip-file fileb://lambda/lambda_function.zip \
  --region ap-south-1
```

**When frontend changes:**
```bash
aws s3 cp frontend/index.html s3://YOUR_BUCKET_NAME/index.html --content-type "text/html"
```

---

## IAM Security Design

This project follows the principle of least privilege throughout:

**Lambda execution role** has only `ReadOnlyAccess` — it can describe and list resources but cannot create, modify, or delete anything. Even if the Lambda function had a bug or was compromised, it cannot cause any destructive action in the AWS account.

**IAM user** (`dashboard-user`) has permissions scoped only to what is needed for deployment — Lambda, API Gateway, S3, IAM, CloudWatch, SNS. No billing write access, no EC2 modification access.

---

## How the Data Flow Works

```
1. Browser loads index.html from S3
2. JavaScript calls fetch(API_URL) — GET request to API Gateway
3. API Gateway receives request and invokes Lambda
4. Lambda assumes execution role and gets temporary credentials
5. boto3 calls EC2, S3, Cost Explorer, IAM, CloudTrail APIs
6. All responses bundled into one JSON object
7. Lambda returns JSON with statusCode 200
8. API Gateway forwards response to browser
9. JavaScript parses raw.body (double parse needed — API Gateway wraps response)
10. Render functions update the DOM with live data
11. Chart.js draws the cost bar chart on canvas element
```

---

## Skills Demonstrated

- Serverless architecture design on AWS
- IAM least-privilege security implementation
- REST API creation with API Gateway
- Python backend development with boto3
- S3 static website hosting and bucket policies
- CloudTrail activity logging and filtering
- CloudWatch monitoring and SNS alerting
- Frontend development with vanilla JavaScript
- AWS CLI for infrastructure deployment
- Git version control

---
