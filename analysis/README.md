# Pipeline Analysis Tools

Tools for deep-diving into HubSpot sales-assisted pipeline data.

## Quick Start

```bash
# Set HubSpot API key
export HUBSPOT_API_KEY="your-private-app-token"

# Run analysis
python analysis/hubspot_pipeline_analysis.py
```

## What This Analyzes

### Data Pulled
- All deals from last 180 days
- Deal properties: name, amount, stage, dates, owner, source, engagement metrics
- Win/loss outcomes with full context

### Metrics Calculated
- **Win Rate**: Deals won / (won + lost)
- **Deal Velocity**: Days from created to closed
- **Pipeline by Stage**: Current deals and value at each stage
- **Size Segmentation**: Small (<$500), Medium ($500-2k), Large ($2k-5k), Enterprise ($5k+)
- **Source Effectiveness**: Win rate by lead source
- **Engagement Correlation**: Touches and contacts vs. outcomes

### Recommendations Generated
Based on analysis, the tool generates prioritized recommendations:
- **HIGH**: Critical issues needing immediate attention
- **MEDIUM**: Opportunities for improvement
- **INFO**: Healthy patterns to maintain

## Output Files

Each run creates:
- `pipeline_analysis_YYYY-MM-DD.txt` - Human-readable report
- `pipeline_analysis_YYYY-MM-DD.json` - Raw data for further analysis

## Integration with Claude

When asked to analyze the pipeline, Claude should:

1. Check if recent analysis exists: `ls -la analysis/pipeline_analysis_*.txt`
2. If fresh data needed, instruct user to run the script locally
3. Read the generated report and provide insights

### Example Prompts

- "Analyze my sales pipeline" → Run analysis, summarize findings
- "What are we winning?" → Look at win patterns in analysis
- "Why are we losing deals?" → Focus on loss patterns and recommendations
- "How's pipeline coverage?" → Check pipeline by stage vs. targets

## Customization

### Adjust Analysis Window
Edit `days_back` in `fetch_all_deals()` - default is 180 days.

### Add Custom Stages
Update `stage_map` in `analyze_deals()` to match your HubSpot stages.

### Modify Deal Size Tiers
Adjust thresholds in `_analyze_patterns()`:
```python
if amount < 500:      # small
elif amount < 2000:   # medium
elif amount < 5000:   # large
else:                 # enterprise
```

## Troubleshooting

**"HUBSPOT_API_KEY required"**
- Set the environment variable with your HubSpot private app token

**"No deals found"**
- Check API key has CRM read permissions
- Verify deals exist in HubSpot

**API Rate Limits**
- HubSpot allows 100 requests/10 seconds
- Script handles pagination but may slow on very large datasets
