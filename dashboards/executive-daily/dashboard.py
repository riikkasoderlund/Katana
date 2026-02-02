"""
Executive Daily Dashboard
Generates daily executive report with pipeline, revenue, and churn metrics
Scheduled to run at 7 AM Helsinki time
"""
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import yaml
import os

from connectors import HubSpotConnector, DatabricksGenieConnector, SlackConnector


class ExecutiveDashboard:
    """Main dashboard class that orchestrates data collection and reporting"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config.yaml")

        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.hubspot = HubSpotConnector()
        self.databricks = DatabricksGenieConnector()
        self.slack = SlackConnector()

        self.today = datetime.now()
        self.yesterday = self.today - timedelta(days=1)

    def get_monthly_targets(self) -> Dict:
        """Get targets for current month from config"""
        year = str(self.today.year)
        month = self.today.strftime("%m")

        targets = self.config.get("targets", {}).get(year, {}).get(month, {})
        return {
            "new_business_mrr": targets.get("new_business_mrr", 0),
            "net_new_mrr": targets.get("net_new_mrr", 0),
            "mrr_eom": targets.get("mrr_eom", 0)
        }

    def calculate_rag_status(self, metric: str, value: float, target: float) -> Tuple[str, str]:
        """Calculate RAG status and return (status, emoji)"""
        thresholds = self.config.get("thresholds", {})

        if metric == "revenue_mtd":
            green_threshold = thresholds.get("revenue", {}).get("mtd_green", 0.95)
            yellow_threshold = thresholds.get("revenue", {}).get("mtd_yellow", 0.80)
        elif metric == "churn":
            green_threshold = thresholds.get("churn", {}).get("gross_churn_green", 0.025)
            yellow_threshold = thresholds.get("churn", {}).get("gross_churn_yellow", 0.030)
            # Invert for churn (lower is better)
            if value <= green_threshold:
                return ("green", ":large_green_circle:")
            elif value <= yellow_threshold:
                return ("yellow", ":large_yellow_circle:")
            else:
                return ("red", ":red_circle:")
        else:
            green_threshold = 0.95
            yellow_threshold = 0.80

        if target == 0:
            return ("green", ":large_green_circle:")

        ratio = value / target
        if ratio >= green_threshold:
            return ("green", ":large_green_circle:")
        elif ratio >= yellow_threshold:
            return ("yellow", ":large_yellow_circle:")
        else:
            return ("red", ":red_circle:")

    def get_trend_indicator(self, current: float, previous: float) -> str:
        """Get trend arrow indicator"""
        if previous == 0:
            return ""
        change_pct = ((current - previous) / previous) * 100

        if change_pct > 5:
            return "↑"
        elif change_pct < -5:
            return "↓"
        else:
            return "→"

    def format_currency(self, amount: float) -> str:
        """Format number as currency"""
        return f"${amount:,.0f}"

    def format_percentage(self, value: float) -> str:
        """Format as percentage"""
        return f"{value:.1%}"

    def generate_pipeline_section(self) -> Dict:
        """Generate pipeline health section"""
        # Get data
        new_deals = self.hubspot.get_deals_created_yesterday()
        stage_movements = self.hubspot.get_stage_movements_yesterday()
        current_pipeline = self.hubspot.get_pipeline_by_stage()

        yesterday_str = self.yesterday.strftime("%Y-%m-%d")
        yesterday_pipeline = self.hubspot.get_pipeline_by_stage_on_date(yesterday_str)

        # Format new deals
        new_deals_count = len(new_deals)
        new_deals_value = sum(d.get("amount", 0) or 0 for d in new_deals)

        # Format stage movements
        movements_formatted = []
        for m in stage_movements[:5]:  # Top 5
            movements_formatted.append(
                f"  {m.get('deal_name', 'Unknown')}: {m.get('from_stage', '?')} → {m.get('to_stage', '?')}"
            )

        # Format pipeline by stage with comparison
        pipeline_formatted = []
        total_pipeline = 0
        for stage in ["Qualification", "Solution Validation", "Order form sent"]:
            current = current_pipeline.get(stage, {"count": 0, "value": 0})
            previous = yesterday_pipeline.get(stage, {"count": 0, "value": 0})

            change = current["value"] - previous["value"]
            trend = self.get_trend_indicator(current["value"], previous["value"])

            pipeline_formatted.append(
                f"  *{stage}*: {current['count']} deals | {self.format_currency(current['value'])} "
                f"({'+' if change >= 0 else ''}{self.format_currency(change)}) {trend}"
            )
            total_pipeline += current["value"]

        # Determine RAG status based on pipeline coverage
        targets = self.get_monthly_targets()
        days_remaining = (self.today.replace(month=self.today.month % 12 + 1, day=1) - timedelta(days=1)).day - self.today.day
        needed_to_close = targets["new_business_mrr"] - self.databricks.get_mtd_revenue().get("new_business_mtd", 0)

        # Simple coverage calculation
        coverage = total_pipeline / needed_to_close if needed_to_close > 0 else 2.0
        status, emoji = self.calculate_rag_status("pipeline", coverage, 1.0)

        formatted = f"""*New Pipeline Yesterday:* {new_deals_count} deals | {self.format_currency(new_deals_value)}

*Stage Movements Yesterday:*
{chr(10).join(movements_formatted) if movements_formatted else '  No stage movements'}

*Current Pipeline by Stage (vs yesterday):*
{chr(10).join(pipeline_formatted)}

*Total Active Pipeline:* {self.format_currency(total_pipeline)}"""

        return {
            "status": status,
            "status_emoji": emoji,
            "formatted": formatted,
            "alerts": self._generate_pipeline_alerts(new_deals_count, stage_movements, coverage)
        }

    def _generate_pipeline_alerts(self, new_deals: int, movements: List, coverage: float) -> List[str]:
        """Generate alerts for pipeline section"""
        alerts = []

        if new_deals == 0:
            alerts.append(":warning: No new deals created yesterday")

        if coverage < 0.8:
            alerts.append(f":red_circle: Pipeline coverage below 80% - need more deals to hit target")

        # Check for deals moving backward
        backward_moves = [m for m in movements if self._is_backward_move(m)]
        if backward_moves:
            alerts.append(f":warning: {len(backward_moves)} deal(s) moved backward in pipeline")

        return alerts

    def _is_backward_move(self, movement: Dict) -> bool:
        """Check if a stage movement is backward"""
        stage_order = ["Qualification", "Solution Validation", "Order form sent", "Closed Won"]
        from_idx = stage_order.index(movement.get("from_stage", "")) if movement.get("from_stage") in stage_order else -1
        to_idx = stage_order.index(movement.get("to_stage", "")) if movement.get("to_stage") in stage_order else -1
        return to_idx < from_idx and to_idx >= 0

    def generate_revenue_section(self) -> Dict:
        """Generate revenue performance section"""
        # Get current metrics
        current_mrr_data = self.databricks.get_current_mrr()
        current_mrr = current_mrr_data.get("mrr", 0)
        current_arr = current_mrr_data.get("arr", 0)

        # Yesterday's metrics
        new_business_yesterday = self.databricks.get_new_business_mrr_yesterday()
        net_new_breakdown = self.databricks.get_net_new_mrr_yesterday()
        net_new_yesterday = net_new_breakdown.get("net_new", 0)

        # MTD metrics
        mtd_revenue = self.databricks.get_mtd_revenue()
        mtd_new_business = mtd_revenue.get("new_business_mtd", 0)
        mtd_net_new = mtd_revenue.get("net_new_mtd", 0)

        # Targets
        targets = self.get_monthly_targets()
        target_new_business = targets["new_business_mrr"]
        target_net_new = targets["net_new_mrr"]

        # Calculate remaining
        days_in_month = (self.today.replace(month=self.today.month % 12 + 1, day=1) - timedelta(days=1)).day
        days_remaining = days_in_month - self.today.day
        days_elapsed = self.today.day

        new_business_remaining = target_new_business - mtd_new_business
        net_new_remaining = target_net_new - mtd_net_new

        daily_needed_new_business = new_business_remaining / days_remaining if days_remaining > 0 else 0
        daily_needed_net_new = net_new_remaining / days_remaining if days_remaining > 0 else 0

        # Expected pace (linear)
        expected_new_business_mtd = (target_new_business / days_in_month) * days_elapsed
        expected_net_new_mtd = (target_net_new / days_in_month) * days_elapsed

        # WoW and MoM trends
        last_week_mrr = self.databricks.get_last_week_mrr()
        last_month_mrr = self.databricks.get_last_month_mrr()

        wow_trend = self.get_trend_indicator(current_mrr, last_week_mrr)
        mom_trend = self.get_trend_indicator(current_mrr, last_month_mrr)

        wow_change = current_mrr - last_week_mrr
        mom_change = current_mrr - last_month_mrr

        # Win rate
        win_rate_data = self.hubspot.get_win_rate_weekly()
        win_rate_current = win_rate_data.get("this_week", 0)
        win_rate_change = win_rate_data.get("change", 0)

        # RAG status based on MTD pace
        new_business_pace = mtd_new_business / expected_new_business_mtd if expected_new_business_mtd > 0 else 1
        net_new_pace = mtd_net_new / expected_net_new_mtd if expected_net_new_mtd > 0 else 1
        overall_pace = (new_business_pace + net_new_pace) / 2

        status, emoji = self.calculate_rag_status("revenue_mtd", overall_pace, 1.0)

        new_business_status, nb_emoji = self.calculate_rag_status("revenue_mtd", new_business_pace, 1.0)
        net_new_status, nn_emoji = self.calculate_rag_status("revenue_mtd", net_new_pace, 1.0)

        formatted = f"""*MRR/ARR Today:*
  MRR: {self.format_currency(current_mrr)} (WoW: {'+' if wow_change >= 0 else ''}{self.format_currency(wow_change)} {wow_trend} | MoM: {'+' if mom_change >= 0 else ''}{self.format_currency(mom_change)} {mom_trend})
  ARR: {self.format_currency(current_arr)}

*Yesterday's Performance:*
  New Business MRR: {self.format_currency(new_business_yesterday)}
  Net New MRR: {self.format_currency(net_new_yesterday)}
    - Expansion: {self.format_currency(net_new_breakdown.get('expansion', 0))}
    - Contraction: {self.format_currency(net_new_breakdown.get('contraction', 0))}
    - Churn: {self.format_currency(net_new_breakdown.get('churn', 0))}
    - Reactivation: {self.format_currency(net_new_breakdown.get('reactivation', 0))}

*MTD vs Target:* {nb_emoji}
  New Business: {self.format_currency(mtd_new_business)} / {self.format_currency(target_new_business)} ({self.format_percentage(mtd_new_business/target_new_business if target_new_business else 0)})
  Net New: {self.format_currency(mtd_net_new)} / {self.format_currency(target_net_new)} ({self.format_percentage(mtd_net_new/target_net_new if target_net_new else 0)}) {nn_emoji}

*To Hit Target ({days_remaining} days remaining):*
  New Business needed: {self.format_currency(new_business_remaining)} ({self.format_currency(daily_needed_new_business)}/day)
  Net New needed: {self.format_currency(net_new_remaining)} ({self.format_currency(daily_needed_net_new)}/day)

*Win Rate (Qualification → Closed Won):*
  This week: {self.format_percentage(win_rate_current)} ({'+' if win_rate_change >= 0 else ''}{self.format_percentage(win_rate_change)} vs last week)"""

        return {
            "status": status,
            "status_emoji": emoji,
            "formatted": formatted,
            "alerts": self._generate_revenue_alerts(
                new_business_pace, net_new_pace, daily_needed_new_business, win_rate_change
            ),
            "new_business_pace": new_business_pace,
            "net_new_pace": net_new_pace
        }

    def _generate_revenue_alerts(self, nb_pace: float, nn_pace: float,
                                  daily_needed: float, win_rate_change: float) -> List[str]:
        """Generate alerts for revenue section"""
        alerts = []

        if nb_pace < 0.8:
            alerts.append(f":red_circle: New business MRR is {self.format_percentage(1-nb_pace)} behind pace")

        if nn_pace < 0.8:
            alerts.append(f":red_circle: Net new MRR is {self.format_percentage(1-nn_pace)} behind pace")

        if daily_needed > 5000:  # High daily target
            alerts.append(f":warning: Need {self.format_currency(daily_needed)}/day - above typical daily close rate")

        if win_rate_change < -0.1:
            alerts.append(f":warning: Win rate dropped {self.format_percentage(abs(win_rate_change))} vs last week")

        return alerts

    def generate_churn_section(self) -> Dict:
        """Generate churn & retention section"""
        # Get churned/downgraded customers
        churned_customers = self.databricks.get_churned_customers_yesterday()

        # Calculate totals
        total_churn_mrr = sum(
            abs(c.get("mrr_change", 0))
            for c in churned_customers
            if c.get("movement_type") == "churn"
        )
        total_contraction_mrr = sum(
            abs(c.get("mrr_change", 0))
            for c in churned_customers
            if c.get("movement_type") == "contraction"
        )

        # Format customer list
        customer_list = []
        for c in churned_customers[:5]:  # Top 5 by impact
            movement = "Churned" if c.get("movement_type") == "churn" else "Downgraded"
            reason = c.get("reason", "No reason provided")
            customer_list.append(
                f"  {c.get('customer_name', 'Unknown')}: {movement} | -{self.format_currency(abs(c.get('mrr_change', 0)))} | Reason: {reason}"
            )

        # Get gross churn rate (would need monthly calculation)
        current_mrr = self.databricks.get_current_mrr().get("mrr", 1)
        gross_churn_rate = (total_churn_mrr + total_contraction_mrr) / current_mrr if current_mrr > 0 else 0

        # RAG status
        daily_churn_alert = self.config.get("thresholds", {}).get("churn", {}).get("daily_churn_alert", 5000)
        total_yesterday_churn = total_churn_mrr + total_contraction_mrr

        if total_yesterday_churn > daily_churn_alert:
            status, emoji = "red", ":red_circle:"
        elif total_yesterday_churn > daily_churn_alert * 0.5:
            status, emoji = "yellow", ":large_yellow_circle:"
        else:
            status, emoji = "green", ":large_green_circle:"

        if not churned_customers:
            formatted = "*No churn or downgrades yesterday* :tada:"
        else:
            formatted = f"""*Churn Yesterday:* {self.format_currency(total_churn_mrr)} ({len([c for c in churned_customers if c.get('movement_type') == 'churn'])} customers)
*Contraction Yesterday:* {self.format_currency(total_contraction_mrr)} ({len([c for c in churned_customers if c.get('movement_type') == 'contraction'])} customers)

*Customers Affected:*
{chr(10).join(customer_list) if customer_list else '  None'}"""

        return {
            "status": status,
            "status_emoji": emoji,
            "formatted": formatted,
            "alerts": self._generate_churn_alerts(total_yesterday_churn, churned_customers),
            "total_churn": total_yesterday_churn
        }

    def _generate_churn_alerts(self, total_churn: float, customers: List) -> List[str]:
        """Generate alerts for churn section"""
        alerts = []
        daily_churn_alert = self.config.get("thresholds", {}).get("churn", {}).get("daily_churn_alert", 5000)

        if total_churn > daily_churn_alert:
            alerts.append(f":red_circle: High churn day - {self.format_currency(total_churn)} lost")

        # Check for any large individual churns
        large_churns = [c for c in customers if abs(c.get("mrr_change", 0)) > 2000]
        if large_churns:
            for c in large_churns:
                alerts.append(
                    f":warning: Large account impact: {c.get('customer_name')} ({self.format_currency(abs(c.get('mrr_change', 0)))})"
                )

        return alerts

    def generate_executive_summary(self, pipeline: Dict, revenue: Dict, churn: Dict) -> List[str]:
        """Generate executive summary bullets based on all sections"""
        summary = []

        # Pipeline summary
        if "red" in pipeline.get("status", ""):
            summary.append(":red_circle: Pipeline coverage is low - need to accelerate deal creation")
        elif pipeline.get("alerts"):
            summary.append(f":large_yellow_circle: Pipeline: {pipeline['alerts'][0]}" if pipeline['alerts'] else "")

        # Revenue summary - most important
        nb_pace = revenue.get("new_business_pace", 1)
        nn_pace = revenue.get("net_new_pace", 1)

        if nb_pace < 0.8:
            summary.append(f":red_circle: New business at {self.format_percentage(nb_pace)} of pace - action needed")
        elif nb_pace < 0.95:
            summary.append(f":large_yellow_circle: New business slightly behind at {self.format_percentage(nb_pace)} of pace")
        else:
            summary.append(f":large_green_circle: New business on track at {self.format_percentage(nb_pace)} of pace")

        if nn_pace < 0.8:
            summary.append(f":red_circle: Net new MRR at {self.format_percentage(nn_pace)} of pace - review expansion and churn")
        elif nn_pace >= 1.0:
            summary.append(f":large_green_circle: Net new MRR ahead of plan at {self.format_percentage(nn_pace)}")

        # Churn summary
        if churn.get("total_churn", 0) > 5000:
            summary.append(f":warning: Elevated churn yesterday ({self.format_currency(churn['total_churn'])}) - review affected accounts")
        elif churn.get("total_churn", 0) == 0:
            summary.append(":large_green_circle: Clean churn day - no losses yesterday")

        # Add any critical alerts from sections
        all_alerts = pipeline.get("alerts", []) + revenue.get("alerts", []) + churn.get("alerts", [])
        critical_alerts = [a for a in all_alerts if ":red_circle:" in a]
        for alert in critical_alerts[:2]:  # Max 2 additional critical alerts
            if alert not in summary:
                summary.append(alert)

        return summary[:5]  # Max 5 bullets

    def generate_report(self) -> Dict:
        """Generate the complete dashboard report"""
        # Generate all sections
        pipeline = self.generate_pipeline_section()
        revenue = self.generate_revenue_section()
        churn = self.generate_churn_section()

        # Generate executive summary
        executive_summary = self.generate_executive_summary(pipeline, revenue, churn)

        report = {
            "date": self.today.strftime("%Y-%m-%d"),
            "generated_at": self.today.strftime("%Y-%m-%d %H:%M:%S"),
            "executive_summary": executive_summary,
            "pipeline": pipeline,
            "revenue": revenue,
            "churn": churn
        }

        return report

    def send_to_slack(self, report: Dict):
        """Send report to Slack"""
        channel = self.config.get("notifications", {}).get("slack", {}).get("channel", "@riikka")
        self.slack.send_dashboard_report(channel, report)

    def run(self, send_slack: bool = True) -> Dict:
        """Run the dashboard and optionally send to Slack"""
        report = self.generate_report()

        if send_slack:
            self.send_to_slack(report)

        return report


def main():
    """Main entry point for scheduled execution"""
    dashboard = ExecutiveDashboard()
    report = dashboard.run(send_slack=True)
    print(f"Dashboard generated and sent at {report['generated_at']}")
    return report


if __name__ == "__main__":
    main()
