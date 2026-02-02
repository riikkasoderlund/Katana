# Executive Daily Dashboard

Automated daily executive report sent to Slack at 7 AM Helsinki time.

## Setup

### 1. Set Environment Variables

```bash
# HubSpot API
export HUBSPOT_API_KEY="your-hubspot-private-app-token"

# Databricks SQL
export DATABRICKS_HOST="your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="your-databricks-pat"
export DATABRICKS_WAREHOUSE_ID="your-sql-warehouse-id"

# Slack
export SLACK_BOT_TOKEN="xoxb-your-slack-bot-token"
```

### 2. Install Dependencies

```bash
pip install pyyaml pytz schedule
```

### 3. Configure Targets

Edit `config.yaml` to update:
- Monthly revenue targets (already configured for 2026)
- Pipeline stages to match your HubSpot setup
- RAG thresholds for alerts
- Slack channel (`@riikka` by default)

### 4. Databricks Tables

The dashboard expects these tables in Databricks:
- `finance.mrr_daily` - Daily MRR snapshots (columns: `mrr`, `snapshot_date`)
- `finance.mrr_movements` - MRR change events (columns: `movement_date`, `movement_type`, `mrr_change`, `customer_id`, `reason`)
- `finance.customers` - Customer master (columns: `customer_id`, `customer_name`)

## Running

### Test Run (no Slack)
```bash
python generate_test_report.py
```

### One-time Run (sends to Slack)
```bash
python scheduler.py --once
```

### Continuous Scheduler (7 AM Helsinki daily)
```bash
python scheduler.py
```

## Report Sections

1. **Executive Summary** - 3-5 bullets flagging what needs attention today
2. **Pipeline Health** - New deals, stage movements, pipeline by stage vs yesterday
3. **Revenue Performance** - MRR/ARR, MTD vs targets, win rates
4. **Churn & Retention** - Churned/downgraded customers with reasons

## RAG Status

- Green: On track (95%+ of target pace)
- Yellow: Monitor (80-95% of pace)
- Red: Action needed (<80% of pace)
