import json
import boto3
from datetime import datetime, timedelta
from decimal import Decimal

def lambda_handler(event, context):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json"
    }
    try:
        data = {
            "ec2":        get_ec2_instances(),
            "s3":         get_s3_buckets(),
            "cost":       get_cost_data(),
            "summary":    get_account_summary(),
            "activities": get_recent_activities(),
            "budgets":    get_budget_info(),
            "history":    get_snapshot_history()
        }
        try:
            save_snapshot(data)
        except Exception as snap_err:
            print(f"Snapshot save failed: {snap_err}")
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps(data)
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps({"error": str(e)})
        }


def get_ec2_instances():
    ec2 = boto3.client("ec2", region_name="ap-south-1")
    response = ec2.describe_instances()
    instances = []
    for reservation in response["Reservations"]:
        for inst in reservation["Instances"]:
            name = "Unnamed"
            for tag in inst.get("Tags", []):
                if tag["Key"] == "Name":
                    name = tag["Value"]
            instances.append({
                "id":    inst["InstanceId"],
                "name":  name,
                "type":  inst["InstanceType"],
                "state": inst["State"]["Name"]
            })
    return {
        "total":   len(instances),
        "running": sum(1 for i in instances if i["state"] == "running"),
        "stopped": sum(1 for i in instances if i["state"] == "stopped"),
        "list":    instances
    }


def get_s3_buckets():
    s3 = boto3.client("s3", region_name="ap-south-1")
    response = s3.list_buckets()
    buckets = []
    for bucket in response["Buckets"]:
        buckets.append({
            "name":    bucket["Name"],
            "created": str(bucket["CreationDate"])
        })
    return {
        "total": len(buckets),
        "list":  buckets
    }


def get_cost_data():
    ce = boto3.client("ce", region_name="us-east-1")
    end   = datetime.today()
    start = end - timedelta(days=180)

    # Get ALL record types to see what's there
    response = ce.get_cost_and_usage(
        TimePeriod={
            "Start": start.strftime("%Y-%m-%d"),
            "End":   end.strftime("%Y-%m-%d")
        },
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "RECORD_TYPE"}]
    )

    monthly = []
    for result in response["ResultsByTime"]:
        month = result["TimePeriod"]["Start"][:7]
        breakdown = {}
        usage_total = 0

        for g in result["Groups"]:
            record_type = g["Keys"][0]
            amount = float(g["Metrics"]["UnblendedCost"]["Amount"])
            breakdown[record_type] = round(amount, 4)
            # Only sum Usage and Tax — exclude Credits
            if record_type in ["Usage", "Tax", "Fee"]:
                usage_total += amount

        monthly.append({
            "month":     month,
            "total":     round(usage_total, 2),
            "breakdown": breakdown
        })

    current = monthly[-1]["total"] if monthly else 0
    return {
        "current_month": current,
        "monthly":       monthly
    }

def get_account_summary():
    iam = boto3.client("iam", region_name="ap-south-1")
    summary = iam.get_account_summary()["SummaryMap"]
    return {
        "users":       summary.get("Users", 0),
        "roles":       summary.get("Roles", 0),
        "policies":    summary.get("Policies", 0),
        "mfa_enabled": summary.get("AccountMFAEnabled", 0) == 1
    }

def get_recent_activities():
    ct = boto3.client("cloudtrail", region_name="ap-south-1")

    # WHITELIST — only show these meaningful actions
    # Add more here as you use new AWS services
    important_actions = {
        # EC2
        "RunInstances", "StartInstances", "StopInstances",
        "TerminateInstances", "RebootInstances",

        # S3
        "CreateBucket", "DeleteBucket", "PutBucketPolicy",
        "PutBucketWebsite", "PutPublicAccessBlock",

        # IAM
        "CreateUser", "DeleteUser", "CreateRole", "DeleteRole",
        "AttachUserPolicy", "DetachUserPolicy", "AttachRolePolicy",
        "CreateAccessKey", "DeleteAccessKey", "EnableMFADevice",

        # Lambda
        "CreateFunction20150331", "DeleteFunction",
        "UpdateFunctionCode20150331v2",

        # API Gateway
        "CreateRestApi", "DeleteRestApi", "CreateDeployment",

        # CloudWatch
        "PutMetricAlarm", "DeleteAlarms",

        # SNS
        "CreateTopic", "DeleteTopic", "Subscribe",

        # CloudTrail
        "CreateTrail", "DeleteTrail", "StartLogging", "StopLogging",

        # RDS
        "CreateDBInstance", "StopDBInstance",
        "StartDBInstance", "DeleteDBInstance",
    }

    activities = []
    next_token = None

    for _ in range(10):  # look through up to 1000 events
        kwargs = {"MaxResults": 50}
        if next_token:
            kwargs["NextToken"] = next_token

        response = ct.lookup_events(**kwargs)

        for event in response["Events"]:
            action = event["EventName"]

            # Only include if it's in our important list
            if action not in important_actions:
                continue

            resource = ""
            if event.get("Resources"):
                for r in event["Resources"]:
                    name = r.get("ResourceName", "")
                    if name and name != "null":
                        resource = name
                        break

            if not resource and event.get("CloudTrailEvent"):
                try:
                    ct_event = json.loads(event["CloudTrailEvent"])
                    req = ct_event.get("requestParameters", {})
                    if req:
                        resource = (
                            req.get("instancesSet", {}).get("items", [{}])[0].get("instanceId", "") or
                            req.get("bucketName", "") or
                            req.get("functionName", "") or
                            req.get("roleName", "") or
                            req.get("userName", "") or
                            req.get("topicArn", "") or
                            req.get("alarmName", "") or
                            req.get("trailName", "") or
                            req.get("restApiId", "") or
                            ""
                        )
                except:
                    pass

            activities.append({
                "time":     str(event["EventTime"]),
                "user":     event.get("Username", "AWS"),
                "action":   action,
                "resource": resource
            })

            if len(activities) == 15:
                return activities

        next_token = response.get("NextToken")
        if not next_token:
            break

    return activities

def get_budget_info():
    budgets = boto3.client("budgets", region_name="us-east-1")

    try:
        account_id = boto3.client(
            "sts", region_name="ap-south-1"
        ).get_caller_identity()["Account"]

        response = budgets.describe_budgets(
            AccountId=account_id
        )

        budget_list = []
        for budget in response["Budgets"]:
            budget_list.append({
                "name":       budget["BudgetName"],
                "limit":      float(budget["BudgetLimit"]["Amount"]),
                "actual":     float(budget.get("CalculatedSpend", {})
                              .get("ActualSpend", {})
                              .get("Amount", 0)),
                "forecasted": float(budget.get("CalculatedSpend", {})
                              .get("ForecastedSpend", {})
                              .get("Amount", 0))
            })

        return budget_list

    except Exception as e:
        return []    

def save_snapshot(data):
    dynamodb = boto3.resource("dynamodb", region_name="ap-south-1")
    table    = dynamodb.Table("dashboard-snapshots")

    # DynamoDB doesn't accept float — convert to Decimal
    snapshot = {
        "timestamp":      datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        "ec2_total":      data["ec2"]["total"],
        "ec2_running":    data["ec2"]["running"],
        "ec2_stopped":    data["ec2"]["stopped"],
        "s3_total":       data["s3"]["total"],
        "iam_users":      data["summary"]["users"],
        "iam_roles":      data["summary"]["roles"],
        "cost_month":     Decimal(str(data["cost"]["current_month"])),
        "mfa_enabled":    data["summary"]["mfa_enabled"]
    }

    table.put_item(Item=snapshot)

def get_snapshot_history():
    dynamodb = boto3.resource("dynamodb", region_name="ap-south-1")
    table    = dynamodb.Table("dashboard-snapshots")

    response = table.scan(
        Limit=10,
        ProjectionExpression="#ts, ec2_total, ec2_running, s3_total, cost_month",
        ExpressionAttributeNames={"#ts": "timestamp"}
    )

    items = sorted(
        response["Items"],
        key=lambda x: x["timestamp"],
        reverse=True
    )

    return [{
        "timestamp":   item["timestamp"],
        "ec2_total":   int(item.get("ec2_total", 0)),
        "ec2_running": int(item.get("ec2_running", 0)),
        "s3_total":    int(item.get("s3_total", 0)),
        "cost_month":  float(item.get("cost_month", 0))
    } for item in items]