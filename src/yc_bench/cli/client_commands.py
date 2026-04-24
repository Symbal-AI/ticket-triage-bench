from __future__ import annotations

import typer
from sqlalchemy import func

from ..db.models.client import Client, ClientTrust, ClientContract
from ..db.models.ledger import LedgerCategory, LedgerEntry
from ..db.models.sim_state import SimState
from ..db.models.task import Task, TaskStatus
from . import get_db, json_output, error_output

client_app = typer.Typer(help="Client management commands.")


@client_app.command("list")
def client_list():
    """Show all clients with current trust levels."""
    with get_db() as db:
        sim_state = db.query(SimState).first()
        if sim_state is None:
            error_output("No simulation found.")

        clients = db.query(Client).order_by(Client.name).all()
        results = []
        for c in clients:
            ct = (
                db.query(ClientTrust)
                .filter(
                    ClientTrust.company_id == sim_state.company_id,
                    ClientTrust.client_id == c.id,
                )
                .one_or_none()
            )
            results.append(
                {
                    "client_id": str(c.id),
                    "name": c.name,
                    "trust_level": float(ct.trust_level) if ct else 0.0,
                    "tier": c.tier,
                    "specialties": c.specialty_domains or [],
                }
            )

        json_output(
            {
                "count": len(results),
                "clients": results,
            }
        )


@client_app.command("history")
def client_history():
    """Show per-client task history: successes, failures, listed vs actual rewards, disputes."""
    with get_db() as db:
        sim_state = db.query(SimState).first()
        if sim_state is None:
            error_output("No simulation found.")

        company_id = sim_state.company_id
        clients = db.query(Client).order_by(Client.name).all()
        results = []

        for c in clients:
            # Count successes and failures
            success_count = (
                db.query(func.count(Task.id))
                .filter(
                    Task.company_id == company_id,
                    Task.client_id == c.id,
                    Task.status == TaskStatus.COMPLETED_SUCCESS,
                )
                .scalar()
                or 0
            )

            fail_count = (
                db.query(func.count(Task.id))
                .filter(
                    Task.company_id == company_id,
                    Task.client_id == c.id,
                    Task.status == TaskStatus.COMPLETED_FAIL,
                )
                .scalar()
                or 0
            )

            ct = (
                db.query(ClientTrust)
                .filter(
                    ClientTrust.company_id == company_id,
                    ClientTrust.client_id == c.id,
                )
                .one_or_none()
            )

            total = success_count + fail_count
            fail_rate = round(fail_count / total * 100, 1) if total > 0 else 0.0

            results.append(
                {
                    "client_name": c.name,
                    "trust_level": float(ct.trust_level) if ct else 0.0,
                    "tasks_succeeded": success_count,
                    "tasks_failed": fail_count,
                    "failure_rate_pct": fail_rate,
                }
            )

        json_output(
            {
                "count": len(results),
                "client_history": results,
            }
        )


@client_app.command("contracts")
def client_contracts():
    """Show active client contracts with retainer values and renewal dates."""
    with get_db() as db:
        sim_state = db.query(SimState).first()
        if sim_state is None:
            error_output("No simulation found.")

        company_id = sim_state.company_id
        
        # Get all active contracts
        contracts = (
            db.query(ClientContract)
            .join(Client, ClientContract.client_id == Client.id)
            .filter(
                ClientContract.company_id == company_id,
                ClientContract.active == True,
            )
            .order_by(ClientContract.contract_end)
            .all()
        )

        results = []
        total_quarterly_revenue = 0
        for contract in contracts:
            client = db.query(Client).filter(Client.id == contract.client_id).one()
            quarterly_value = contract.contract_value_cents / 100
            total_quarterly_revenue += contract.contract_value_cents
            
            results.append(
                {
                    "client_name": client.name,
                    "client_tier": client.tier,
                    "quarterly_retainer_usd": f"${quarterly_value:,.2f}",
                    "contract_start": contract.contract_start.isoformat(),
                    "contract_end": contract.contract_end.isoformat(),
                    "renewed": contract.renewed,
                }
            )

        json_output(
            {
                "active_contracts": len(results),
                "total_quarterly_revenue_usd": f"${total_quarterly_revenue / 100:,.2f}",
                "contracts": results,
            }
        )

