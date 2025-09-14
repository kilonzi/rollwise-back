# RollWise Scripts

This directory contains utility scripts for managing the RollWise Multi-Tenant AI Voice Agent Platform.

## Available Scripts

### `setup_demo.py`

Creates demo data for testing the multi-tenant platform.

**Usage:**
```bash
python scripts/setup_demo.py
```

**What it creates:**
- **Bella's Beauty Salon** (tenant) with Sofia (AI agent)
- **Mike's Auto Repair** (tenant) with Alex (AI agent)
- Admin users for both tenants
- Configured tools and prompts for each business type

**After running:**
1. Update Twilio webhook URLs to use the agent IDs
2. Replace demo phone numbers with your actual Twilio numbers
3. Test by calling the configured phone numbers

### Future Scripts

Additional scripts will be added for:
- Database migrations
- Tenant data export/import
- Agent configuration updates
- Analytics and reporting

## Requirements

Before running any scripts:
1. Install dependencies: `pip install -r requirements.txt`
2. Configure `.env` with your settings
3. Ensure database is accessible

## Support

For issues with scripts, check the main project README or create an issue.