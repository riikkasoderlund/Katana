"""
Generate a test report for review before enabling automation.
Uses mock data to simulate what the actual report will look like.
"""
from datetime import datetime, timedelta
import os


def generate_test_report():
    """Generate a test report with sample data for review"""

    today = datetime.now()
    yesterday = today - timedelta(days=1)

    # Sample data based on typical metrics
    report = {
        "date": today.strftime("%Y-%m-%d"),
        "generated_at": today.strftime("%Y-%m-%d %H:%M:%S"),
        "executive_summary": [
            ":large_green_circle: New business on track at 94% of pace",
            ":large_yellow_circle: Net new MRR slightly behind at 87% of pace - monitor expansion",
            ":large_green_circle: Clean churn day - no losses yesterday",
            ":warning: Pipeline coverage at 85% - need 2-3 more qualified deals"
        ],
        "pipeline": {
            "status": "yellow",
            "status_emoji": ":large_yellow_circle:",
            "formatted": f"""*New Pipeline Yesterday:* 3 deals | $47,500

*Stage Movements Yesterday:*
  Acme Corp: Qualification → Solution Validation
  TechStart Inc: Solution Validation → Order form sent
  DataFlow Ltd: Order form sent → Closed Won

*Current Pipeline by Stage (vs yesterday):*
  *Qualification*: 12 deals | $156,000 (+$23,000) ↑
  *Solution Validation*: 8 deals | $234,500 (-$45,000) ↓
  *Order form sent*: 5 deals | $187,000 (+$62,000) ↑

*Total Active Pipeline:* $577,500""",
            "alerts": [":warning: Pipeline coverage at 85% - need more qualified deals"]
        },
        "revenue": {
            "status": "yellow",
            "status_emoji": ":large_yellow_circle:",
            "formatted": f"""*MRR/ARR Today:*
  MRR: $1,102,450 (WoW: +$8,234 ↑ | MoM: +$32,519 ↑)
  ARR: $13,229,400

*Yesterday's Performance:*
  New Business MRR: $2,850
  Net New MRR: $1,425
    - Expansion: $1,200
    - Contraction: -$625
    - Churn: $0
    - Reactivation: $0

*MTD vs Target:* :large_yellow_circle:
  New Business: $6,720 / $33,425 (20.1%)
  Net New: $2,850 / $15,106 (18.9%) :large_yellow_circle:

*To Hit Target (26 days remaining):*
  New Business needed: $26,705 ($1,027/day)
  Net New needed: $12,256 ($472/day)

*Win Rate (Qualification → Closed Won):*
  This week: 28.5% (+2.3% vs last week)""",
            "alerts": [],
            "new_business_pace": 0.94,
            "net_new_pace": 0.87
        },
        "churn": {
            "status": "green",
            "status_emoji": ":large_green_circle:",
            "formatted": "*No churn or downgrades yesterday* :tada:",
            "alerts": [],
            "total_churn": 0
        }
    }

    return report


def format_slack_preview(report: dict) -> str:
    """Format report as text preview of Slack message"""

    output = []
    output.append("=" * 60)
    output.append(f"  EXECUTIVE DASHBOARD - {report['date']}")
    output.append("=" * 60)
    output.append("")

    output.append("EXECUTIVE SUMMARY")
    output.append("-" * 40)
    for item in report["executive_summary"]:
        output.append(f"  {item}")
    output.append("")

    output.append(f"PIPELINE HEALTH {report['pipeline']['status_emoji']}")
    output.append("-" * 40)
    output.append(report["pipeline"]["formatted"])
    output.append("")

    output.append(f"REVENUE PERFORMANCE {report['revenue']['status_emoji']}")
    output.append("-" * 40)
    output.append(report["revenue"]["formatted"])
    output.append("")

    output.append(f"CHURN & RETENTION {report['churn']['status_emoji']}")
    output.append("-" * 40)
    output.append(report["churn"]["formatted"])
    output.append("")

    output.append("=" * 60)
    output.append(f"Generated at {report['generated_at']} Helsinki")
    output.append("Data sources: HubSpot, Databricks Genie")
    output.append("=" * 60)

    return "\n".join(output)


def main():
    """Generate and display test report"""
    print("\n" + "=" * 60)
    print("  GENERATING TEST EXECUTIVE DASHBOARD")
    print("  This is a PREVIEW with sample data")
    print("=" * 60 + "\n")

    report = generate_test_report()
    preview = format_slack_preview(report)
    print(preview)

    print("\n" + "=" * 60)
    print("  END OF TEST REPORT")
    print("=" * 60)
    print("\nThis report shows the format that will be sent to Slack.")
    print("Actual data will come from HubSpot and Databricks Genie.")
    print("\nTo enable automatic scheduling:")
    print("  1. Review this format and confirm it meets your needs")
    print("  2. Run: python scheduler.py")
    print("  3. Or for a one-time real run: python scheduler.py --once")
    print("")

    return report


if __name__ == "__main__":
    main()
