#!/bin/bash
# Executive Dashboard Setup Script

set -e

echo "Executive Dashboard Setup"
echo "========================="
echo ""

# Check for required environment variables
check_env() {
    local var_name=$1
    local var_value=${!var_name}
    if [ -z "$var_value" ]; then
        echo "MISSING: $var_name"
        return 1
    else
        echo "OK: $var_name"
        return 0
    fi
}

echo "Checking environment variables..."
echo ""

missing=0

check_env "HUBSPOT_API_KEY" || missing=1
check_env "DATABRICKS_HOST" || missing=1
check_env "DATABRICKS_TOKEN" || missing=1
check_env "DATABRICKS_WAREHOUSE_ID" || missing=1
check_env "SLACK_BOT_TOKEN" || missing=1

echo ""

if [ $missing -eq 1 ]; then
    echo "Some environment variables are missing."
    echo ""
    echo "Add them to your environment or create a .env file:"
    echo ""
    echo "  export HUBSPOT_API_KEY='your-hubspot-private-app-token'"
    echo "  export DATABRICKS_HOST='your-workspace.cloud.databricks.com'"
    echo "  export DATABRICKS_TOKEN='your-databricks-pat'"
    echo "  export DATABRICKS_WAREHOUSE_ID='your-sql-warehouse-id'"
    echo "  export SLACK_BOT_TOKEN='xoxb-your-slack-bot-token'"
    echo ""
    exit 1
fi

echo "All environment variables are set!"
echo ""

# Install dependencies
echo "Installing Python dependencies..."
pip install -q pyyaml pytz schedule

echo ""
echo "Setup complete! You can now run:"
echo ""
echo "  Test report (no Slack):  python generate_test_report.py"
echo "  One-time run:            python scheduler.py --once"
echo "  Start scheduler:         python scheduler.py"
echo ""
