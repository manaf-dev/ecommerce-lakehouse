# Deployment Guide — E-Commerce Lakehouse Pipeline

This guide walks you through deploying the pipeline to a **brand-new AWS account** from scratch. Every resource is covered: the Terraform state bucket, GitHub OIDC trust, IAM deployment role, repo configuration, and the Terraform apply itself.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Choose Your Names](#2-choose-your-names)
3. [Bootstrap: Terraform State Bucket](#3-bootstrap-terraform-state-bucket)
4. [GitHub OIDC Provider](#4-github-oidc-provider)
5. [GitHub Actions IAM Role](#5-github-actions-iam-role)
6. [GitHub Repository Setup](#6-github-repository-setup)
7. [Deploy](#7-deploy)
8. [Post-Deployment](#8-post-deployment)
9. [Grafana Cloud Setup](#9-grafana-cloud-setup)
10. [Appendix A — Terraform Variable Reference](#appendix-a--terraform-variable-reference)
11. [Appendix B — What Gets Created by Terraform](#appendix-b--what-gets-created-by-terraform)

---

## 1. Prerequisites

Install and configure the following before starting:

| Tool | Minimum version | Purpose |
|------|----------------|---------|
| AWS CLI | v2 | Bootstrap + verification |
| Terraform | ≥ 1.5 | Infrastructure deployment |
| Python | ≥ 3.12 | Building `utils.zip` locally |
| Git | any | Cloning the repo |
| `gh` CLI *(optional)* | any | Setting GitHub variables/secrets from the terminal |

**AWS CLI authentication** — your local session must have `AdministratorAccess` (or equivalent) on the target account before running the bootstrap steps. The GitHub Actions role created in Step 5 is what runs Terraform in CI/CD — your personal credentials are only needed for the one-time bootstrap.

```bash
# Verify you are authenticated to the correct account
aws sts get-caller-identity
```

---

## 2. Choose Your Names

All resource names derive from three values you pick now. Write them down — you will use them throughout this guide.

| Variable | Description | Constraints | Example |
|----------|-------------|-------------|---------|
| `PROJECT` | Prefix for every AWS resource name | lowercase, hyphens only | `ecommerce-lakehouse-alice` |
| `LAKEHOUSE_BUCKET` | S3 bucket for all pipeline data | globally unique | `my-ecommerce-lakehouse-alice` |
| `TF_STATE_BUCKET` | S3 bucket for Terraform remote state | globally unique | `ecommerce-lakehouse-alice-tfstate` |
| `AWS_REGION` | AWS region to deploy into | valid region code | `eu-central-1` |
| `ALERT_EMAIL` | Email for SNS pipeline failure alerts | valid email | `ops@example.com` |
| `GITHUB_ORG` | GitHub org or username that owns the repo | | `my-org` |
| `GITHUB_REPO` | GitHub repository name | | `ecommerce-lakehouse` |

> **Naming rule:** `PROJECT` must be short enough that `{PROJECT}-ingest-delta` stays under 255 characters (it will be an IAM role name, Glue job name, etc.). Keep it under 40 characters.

Set them as shell variables for the commands in this guide:

```bash
export PROJECT="ecommerce-lakehouse-alice"
export LAKEHOUSE_BUCKET="my-ecommerce-lakehouse-alice"
export TF_STATE_BUCKET="ecommerce-lakehouse-alice-tfstate"
export AWS_REGION="eu-central-1"
export ALERT_EMAIL="ops@example.com"
export GITHUB_ORG="my-org"
export GITHUB_REPO="ecommerce-lakehouse"
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
```

---

## 3. Bootstrap: Terraform State Bucket

Terraform stores its state in S3. This bucket must exist **before** running any Terraform command. It is created manually (not by Terraform) so it is never accidentally destroyed.

### AWS CLI

```bash
# Create the bucket
aws s3api create-bucket \
  --bucket "$TF_STATE_BUCKET" \
  --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION"

# Enable versioning — protects state files from accidental deletion
aws s3api put-bucket-versioning \
  --bucket "$TF_STATE_BUCKET" \
  --versioning-configuration Status=Enabled

# Enable server-side encryption (AES-256)
aws s3api put-bucket-encryption \
  --bucket "$TF_STATE_BUCKET" \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'

# Block all public access
aws s3api put-public-access-block \
  --bucket "$TF_STATE_BUCKET" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Verify
aws s3api get-bucket-versioning --bucket "$TF_STATE_BUCKET"
```

> **Note for `us-east-1`:** Omit `--create-bucket-configuration LocationConstraint` — that flag is not valid in us-east-1.

### AWS Console

1. Open **S3** → **Create bucket**
2. **Bucket name:** `<TF_STATE_BUCKET>`
3. **AWS Region:** `<AWS_REGION>`
4. **Object Ownership:** leave at ACLs disabled
5. **Block Public Access:** tick all four boxes → **Block all public access**
6. **Bucket Versioning:** Enable
7. **Default encryption:** Amazon S3 managed keys (SSE-S3)
8. Click **Create bucket**

---

## 4. GitHub OIDC Provider

GitHub Actions authenticates to AWS without long-lived access keys by using OpenID Connect. You create an OIDC **provider** in IAM once per account — not per repo.

> Skip this step if the provider `token.actions.githubusercontent.com` already exists in the account (`aws iam list-open-id-connect-providers`).

### AWS CLI

```bash
aws iam create-open-id-connect-provider \
  --url "https://token.actions.githubusercontent.com" \
  --client-id-list "sts.amazonaws.com" \
  --thumbprint-list \
    "6938fd4d98bab03faadb97b34396831e3780aea1" \
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd"
```

The two thumbprints cover GitHub's current and previous certificate authorities. AWS validates the token against the OIDC discovery document; the thumbprints are a secondary safety check.

### AWS Console

1. Open **IAM** → **Identity providers** → **Add provider**
2. **Provider type:** OpenID Connect
3. **Provider URL:** `https://token.actions.githubusercontent.com` → click **Get thumbprint**
4. **Audience:** `sts.amazonaws.com`
5. Click **Add provider**

---

## 5. GitHub Actions IAM Role

This role is assumed by GitHub Actions via OIDC when a push lands on `main`. It has exactly the permissions Terraform needs to create and manage all pipeline infrastructure.

### 5a. Create the trust policy file

```bash
cat > /tmp/trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:${GITHUB_ORG}/${GITHUB_REPO}:ref:refs/heads/main"
        }
      }
    }
  ]
}
EOF
```

> The `sub` condition locks the role to pushes on `main` from your specific repo. If you want to also allow manual workflow dispatches or other branches, add them as additional `sub` values in a `StringLike` condition instead of `StringEquals`.

### 5b. Create the permissions policy file

This policy covers every AWS action Terraform performs across all modules (S3, IAM, Glue, Athena, Step Functions, EventBridge, SNS, CloudWatch Logs).

```bash
cat > /tmp/deploy-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [

    {
      "Sid": "TerraformStateAccess",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::${TF_STATE_BUCKET}",
        "arn:aws:s3:::${TF_STATE_BUCKET}/*"
      ]
    },

    {
      "Sid": "LakehouseBucketManagement",
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:DeleteBucket",
        "s3:ListBucket",
        "s3:GetBucketLocation",
        "s3:GetBucketVersioning",
        "s3:PutBucketVersioning",
        "s3:GetBucketEncryption",
        "s3:PutBucketEncryption",
        "s3:GetBucketPublicAccessBlock",
        "s3:PutBucketPublicAccessBlock",
        "s3:GetBucketTagging",
        "s3:PutBucketTagging",
        "s3:GetLifecycleConfiguration",
        "s3:PutLifecycleConfiguration",
        "s3:GetBucketNotification",
        "s3:PutBucketNotification",
        "s3:GetBucketAcl",
        "s3:GetBucketCORS",
        "s3:GetBucketObjectLockConfiguration",
        "s3:GetBucketRequestPayment",
        "s3:GetBucketWebsite",
        "s3:GetAccelerateConfiguration",
        "s3:GetReplicationConfiguration",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:GetObjectTagging",
        "s3:PutObjectTagging"
      ],
      "Resource": [
        "arn:aws:s3:::${LAKEHOUSE_BUCKET}",
        "arn:aws:s3:::${LAKEHOUSE_BUCKET}/*"
      ]
    },

    {
      "Sid": "IamRoleManagement",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:GetRole",
        "iam:UpdateRole",
        "iam:DeleteRole",
        "iam:TagRole",
        "iam:UntagRole",
        "iam:ListRoleTags",
        "iam:PutRolePolicy",
        "iam:GetRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:ListRolePolicies",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:ListAttachedRolePolicies",
        "iam:ListInstanceProfilesForRole",
        "iam:UpdateAssumeRolePolicy"
      ],
      "Resource": [
        "arn:aws:iam::${ACCOUNT_ID}:role/${PROJECT}-*"
      ]
    },

    {
      "Sid": "IamUserManagement",
      "Effect": "Allow",
      "Action": [
        "iam:CreateUser",
        "iam:GetUser",
        "iam:DeleteUser",
        "iam:TagUser",
        "iam:UntagUser",
        "iam:ListUserTags",
        "iam:PutUserPolicy",
        "iam:GetUserPolicy",
        "iam:DeleteUserPolicy",
        "iam:ListUserPolicies"
      ],
      "Resource": [
        "arn:aws:iam::${ACCOUNT_ID}:user/${PROJECT}-*"
      ]
    },

    {
      "Sid": "IamPassRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::${ACCOUNT_ID}:role/${PROJECT}-glue-role",
        "arn:aws:iam::${ACCOUNT_ID}:role/${PROJECT}-sfn-role",
        "arn:aws:iam::${ACCOUNT_ID}:role/${PROJECT}-eventbridge-role"
      ]
    },

    {
      "Sid": "GlueManagement",
      "Effect": "Allow",
      "Action": [
        "glue:CreateDatabase",
        "glue:GetDatabase",
        "glue:DeleteDatabase",
        "glue:CreateJob",
        "glue:GetJob",
        "glue:UpdateJob",
        "glue:DeleteJob",
        "glue:CreateCrawler",
        "glue:GetCrawler",
        "glue:UpdateCrawler",
        "glue:DeleteCrawler",
        "glue:TagResource",
        "glue:UntagResource",
        "glue:GetTags"
      ],
      "Resource": [
        "arn:aws:glue:${AWS_REGION}:${ACCOUNT_ID}:catalog",
        "arn:aws:glue:${AWS_REGION}:${ACCOUNT_ID}:database/lakehouse_dwh",
        "arn:aws:glue:${AWS_REGION}:${ACCOUNT_ID}:job/${PROJECT}-*",
        "arn:aws:glue:${AWS_REGION}:${ACCOUNT_ID}:crawler/${PROJECT}-*"
      ]
    },

    {
      "Sid": "AthenaManagement",
      "Effect": "Allow",
      "Action": [
        "athena:CreateWorkGroup",
        "athena:GetWorkGroup",
        "athena:UpdateWorkGroup",
        "athena:DeleteWorkGroup",
        "athena:TagResource",
        "athena:UntagResource",
        "athena:ListTagsForResource"
      ],
      "Resource": [
        "arn:aws:athena:${AWS_REGION}:${ACCOUNT_ID}:workgroup/${PROJECT}-*"
      ]
    },

    {
      "Sid": "StepFunctionsManagement",
      "Effect": "Allow",
      "Action": [
        "states:CreateStateMachine",
        "states:DescribeStateMachine",
        "states:UpdateStateMachine",
        "states:DeleteStateMachine",
        "states:TagResource",
        "states:UntagResource",
        "states:ListTagsForResource"
      ],
      "Resource": [
        "arn:aws:states:${AWS_REGION}:${ACCOUNT_ID}:stateMachine:${PROJECT}-*"
      ]
    },

    {
      "Sid": "EventBridgeManagement",
      "Effect": "Allow",
      "Action": [
        "events:PutRule",
        "events:DescribeRule",
        "events:DeleteRule",
        "events:PutTargets",
        "events:RemoveTargets",
        "events:ListTargetsByRule",
        "events:TagResource",
        "events:UntagResource",
        "events:ListTagsForResource"
      ],
      "Resource": [
        "arn:aws:events:${AWS_REGION}:${ACCOUNT_ID}:rule/${PROJECT}-*"
      ]
    },

    {
      "Sid": "SnsManagement",
      "Effect": "Allow",
      "Action": [
        "sns:CreateTopic",
        "sns:GetTopicAttributes",
        "sns:SetTopicAttributes",
        "sns:DeleteTopic",
        "sns:Subscribe",
        "sns:GetSubscriptionAttributes",
        "sns:SetSubscriptionAttributes",
        "sns:Unsubscribe",
        "sns:ListSubscriptionsByTopic",
        "sns:TagResource",
        "sns:UntagResource",
        "sns:ListTagsForResource"
      ],
      "Resource": [
        "arn:aws:sns:${AWS_REGION}:${ACCOUNT_ID}:${PROJECT}-*"
      ]
    },

    {
      "Sid": "CloudWatchLogsManagement",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:DeleteLogGroup",
        "logs:PutRetentionPolicy",
        "logs:TagLogGroup",
        "logs:UntagLogGroup",
        "logs:TagResource",
        "logs:UntagResource",
        "logs:ListTagsForResource",
        "logs:ListTagsLogGroup"
      ],
      "Resource": [
        "arn:aws:logs:${AWS_REGION}:${ACCOUNT_ID}:log-group:/aws-glue/*",
        "arn:aws:logs:${AWS_REGION}:${ACCOUNT_ID}:log-group:/aws/states/${PROJECT}-*"
      ]
    },

    {
      "Sid": "CloudWatchLogsDescribe",
      "Effect": "Allow",
      "Action": [
        "logs:DescribeLogGroups"
      ],
      "Resource": "*"
    }

  ]
}
EOF
```

### 5c. Create the role

```bash
ROLE_NAME="${PROJECT}-github-actions"

# Create the role with the trust policy
aws iam create-role \
  --role-name "$ROLE_NAME" \
  --assume-role-policy-document file:///tmp/trust-policy.json \
  --description "GitHub Actions OIDC deployment role for ${PROJECT}"

# Attach the permissions policy
aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "${PROJECT}-deploy" \
  --policy-document file:///tmp/deploy-policy.json

# Save the ARN — you will need it for GitHub Secrets
ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text)
echo "Role ARN: $ROLE_ARN"
```

### AWS Console — Role creation

1. Open **IAM** → **Roles** → **Create role**
2. **Trusted entity type:** Web identity
3. **Identity provider:** `token.actions.githubusercontent.com`
4. **Audience:** `sts.amazonaws.com`
5. **GitHub organization:** `<GITHUB_ORG>`
6. **GitHub repository:** `<GITHUB_REPO>`
7. **GitHub branch:** `main`
8. Click **Next**
9. On Permissions: skip for now (you will add the inline policy after creation) → **Next**
10. **Role name:** `<PROJECT>-github-actions`
11. Click **Create role**
12. Open the newly created role → **Add permissions** → **Create inline policy**
13. Switch to the **JSON** tab → paste the `deploy-policy.json` content from above (with real values substituted for `${...}` placeholders)
14. **Policy name:** `<PROJECT>-deploy` → **Create policy**

---

## 6. GitHub Repository Setup

You need four **Variables** (non-secret config) and two **Secrets** (sensitive values) set on the repository.

### Values to set

| Type | Name | Value |
|------|------|-------|
| Variable | `AWS_REGION` | `<AWS_REGION>` |
| Variable | `TF_STATE_BUCKET` | `<TF_STATE_BUCKET>` |
| Variable | `TF_PROJECT` | `<PROJECT>` |
| Variable | `LAKEHOUSE_BUCKET` | `<LAKEHOUSE_BUCKET>` |
| Secret | `AWS_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/<PROJECT>-github-actions` |
| Secret | `ALERT_EMAIL` | `<ALERT_EMAIL>` |

### gh CLI

```bash
# Variables
gh variable set AWS_REGION       --body "$AWS_REGION"       --repo "${GITHUB_ORG}/${GITHUB_REPO}"
gh variable set TF_STATE_BUCKET  --body "$TF_STATE_BUCKET"  --repo "${GITHUB_ORG}/${GITHUB_REPO}"
gh variable set TF_PROJECT       --body "$PROJECT"          --repo "${GITHUB_ORG}/${GITHUB_REPO}"
gh variable set LAKEHOUSE_BUCKET --body "$LAKEHOUSE_BUCKET" --repo "${GITHUB_ORG}/${GITHUB_REPO}"

# Secrets
gh secret set AWS_ROLE_ARN  --body "$ROLE_ARN"      --repo "${GITHUB_ORG}/${GITHUB_REPO}"
gh secret set ALERT_EMAIL   --body "$ALERT_EMAIL"   --repo "${GITHUB_ORG}/${GITHUB_REPO}"
```

### GitHub Console

1. Open the repository → **Settings** → **Secrets and variables** → **Actions**

**Add each Variable** (under the *Variables* tab):
- Click **New repository variable** for each row marked *Variable* in the table above

**Add each Secret** (under the *Secrets* tab):
- Click **New repository secret** for each row marked *Secret* in the table above

---

## 7. Deploy

You have two options. **Option A (CD pipeline)** is the standard path — it is identical to how every future change deploys. **Option B (manual)** is useful if you want to apply infrastructure without pushing code, or if you are debugging.

### Option A: CD Pipeline (recommended)

Once the steps above are complete, push any commit to `main`. The CD workflow (`.github/workflows/cd.yml`) runs automatically:

1. Lint + test gate
2. Terraform init → apply
3. Upload Glue job scripts to S3
4. Build and upload `utils.zip` to S3

```bash
git clone https://github.com/${GITHUB_ORG}/${GITHUB_REPO}.git
cd ${GITHUB_REPO}

# If you need to make a trivial commit to trigger the workflow:
git commit --allow-empty -m "chore: trigger initial deployment"
git push origin main
```

Monitor the run at: `https://github.com/<GITHUB_ORG>/<GITHUB_REPO>/actions`

### Option B: Manual Terraform

Use this to deploy locally (e.g. testing a new account without pushing).

```bash
# 1. Clone and install dependencies
git clone https://github.com/${GITHUB_ORG}/${GITHUB_REPO}.git
cd ${GITHUB_REPO}
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .

# 2. Build utils.zip (must exist before Terraform runs — it uploads the placeholder)
make build-utils-zip
make verify-zip

# 3. Terraform init (connects to the S3 backend)
terraform -chdir=terraform/environments/prod init \
  -backend-config="bucket=${TF_STATE_BUCKET}" \
  -backend-config="region=${AWS_REGION}" \
  -input=false

# 4. Plan — review what will be created (expect ~30 resources on first run)
terraform -chdir=terraform/environments/prod plan \
  -var="project=${PROJECT}" \
  -var="bucket=${LAKEHOUSE_BUCKET}" \
  -var="region=${AWS_REGION}" \
  -var="alert_email=${ALERT_EMAIL}"

# 5. Apply
terraform -chdir=terraform/environments/prod apply \
  -var="project=${PROJECT}" \
  -var="bucket=${LAKEHOUSE_BUCKET}" \
  -var="region=${AWS_REGION}" \
  -var="alert_email=${ALERT_EMAIL}"

# 6. Upload Glue scripts
aws s3 sync src/glue_jobs/ \
  "s3://${LAKEHOUSE_BUCKET}/scripts/" \
  --exact-timestamps \
  --exclude "__pycache__/*"

# 7. Upload utils.zip
aws s3 cp dist/utils.zip "s3://${LAKEHOUSE_BUCKET}/scripts/utils.zip"
```

---

## 8. Post-Deployment

### 8a. Confirm the SNS email subscription

Terraform creates an SNS subscription for `ALERT_EMAIL`. AWS sends a confirmation email immediately after `terraform apply`. **You must click the confirmation link** in that email before pipeline failure alerts will be delivered.

Subject line: *AWS Notification - Subscription Confirmation*

If the email did not arrive, re-send it:

```bash
# List subscriptions for the topic
TOPIC_ARN="arn:aws:sns:${AWS_REGION}:${ACCOUNT_ID}:${PROJECT}-pipeline-alerts"
aws sns list-subscriptions-by-topic --topic-arn "$TOPIC_ARN" --region "$AWS_REGION"
```

### 8b. Verify key resources

```bash
# Lakehouse S3 bucket
aws s3 ls "s3://${LAKEHOUSE_BUCKET}/"

# Glue jobs
aws glue get-job --job-name "${PROJECT}-ingest-delta"  --region "$AWS_REGION" --query Job.Name
aws glue get-job --job-name "${PROJECT}-archive-files" --region "$AWS_REGION" --query Job.Name

# Glue crawler
aws glue get-crawler --name "${PROJECT}-crawler" --region "$AWS_REGION" --query Crawler.State

# Athena workgroup
aws athena get-work-group --work-group "${PROJECT}-workgroup" --region "$AWS_REGION" --query WorkGroup.Name

# Step Functions state machine
aws stepfunctions describe-state-machine \
  --state-machine-arn "arn:aws:states:${AWS_REGION}:${ACCOUNT_ID}:stateMachine:${PROJECT}-pipeline" \
  --region "$AWS_REGION" --query name
```

### 8c. Trigger the pipeline manually

The pipeline runs automatically when files land in `s3://<LAKEHOUSE_BUCKET>/raw/products/`, `/raw/orders/`, or `/raw/order_items/` (via EventBridge). The sample data files are uploaded by Terraform — dropping a new file in any of those prefixes will trigger a run.

To trigger a run immediately without uploading new files:

```bash
aws stepfunctions start-execution \
  --state-machine-arn "arn:aws:states:${AWS_REGION}:${ACCOUNT_ID}:stateMachine:${PROJECT}-pipeline" \
  --input "{\"bucket\":\"${LAKEHOUSE_BUCKET}\"}" \
  --region "$AWS_REGION"
```

Monitor in the AWS Console under **Step Functions** → **State machines** → `<PROJECT>-pipeline` → **Executions**, or via CLI:

```bash
EXEC_ARN="<execution ARN from above output>"
aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" --region "$AWS_REGION" \
  --query "{status:status,start:startDate,stop:stopDate}"
```

---

## 9. Grafana Cloud Setup

This section walks through connecting Grafana Cloud to the lakehouse Athena views so you can import the pre-built dashboards. The CD pipeline automatically creates the four Athena views (`revenue_by_month`, `orders_daily`, `top_products`, `dept_breakdown`) on every deployment.

### 9a. Generate Grafana IAM access key

Terraform creates a read-only IAM user (`<PROJECT>-grafana-reader`) but does **not** generate access keys (to avoid storing secrets in state). Generate them once after your first successful deploy:

```bash
# Get the user name from Terraform output
terraform -chdir=terraform/environments/prod output grafana_reader_user_name

# Generate the access key (save both values — the secret is shown only once)
aws iam create-access-key \
  --user-name "$(terraform -chdir=terraform/environments/prod output -raw grafana_reader_user_name)" \
  --region "$AWS_REGION"
```

The output contains `AccessKeyId` and `SecretAccessKey`. Store both securely — you will need them in step 9c.

### 9b. Create a Grafana Cloud account

1. Go to [grafana.com](https://grafana.com) → **Get started for free**
2. Create an account and a new stack (any region; the Athena plugin works regardless)
3. Note your **Grafana URL** (e.g. `https://yourname.grafana.net`)

### 9c. Install the Athena plugin

1. In your Grafana instance, open **Administration** → **Plugins**
2. Search for **Amazon Athena** → click **Install**
3. After install, click **Add new data source**
4. Configure the datasource:

| Field | Value |
|-------|-------|
| **Authentication Provider** | Access & secret key |
| **Access Key ID** | *(from step 9a)* |
| **Secret Access Key** | *(from step 9a)* |
| **Default Region** | `<AWS_REGION>` |
| **Catalog** | `AwsDataCatalog` |
| **Database** | `lakehouse_dwh` |
| **Workgroup** | `<PROJECT>-workgroup` |
| **Output Location** | `s3://<LAKEHOUSE_BUCKET>/athena-results/` |

5. Click **Save & Test** — you should see "Data source is working"

### 9d. Import the dashboards

Two dashboard JSON files are in the `dashboards/` directory:

| File | Title | Panels |
|------|-------|--------|
| [`dashboards/revenue_overview.json`](dashboards/revenue_overview.json) | E-Commerce Revenue Overview | 8 panels: 4 KPI stats, revenue trend, monthly bar charts, daily detail |
| [`dashboards/product_performance.json`](dashboards/product_performance.json) | E-Commerce Product Performance | 8 panels: 4 KPI stats, top products bar, dept pie, reorder rate, detail table |

**To import each dashboard:**

1. In Grafana, click **Dashboards** (left sidebar) → **New** → **Import**
2. Click **Upload dashboard JSON file** → select the file
3. On the import screen, map **Athena** datasource to the datasource you configured in step 9c
4. Click **Import**

> **Cross-linking:** Both dashboards have a navigation link to each other under the dashboard title. After import, the links become clickable.

### 9e. Verify the data loads

Open **E-Commerce Revenue Overview**. Within ~30 seconds all panels should populate. If a panel shows an error:

- **"No data"** — the pipeline hasn't run yet; trigger a manual execution (see [Section 8c](#8c-trigger-the-pipeline-manually))
- **"Access denied"** — the IAM user policy is missing a permission; verify `grafana.tf` was applied and the correct access key is set in the datasource
- **"Table not found"** — the Athena view wasn't created; check the *Deploy Athena views* step in the last CD run

---

## Appendix A — Terraform Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `project` | Yes | — | Prefix for all AWS resource names. Must be lowercase with hyphens. |
| `bucket` | Yes | — | Globally unique S3 bucket name for all lakehouse data. |
| `region` | No | `us-east-1` | AWS region to deploy into. |
| `alert_email` | Yes | — | Email address for SNS pipeline failure notifications. |

These map to GitHub variables/secrets as:

| Terraform var | GitHub source |
|---------------|---------------|
| `project` | `vars.TF_PROJECT` |
| `bucket` | `vars.LAKEHOUSE_BUCKET` |
| `region` | `vars.AWS_REGION` |
| `alert_email` | `secrets.ALERT_EMAIL` |

---

## Appendix B — What Gets Created by Terraform

All resources are prefixed with `PROJECT` unless noted.

| Service | Resource | Name |
|---------|----------|------|
| **S3** | Lakehouse bucket | `<LAKEHOUSE_BUCKET>` |
| S3 | Sample data objects | `raw/products/`, `raw/orders/`, `raw/order_items/` |
| S3 | Script placeholder | `scripts/utils.zip` *(content managed by CD)* |
| **IAM** | Glue execution role | `<PROJECT>-glue-role` |
| IAM | Step Functions execution role | `<PROJECT>-sfn-role` |
| IAM | EventBridge execution role | `<PROJECT>-eventbridge-role` |
| IAM | Grafana read-only user | `<PROJECT>-grafana-reader` *(access keys created manually)* |
| **Glue** | Catalog database | `lakehouse_dwh` |
| Glue | PySpark ingest job | `<PROJECT>-ingest-delta` |
| Glue | Python Shell archive job | `<PROJECT>-archive-files` |
| Glue | Python Shell timestamp fix job | `<PROJECT>-fix-catalog-timestamps` |
| Glue | Delta Lake crawler | `<PROJECT>-crawler` |
| **Athena** | Workgroup | `<PROJECT>-workgroup` |
| **Step Functions** | State machine | `<PROJECT>-pipeline` |
| **EventBridge** | S3 trigger rule | `<PROJECT>-s3-raw-trigger` |
| **SNS** | Alert topic | `<PROJECT>-pipeline-alerts` |
| SNS | Email subscription | `<ALERT_EMAIL>` |
| **CloudWatch** | Glue crawler log group | `/aws-glue/crawlers` |
| CloudWatch | Ingest job log group | `/aws-glue/jobs/<PROJECT>-ingest-delta` |
| CloudWatch | Archive job log group | `/aws-glue/jobs/<PROJECT>-archive-files` |
| CloudWatch | Timestamp fix log group | `/aws-glue/jobs/<PROJECT>-fix-catalog-timestamps` |
| CloudWatch | SFN execution log group | `/aws/states/<PROJECT>-pipeline` |

> **Lifecycle rules** on the lakehouse bucket: quarantine files expire after 90 days; archive files transition to Glacier after 365 days; Athena query results expire after 30 days.
