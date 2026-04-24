"""Handler for task_completed events.

On completion:
- If completion_time <= deadline: success → add reward funds, add prestige, skill-boost employees.
- If completion_time > deadline: fail → set completed_fail, apply 0.8 * delta prestige penalty.
After either outcome, recalculate ETAs (freed employees change topology).
Payment disputes may be scheduled for RAT clients at high trust.
"""

from __future__ import annotations

import random as _stdlib_random
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Dict
from uuid import UUID

from sqlalchemy.orm import Session

from ...db.models.client import Client, ClientTrust
from ...db.models.company import Company, CompanyPrestige, Domain
from ...db.models.employee import Employee, EmployeeSkillRate
from ...config import get_world_config
from ...db.models.event import EventType, SimEvent
from ...db.models.ledger import LedgerCategory, LedgerEntry
from ...db.models.task import Task, TaskAssignment, TaskRequirement, TaskStatus, TicketType
from ..events import insert_event


@dataclass
class TaskCompleteResult:
    task_id: UUID
    success: bool
    grade: str = "on_time"  # on_time | late_24h | late_72h | failed
    reward_multiplier: float = 1.0
    funds_delta: int = 0
    listed_reward: int = 0
    prestige_changes: Dict[str, float] = field(default_factory=dict)
    trust_delta: float = 0.0
    bankrupt: bool = False


_GRACE_24H = timedelta(hours=24)
_GRACE_72H = timedelta(hours=72)


def _grade_deadline(sim_time, deadline):
    """Grade a task completion against its deadline.

    Returns (grade, reward_multiplier, counts_as_success). Real clients tolerate
    days of slippage; binary on-time/fail was punishing normal slippage as
    catastrophic failure.
    """
    if sim_time <= deadline:
        return "on_time", 1.0, True
    overrun = sim_time - deadline
    if overrun <= _GRACE_24H:
        return "late_24h", 0.8, True
    if overrun <= _GRACE_72H:
        return "late_72h", 0.5, True
    return "failed", 0.0, False


def handle_task_complete(db: Session, event: SimEvent, sim_time) -> TaskCompleteResult:
    """Process task completion: finalize progress, determine success/fail, apply rewards/penalties."""
    task_id = UUID(event.payload["task_id"])
    task = db.query(Task).filter(Task.id == task_id).one()
    company_id = task.company_id

    # Finalize all domain progress to 100%
    reqs = db.query(TaskRequirement).filter(TaskRequirement.task_id == task_id).all()
    for req in reqs:
        req.completed_qty = req.required_qty
    db.flush()

    task.completed_at = sim_time
    grade, reward_mult, success = _grade_deadline(sim_time, task.deadline)

    wc = get_world_config()
    prestige_changes: Dict[str, float] = {}
    funds_delta = 0

    if success:
        task.status = TaskStatus.COMPLETED_SUCCESS
        task.success = True

        # Add reward funds (reduced for feature requests - retainer model)
        company = db.query(Company).filter(Company.id == company_id).one()

        # Feature requests: 10% completion bonus (retainer covers main payment),
        # further scaled by on-time grade (100% / 80% / 50%).
        # Tech debt & CVEs: no direct payment.
        if task.ticket_type == TicketType.FEATURE_REQUEST:
            completion_bonus = int(task.reward_funds_cents * 0.1 * reward_mult)
        else:
            completion_bonus = task.reward_funds_cents  # Already 0 for tech debt/CVEs

        company.funds_cents += completion_bonus
        funds_delta = completion_bonus

        # Ledger entry
        if completion_bonus > 0:
            db.add(
                LedgerEntry(
                    company_id=company_id,
                    occurred_at=sim_time,
                    category=LedgerCategory.TASK_REWARD,
                    amount_cents=completion_bonus,
                    ref_type="task",
                    ref_id=task_id,
                )
            )

        # Add prestige to each domain
        for req in reqs:
            prestige = (
                db.query(CompanyPrestige)
                .filter(
                    CompanyPrestige.company_id == company_id,
                    CompanyPrestige.domain == req.domain,
                )
                .one_or_none()
            )
            if prestige is not None:
                old = float(prestige.prestige_level)
                prestige.prestige_level = min(
                    Decimal(str(wc.prestige_max)),
                    prestige.prestige_level
                    + Decimal(str(float(task.reward_prestige_delta) * reward_mult)),
                )
                prestige_changes[req.domain.value] = (
                    float(prestige.prestige_level) - old
                )

        # Skill boost: only the top contributors get boosted (Brooks's Law).
        # Overcrowded employees (beyond the efficient team size) are overhead
        # and don't learn from the experience.
        from ..progress import _EFFICIENT_TEAM_SIZE

        assignments = (
            db.query(TaskAssignment).filter(TaskAssignment.task_id == task_id).all()
        )
        if task.skill_boost_pct > 0:
            task_domains = {req.domain for req in reqs}
            for domain in task_domains:
                # Rank employees by their rate in this domain (best first)
                emp_rates = []
                for a in assignments:
                    skill = (
                        db.query(EmployeeSkillRate)
                        .filter(
                            EmployeeSkillRate.employee_id == a.employee_id,
                            EmployeeSkillRate.domain == domain,
                        )
                        .one_or_none()
                    )
                    if skill is not None:
                        emp_rates.append(skill)
                emp_rates.sort(key=lambda s: s.rate_domain_per_hour, reverse=True)

                # Only boost the top N (efficient team size)
                for skill in emp_rates[:_EFFICIENT_TEAM_SIZE]:
                    boost = skill.rate_domain_per_hour * Decimal(
                        str(float(task.skill_boost_pct))
                    )
                    skill.rate_domain_per_hour = min(
                        skill.rate_domain_per_hour + boost,
                        Decimal(str(wc.skill_rate_max)),
                    )

        # Salary bump: fixed raise per tier (linear, not compounding).
        # Bump = tier midpoint salary × salary_bump_pct (computed once from config).
        if wc.salary_bump_pct > 0:
            tier_midpoints = {
                "junior": (wc.salary_junior.min_cents + wc.salary_junior.max_cents)
                // 2,
                "mid": (wc.salary_mid.min_cents + wc.salary_mid.max_cents) // 2,
                "senior": (wc.salary_senior.min_cents + wc.salary_senior.max_cents)
                // 2,
            }
            for a in assignments:
                employee = (
                    db.query(Employee)
                    .filter(Employee.id == a.employee_id)
                    .one_or_none()
                )
                if employee is not None and employee.salary_cents < wc.salary_max_cents:
                    bump = int(
                        tier_midpoints.get(employee.tier, 0) * wc.salary_bump_pct
                    )
                    employee.salary_cents = min(
                        wc.salary_max_cents, employee.salary_cents + bump
                    )

    else:
        task.status = TaskStatus.COMPLETED_FAIL
        task.success = False

        # Apply penalty_fail_multiplier * reward_prestige_delta penalty
        penalty = Decimal(str(wc.penalty_fail_multiplier)) * task.reward_prestige_delta
        for req in reqs:
            prestige = (
                db.query(CompanyPrestige)
                .filter(
                    CompanyPrestige.company_id == company_id,
                    CompanyPrestige.domain == req.domain,
                )
                .one_or_none()
            )
            if prestige is not None:
                old = float(prestige.prestige_level)
                prestige.prestige_level = max(
                    Decimal(str(wc.prestige_min)),
                    prestige.prestige_level - penalty,
                )
                prestige_changes[req.domain.value] = (
                    float(prestige.prestige_level) - old
                )

        # Financial penalty: deduct a fraction of the advertised reward
        if wc.penalty_fail_funds_pct > 0:
            advertised = task.advertised_reward_cents or task.reward_funds_cents
            penalty_cents = int(advertised * wc.penalty_fail_funds_pct)
            company = db.query(Company).filter(Company.id == company_id).one()
            company.funds_cents -= penalty_cents
            funds_delta = -penalty_cents
            db.add(
                LedgerEntry(
                    company_id=company_id,
                    occurred_at=sim_time,
                    category=LedgerCategory.TASK_REWARD,
                    amount_cents=-penalty_cents,
                    ref_type="task",
                    ref_id=task_id,
                )
            )

    # --- Ticket type specific logic ---
    company = db.query(Company).filter(Company.id == company_id).one()
    
    # Feature requests: succeeded = merged PR (adds tech debt), failed = client unhappy
    if task.ticket_type == TicketType.FEATURE_REQUEST:
        if success:
            # Merged PR adds technical debt
            # Amount based on task size (sum of requirements)
            total_work = sum(float(req.required_qty) for req in reqs)
            tech_debt_added = int(total_work * 0.1)  # 10% of work becomes tech debt
            company.technical_debt += tech_debt_added
        else:
            # Failed feature request
            if task.client_id:
                client = db.query(Client).filter(Client.id == task.client_id).one_or_none()
                if client:
                    client.failed_features_count += 1
    
    # Tech debt tickets: reduce accumulated debt
    elif task.ticket_type == TicketType.TECH_DEBT:
        if success and task.technical_debt_delta < 0:
            # Reduce technical debt (delta is negative)
            debt_reduction = abs(task.technical_debt_delta)
            company.technical_debt = max(0, company.technical_debt - debt_reduction)
    
    # CVEs: success = patched, failure = will become breach
    elif task.ticket_type == TicketType.CVE:
        if not success:
            # CVE not fixed in time - will breach
            # This is handled by the SECURITY_BREACH event scheduled when CVE was accepted
            pass

    # --- Client trust update ---
    trust_delta = 0.0
    if task.client_id is not None:
        ct = (
            db.query(ClientTrust)
            .filter(
                ClientTrust.company_id == company_id,
                ClientTrust.client_id == task.client_id,
            )
            .one_or_none()
        )
        if ct is not None:
            if success:
                # Diminishing returns: gain = base × (1 - trust/max)^power × reward_mult.
                # Late-but-success (grace curve) gets a smaller trust gain than on-time.
                ratio = float(ct.trust_level) / wc.trust_max
                gain = (
                    wc.trust_gain_base
                    * ((1 - ratio) ** wc.trust_gain_diminishing_power)
                    * reward_mult
                )
                new_level = min(wc.trust_max, float(ct.trust_level) + gain)
                trust_delta = new_level - float(ct.trust_level)
                ct.trust_level = Decimal(str(round(new_level, 3)))
            else:
                old_level = float(ct.trust_level)
                new_level = max(wc.trust_min, old_level - wc.trust_fail_penalty)
                trust_delta = new_level - old_level
                ct.trust_level = Decimal(str(round(new_level, 3)))

        # Cross-client trust decay: working for Client A erodes trust with others.
        # Clients notice when you spread attention too thin.
        if wc.trust_cross_client_decay > 0:
            other_cts = (
                db.query(ClientTrust)
                .filter(
                    ClientTrust.company_id == company_id,
                    ClientTrust.client_id != task.client_id,
                )
                .all()
            )
            for other_ct in other_cts:
                old = float(other_ct.trust_level)
                if old > wc.trust_min:
                    new = max(wc.trust_min, old - wc.trust_cross_client_decay)
                    other_ct.trust_level = Decimal(str(round(new, 3)))

    # Payment disputes disabled — scope creep (deadline failures) is the primary RAT mechanic.

    db.flush()

    # Check bankruptcy
    company = db.query(Company).filter(Company.id == company_id).one()
    bankrupt = company.funds_cents < 0

    return TaskCompleteResult(
        task_id=task_id,
        success=success,
        grade=grade,
        reward_multiplier=reward_mult,
        funds_delta=funds_delta,
        listed_reward=task.advertised_reward_cents or task.reward_funds_cents,
        prestige_changes=prestige_changes,
        trust_delta=trust_delta,
        bankrupt=bankrupt,
    )
