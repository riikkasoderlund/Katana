#!/usr/bin/env python3
"""
HubSpot Sales-Assisted Pipeline Deep Analysis
Analyzes deal patterns, win/loss characteristics, and provides strategic recommendations.

Run this locally with HUBSPOT_API_KEY environment variable set.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict
import os
import json
import urllib.request
import urllib.error
import statistics


class HubSpotAnalyzer:
    """Deep analysis of HubSpot sales pipeline"""

    def __init__(self):
        self.api_key = os.environ.get("HUBSPOT_API_KEY", "")
        self.base_url = "https://api.hubapi.com"
        if not self.api_key:
            raise ValueError("HUBSPOT_API_KEY environment variable required")

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
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            print(f"HubSpot API error: {e.code} - {e.read().decode()}")
            return None

    def fetch_all_deals(self, days_back: int = 180) -> List[Dict]:
        """Fetch all deals from the last N days with full properties"""
        deals = []
        after = None
        cutoff = datetime.now() - timedelta(days=days_back)
        cutoff_ms = int(cutoff.timestamp() * 1000)

        properties = [
            "dealname", "amount", "dealstage", "closedate", "createdate",
            "hs_lastmodifieddate", "pipeline", "hubspot_owner_id",
            "hs_deal_stage_probability", "hs_is_closed_won", "hs_is_closed",
            "hs_time_in_qualification", "hs_time_in_solution_validation",
            "hs_time_in_order_form_sent", "deal_currency_code",
            "hs_closed_amount", "hs_forecast_amount", "hs_projected_amount",
            "hs_deal_stage_probability_shadow", "notes_last_updated",
            "hs_analytics_source", "hs_analytics_source_data_1",
            "hs_num_associated_contacts", "num_associated_contacts",
            "hs_num_times_contacted", "hs_last_meeting_booked",
            "industry", "company_size", "hs_object_source"
        ]

        print("Fetching deals from HubSpot...")
        while True:
            query = {
                "filterGroups": [{
                    "filters": [{
                        "propertyName": "createdate",
                        "operator": "GTE",
                        "value": str(cutoff_ms)
                    }]
                }],
                "properties": properties,
                "limit": 100,
                "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}]
            }

            if after:
                query["after"] = after

            result = self._request("POST", "/crm/v3/objects/deals/search", query)

            if not result or "results" not in result:
                break

            deals.extend(result["results"])
            print(f"  Fetched {len(deals)} deals...")

            if "paging" in result and "next" in result["paging"]:
                after = result["paging"]["next"]["after"]
            else:
                break

        print(f"Total deals fetched: {len(deals)}")
        return deals

    def fetch_deal_associations(self, deal_id: str) -> Dict:
        """Fetch company and contact associations for a deal"""
        associations = {}

        # Get associated companies
        result = self._request("GET", f"/crm/v4/objects/deals/{deal_id}/associations/companies")
        if result and "results" in result:
            associations["companies"] = result["results"]

        # Get associated contacts
        result = self._request("GET", f"/crm/v4/objects/deals/{deal_id}/associations/contacts")
        if result and "results" in result:
            associations["contacts"] = result["results"]

        return associations

    def get_company_details(self, company_id: str) -> Dict:
        """Fetch company details"""
        result = self._request("GET",
            f"/crm/v3/objects/companies/{company_id}?properties=name,industry,numberofemployees,annualrevenue,country,city")
        return result.get("properties", {}) if result else {}

    def analyze_deals(self, deals: List[Dict]) -> Dict:
        """Comprehensive deal analysis"""
        analysis = {
            "summary": {},
            "by_stage": {},
            "won_deals": [],
            "lost_deals": [],
            "open_deals": [],
            "win_patterns": {},
            "loss_patterns": {},
            "velocity": {},
            "recommendations": []
        }

        stage_map = {
            "qualification": "Qualification",
            "solution_validation": "Solution Validation",
            "order_form_sent": "Order form sent",
            "closedwon": "Closed Won",
            "closedlost": "Closed Lost"
        }

        # Categorize deals
        for deal in deals:
            props = deal.get("properties", {})
            stage = props.get("dealstage", "").lower()
            amount = float(props.get("amount") or 0)

            deal_data = {
                "id": deal.get("id"),
                "name": props.get("dealname"),
                "amount": amount,
                "stage": stage_map.get(stage, stage),
                "created": props.get("createdate"),
                "closed": props.get("closedate"),
                "owner_id": props.get("hubspot_owner_id"),
                "source": props.get("hs_analytics_source"),
                "contacts": int(props.get("hs_num_associated_contacts") or props.get("num_associated_contacts") or 0),
                "times_contacted": int(props.get("hs_num_times_contacted") or 0),
                "last_meeting": props.get("hs_last_meeting_booked"),
                "raw_props": props
            }

            if stage == "closedwon":
                analysis["won_deals"].append(deal_data)
            elif stage == "closedlost":
                analysis["lost_deals"].append(deal_data)
            else:
                analysis["open_deals"].append(deal_data)

        # Summary stats
        analysis["summary"] = {
            "total_deals": len(deals),
            "won_count": len(analysis["won_deals"]),
            "lost_count": len(analysis["lost_deals"]),
            "open_count": len(analysis["open_deals"]),
            "won_value": sum(d["amount"] for d in analysis["won_deals"]),
            "lost_value": sum(d["amount"] for d in analysis["lost_deals"]),
            "open_pipeline": sum(d["amount"] for d in analysis["open_deals"]),
            "win_rate": len(analysis["won_deals"]) / max(len(analysis["won_deals"]) + len(analysis["lost_deals"]), 1),
            "avg_won_deal": statistics.mean([d["amount"] for d in analysis["won_deals"]]) if analysis["won_deals"] else 0,
            "avg_lost_deal": statistics.mean([d["amount"] for d in analysis["lost_deals"]]) if analysis["lost_deals"] else 0
        }

        # Pipeline by stage
        for deal_data in analysis["open_deals"]:
            stage = deal_data["stage"]
            if stage not in analysis["by_stage"]:
                analysis["by_stage"][stage] = {"count": 0, "value": 0, "deals": []}
            analysis["by_stage"][stage]["count"] += 1
            analysis["by_stage"][stage]["value"] += deal_data["amount"]
            analysis["by_stage"][stage]["deals"].append(deal_data)

        # Win patterns
        analysis["win_patterns"] = self._analyze_patterns(analysis["won_deals"], "won")
        analysis["loss_patterns"] = self._analyze_patterns(analysis["lost_deals"], "lost")

        # Calculate velocity (days to close)
        analysis["velocity"] = self._analyze_velocity(analysis["won_deals"], analysis["lost_deals"])

        # Generate recommendations
        analysis["recommendations"] = self._generate_recommendations(analysis)

        return analysis

    def _analyze_patterns(self, deals: List[Dict], outcome: str) -> Dict:
        """Analyze patterns in won or lost deals"""
        if not deals:
            return {}

        patterns = {
            "by_size": {"small": [], "medium": [], "large": [], "enterprise": []},
            "by_source": defaultdict(list),
            "by_owner": defaultdict(list),
            "engagement_stats": {}
        }

        for deal in deals:
            # Size segmentation
            amount = deal["amount"]
            if amount < 500:
                patterns["by_size"]["small"].append(deal)
            elif amount < 2000:
                patterns["by_size"]["medium"].append(deal)
            elif amount < 5000:
                patterns["by_size"]["large"].append(deal)
            else:
                patterns["by_size"]["enterprise"].append(deal)

            # By source
            source = deal.get("source") or "unknown"
            patterns["by_source"][source].append(deal)

            # By owner
            owner = deal.get("owner_id") or "unassigned"
            patterns["by_owner"][owner].append(deal)

        # Engagement analysis
        contacts = [d["contacts"] for d in deals if d["contacts"] > 0]
        touches = [d["times_contacted"] for d in deals if d["times_contacted"] > 0]

        patterns["engagement_stats"] = {
            "avg_contacts": statistics.mean(contacts) if contacts else 0,
            "avg_touches": statistics.mean(touches) if touches else 0,
            "deals_with_meetings": sum(1 for d in deals if d.get("last_meeting"))
        }

        # Convert defaultdicts
        patterns["by_source"] = dict(patterns["by_source"])
        patterns["by_owner"] = dict(patterns["by_owner"])

        return patterns

    def _analyze_velocity(self, won_deals: List[Dict], lost_deals: List[Dict]) -> Dict:
        """Analyze deal velocity - time to close"""
        velocity = {
            "won": {"avg_days": 0, "by_size": {}},
            "lost": {"avg_days": 0}
        }

        def calc_days(deal):
            if not deal.get("created") or not deal.get("closed"):
                return None
            try:
                created = datetime.fromisoformat(deal["created"].replace("Z", "+00:00"))
                closed = datetime.fromisoformat(deal["closed"].replace("Z", "+00:00"))
                return (closed - created).days
            except:
                return None

        won_days = [d for d in [calc_days(deal) for deal in won_deals] if d is not None]
        lost_days = [d for d in [calc_days(deal) for deal in lost_deals] if d is not None]

        velocity["won"]["avg_days"] = statistics.mean(won_days) if won_days else 0
        velocity["lost"]["avg_days"] = statistics.mean(lost_days) if lost_days else 0
        velocity["won"]["median_days"] = statistics.median(won_days) if won_days else 0

        return velocity

    def _generate_recommendations(self, analysis: Dict) -> List[Dict]:
        """Generate strategic recommendations based on analysis"""
        recommendations = []

        summary = analysis["summary"]
        won_patterns = analysis.get("win_patterns", {})
        loss_patterns = analysis.get("loss_patterns", {})
        velocity = analysis.get("velocity", {})

        # Win rate analysis
        win_rate = summary["win_rate"]
        if win_rate < 0.20:
            recommendations.append({
                "priority": "HIGH",
                "area": "Win Rate",
                "insight": f"Win rate is {win_rate:.1%} - significantly below healthy benchmark of 25-30%",
                "action": "Review qualification criteria and deal entry process. Consider tightening ICP."
            })
        elif win_rate < 0.25:
            recommendations.append({
                "priority": "MEDIUM",
                "area": "Win Rate",
                "insight": f"Win rate is {win_rate:.1%} - room for improvement",
                "action": "Analyze lost deal patterns to identify qualification improvements."
            })
        else:
            recommendations.append({
                "priority": "INFO",
                "area": "Win Rate",
                "insight": f"Win rate is {win_rate:.1%} - healthy",
                "action": "Maintain current qualification standards."
            })

        # Deal size analysis
        avg_won = summary["avg_won_deal"]
        avg_lost = summary["avg_lost_deal"]
        if avg_lost > avg_won * 1.3:
            recommendations.append({
                "priority": "HIGH",
                "area": "Deal Size",
                "insight": f"Lost deals avg ${avg_lost:,.0f} vs won avg ${avg_won:,.0f}",
                "action": "Larger deals have lower win rates. Investigate: pricing, competition, or fit issues at enterprise level."
            })

        # Engagement patterns
        if won_patterns and loss_patterns:
            won_engagement = won_patterns.get("engagement_stats", {})
            lost_engagement = loss_patterns.get("engagement_stats", {})

            won_touches = won_engagement.get("avg_touches", 0)
            lost_touches = lost_engagement.get("avg_touches", 0)

            if won_touches > lost_touches * 1.5 and won_touches > 3:
                recommendations.append({
                    "priority": "MEDIUM",
                    "area": "Engagement",
                    "insight": f"Won deals have {won_touches:.1f} avg touches vs {lost_touches:.1f} for lost",
                    "action": "Increase touchpoint frequency. Deals need more nurturing to close."
                })

        # Velocity recommendations
        avg_days = velocity.get("won", {}).get("avg_days", 0)
        if avg_days > 60:
            recommendations.append({
                "priority": "MEDIUM",
                "area": "Sales Cycle",
                "insight": f"Average sales cycle is {avg_days:.0f} days",
                "action": "Look for bottlenecks. Which stage has longest dwell time?"
            })

        # Pipeline health
        open_pipeline = summary["open_pipeline"]
        target_monthly = 33425  # Feb target from config
        coverage = open_pipeline / (target_monthly * 3) if target_monthly > 0 else 0

        if coverage < 1.0:
            recommendations.append({
                "priority": "HIGH",
                "area": "Pipeline Coverage",
                "insight": f"Pipeline coverage is {coverage:.1%} of 3x target",
                "action": "Need more qualified pipeline. Increase top-of-funnel activity."
            })
        elif coverage < 1.2:
            recommendations.append({
                "priority": "MEDIUM",
                "area": "Pipeline Coverage",
                "insight": f"Pipeline coverage is {coverage:.1%} - tight",
                "action": "Maintain prospecting cadence. Don't let pipeline slip."
            })

        # Source effectiveness
        if won_patterns.get("by_source") and loss_patterns.get("by_source"):
            for source, deals in won_patterns["by_source"].items():
                won_from_source = len(deals)
                lost_from_source = len(loss_patterns["by_source"].get(source, []))
                if won_from_source + lost_from_source >= 5:
                    source_win_rate = won_from_source / (won_from_source + lost_from_source)
                    if source_win_rate > win_rate + 0.1:
                        recommendations.append({
                            "priority": "MEDIUM",
                            "area": "Lead Source",
                            "insight": f"'{source}' has {source_win_rate:.1%} win rate vs {win_rate:.1%} overall",
                            "action": f"Double down on {source} - high-converting source."
                        })
                    elif source_win_rate < win_rate - 0.1 and lost_from_source > 5:
                        recommendations.append({
                            "priority": "MEDIUM",
                            "area": "Lead Source",
                            "insight": f"'{source}' has only {source_win_rate:.1%} win rate",
                            "action": f"Review qualification for {source} leads - may not be ICP."
                        })

        return recommendations

    def generate_report(self, analysis: Dict) -> str:
        """Generate human-readable report"""
        lines = []
        lines.append("=" * 70)
        lines.append("  HUBSPOT SALES-ASSISTED PIPELINE ANALYSIS")
        lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("=" * 70)
        lines.append("")

        # Summary
        s = analysis["summary"]
        lines.append("EXECUTIVE SUMMARY")
        lines.append("-" * 50)
        lines.append(f"  Total Deals Analyzed: {s['total_deals']}")
        lines.append(f"  Won: {s['won_count']} (${s['won_value']:,.0f})")
        lines.append(f"  Lost: {s['lost_count']} (${s['lost_value']:,.0f})")
        lines.append(f"  Open Pipeline: {s['open_count']} deals (${s['open_pipeline']:,.0f})")
        lines.append(f"  Win Rate: {s['win_rate']:.1%}")
        lines.append(f"  Avg Won Deal: ${s['avg_won_deal']:,.0f}")
        lines.append(f"  Avg Lost Deal: ${s['avg_lost_deal']:,.0f}")
        lines.append("")

        # Pipeline by Stage
        lines.append("CURRENT PIPELINE BY STAGE")
        lines.append("-" * 50)
        for stage in ["Qualification", "Solution Validation", "Order form sent"]:
            data = analysis["by_stage"].get(stage, {"count": 0, "value": 0})
            lines.append(f"  {stage}: {data['count']} deals | ${data['value']:,.0f}")
        lines.append("")

        # Velocity
        v = analysis.get("velocity", {})
        lines.append("SALES VELOCITY")
        lines.append("-" * 50)
        lines.append(f"  Avg Days to Close (Won): {v.get('won', {}).get('avg_days', 0):.0f}")
        lines.append(f"  Median Days to Close (Won): {v.get('won', {}).get('median_days', 0):.0f}")
        lines.append(f"  Avg Days to Close (Lost): {v.get('lost', {}).get('avg_days', 0):.0f}")
        lines.append("")

        # What We're Winning
        lines.append("WHAT WE'RE WINNING")
        lines.append("-" * 50)
        wp = analysis.get("win_patterns", {})
        if wp:
            by_size = wp.get("by_size", {})
            for size, deals in by_size.items():
                if deals:
                    total = sum(d["amount"] for d in deals)
                    lines.append(f"  {size.title()}: {len(deals)} deals (${total:,.0f})")
            lines.append("")

            by_source = wp.get("by_source", {})
            if by_source:
                lines.append("  Top winning sources:")
                sorted_sources = sorted(by_source.items(), key=lambda x: len(x[1]), reverse=True)[:5]
                for source, deals in sorted_sources:
                    lines.append(f"    - {source}: {len(deals)} deals")
            lines.append("")

            # Top won deals
            sorted_won = sorted(analysis["won_deals"], key=lambda x: x["amount"], reverse=True)[:5]
            if sorted_won:
                lines.append("  Recent top wins:")
                for deal in sorted_won:
                    lines.append(f"    - {deal['name']}: ${deal['amount']:,.0f}")
        lines.append("")

        # What We're Losing
        lines.append("WHAT WE'RE LOSING")
        lines.append("-" * 50)
        lp = analysis.get("loss_patterns", {})
        if lp:
            by_size = lp.get("by_size", {})
            for size, deals in by_size.items():
                if deals:
                    total = sum(d["amount"] for d in deals)
                    lines.append(f"  {size.title()}: {len(deals)} deals (${total:,.0f})")
            lines.append("")

            by_source = lp.get("by_source", {})
            if by_source:
                lines.append("  Top losing sources:")
                sorted_sources = sorted(by_source.items(), key=lambda x: len(x[1]), reverse=True)[:5]
                for source, deals in sorted_sources:
                    lines.append(f"    - {source}: {len(deals)} deals")
            lines.append("")

            # Top lost deals
            sorted_lost = sorted(analysis["lost_deals"], key=lambda x: x["amount"], reverse=True)[:5]
            if sorted_lost:
                lines.append("  Largest recent losses:")
                for deal in sorted_lost:
                    lines.append(f"    - {deal['name']}: ${deal['amount']:,.0f}")
        lines.append("")

        # Recommendations
        lines.append("STRATEGIC RECOMMENDATIONS")
        lines.append("-" * 50)
        for rec in analysis.get("recommendations", []):
            priority = rec["priority"]
            icon = {"HIGH": "🔴", "MEDIUM": "🟡", "INFO": "🟢"}.get(priority, "")
            lines.append(f"\n  [{priority}] {rec['area']}")
            lines.append(f"  Insight: {rec['insight']}")
            lines.append(f"  Action: {rec['action']}")
        lines.append("")

        # Focus Areas
        lines.append("=" * 70)
        lines.append("WHAT TO FOCUS ON")
        lines.append("=" * 70)
        high_priority = [r for r in analysis.get("recommendations", []) if r["priority"] == "HIGH"]
        if high_priority:
            lines.append("\nTOP PRIORITIES:")
            for i, rec in enumerate(high_priority, 1):
                lines.append(f"  {i}. {rec['area']}: {rec['action']}")
        else:
            lines.append("\n  No critical issues identified. Stay the course.")
        lines.append("")

        return "\n".join(lines)


def main():
    """Run the analysis"""
    print("\n" + "=" * 60)
    print("  STARTING HUBSPOT PIPELINE ANALYSIS")
    print("=" * 60 + "\n")

    try:
        analyzer = HubSpotAnalyzer()
    except ValueError as e:
        print(f"ERROR: {e}")
        print("Set HUBSPOT_API_KEY environment variable and try again.")
        return

    # Fetch deals
    deals = analyzer.fetch_all_deals(days_back=180)

    if not deals:
        print("No deals found. Check API key and permissions.")
        return

    # Analyze
    print("\nAnalyzing deals...")
    analysis = analyzer.analyze_deals(deals)

    # Generate report
    report = analyzer.generate_report(analysis)
    print(report)

    # Save to file
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(output_dir, f"pipeline_analysis_{datetime.now().strftime('%Y-%m-%d')}.txt")
    with open(output_file, "w") as f:
        f.write(report)
    print(f"\nReport saved to: {output_file}")

    # Also save raw analysis as JSON
    json_file = os.path.join(output_dir, f"pipeline_analysis_{datetime.now().strftime('%Y-%m-%d')}.json")

    # Make JSON serializable
    def make_serializable(obj):
        if isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_serializable(i) for i in obj]
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    with open(json_file, "w") as f:
        json.dump(make_serializable(analysis), f, indent=2)
    print(f"Raw data saved to: {json_file}")

    return analysis


if __name__ == "__main__":
    main()
