"""
Data connectors for Executive Dashboard
Connects to HubSpot, Databricks Genie, and Slack via REST APIs
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import os
import json
import urllib.request
import urllib.error


class HubSpotConnector:
    """Connector for HubSpot CRM data via REST API"""

    def __init__(self):
        self.api_key = os.environ.get("HUBSPOT_API_KEY", "")
        self.base_url = "https://api.hubapi.com"

    def _request(self, method: str, endpoint: str, data: Dict = None) -> Any:
        """Make HTTP request to HubSpot API"""
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        req_data = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            print(f"HubSpot API error: {e.code} - {e.read().decode()}")
            return None

    def get_deals_created_yesterday(self) -> List[Dict]:
        """Get all sales-assisted pipeline deals created yesterday"""
        yesterday = datetime.now() - timedelta(days=1)
        yesterday_start = int(yesterday.replace(hour=0, minute=0, second=0).timestamp() * 1000)
        yesterday_end = int(yesterday.replace(hour=23, minute=59, second=59).timestamp() * 1000)

        query = {
            "filterGroups": [{
                "filters": [
                    {"propertyName": "createdate", "operator": "GTE", "value": str(yesterday_start)},
                    {"propertyName": "createdate", "operator": "LTE", "value": str(yesterday_end)}
                ]
            }],
            "properties": ["dealname", "amount", "dealstage", "closedate", "hubspot_owner_id", "pipeline"],
            "limit": 100
        }

        result = self._request("POST", "/crm/v3/objects/deals/search", query)
        if result and "results" in result:
            return [{"deal_name": r["properties"].get("dealname"),
                     "amount": float(r["properties"].get("amount") or 0),
                     "stage": r["properties"].get("dealstage"),
                     "pipeline": r["properties"].get("pipeline")}
                    for r in result["results"]]
        return []

    def get_stage_movements_yesterday(self) -> List[Dict]:
        """Get deals that moved stages yesterday via property history"""
        # Get all deals and check their history
        yesterday = datetime.now() - timedelta(days=1)
        movements = []

        # Get recent deals
        result = self._request("POST", "/crm/v3/objects/deals/search", {
            "filterGroups": [{
                "filters": [
                    {"propertyName": "hs_lastmodifieddate", "operator": "GTE",
                     "value": str(int(yesterday.replace(hour=0, minute=0, second=0).timestamp() * 1000))}
                ]
            }],
            "properties": ["dealname", "dealstage", "amount"],
            "limit": 100
        })

        if result and "results" in result:
            for deal in result["results"]:
                deal_id = deal["id"]
                # Get property history for dealstage
                history = self._request("GET", f"/crm/v3/objects/deals/{deal_id}?propertiesWithHistory=dealstage")
                if history and "propertiesWithHistory" in history:
                    stage_history = history["propertiesWithHistory"].get("dealstage", [])
                    for i, change in enumerate(stage_history[:-1] if len(stage_history) > 1 else []):
                        change_time = datetime.fromtimestamp(int(change.get("timestamp", 0)) / 1000)
                        if change_time.date() == yesterday.date():
                            movements.append({
                                "deal_name": deal["properties"].get("dealname"),
                                "from_stage": self._stage_id_to_name(change.get("value")),
                                "to_stage": self._stage_id_to_name(stage_history[i + 1].get("value")) if i + 1 < len(stage_history) else "Unknown",
                                "amount": float(deal["properties"].get("amount") or 0)
                            })
        return movements

    def _stage_id_to_name(self, stage_id: str) -> str:
        """Map stage ID to readable name"""
        stage_map = {
            "qualification": "Qualification",
            "solution_validation": "Solution Validation",
            "order_form_sent": "Order form sent",
            "closedwon": "Closed Won",
            "closedlost": "Closed Lost"
        }
        return stage_map.get(stage_id, stage_id or "Unknown")

    def get_pipeline_by_stage(self) -> Dict[str, Dict]:
        """Get current pipeline value grouped by stage"""
        stages = {
            "Qualification": "qualification",
            "Solution Validation": "solution_validation",
            "Order form sent": "order_form_sent"
        }
        pipeline_data = {}

        for stage_name, stage_id in stages.items():
            result = self._request("POST", "/crm/v3/objects/deals/search", {
                "filterGroups": [{
                    "filters": [{"propertyName": "dealstage", "operator": "EQ", "value": stage_id}]
                }],
                "properties": ["dealname", "amount"],
                "limit": 100
            })

            deals = result.get("results", []) if result else []
            pipeline_data[stage_name] = {
                "count": len(deals),
                "value": sum(float(d["properties"].get("amount") or 0) for d in deals)
            }

        return pipeline_data

    def get_pipeline_by_stage_on_date(self, date: str) -> Dict[str, Dict]:
        """Get historical pipeline snapshot - approximation based on current data"""
        # HubSpot doesn't have native snapshots, return current as baseline
        return self.get_pipeline_by_stage()

    def get_win_rate_weekly(self) -> Dict[str, float]:
        """Calculate week-over-week win rate from Qualification to Closed Won"""
        today = datetime.now()
        this_week_start = today - timedelta(days=today.weekday() + 7)
        last_week_start = this_week_start - timedelta(days=7)

        def get_closed_deals(start: datetime, end: datetime, won: bool) -> int:
            stage = "closedwon" if won else "closedlost"
            result = self._request("POST", "/crm/v3/objects/deals/search", {
                "filterGroups": [{
                    "filters": [
                        {"propertyName": "dealstage", "operator": "EQ", "value": stage},
                        {"propertyName": "closedate", "operator": "GTE",
                         "value": str(int(start.timestamp() * 1000))},
                        {"propertyName": "closedate", "operator": "LTE",
                         "value": str(int(end.timestamp() * 1000))}
                    ]
                }],
                "limit": 100
            })
            return len(result.get("results", [])) if result else 0

        this_won = get_closed_deals(this_week_start, today, True)
        this_lost = get_closed_deals(this_week_start, today, False)
        last_won = get_closed_deals(last_week_start, this_week_start, True)
        last_lost = get_closed_deals(last_week_start, this_week_start, False)

        this_rate = this_won / (this_won + this_lost) if (this_won + this_lost) > 0 else 0
        last_rate = last_won / (last_won + last_lost) if (last_won + last_lost) > 0 else 0

        return {
            "this_week": this_rate,
            "last_week": last_rate,
            "change": this_rate - last_rate
        }


class DatabricksGenieConnector:
    """Connector for Databricks Genie revenue/billing data via SQL API"""

    def __init__(self):
        self.host = os.environ.get("DATABRICKS_HOST", "")
        self.token = os.environ.get("DATABRICKS_TOKEN", "")
        self.warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")

    def query(self, sql: str) -> List[Dict]:
        """Execute SQL query via Databricks SQL API"""
        url = f"https://{self.host}/api/2.0/sql/statements"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        data = json.dumps({
            "warehouse_id": self.warehouse_id,
            "statement": sql,
            "wait_timeout": "30s"
        }).encode()

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode())

                if result.get("status", {}).get("state") == "SUCCEEDED":
                    columns = [col["name"] for col in result.get("manifest", {}).get("schema", {}).get("columns", [])]
                    rows = result.get("result", {}).get("data_array", [])
                    return [dict(zip(columns, row)) for row in rows]
                return []
        except urllib.error.HTTPError as e:
            print(f"Databricks API error: {e.code} - {e.read().decode()}")
            return []

    def get_current_mrr(self) -> Dict:
        """Get current MRR and ARR"""
        result = self.query("""
            SELECT mrr, mrr * 12 as arr, snapshot_date
            FROM finance.mrr_daily
            WHERE snapshot_date = CURRENT_DATE()
        """)
        if result:
            return result[0]
        return {"mrr": 0, "arr": 0, "snapshot_date": datetime.now().strftime("%Y-%m-%d")}

    def get_yesterday_mrr(self) -> Dict:
        """Get MRR from yesterday for comparison"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        result = self.query(f"""
            SELECT mrr, mrr * 12 as arr, snapshot_date
            FROM finance.mrr_daily WHERE snapshot_date = '{yesterday}'
        """)
        return result[0] if result else {"mrr": 0, "arr": 0}

    def get_new_business_mrr_yesterday(self) -> float:
        """Get new business MRR from yesterday (new customers)"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        result = self.query(f"""
            SELECT COALESCE(SUM(mrr_change), 0) as new_business_mrr
            FROM finance.mrr_movements
            WHERE movement_date = '{yesterday}' AND movement_type = 'new_business'
        """)
        return float(result[0]["new_business_mrr"]) if result else 0

    def get_net_new_mrr_yesterday(self) -> Dict:
        """Get net new MRR breakdown from yesterday"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        result = self.query(f"""
            SELECT movement_type, SUM(mrr_change) as amount
            FROM finance.mrr_movements
            WHERE movement_date = '{yesterday}'
            GROUP BY movement_type
        """)

        breakdown = {"new_business": 0, "expansion": 0, "contraction": 0, "churn": 0, "reactivation": 0}
        for row in result:
            if row["movement_type"] in breakdown:
                breakdown[row["movement_type"]] = float(row["amount"])

        breakdown["net_new"] = (
            breakdown["new_business"] + breakdown["expansion"] + breakdown["reactivation"]
            - abs(breakdown["contraction"]) - abs(breakdown["churn"])
        )
        return breakdown

    def get_mtd_revenue(self) -> Dict:
        """Get month-to-date revenue actuals"""
        month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        result = self.query(f"""
            SELECT
                SUM(CASE WHEN movement_type = 'new_business' THEN mrr_change ELSE 0 END) as new_business_mtd,
                SUM(mrr_change) as net_new_mtd
            FROM finance.mrr_movements
            WHERE movement_date >= '{month_start}' AND movement_date <= CURRENT_DATE()
        """)
        if result:
            return {"new_business_mtd": float(result[0]["new_business_mtd"] or 0),
                    "net_new_mtd": float(result[0]["net_new_mtd"] or 0)}
        return {"new_business_mtd": 0, "net_new_mtd": 0}

    def get_churned_customers_yesterday(self) -> List[Dict]:
        """Get customers who churned or downgraded yesterday"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        return self.query(f"""
            SELECT c.customer_name, m.mrr_change, m.movement_type, m.reason
            FROM finance.mrr_movements m
            JOIN finance.customers c ON m.customer_id = c.customer_id
            WHERE m.movement_date = '{yesterday}'
            AND m.movement_type IN ('churn', 'contraction')
            ORDER BY ABS(m.mrr_change) DESC
        """)

    def get_last_week_mrr(self) -> float:
        """Get MRR from 7 days ago for WoW comparison"""
        last_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        result = self.query(f"SELECT mrr FROM finance.mrr_daily WHERE snapshot_date = '{last_week}'")
        return float(result[0]["mrr"]) if result else 0

    def get_last_month_mrr(self) -> float:
        """Get MRR from 30 days ago for MoM comparison"""
        last_month = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        result = self.query(f"SELECT mrr FROM finance.mrr_daily WHERE snapshot_date = '{last_month}'")
        return float(result[0]["mrr"]) if result else 0


class SlackConnector:
    """Connector for sending Slack messages via API"""

    def __init__(self):
        self.token = os.environ.get("SLACK_BOT_TOKEN", "")

    def send_message(self, channel: str, text: str, blocks: Optional[List[Dict]] = None):
        """Send a message to Slack channel or user"""
        url = "https://slack.com/api/chat.postMessage"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        payload = {"channel": channel, "text": text}
        if blocks:
            payload["blocks"] = blocks

        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode())
                if not result.get("ok"):
                    print(f"Slack API error: {result.get('error')}")
                return result
        except urllib.error.HTTPError as e:
            print(f"Slack API error: {e.code} - {e.read().decode()}")
            return None

    def send_dashboard_report(self, channel: str, report: Dict):
        """Send formatted dashboard report to Slack"""
        blocks = self._format_report_blocks(report)
        self.send_message(channel=channel, text=f"Daily Executive Dashboard - {report['date']}", blocks=blocks)

    def _format_report_blocks(self, report: Dict) -> List[Dict]:
        """Format report into Slack blocks"""
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"Daily Executive Dashboard - {report['date']}"}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*EXECUTIVE SUMMARY*"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join([f"  {item}" for item in report["executive_summary"]])}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*PIPELINE HEALTH* {report['pipeline']['status_emoji']}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": report["pipeline"]["formatted"]}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*REVENUE PERFORMANCE* {report['revenue']['status_emoji']}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": report["revenue"]["formatted"]}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*CHURN & RETENTION* {report['churn']['status_emoji']}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": report["churn"]["formatted"]}},
            {"type": "divider"},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M')} Helsinki | Data sources: HubSpot, Databricks Genie"}]}
        ]
        return blocks
