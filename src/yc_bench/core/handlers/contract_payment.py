"""Handler for contract_payment events.

When a client contract payment is due (start/renewal):
- Add contract value to company funds
- Create ledger entry for the payment
- Track as recurring revenue from active contracts
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from ...db.models.client import Client, ClientContract
from ...db.models.company import Company
from ...db.models.event import SimEvent
from ...db.models.ledger import LedgerCategory, LedgerEntry


@dataclass
class ContractPaymentResult:
    client_id: UUID
    client_name: str
    contract_value: int
    active_contracts: int


def handle_contract_payment(db: Session, event: SimEvent, sim_time) -> ContractPaymentResult:
    """Process contract payment from client."""
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
    
    if not contract or not contract.active:
        # Contract was cancelled, no payment
        return ContractPaymentResult(
            client_id=client_id,
            client_name=client.name,
            contract_value=0,
            active_contracts=0,
        )
    
    # Add contract payment to company funds
    company = db.query(Company).filter(Company.id == company_id).one()
    contract_value = contract.contract_value_cents
    company.funds_cents += contract_value
    
    # Create ledger entry
    db.add(
        LedgerEntry(
            company_id=company_id,
            occurred_at=sim_time,
            category=LedgerCategory.CONTRACT_PAYMENT,
            amount_cents=contract_value,
            ref_type="client",
            ref_id=client_id,
        )
    )
    
    # Count active contracts
    active_contracts = (
        db.query(ClientContract)
        .filter(
            ClientContract.company_id == company_id,
            ClientContract.active == True,
        )
        .count()
    )
    
    db.flush()
    
    return ContractPaymentResult(
        client_id=client_id,
        client_name=client.name,
        contract_value=contract_value,
        active_contracts=active_contracts,
    )
