SMS Keyword Opt-In Consent (Toll-Free Messaging)
================================================

Overview
--------
We collect explicit SMS opt-in via keyword replies and store verifiable evidence for toll-free verification. This document summarizes the flow, consent language, and what we log as proof.

Opt-In Flow
-----------
- Channel: SMS to the business toll-free number.
- Trigger keywords: e.g., "START", "YES", or a campaign-specific keyword (configurable).
- Response: An immediate confirmation message that includes sender identity, purpose, and opt-out/help instructions.
- Eligibility: Only verified/known recipients (trial-mode requires Twilio-verified destination numbers).

Consent Language
----------------
Example confirmation message (adjust per campaign):
- "Thanks for subscribing to Raven Service Assistant alerts. Reply STOP to opt out, HELP for help. Msg&data rates may apply. Up to N msgs/month."
- Includes business name, purpose (alerts/appointments/updates), frequency, and STOP/HELP instructions.

Evidence We Store
-----------------
- Phone number, keyword received, and confirmation message sent.
- Timestamp (UTC) and message SID from Twilio.
- Inbound/outbound message bodies for the opt-in exchange.
- Channel: toll-free SMS.
- Optional: source IP/device is not available for SMS; consent proof relies on Twilio message logs + stored bodies/SIDs.

STOP/HELP Handling
------------------
- STOP, STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT → immediately suppress further sends to that number; record timestamp and SID.
- HELP → return support contact and brand name.

Data Retention
--------------
- Opt-in/opt-out logs retained per retention policy to satisfy audits and carrier reviews.

Webhook Expectation (Debugger Events)
-------------------------------------
- If using Twilio Debugger webhooks for error/warning visibility, set: `https://ravdevops.com/v1/twilio/owner-voice`
- Payload fields: `AccountSid`, `Sid`, `ParentAccountSid` (if subaccount), `Timestamp`, `Level` (Error|Warning), `PayloadType` (application/json), `Payload` (event-specific JSON).

Operational Notes
-----------------
- Signature verification: enabled via Twilio auth token on `/v1/twilio/*` routes.
- Cloud Armor: Twilio IPs are allow-listed; other sources are denied.
- Trial limitations: destination numbers must be verified in Twilio trial; production requires full toll-free verification with the above consent evidence.
