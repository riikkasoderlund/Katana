"""
Data connectors for Executive Dashboard
Connects to HubSpot, Databricks Genie, and Slack via configured connectors
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import os


class HubSpotConnector:
    """Connector for HubSpot CRM data via HubSpot connector"""

    def __init__(self):
        # Connector handles authentication automatically
        pass

    def get_deals_created_yesterday(self) -> List[Dict]:
        """Get all sales-assisted pipeline deals created yesterday"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # Query via HubSpot connector
        query = {
            "filterGroups": [{
                "filters": [
                    {
                        "propertyName": "createdate",
                        "operator": "BETWEEN",
                        "value": f"{yesterday}T00:00:00Z",
                        "highValue": f"{yesterday}T23:59:59Z"
                    },
                    {
                        "propertyName": "pipeline",
                        "operator": "EQ",
                        "value": "sales_assisted"
                    }
                ]
            }],
            "properties": ["dealname", "amount", "dealstage", "closedate", "hubspot_owner_id"]
        }

        # Execute via connector
        from connectors import hubspot
        return hubspot.search_deals(query)

    def get_stage_movements_yesterday(self) -> List[Dict]:
        """Get deals that moved stages yesterday"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        from connectors import hubspot

        # Get deal stage changes from activity log
        movements = hubspot.get_deal_property_changes(
            property_name="dealstage",
            from_date=f"{yesterday}T00:00:00Z",
            to_date=f"{yesterday}T23:59:59Z"
        )

        return movements

    def get_pipeline_by_stage(self) -> Dict[str, Dict]:
        """Get current pipeline value grouped by stage"""
        from connectors import hubspot

        stages = ["Qualification", "Solution Validation", "Order form sent"]
        pipeline_data = {}

        for stage in stages:
            deals = hubspot.search_deals({
                "filterGroups": [{
                    "filters": [{
                        "propertyName": "dealstage",
                        "operator": "EQ",
                        "value": stage.lower().replace(" ", "_")
                    }]
                }],
                "properties": ["dealname", "amount"]
            })

            pipeline_data[stage] = {
                "count": len(deals),
                "value": sum(d.get("amount", 0) or 0 for d in deals)
            }

        return pipeline_data

    def get_pipeline_by_stage_on_date(self, date: str) -> Dict[str, Dict]:
        """Get historical pipeline snapshot for a date (for comparison)"""
        from connectors import hubspot

        # Use HubSpot's historical snapshot API if available
        # Otherwise calculate from deal history
        return hubspot.get_pipeline_snapshot(date=date)

    def get_win_rate_weekly(self) -> Dict[str, float]:
        """Calculate week-over-week win rate from Qualification to Closed Won"""
        from connectors import hubspot

        today = datetime.now()
        this_week_start = today - timedelta(days=today.weekday() + 7)  # Last Mon
        last_week_start = this_week_start - timedelta(days=7)

        def calculate_win_rate(start_date: datetime, end_date: datetime) -> float:
            # Get deals that reached Closed Won or Closed Lost in period
            closed_won = hubspot.search_deals({
                "filterGroups": [{
                    "filters": [
                        {
                            "propertyName": "dealstage",
                            "operator": "EQ",
                            "value": "closed_won"
                        },
                        {
                            "propertyName": "closedate",
                            "operator": "BETWEEN",
                            "value": start_date.strftime("%Y-%m-%dT00:00:00Z"),
                            "highValue": end_date.strftime("%Y-%m-%dT23:59:59Z")
                        }
                    ]
                }]
            })

            closed_lost = hubspot.search_deals({
                "filterGroups": [{
                    "filters": [
                        {
                            "propertyName": "dealstage",
                            "operator": "EQ",
                            "value": "closed_lost"
                        },
                        {
                            "propertyName": "closedate",
                            "operator": "BETWEEN",
                            "value": start_date.strftime("%Y-%m-%dT00:00:00Z"),
                            "highValue": end_date.strftime("%Y-%m-%dT23:59:59Z")
                        }
                    ]
                }]
            })

            total = len(closed_won) + len(closed_lost)
            if total == 0:
                return 0.0
            return len(closed_won) / total

        this_week_rate = calculate_win_rate(this_week_start, today)
        last_week_rate = calculate_win_rate(last_week_start, this_week_start)

        return {
            "this_week": this_week_rate,
            "last_week": last_week_rate,
            "change": this_week_rate - last_week_rate
        }


class DatabricksGenieConnector:
    """Connector for Databricks Genie revenue/billing data"""

    def __init__(self):
        pass

    def query(self, sql: str) -> List[Dict]:
        """Execute SQL query via Databricks Genie connector"""
        from connectors import databricks_genie
        return databricks_genie.query(sql)

    def get_current_mrr(self) -> Dict:
        """Get current MRR and ARR"""
        result = self.query("""
            SELECT
                mrr,
                mrr * 12 as arr,
                snapshot_date
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
            SELECT
                mrr,
                mrr * 12 as arr,
                snapshot_date
            FROM finance.mrr_daily
            WHERE snapshot_date = '{yesterday}'
        """)

        if result:
            return result[0]
        return {"mrr": 0, "arr": 0}

    def get_new_business_mrr_yesterday(self) -> float:
        """Get new business MRR from yesterday (new customers)"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        result = self.query(f"""
            SELECT COALESCE(SUM(mrr_change), 0) as new_business_mrr
            FROM finance.mrr_movements
            WHERE movement_date = '{yesterday}'
            AND movement_type = 'new_business'
        """)

        return result[0]["new_business_mrr"] if result else 0

    def get_net_new_mrr_yesterday(self) -> Dict:
        """Get net new MRR breakdown from yesterday"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        result = self.query(f"""
            SELECT
                movement_type,
                SUM(mrr_change) as amount
            FROM finance.mrr_movements
            WHERE movement_date = '{yesterday}'
            GROUP BY movement_type
        """)

        breakdown = {
            "new_business": 0,
            "expansion": 0,
            "contraction": 0,
            "churn": 0,
            "reactivation": 0
        }

        for row in result:
            if row["movement_type"] in breakdown:
                breakdown[row["movement_type"]] = row["amount"]

        breakdown["net_new"] = (
            breakdown["new_business"] +
            breakdown["expansion"] +
            breakdown["reactivation"] -
            abs(breakdown["contraction"]) -
            abs(breakdown["churn"])
        )

        return breakdown

    def get_mtd_revenue(self) -> Dict:
        """Get month-to-date revenue actuals"""
        today = datetime.now()
        month_start = today.replace(day=1).strftime("%Y-%m-%d")

        result = self.query(f"""
            SELECT
                SUM(CASE WHEN movement_type = 'new_business' THEN mrr_change ELSE 0 END) as new_business_mtd,
                SUM(mrr_change) as net_new_mtd
            FROM finance.mrr_movements
            WHERE movement_date >= '{month_start}'
            AND movement_date <= CURRENT_DATE()
        """)

        return result[0] if result else {"new_business_mtd": 0, "net_new_mtd": 0}

    def get_churned_customers_yesterday(self) -> List[Dict]:
        """Get customers who churned or downgraded yesterday"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        result = self.query(f"""
            SELECT
                c.customer_name,
                m.mrr_change,
                m.movement_type,
                m.reason
            FROM finance.mrr_movements m
            JOIN finance.customers c ON m.customer_id = c.customer_id
            WHERE m.movement_date = '{yesterday}'
            AND m.movement_type IN ('churn', 'contraction')
            ORDER BY ABS(m.mrr_change) DESC
        """)

        return result

    def get_last_week_mrr(self) -> float:
        """Get MRR from 7 days ago for WoW comparison"""
        last_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        result = self.query(f"""
            SELECT mrr
            FROM finance.mrr_daily
            WHERE snapshot_date = '{last_week}'
        """)

        return result[0]["mrr"] if result else 0

    def get_last_month_mrr(self) -> float:
        """Get MRR from 30 days ago for MoM comparison"""
        last_month = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        result = self.query(f"""
            SELECT mrr
            FROM finance.mrr_daily
            WHERE snapshot_date = '{last_month}'
        """)

        return result[0]["mrr"] if result else 0


class SlackConnector:
    """Connector for sending Slack messages"""

    def __init__(self):
        pass

    def send_message(self, channel: str, text: str, blocks: Optional[List[Dict]] = None):
        """Send a message to Slack channel or user"""
        from connectors import slack

        slack.post_message(
            channel=channel,
            text=text,
            blocks=blocks
        )

    def send_dashboard_report(self, channel: str, report: Dict):
        """Send formatted dashboard report to Slack"""
        blocks = self._format_report_blocks(report)

        self.send_message(
            channel=channel,
            text=f"Daily Executive Dashboard - {report['date']}",
            blocks=blocks
        )

    def _format_report_blocks(self, report: Dict) -> List[Dict]:
        """Format report into Slack blocks"""
        blocks = []

        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Daily Executive Dashboard - {report['date']}"
            }
        })

        # Executive Summary
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*EXECUTIVE SUMMARY*"
            }
        })

        summary_text = "\n".join([f"  {item}" for item in report["executive_summary"]])
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": summary_text
            }
        })

        # Pipeline Health
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*PIPELINE HEALTH* {report['pipeline']['status_emoji']}"
            }
        })
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": report["pipeline"]["formatted"]
            }
        })

        # Revenue Performance
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*REVENUE PERFORMANCE* {report['revenue']['status_emoji']}"
            }
        })
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": report["revenue"]["formatted"]
            }
        })

        # Churn & Retention
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*CHURN & RETENTION* {report['churn']['status_emoji']}"
            }
        })
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": report["churn"]["formatted"]
            }
        })

        # Footer
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M')} Helsinki | Data sources: HubSpot, Databricks Genie"
            }]
        })

        return blocks
