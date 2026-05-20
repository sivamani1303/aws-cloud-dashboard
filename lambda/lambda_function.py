import json
import boto3
from datetime import datetime, timedelta


def lambda_handler(event, context):
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/json"
    }
    try:
        data = {
            "ec2":     get_ec2_instances(),
            "s3":      get_s3_buckets(),
            "cost":    get_cost_data(),
            "summary": get_account_summary()
        }
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
    response = ce.get_cost_and_usage(
        TimePeriod={
            "Start": start.strftime("%Y-%m-%d"),
            "End":   end.strftime("%Y-%m-%d")
        },
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}]
    )
    monthly = []
    for result in response["ResultsByTime"]:
        month = result["TimePeriod"]["Start"][:7]
        total = sum(
            float(g["Metrics"]["UnblendedCost"]["Amount"])
            for g in result["Groups"]
        )
        monthly.append({
            "month": month,
            "total": round(total, 2)
        })
    current = monthly[-1]["total"] if monthly else 0
    return {
        "current_month": current,
        "monthly": monthly
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


