from flask import Flask, render_template, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
import os
import re
from datetime import datetime, timedelta
import pandas as pd
import json

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

app = Flask(__name__)

# Persistent history file (survives beyond Slack's 90-day retention)
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workflow_history.json')

# Configuration
SLACK_BOT_TOKEN = os.environ['SLACK_BOT_TOKEN']
CHANNEL_NAME = os.environ['CHANNEL_NAME']

client = WebClient(token=SLACK_BOT_TOKEN)

def parse_duration(duration_str):
    """Convert duration string like '19 mins, 42 secs' to total seconds"""
    total_seconds = 0
    
    # Match patterns like "X mins", "X min", "X secs", "X sec"
    mins_match = re.search(r'(\d+)\s*mins?', duration_str)
    secs_match = re.search(r'(\d+)\s*secs?', duration_str)
    
    if mins_match:
        total_seconds += int(mins_match.group(1)) * 60
    if secs_match:
        total_seconds += int(secs_match.group(1))
    
    return total_seconds

def get_channel_id(channel_name):
    """Get channel ID from channel name"""
    try:
        # Try conversations.list for private channels
        result = client.conversations_list(types="private_channel")
        for channel in result["channels"]:
            if channel["name"] == channel_name:
                return channel["id"]
        
        # If not found, try public channels
        result = client.conversations_list(types="public_channel")
        for channel in result["channels"]:
            if channel["name"] == channel_name:
                return channel["id"]
                
        return None
    except SlackApiError as e:
        print(f"Error getting channel ID: {e}")
        return None

def fetch_slack_messages(days_back=90):
    """Fetch messages from Slack channel"""
    channel_id = get_channel_id(CHANNEL_NAME)
    
    if not channel_id:
        print(f"Could not find channel: {CHANNEL_NAME}")
        return []
    
    print(f"Found channel ID: {channel_id}")
    
    # Calculate timestamp for X days ago
    oldest = (datetime.now() - timedelta(days=days_back)).timestamp()
    
    messages = []
    try:
        result = client.conversations_history(
            channel=channel_id,
            oldest=oldest,
            limit=1000
        )
        messages = result["messages"]
        
        # Handle pagination if there are more messages
        while result.get("has_more"):
            result = client.conversations_history(
                channel=channel_id,
                oldest=oldest,
                cursor=result["response_metadata"]["next_cursor"],
                limit=1000
            )
            messages.extend(result["messages"])
        
        print(f"Fetched {len(messages)} messages")
        return messages
    
    except SlackApiError as e:
        print(f"Error fetching messages: {e}")
        return []

def parse_workflow_data(messages):
    """Parse messages to extract workflow execution data"""
    workflow_data = []
    current_date = None
    start_time = None
    prev_msg_datetime = None

    # Sort messages by timestamp (oldest first)
    messages = sorted(messages, key=lambda x: float(x['ts']))

    for msg in messages:
        text = msg.get('text', '')
        timestamp = float(msg['ts'])
        msg_datetime = datetime.fromtimestamp(timestamp)

        # Check for "Starting Nightly Process"
        if 'Starting Nightly Process' in text:
            current_date = msg_datetime.date()
            start_time = msg_datetime
            prev_msg_datetime = msg_datetime
            continue

        # Check for "Nightly Process Completed"
        if 'Nightly Process Completed' in text:
            if start_time and current_date:
                total_duration = (msg_datetime - start_time).total_seconds()
                workflow_data.append({
                    'workflow_name': 'TOTAL_NIGHTLY_PROCESS',
                    'date': current_date,
                    'duration_seconds': total_duration,
                    'timestamp': msg_datetime,
                    'status': 'success',
                    'error_message': ''
                })
            prev_msg_datetime = msg_datetime
            continue

        # Parse workflow completion messages
        match = re.match(r'^(.+?)\s*:\s*Completed in\s+(.+)$', text)
        if match and current_date:
            workflow_name = match.group(1).strip()
            duration_str = match.group(2).strip()
            duration_seconds = parse_duration(duration_str)

            workflow_data.append({
                'workflow_name': workflow_name,
                'date': current_date,
                'duration_seconds': duration_seconds,
                'timestamp': msg_datetime,
                'status': 'success',
                'error_message': ''
            })
            prev_msg_datetime = msg_datetime
            continue

        # Parse workflow failure messages
        lines = text.split('\n')
        failure_match = re.match(r'^(.+?)\s*:\s*(Failure.*)', lines[0])
        if failure_match and current_date:
            workflow_name = failure_match.group(1).strip()

            # Calculate duration from previous message timestamp
            duration_seconds = 0
            if prev_msg_datetime:
                duration_seconds = (msg_datetime - prev_msg_datetime).total_seconds()

            # Collect error message: failure text + any additional lines
            error_parts = [failure_match.group(2).strip()]
            if len(lines) > 1:
                error_parts.extend(lines[1:])
            error_message = '\n'.join(error_parts).strip()

            workflow_data.append({
                'workflow_name': workflow_name,
                'date': current_date,
                'duration_seconds': duration_seconds,
                'timestamp': msg_datetime,
                'status': 'error',
                'error_message': error_message
            })
            prev_msg_datetime = msg_datetime
            continue

        # Update prev_msg_datetime for any unrecognized message within a nightly process
        if current_date:
            prev_msg_datetime = msg_datetime

    return workflow_data

def load_history():
    """Load existing historical data from disk"""
    try:
        df = pd.read_json(HISTORY_FILE, convert_dates=False)
        # Ensure status and error_message columns exist (backward compatibility)
        if 'status' not in df.columns:
            df['status'] = 'success'
        if 'error_message' not in df.columns:
            df['error_message'] = ''
        df['error_message'] = df['error_message'].fillna('')
        # Normalize dates to YYYY-MM-DD (strip any time component)
        if 'date' in df.columns:
            df['date'] = df['date'].astype(str).str[:10]
            df = df.drop_duplicates(subset=['workflow_name', 'date'], keep='last')
        return df
    except (FileNotFoundError, ValueError):
        return pd.DataFrame()


@app.route('/')
def index():
    """Render main dashboard page"""
    return render_template('index.html')

@app.route('/api/refresh')
def refresh_data():
    """Fetch fresh data from Slack and merge with historical data"""
    messages = fetch_slack_messages(days_back=90)
    workflow_data = parse_workflow_data(messages)

    # Convert new data to DataFrame
    new_df = pd.DataFrame(workflow_data)

    if not new_df.empty:
        new_df['date'] = new_df['date'].astype(str).str[:10]
        new_df['timestamp'] = new_df['timestamp'].astype(str)

    # Load existing history and merge
    history_df = load_history()

    if not new_df.empty and not history_df.empty:
        merged = pd.concat([history_df, new_df], ignore_index=True)
        # Deduplicate: keep the latest entry (from new fetch) for same workflow+date
        merged = merged.drop_duplicates(subset=['workflow_name', 'date'], keep='last')
    elif not new_df.empty:
        merged = new_df
    elif not history_df.empty:
        merged = history_df
    else:
        return jsonify({
            'success': False,
            'message': 'No workflow data found',
            'data': []
        })

    merged = merged.sort_values(['date', 'workflow_name']).reset_index(drop=True)

    # Save merged history
    merged.to_json(HISTORY_FILE, orient='records', date_format='iso')

    new_count = len(new_df) if not new_df.empty else 0
    return jsonify({
        'success': True,
        'message': f'Fetched {new_count} records from Slack. Total history: {len(merged)} records.',
        'data': merged.to_dict(orient='records')
    })

@app.route('/api/data')
def get_data():
    """Get all historical workflow data"""
    df = load_history()
    if df.empty:
        return jsonify({
            'success': False,
            'message': 'No data yet. Click Refresh to load from Slack.',
            'data': []
        })
    return jsonify({
        'success': True,
        'data': df.to_dict(orient='records')
    })

@app.route('/api/workflows')
def get_workflows():
    """Get list of unique workflows"""
    df = load_history()
    if df.empty:
        return jsonify({
            'success': False,
            'workflows': []
        })
    workflows = sorted(df['workflow_name'].unique().tolist())
    return jsonify({
        'success': True,
        'workflows': workflows
    })

if __name__ == '__main__':
    print("Starting KNIME Workflow Dashboard...")
    print("Open your browser to: http://localhost:5050")
    app.run(debug=True, port=5050)
