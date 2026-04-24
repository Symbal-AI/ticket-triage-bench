"""Handler for contract_renewal_check events.

When a client contract is up for renewal:
- Check client's failed features count and security exposure
- If too many failed features or security exposures, client does not renew
- If renewed, reset counters and extend contract
- If not renewed, mark contract as inactive
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from ...db.models.client import Client, ClientContract
from ...db.models.event import SimEvent, EventType
from ..events import insert_event


@dataclass
class ContractRenewalResult:
    client_id: UUID
    client_name: str
    renewed: bool
    failed_features: int
    security_exposures: int
    reason: str = ""


def handle_contract_renewal(db: Session, event: SimEvent, sim_time) -> ContractRenewalResult:
    """Process contract renewal decision."""
    client_id = UUID(event.payload["client_id"])
    company_id = UUID(event.payload["company_id"])
    
    client = db.query(Client).filter(Client.id == client_id).one()
    contract = (
        db.query(ClientContract)
        .filter(
            ClientContract.company_id == company_id,
            ClientContract.client_id == client_id,
        )
        .one_or_none()
    )

    # Renewal decision based on performance
    # Thresholds:
    # - More than 3 failed features: likely won't renew
    # - Any security breach exposures: reduces likelihood
    # - Combined: too much = no renewal
    
    failed_features = client.failed_features_count
    security_exposures = client.security_breach_exposure_count
    
    # Calculate renewal probability
    renewal_score = 1.0
    renewal_score -= min(0.8, failed_features * 0.2)  # -20% per failed feature
    renewal_score -= min(0.5, security_exposures * 0.15)  # -15% per breach exposure
    
    # Random element with seed from payload
    renewed = renewal_score > 0.5
    
    if event.payload.get("rng_seed"):
        import random
        rng = random.Random(event.payload["rng_seed"])
        if renewal_score <= 0.9:  # Add randomness if not perfect score
            renewed = rng.random() < renewal_score

    reason = ""
    if not renewed:
        if failed_features > 3:
            reason = f"Too many failed features ({failed_features})"
        elif security_exposures > 0:
            reason = f"Security concerns ({security_exposures} breach exposures)"
        else:
            reason = "Poor overall performance"
    
    if contract:
        if renewed:
            # Reset counters and extend contract
            client.failed_features_count = 0
            client.security_breach_exposure_count = 0
            contract.contract_start = sim_time
            contract.contract_end = sim_time + timedelta(days=90)  # 3-month contract
            contract.renewed = True
            contract.active = True
            
            # Schedule contract payment at renewal
            insert_event(
                db,
                company_id=company_id,
                event_type=EventType.CONTRACT_PAYMENT,
                scheduled_at=sim_time,
                payload={
                    "client_id": str(client_id),
                    "company_id": str(company_id),
                },
                dedupe_key=f"contract_payment_{company_id}_{client_id}_{event.payload.get('renewal_count', 0) + 1}",
            )
            
            # Schedule next renewal check
            next_check_time = contract.contract_end
            renewal_count = event.payload.get("renewal_count", 0) + 1
            insert_event(
                db,
                company_id=company_id,
                event_type=EventType.CONTRACT_RENEWAL_CHECK,
                scheduled_at=next_check_time,
                payload={
                    "client_id": str(client_id),
                    "company_id": str(company_id),
                    "rng_seed": event.payload.get("rng_seed", 0) + renewal_count,
                    "renewal_count": renewal_count,
                },
                dedupe_key=f"contract_renewal_{company_id}_{client_id}_{renewal_count}",
            )
        else:
            # Mark contract as inactive
            contract.active = False
            contract.renewed = False

    db.flush()

    return ContractRenewalResult(
        client_id=client_id,
        client_name=client.name,
        renewed=renewed,
        failed_features=failed_features,
        security_exposures=security_exposures,
        reason=reason,
    )
