TITLE: How to access OpenAI API usage statistics + costs with an API key (copy/paste for another LLM)

GOAL
- Identify which user/org(s) an API key belongs to
- Pull usage metrics (tokens/requests) and costs (spend) programmatically
- Optionally scope calls to a specific organization/project

1) Identify the user + organizations for a key (/v1/me)
Use your API key to see the user and the org(s) it’s associated with:

curl https://api.openai.com/v1/me \
  -H "Authorization: Bearer $SPANGLE_OPENAI_API_KEY"

Notes:
- The response includes a user object and an org list (org IDs + titles).
Ref: https://help.openai.com/en/articles/9132009-how-can-i-view-the-users-or-organizations-associated-with-an-api-key

2) (Optional) Scope requests to a specific organization + project (headers)
If you belong to multiple organizations or have legacy access, specify headers:

curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $SPANGLE_OPENAI_API_KEY" \
  -H "OpenAI-Organization: $ORGANIZATION_ID" \
  -H "OpenAI-Project: $PROJECT_ID"

Notes:
- Usage counts toward the org/project you specify.
- Org IDs are in org settings; project IDs in project settings.
Ref: https://platform.openai.com/docs/api-reference/introduction

3) Programmatic USAGE (activity metrics) — Usage API
The Usage API is organization-level and provides bucketed usage data. Example endpoint:

GET https://api.openai.com/v1/organization/usage/completions

Key query parameters (varies slightly by endpoint):
- start_time (required): Unix seconds, inclusive
- end_time: Unix seconds, exclusive
- bucket_width: 1m / 1h / 1d (defaults to 1d)
- group_by[]: project_id, user_id, api_key_id, model, batch, service_tier (and combinations)
- filters: project_ids[], user_ids[], api_key_ids[], models[] (plus endpoint-specific filters)

Example (completions usage):
curl "https://api.openai.com/v1/organization/usage/completions?start_time=1730419200&end_time=1731024000&bucket_width=1d&group_by[]=model&group_by[]=api_key_id" \
  -H "Authorization: Bearer $ADMIN_OPENAI_API_KEY" \
  -H "Content-Type: application/json"

Notes:
- The official examples show Authorization with an org Admin key for organization usage endpoints (spangle uses `$ADMIN_OPENAI_API_KEY`).
Ref: https://platform.openai.com/docs/api-reference/usage

4) Programmatic COSTS (spend) — Costs endpoint
Costs are available via:

GET https://api.openai.com/v1/organization/costs

Key query parameters:
- start_time (required): Unix seconds, inclusive
- end_time: Unix seconds, exclusive
- bucket_width: only 1d supported (defaults to 1d)
- group_by[]: project_id, line_item (and combinations)

Example (grouped by project + invoice line item):
curl "https://api.openai.com/v1/organization/costs?start_time=1730419200&end_time=1731024000&group_by[]=project_id&group_by[]=line_item" \
  -H "Authorization: Bearer $ADMIN_OPENAI_API_KEY" \
  -H "Content-Type: application/json"

Notes:
- The official examples show Authorization with an org Admin key for costs (spangle uses `$ADMIN_OPENAI_API_KEY`).
- The docs note Usage and Costs may differ slightly; Costs is recommended for financial reconciliation/invoices.
Ref: https://platform.openai.com/docs/api-reference/usage

5) Admin API keys (why you may need one)
Admin API keys can be created/used by Organization Owners and have elevated permissions for organization management.
Refs:
- https://platform.openai.com/docs/api-reference/admin-api-keys
- https://platform.openai.com/docs/api-reference/administration

Practical guidance:
- If your normal project API key can’t access the org-level Usage/Costs endpoints (401/403), ask an org owner to create an Admin API key and use that for these endpoints.

6) Dashboard (non-programmatic)
You can also view usage in the OpenAI Platform dashboard “Usage” area (Cost/Activity views) and export data.
Ref (legacy article; links to the new dashboard article from there):
- https://help.openai.com/en/articles/8554956-usage-dashboard-legacy

7) Security note (don’t leak keys)
- API keys are secrets; don’t embed them in client-side apps.
Ref: https://platform.openai.com/docs/api-reference/introduction

REFERENCES (URLs)
- /v1/me (find orgs tied to a key): https://help.openai.com/en/articles/9132009-how-can-i-view-the-users-or-organizations-associated-with-an-api-key
- API reference intro + org/project headers: https://platform.openai.com/docs/api-reference/introduction
- Usage + Costs endpoints + parameters: https://platform.openai.com/docs/api-reference/usage
- Admin API keys (owners, elevated perms): https://platform.openai.com/docs/api-reference/admin-api-keys
- Administration overview (admin-key context): https://platform.openai.com/docs/api-reference/administration
- Usage dashboard (legacy article, links onward): https://help.openai.com/en/articles/8554956-usage-dashboard-legacy
