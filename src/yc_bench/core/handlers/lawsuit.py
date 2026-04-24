"""Handler for lawsuit_filed events.

When a lawsuit is filed due to a security breach:
- Deduct significant funds from company based on breach severity
- Create ledger entry for the lawsuit cost
- May trigger bankruptcy if funds go negative
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from ...db.models.company import Company
from ...db.models.event import SimEvent
from ...db.models.ledger import LedgerCategory, LedgerEntry
from ...db.models.task import Task


@dataclass
class LawsuitResult:
    breach_task_id: UUID
    severity: str
    lawsuit_cost: int
    bankrupt: bool = False


def handle_lawsuit(db: Session, event: SimEvent, sim_time) -> LawsuitResult:
    """Process lawsuit filing from security breach."""
    breach_task_id = UUID(event.payload["breach_task_id"])
    severity = event.payload["severity"]
    
    # Get the company from the breach task
    task = db.query(Task).filter(Task.id == breach_task_id).one()
    company_id = task.company_id
    company = db.query(Company).filter(Company.id == company_id).one()

    # Calculate lawsuit cost based on severity
    lawsuit_costs = {
        "critical": 10_000_000,  # $100k
        "high": 5_000_000,       # $50k
        "medium": 2_000_000,     # $20k
        "low": 500_000,          # $5k
    }
    lawsuit_cost = lawsuit_costs.get(severity, 2_000_000)

    # Deduct funds
    company.funds_cents -= lawsuit_cost

    # Create ledger entry
    db.add(
        LedgerEntry(
            company_id=company_id,
            occurred_at=sim_time,
            category=LedgerCategory.LAWSUIT,
            amount_cents=-lawsuit_cost,
            ref_type="task",
            ref_id=breach_task_id,
        )
    )

    db.flush()

    # Check for bankruptcy
    bankrupt = company.funds_cents < 0

    return LawsuitResult(
        breach_task_id=breach_task_id,
        severity=severity,
        lawsuit_cost=lawsuit_cost,
        bankrupt=bankrupt,
    )
