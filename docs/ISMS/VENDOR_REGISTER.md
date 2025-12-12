Vendor Register and DPAs
========================

Register
--------
| Vendor | Purpose | Data Processed | DPA/Security Review | Owner | Notes |
| --- | --- | --- | --- | --- | --- |
| Twilio | Voice/SMS, webhooks | Phone numbers, call metadata, transcripts (short), voicemail URLs | DPA required; enable signature verification (in place) | Eng | Use restricted webhook IPs and signature checks; rotate auth tokens quarterly. |
| Stripe | Billing/subscriptions | Customer name/email, subscription ids, payment links (no PAN) | DPA required; PCI handled by Stripe | Eng/Finance | Webhook signatures enforced; test mode by default. |
| Google (Calendar, OAuth, GCS) | Scheduling, storage | Calendar events, auth tokens, dashboard assets | DPA via Workspace; security review complete | Eng | OAuth tokens stored in Secret Manager; limited scopes. |
| QuickBooks Online | Invoicing/exports | Customer/contact details, invoice metadata | DPA required | Finance | Sandbox by default; production only with owner approval. |
| OpenAI or other LLM APIs (optional) | Intent assist | Snippets of transcript | Vendor review + data handling restrictions before enabling | Eng/Product | Off by default; enable only per-tenant with data policy acknowledged. |
| Email provider (e.g., Gmail/Workspace) | Owner/customer email | Owner email, summaries | DPA via Workspace | Eng | Disable if not needed; use service account with least privilege. |

Management
----------
- Review vendor list quarterly; add/remove entries when integrations change.
- Store signed DPAs in the shared secure drive; link to GitHub issue for traceability.
- For each vendor, record last penetration test date (if provided) and SOC2/ISO certificates when available.
