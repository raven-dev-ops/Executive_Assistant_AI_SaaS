Risk Management Method
======================

Approach
--------
- **Cadence**: Quarterly risk review (or after any P0/P1 incident), recorded in the risk register.
- **Method**: Identify threats → map to assets → rate likelihood and impact (Low/Med/High) → compute risk score (1-9) → select treatment (Accept, Mitigate, Transfer, Avoid).
- **Evidence**: Each risk item gets an owner, due date, and a link to the mitigation issue/PR.

Scoring rubric
--------------
- Likelihood: 1 (unlikely), 2 (possible), 3 (likely).
- Impact: 1 (limited/local), 2 (customer-facing but recoverable), 3 (material outage/data breach).
- Risk score = Likelihood × Impact.
- Severity buckets: 1-2 (Low), 3-4 (Medium), 6-9 (High).

Risk register template
----------------------
| ID | Date | Asset/Process | Threat | Likelihood | Impact | Score | Treatment | Owner | Due | Evidence/Link |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-001 | 2025-12-12 | Twilio webhooks | Replay or spoofed webhook | 2 | 3 | 6 | Mitigate (HMAC verification + gcloud armor) | Eng | 2025-12-15 | #88, `gcloud-armor-twilio.txt` |
| R-002 | 2025-12-12 | Google Calendar OAuth tokens | Token leak | 2 | 3 | 6 | Mitigate (Secret Manager + key rotation SOP) | Eng | 2025-12-20 | #84, rotation checklist |
| R-003 | 2025-12-12 | Owner alerting | SMS delivery failure | 2 | 2 | 4 | Mitigate (retry + email fallback) | Eng | 2025-12-10 | #79, `owner_notifications.py` |

Operations
----------
- Keep the register in GitHub (issue label `risk`) with links back to this method.
- Tabletop exercises: simulate at least one P0 scenario per quarter (Twilio outage, calendar write failure, auth compromise), capture outcomes in the register and incident postmortems.
- Residual risk review and acceptance are recorded by the ISMS owner and Product leader jointly.
