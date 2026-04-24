from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from ..config.schema import WorldConfig
from ..db.models.client import Client, ClientTrust, ClientContract
from ..db.models.company import Company, CompanyPrestige, Domain
from ..db.models.employee import Employee, EmployeeSkillRate
from ..db.models.task import Task, TaskRequirement, TaskStatus
from ..db.models.event import EventType
from ..core.events import insert_event

from .generate_clients import generate_clients
from .generate_employees import generate_employees
from .generate_tasks import generate_tasks

_ALL_DOMAINS = list(Domain)


@dataclass(frozen=True)
class SeedWorldRequest:
    run_seed: int
    company_name: str
    horizon_years: int
    employee_count: int
    market_task_count: int
    cfg: WorldConfig
    start_date: datetime | None = None


@dataclass(frozen=True)
class SeedWorldResult:
    company_id: str
    seeded_at: datetime


def _seed_company(db, req):
    # Tech stack is deterministic from run_seed so CVEs can reference it.
    from .cve_content import generate_tech_stack
    from .rng import RngStreams

    streams = RngStreams(req.run_seed)
    tech_stack = generate_tech_stack(streams.stream("tech_stack"))

    company = Company(
        id=uuid4(),
        name=req.company_name,
        funds_cents=req.cfg.initial_funds_cents,
        technical_debt=0,
        security_breach_count=0,
        tech_stack=tech_stack,
    )
    db.add(company)
    db.flush()
    return company


def _seed_company_prestige(db, company, cfg):
    for domain in _ALL_DOMAINS:
        db.add(
            CompanyPrestige(
                company_id=company.id,
                domain=domain,
                prestige_level=cfg.initial_prestige_level,
            )
        )


_FIXED_WORLD_SEED = 1  # employees + clients identical across all run seeds


def _seed_employees(db, company, req):
    generated = generate_employees(
        run_seed=_FIXED_WORLD_SEED, count=req.employee_count, cfg=req.cfg
    )
    for emp in generated:
        employee = Employee(
            id=uuid4(),
            company_id=company.id,
            name=emp.name,
            tier=emp.tier,
            work_hours_per_day=emp.work_hours_per_day,
            salary_cents=emp.salary_cents,
        )
        db.add(employee)

        for domain, rate in emp.rates_by_domain.items():
            db.add(
                EmployeeSkillRate(
                    employee_id=employee.id,
                    domain=domain,
                    rate_domain_per_hour=rate,
                )
            )


def _seed_clients(db, company, req):
    """Create Client rows, ClientTrust rows (all starting at 0.0), and initial contracts."""
    generated = generate_clients(
        run_seed=_FIXED_WORLD_SEED, count=req.cfg.num_clients, cfg=req.cfg
    )
    clients = []
    start_date = req.start_date or datetime.now(timezone.utc)
    
    for gc in generated:
        client = Client(
            id=uuid4(),
            name=gc.name,
            reward_multiplier=gc.reward_multiplier,
            tier=gc.tier,
            specialty_domains=gc.specialty_domains,
            loyalty=gc.loyalty,
        )
        db.add(client)
        clients.append(client)
        db.add(
            ClientTrust(
                company_id=company.id,
                client_id=client.id,
                trust_level=0,
            )
        )
        
        # Calculate contract value (3-month retainer based on tier)
        # Base retainer: $50k/quarter, scaled by reward_multiplier
        base_retainer = 5_000_000  # $50k in cents
        contract_value = int(base_retainer * gc.reward_multiplier)
        
        # Create initial contract (3 months)
        contract_end = start_date + timedelta(days=90)
        db.add(
            ClientContract(
                company_id=company.id,
                client_id=client.id,
                contract_start=start_date,
                contract_end=contract_end,
                contract_value_cents=contract_value,
                active=True,
                renewed=False,
            )
        )
        
        # Schedule contract payment at start (immediate)
        insert_event(
            db,
            company_id=company.id,
            event_type=EventType.CONTRACT_PAYMENT,
            scheduled_at=start_date,
            payload={
                "client_id": str(client.id),
                "company_id": str(company.id),
            },
            dedupe_key=f"contract_payment_{company.id}_{client.id}_0",
        )
        
        # Schedule contract renewal check event
        insert_event(
            db,
            company_id=company.id,
            event_type=EventType.CONTRACT_RENEWAL_CHECK,
            scheduled_at=contract_end,
            payload={
                "client_id": str(client.id),
                "company_id": str(company.id),
                "rng_seed": req.run_seed + hash(str(client.id)) % 1000000,
            },
            dedupe_key=f"contract_renewal_{company.id}_{client.id}_0",
        )
        
    db.flush()
    return clients


def _seed_market_tasks(db, company, req, clients):
    # Build specialty list and reward multipliers indexed by client order
    client_specialties = (
        [c.specialty_domains or [] for c in clients] if clients else None
    )
    client_reward_mults = [c.reward_multiplier for c in clients] if clients else None
    generated = generate_tasks(
        run_seed=req.run_seed,
        count=req.market_task_count,
        cfg=req.cfg,
        client_specialties=client_specialties,
        client_reward_mults=client_reward_mults,
        tech_stack=company.tech_stack,
    )
    for slot_idx, task in enumerate(generated):
        # Map client_index to actual client for feature requests
        client = None
        if task.ticket_type == "feature_request" and clients:
            client = clients[task.client_index % len(clients)]
        
        # Map employee_index to actual employee for tech debt tickets
        employee_id = None
        if task.ticket_type == "tech_debt":
            employees = db.query(Employee).filter(Employee.company_id == company.id).all()
            if employees and task.employee_index is not None:
                employee_id = employees[task.employee_index % len(employees)].id
        
        task_row = Task(
            id=uuid4(),
            company_id=None,
            client_id=client.id if client else None,
            employee_id=employee_id,
            status=TaskStatus.MARKET,
            ticket_type=task.ticket_type,
            cve_severity=task.cve_severity,
            time_to_breach_hours=task.time_to_breach_hours,
            technical_debt_delta=task.technical_debt_delta,
            cve_metadata=task.cve_metadata,
            title=task.title,
            required_prestige=task.required_prestige,
            reward_funds_cents=task.reward_funds_cents,
            reward_prestige_delta=task.reward_prestige_delta,
            skill_boost_pct=task.skill_boost_pct,
            accepted_at=None,
            deadline=None,
            completed_at=None,
            success=None,
            progress_milestone_pct=0,
            required_trust=task.required_trust,
            market_slot=slot_idx,
        )
        db.add(task_row)

        for domain, qty in task.requirements.items():
            db.add(
                TaskRequirement(
                    task_id=task_row.id,
                    domain=domain,
                    required_qty=qty,
                    completed_qty=0,
                )
            )

        # Schedule the CVE's breach timer at world-seed time, not at accept time.
        # Real CVEs are a risk whether you triage them or not — ignoring a
        # vulnerability in the market still exposes the company. Accepting and
        # completing the CVE before breach_time is how you PREVENT the breach.
        if task.ticket_type == "cve" and task.time_to_breach_hours:
            start = req.start_date or datetime.now(timezone.utc)
            breach_time = start + timedelta(hours=task.time_to_breach_hours)
            insert_event(
                db,
                company_id=company.id,
                event_type=EventType.SECURITY_BREACH,
                scheduled_at=breach_time,
                payload={
                    "task_id": str(task_row.id),
                    "rng_seed": req.run_seed + task.time_to_breach_hours,
                },
                dedupe_key=f"breach_{task_row.id}",
            )


def seed_world(db, req):
    if req.employee_count <= 0:
        raise ValueError("employee_count must be positive")
    if req.market_task_count <= 0:
        raise ValueError("market_task_count must be positive")

    seeded_at = req.start_date

    company = _seed_company(db, req)
    _seed_company_prestige(db, company, req.cfg)
    _seed_employees(db, company, req)
    clients = _seed_clients(db, company, req)
    _seed_market_tasks(db, company, req, clients)

    return SeedWorldResult(
        company_id=company.id,
        seeded_at=seeded_at,
    )


def seed_world_transactional(db, req):
    result = seed_world(db, req)
    db.flush()
    return result


__all__ = [
    "SeedWorldRequest",
    "SeedWorldResult",
    "seed_world",
    "seed_world_transactional",
]
