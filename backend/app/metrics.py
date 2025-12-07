from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict


@dataclass
class BusinessSmsMetrics:
    sms_sent_total: int = 0
    sms_sent_owner: int = 0
    sms_sent_customer: int = 0
    lead_followups_sent: int = 0
    retention_messages_sent: int = 0
    sms_confirmations_via_sms: int = 0
    sms_cancellations_via_sms: int = 0
    sms_reschedules_via_sms: int = 0
    sms_opt_out_events: int = 0
    sms_opt_in_events: int = 0


@dataclass
class BusinessTwilioMetrics:
    voice_requests: int = 0
    voice_errors: int = 0
    sms_requests: int = 0
    sms_errors: int = 0


@dataclass
class BusinessVoiceSessionMetrics:
    requests: int = 0
    errors: int = 0


@dataclass
class RouteMetrics:
    request_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0


@dataclass
class CallbackItem:
    phone: str
    first_seen: datetime
    last_seen: datetime
    count: int = 0
    channel: str = "phone"
    lead_source: str | None = None
    status: str = "PENDING"
    last_result: str | None = None
    reason: str = "MISSED_CALL"


@dataclass
class Metrics:
    total_requests: int = 0
    total_errors: int = 0
    appointments_scheduled: int = 0
    users_registered: int = 0
    sms_sent_total: int = 0
    sms_sent_owner: int = 0
    sms_sent_customer: int = 0
    lead_followups_sent: int = 0
    subscription_activations: int = 0
    subscription_failures: int = 0
    qbo_connections: int = 0
    qbo_sync_errors: int = 0
    contacts_imported: int = 0
    contacts_import_errors: int = 0
    chat_messages: int = 0
    chat_failures: int = 0
    chat_latency_ms_total: float = 0.0
    chat_latency_ms_max: float = 0.0
    chat_latency_samples: int = 0
    billing_webhook_failures: int = 0
    background_job_errors: int = 0
    sms_by_business: Dict[str, BusinessSmsMetrics] = field(default_factory=dict)
    twilio_voice_requests: int = 0
    twilio_voice_errors: int = 0
    twilio_sms_requests: int = 0
    twilio_sms_errors: int = 0
    twilio_by_business: Dict[str, BusinessTwilioMetrics] = field(default_factory=dict)
    voice_session_requests: int = 0
    voice_session_errors: int = 0
    voice_sessions_by_business: Dict[str, BusinessVoiceSessionMetrics] = field(
        default_factory=dict
    )
    route_metrics: Dict[str, RouteMetrics] = field(default_factory=dict)
    callbacks_by_business: Dict[str, Dict[str, CallbackItem]] = field(
        default_factory=dict
    )
    retention_by_business: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "appointments_scheduled": self.appointments_scheduled,
            "users_registered": self.users_registered,
            "sms_sent_total": self.sms_sent_total,
            "sms_sent_owner": self.sms_sent_owner,
            "sms_sent_customer": self.sms_sent_customer,
            "lead_followups_sent": self.lead_followups_sent,
            "subscription_activations": self.subscription_activations,
            "subscription_failures": self.subscription_failures,
            "qbo_connections": self.qbo_connections,
            "qbo_sync_errors": self.qbo_sync_errors,
            "contacts_imported": self.contacts_imported,
            "contacts_import_errors": self.contacts_import_errors,
            "chat_messages": self.chat_messages,
            "chat_failures": self.chat_failures,
            "chat_latency_ms_total": self.chat_latency_ms_total,
            "chat_latency_ms_max": self.chat_latency_ms_max,
            "chat_latency_samples": self.chat_latency_samples,
            "billing_webhook_failures": self.billing_webhook_failures,
            "background_job_errors": self.background_job_errors,
            "sms_by_business": {
                business_id: {
                    "sms_sent_total": m.sms_sent_total,
                    "sms_sent_owner": m.sms_sent_owner,
                    "sms_sent_customer": m.sms_sent_customer,
                    "lead_followups_sent": m.lead_followups_sent,
                    "retention_messages_sent": m.retention_messages_sent,
                    "sms_confirmations_via_sms": m.sms_confirmations_via_sms,
                    "sms_cancellations_via_sms": m.sms_cancellations_via_sms,
                    "sms_reschedules_via_sms": m.sms_reschedules_via_sms,
                    "sms_opt_out_events": m.sms_opt_out_events,
                    "sms_opt_in_events": m.sms_opt_in_events,
                }
                for business_id, m in self.sms_by_business.items()
            },
            "twilio_voice_requests": self.twilio_voice_requests,
            "twilio_voice_errors": self.twilio_voice_errors,
            "twilio_sms_requests": self.twilio_sms_requests,
            "twilio_sms_errors": self.twilio_sms_errors,
            "twilio_by_business": {
                business_id: {
                    "voice_requests": m.voice_requests,
                    "voice_errors": m.voice_errors,
                    "sms_requests": m.sms_requests,
                    "sms_errors": m.sms_errors,
                }
                for business_id, m in self.twilio_by_business.items()
            },
            "voice_session_requests": self.voice_session_requests,
            "voice_session_errors": self.voice_session_errors,
            "voice_sessions_by_business": {
                business_id: {
                    "requests": m.requests,
                    "errors": m.errors,
                }
                for business_id, m in self.voice_sessions_by_business.items()
            },
            "route_metrics": {
                path: {
                    "request_count": rm.request_count,
                    "error_count": rm.error_count,
                    "total_latency_ms": rm.total_latency_ms,
                    "max_latency_ms": rm.max_latency_ms,
                }
                for path, rm in self.route_metrics.items()
            },
            "callbacks_by_business": {
                business_id: {
                    phone: {
                        "phone": item.phone,
                        "first_seen": item.first_seen.isoformat(),
                        "last_seen": item.last_seen.isoformat(),
                        "count": item.count,
                        "channel": item.channel,
                        "lead_source": item.lead_source or "",
                        "status": item.status,
                        "last_result": item.last_result or "",
                        "reason": item.reason,
                    }
                    for phone, item in queue.items()
                }
                for business_id, queue in self.callbacks_by_business.items()
            },
            "retention_by_business": {
                business_id: dict(campaigns)
                for business_id, campaigns in self.retention_by_business.items()
            },
        }


metrics = Metrics()
