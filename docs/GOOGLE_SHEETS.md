# Google Sheets workflow action

The `google_sheets_append` action appends one row to a spreadsheet using the Google Sheets API. It uses the workflow owner's encrypted `oauth2_google` credential; access tokens and API errors are never included in node output.

## Setup

1. Enable the Google Sheets API in the Google Cloud project used by FlowForge OAuth.
2. Reconnect the Google credential in FlowForge to grant the Sheets scope. Existing credentials only have Gmail scopes until the owner consents again.
3. Give the connected Google account edit access to the destination spreadsheet.

The OAuth request uses `https://www.googleapis.com/auth/spreadsheets` along with the Gmail scopes already used by FlowForge. Google may require the app to be configured for this sensitive scope before production distribution.

## Node configuration

Connect `Gmail Trigger` to `AI Agent (Ollama)`, then to `Google Sheets · Ajouter une ligne`. Select the same Google credential in the Gmail and Sheets nodes. Configure the Sheets node with:

```json
{
  "credential_id": "<select the connected Google credential>",
  "spreadsheet_id": "<ID from the Google Sheets URL>",
  "range": "Emails!A:C",
  "values": [
    "{{gmail.from}}",
    "{{gmail.subject}}",
    "{{ai.response}}"
  ]
}
```

Replace `gmail` and `ai` with the IDs of those nodes in the workflow. The selected A1 range identifies the table; each execution appends one row, and values are written as raw text. The action returns the updated range and row count.
