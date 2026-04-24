from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4, UUID

import typer
from sqlalchemy import func

from ..config import get_world_config
from ..db.models.company import Company, Domain
from ..db.models.employee import Employee, EmployeeSkillRate
from ..db.models.ledger import LedgerCategory, LedgerEntry
from ..db.models.task import Task, TaskAssignment, TaskStatus
from ..db.models.sim_state import SimState
from . import get_db, json_output, error_output

employee_app = typer.Typer(help="Employee management commands.")


# Contractor policy
_CONTRACTOR_PREMIUM = 1.5  # paid 1.5x the mid-tier monthly salary
_MAX_ACTIVE_CONTRACTORS = 2


def _active_contractor_count(db, company_id, sim_time) -> int:
    """Count contractors whose term hasn't expired yet."""
    return (
        db.query(Employee)
        .filter(
            Employee.company_id == company_id,
            Employee.contractor_until.isnot(None),
            Employee.contractor_until > sim_time,
        )
        .count()
    )


@employee_app.command("list")
def employee_list():
    """List all employees with their skills and current assignments."""
    with get_db() as db:
        sim_state = db.query(SimState).first()
        if sim_state is None:
            error_output("No simulation found.")

        employees = (
            db.query(Employee).filter(Employee.company_id == sim_state.company_id).all()
        )

        results = []
        for emp in employees:
            # Current active assignments (show task titles, not UUIDs)
            active_assignments = (
                db.query(Task)
                .join(TaskAssignment, Task.id == TaskAssignment.task_id)
                .filter(
                    TaskAssignment.employee_id == emp.id,
                    Task.status == TaskStatus.ACTIVE,
                )
                .all()
            )
            active_tasks = [t.title for t in active_assignments]

            # Skill rates per domain
            skill_rows = (
                db.query(EmployeeSkillRate)
                .filter(EmployeeSkillRate.employee_id == emp.id)
                .all()
            )
            skill_rates = {
                r.domain.value: round(float(r.rate_domain_per_hour), 2)
                for r in skill_rows
            }

            row = {
                "name": emp.name,
                "tier": emp.tier,
                "salary_cents": emp.salary_cents,
                "skill_rates": skill_rates,
                "active_tasks": active_tasks,
            }
            if emp.contractor_until is not None:
                row["is_contractor"] = True
                row["contractor_until"] = emp.contractor_until.isoformat()
                row["expired"] = emp.contractor_until <= sim_state.sim_time
            results.append(row)

        json_output(
            {
                "count": len(results),
                "employees": results,
            }
        )


@employee_app.command("hire-contractor")
def hire_contractor(
    domain: Domain = typer.Option(..., "--domain", help="Specialty domain"),
    weeks: int = typer.Option(..., "--weeks", help="Contract length in weeks (1-12)"),
    name: str = typer.Option(
        None, "--name", help="Optional contractor name (auto-generated otherwise)"
    ),
):
    """Hire a mid-tier contractor in one domain for N weeks.

    Cost is paid upfront, equal to mid-tier monthly salary * (weeks/4) * contractor
    premium. Capped at 2 active contractors at once.
    """
    if weeks < 1 or weeks > 12:
        error_output("weeks must be between 1 and 12")

    with get_db() as db:
        sim_state = db.query(SimState).first()
        if sim_state is None:
            error_output("No simulation found.")

        if _active_contractor_count(db, sim_state.company_id, sim_state.sim_time) >= _MAX_ACTIVE_CONTRACTORS:
            error_output(
                f"Active contractor cap reached ({_MAX_ACTIVE_CONTRACTORS}). Wait for one to expire."
            )

        wc = get_world_config()
        mid_monthly_midpoint = (wc.salary_mid.min_cents + wc.salary_mid.max_cents) // 2
        cost_cents = int(mid_monthly_midpoint * (weeks / 4.0) * _CONTRACTOR_PREMIUM)

        company = db.query(Company).filter(Company.id == sim_state.company_id).one()
        if company.funds_cents < cost_cents:
            error_output(
                f"Insufficient funds: need {cost_cents} cents, have {company.funds_cents}"
            )

        expiry = sim_state.sim_time + timedelta(weeks=weeks)

        # Mid-tier skill rate midpoint in the contractor's domain; zero elsewhere.
        mid_rate_midpoint = Decimal(
            str((wc.salary_mid.rate_min + wc.salary_mid.rate_max) / 2.0)
        )

        contractor_name = name or f"Contractor_{uuid4().hex[:6]}"
        emp = Employee(
            id=uuid4(),
            company_id=sim_state.company_id,
            name=contractor_name,
            tier="contractor",
            work_hours_per_day=Decimal("9.00"),
            # Salary is $0 — cost is the upfront payment; contractors aren't payrolled.
            salary_cents=0,
            contractor_until=expiry,
        )
        db.add(emp)
        db.flush()

        # Only one productive domain. Other domains get zero rate so they can't
        # be misassigned to unrelated work.
        for d in Domain:
            db.add(
                EmployeeSkillRate(
                    employee_id=emp.id,
                    domain=d,
                    rate_domain_per_hour=mid_rate_midpoint if d == domain else Decimal("0"),
                )
            )

        # Pay up front
        company.funds_cents -= cost_cents
        db.add(
            LedgerEntry(
                company_id=sim_state.company_id,
                occurred_at=sim_state.sim_time,
                category=LedgerCategory.CONTRACTOR_COST,
                amount_cents=-cost_cents,
                ref_type="employee",
                ref_id=emp.id,
            )
        )

        db.flush()

        json_output(
            {
                "employee_id": str(emp.id),
                "name": emp.name,
                "domain": domain.value,
                "rate_per_hour": float(mid_rate_midpoint),
                "contractor_until": expiry.isoformat(),
                "cost_cents": cost_cents,
                "active_contractors": _active_contractor_count(
                    db, sim_state.company_id, sim_state.sim_time
                ),
                "funds_cents": company.funds_cents,
            }
        )
