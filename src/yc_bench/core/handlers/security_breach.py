"""Handler for security_breach events.

When a CVE ticket reaches its time-to-breach without being fixed:
- Mark the ticket as breached
- Increase company security breach count
- Affect all active clients (exposure count increases)
- Schedule potential lawsuit events
- May cause clients to not renew their contracts
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from ...db.models.client import Client
from ...db.models.company import Company
from ...db.models.event import EventType, SimEvent
from ...db.models.task import Task, TaskStatus
from ..events import insert_event


@dataclass
class SecurityBreachResult:
    task_id: UUID
    cve_severity: str
    affected_clients: int = 0
    lawsuit_scheduled: bool = False


def handle_security_breach(db: Session, event: SimEvent, sim_time) -> SecurityBreachResult:
    """Process security breach from unpatched CVE.

    CVEs that are still in MARKET status (never accepted) also breach here —
    the event was scheduled at world-seed time based on sim_start +
    time_to_breach_hours. Ignoring a CVE doesn't make you safer.
    """
    task_id = UUID(event.payload["task_id"])
    task = db.query(Task).filter(Task.id == task_id).one()

    # If CVE was already fixed, no breach occurs
    if task.status == TaskStatus.COMPLETED_SUCCESS:
        return SecurityBreachResult(
            task_id=task_id,
            cve_severity=task.cve_severity or "medium",
            affected_clients=0,
            lawsuit_scheduled=False,
        )

    # Prefer event.company_id (always set); task.company_id is None for
    # unaccepted MARKET-status CVEs.
    company_id = event.company_id

    # Mark task as breached
    task.status = TaskStatus.SECURITY_BREACH
    task.breached_at = sim_time

    # Increment company security breach count
    company = db.query(Company).filter(Company.id == company_id).one()
    company.security_breach_count += 1

    # Get all clients and increase their exposure count
    clients = db.query(Client).all()
    for client in clients:
        client.security_breach_exposure_count += 1

    affected_clients = len(clients)

    # Schedule lawsuit with probability based on severity
    lawsuit_prob = {
        "critical": 0.8,
        "high": 0.5,
        "medium": 0.2,
        "low": 0.05,
    }
    severity = task.cve_severity or "medium"
    
    lawsuit_scheduled = False
    if event.payload.get("rng_seed"):
        import random
        rng = random.Random(event.payload["rng_seed"])
        if rng.random() < lawsuit_prob.get(severity, 0.2):
            # Schedule lawsuit event 1-7 days after breach
            lawsuit_delay_hours = int(rng.uniform(24, 168))
            lawsuit_time = sim_time + __import__('datetime').timedelta(hours=lawsuit_delay_hours)
            
            insert_event(
                db,
                company_id=company_id,
                event_type=EventType.LAWSUIT_FILED,
                scheduled_at=lawsuit_time,
                payload={
                    "breach_task_id": str(task_id),
                    "severity": severity,
                },
                dedupe_key=f"lawsuit_breach_{task_id}",
            )
            lawsuit_scheduled = True

    db.flush()

    return SecurityBreachResult(
        task_id=task_id,
        cve_severity=severity,
        affected_clients=affected_clients,
        lawsuit_scheduled=lawsuit_scheduled,
    )
