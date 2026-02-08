# KNIME Workflow Dashboard

A Flask web app that monitors KNIME workflow execution times by reading completion messages from a Slack channel. It stores data locally so historical trends are preserved beyond Slack's 90-day message retention limit.

## Features

- **Stacked bar chart** showing total nightly process duration, broken down by workflow
- **Line chart** for individual workflow execution times over time
- **Click-to-filter**: click a segment in the stacked bar chart to isolate that workflow
- **Persistent history**: each refresh merges new Slack data with local history, so data older than 90 days is never lost
- **Date range filter**: view last 30, 60, 90, 180, 365 days, or all time

## Prerequisites

- Python 3.9+
- A Slack Bot Token with access to the channel where KNIME posts workflow completion messages

### Slack Bot Setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app
2. Under **OAuth & Permissions**, add the `channels:history`, `channels:read`, `groups:history`, and `groups:read` scopes
3. Install the app to your workspace and copy the **Bot User OAuth Token** (starts with `xoxb-`)
4. Invite the bot to the Slack channel where KNIME posts messages

## Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/justinmaclean/knime_dashboard.git
   cd knime_dashboard
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root:

   ```
   SLACK_BOT_TOKEN=xoxb-your-token-here
   CHANNEL_NAME=your-channel-name
   ```

5. Run the app:

   ```bash
   python app.py
   ```

6. Open http://localhost:5050 in your browser.

## Usage

- **Refresh from Slack** fetches the last 90 days of messages from Slack and merges them with your local history
- Use the **date range dropdown** to control how much history is displayed in the charts
- **Click a segment** in the top stacked bar chart to filter the bottom chart to that workflow
- Use the **Select All / Deselect All** button or individual checkboxes to pick which workflows appear in the bottom chart

## Expected Slack Message Format

The app parses messages in this format from the configured channel:

```
Starting Nightly Process
Payment ETL : Completed in 16 mins, 43 secs
Invoice ETL : Completed in 8 mins, 12 secs
...
Nightly Process Completed
```

## Project Structure

```
knime_dashboard/
  app.py              # Flask backend
  requirements.txt    # Python dependencies
  .env                # Slack credentials (not committed)
  .gitignore
  templates/
    index.html        # Dashboard frontend
  workflow_history.json  # Persistent local data (not committed)
```
