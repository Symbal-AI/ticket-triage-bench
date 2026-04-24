from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..config.sampling import sample_from_spec
from ..config.schema import WorldConfig
from ..db.models.company import Domain
from ..db.models.task import TicketType, CVESeverity
from .rng import RngStreams, sample_without_replacement


@dataclass(frozen=True)
class GeneratedTask:
    title: str
    required_prestige: int
    reward_funds_cents: int
    reward_prestige_delta: float
    skill_boost_pct: float
    status: str
    company_id: Any | None
    accepted_at: datetime | None
    deadline: datetime | None
    completed_at: datetime | None
    success: bool | None
    progress_milestone_pct: int
    requirements: dict[str, int]
    client_index: int = 0
    required_trust: int = 0
    ticket_type: str = "feature_request"
    cve_severity: str | None = None
    time_to_breach_hours: int | None = None
    employee_index: int | None = None
    technical_debt_delta: int = 0
    cve_metadata: dict | None = None


# First 10 market tasks are forced to prestige 1 to guarantee a
# bootstrapping path regardless of the prestige distribution.
_STRATIFIED_PRESTIGE = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]

_ALL_DOMAINS = list(Domain)


def _sample_required_prestige(rng, cfg, index=None):
    if index is not None and index < len(_STRATIFIED_PRESTIGE):
        return _STRATIFIED_PRESTIGE[index]
    return int(sample_from_spec(rng, cfg.dist.required_prestige))


def _sample_reward_funds_cents(rng, cfg, prestige=1):
    base = int(sample_from_spec(rng, cfg.dist.reward_funds_cents))
    # Scale reward by prestige: higher-prestige tasks pay proportionally more
    return int(base * (1 + cfg.reward_prestige_scale * (prestige - 1)))


def _sample_reward_prestige_delta(rng, cfg):
    return sample_from_spec(rng, cfg.dist.reward_prestige_delta)


def _sample_skill_boost_pct(rng, cfg):
    return sample_from_spec(rng, cfg.dist.skill_boost)


def _sample_domain_count(rng, cfg):
    return int(sample_from_spec(rng, cfg.dist.domain_count))


def _sample_required_qty(rng, cfg):
    return int(sample_from_spec(rng, cfg.dist.required_qty))


def _sample_domains_with_bias(rng, k, specialty_domains=None, specialty_bias=0.7):
    """Sample k domains, biased toward client specialties.

    First domain pick: specialty_bias chance of being a specialty (if specialties exist).
    Remaining picks: uniform random from remaining domains.
    """
    if not specialty_domains or k <= 0:
        return sample_without_replacement(rng, _ALL_DOMAINS, k)

    picked = []
    available = list(_ALL_DOMAINS)

    # First pick: specialty bias
    specialty_enums = [d for d in _ALL_DOMAINS if d.value in specialty_domains]
    if specialty_enums and rng.random() < specialty_bias:
        first = rng.choice(specialty_enums)
    else:
        first = rng.choice(available)
    picked.append(first)
    available.remove(first)

    # Remaining picks: uniform random
    if k > 1 and available:
        remaining = sample_without_replacement(
            rng, available, min(k - 1, len(available))
        )
        picked.extend(remaining)

    return picked


def _sample_requirements(rng, cfg, prestige=1, specialty_domains=None):
    k = _sample_domain_count(rng, cfg)
    picked_domains = _sample_domains_with_bias(
        rng,
        k,
        specialty_domains=specialty_domains,
        specialty_bias=cfg.task_specialty_domain_bias,
    )
    scale = 1 + cfg.prestige_qty_scale * (prestige - 1)
    return {
        domain: int(_sample_required_qty(rng, cfg) * scale) for domain in picked_domains
    }


def _required_trust_from_reward(rng, cfg, reward_cents):
    """Premium tasks require established client trust.

    Clients don't hand their best projects to unproven vendors.
    Low-reward tasks are open to everyone; high-reward tasks require
    progressively more trust, reflecting how real client relationships
    work (prove yourself on small jobs before getting big ones).
    """
    # Normalize reward into 0-1 range using the distribution bounds
    reward_floor = getattr(cfg.dist.reward_funds_cents, "low", 300_000)
    reward_ceiling = getattr(cfg.dist.reward_funds_cents, "high", 4_000_000)
    if reward_cents <= reward_floor:
        return 0

    reward_frac = min(
        1.0, (reward_cents - reward_floor) / (reward_ceiling - reward_floor)
    )

    # Only premium tasks (top portion) require trust.
    trust_prob = max(
        0.0, (reward_frac - cfg.trust_reward_threshold) / cfg.trust_reward_ramp
    )
    if rng.random() >= trust_prob:
        return 0

    # Trust level required: 1 at threshold, up to max for top tasks
    return max(
        1,
        min(
            int(1 + reward_frac * cfg.trust_level_reward_scale),
            cfg.trust_level_max_required,
        ),
    )


def _sample_cve_severity(rng):
    """Sample CVE severity with distribution weighted toward less critical."""
    weights = {
        CVESeverity.CRITICAL: 0.05,
        CVESeverity.HIGH: 0.15,
        CVESeverity.MEDIUM: 0.35,
        CVESeverity.LOW: 0.45,
    }
    choices = list(weights.keys())
    probs = [weights[c] for c in choices]
    return rng.choices(choices, weights=probs, k=1)[0]


def _calculate_time_to_breach(severity, rng):
    """Calculate time to breach in hours based on CVE severity."""
    # Base time to breach (in hours) by severity
    base_times = {
        CVESeverity.CRITICAL: (24, 72),      # 1-3 days
        CVESeverity.HIGH: (72, 168),         # 3-7 days
        CVESeverity.MEDIUM: (168, 336),      # 7-14 days
        CVESeverity.LOW: (336, 720),         # 14-30 days
    }
    min_hours, max_hours = base_times[severity]
    return int(rng.uniform(min_hours, max_hours))


def _sample_tech_debt_reduction(rng, cfg):
    """Sample amount of technical debt reduced by cleanup task."""
    # Tech debt cleanup tasks remove between 500-5000 units of debt
    return int(rng.uniform(500, 5000))


def _make_task(rng, cfg, prestige, serial, requirements, client_index=0):
    reward = _sample_reward_funds_cents(rng, cfg, prestige=prestige)
    required_trust = _required_trust_from_reward(rng, cfg, reward)
    if required_trust > 0:
        reward = int(reward * (1.0 + cfg.trust_gated_reward_boost * required_trust))
    return GeneratedTask(
        title=f"Task-{serial}",
        required_prestige=prestige,
        reward_funds_cents=reward,
        reward_prestige_delta=_sample_reward_prestige_delta(rng, cfg),
        skill_boost_pct=_sample_skill_boost_pct(rng, cfg),
        status="market",
        company_id=None,
        accepted_at=None,
        deadline=None,
        completed_at=None,
        success=None,
        progress_milestone_pct=0,
        requirements=requirements,
        client_index=client_index,
        required_trust=required_trust,
        ticket_type="feature_request",
        technical_debt_delta=0,
    )


def _make_cve_ticket(rng, cfg, prestige, serial, requirements, tech_stack=None):
    """Generate a CVE (security vulnerability) ticket."""
    from .cve_content import build_cve_metadata

    severity = _sample_cve_severity(rng)
    time_to_breach = _calculate_time_to_breach(severity, rng)

    title = f"CVE-{serial}"
    metadata = build_cve_metadata(
        rng,
        cve_id=title,
        true_severity=severity.value,
        tech_stack=tech_stack,
    )

    # CVEs don't pay, but failing to fix them causes major problems
    return GeneratedTask(
        title=title,
        required_prestige=prestige,
        reward_funds_cents=0,
        reward_prestige_delta=0.0,
        skill_boost_pct=0.0,
        status="market",
        company_id=None,
        accepted_at=None,
        deadline=None,
        completed_at=None,
        success=None,
        progress_milestone_pct=0,
        requirements=requirements,
        client_index=0,
        required_trust=0,
        ticket_type="cve",
        cve_severity=severity.value,
        time_to_breach_hours=time_to_breach,
        technical_debt_delta=0,
        cve_metadata=metadata,
    )


def _make_tech_debt_ticket(rng, cfg, prestige, serial, requirements, employee_index=0):
    """Generate a technical debt cleanup ticket."""
    debt_reduction = _sample_tech_debt_reduction(rng, cfg)
    
    # Tech debt tickets have small rewards but reduce accumulated debt
    return GeneratedTask(
        title=f"TechDebt-{serial}",
        required_prestige=max(1, prestige - 1),  # Slightly lower prestige requirement
        reward_funds_cents=0,  # No direct payment
        reward_prestige_delta=0.1,  # Small prestige boost
        skill_boost_pct=0.0,
        status="market",
        company_id=None,
        accepted_at=None,
        deadline=None,
        completed_at=None,
        success=None,
        progress_milestone_pct=0,
        requirements=requirements,
        client_index=0,
        required_trust=0,
        ticket_type="tech_debt",
        employee_index=employee_index,
        technical_debt_delta=-debt_reduction,  # Negative = reduces debt
    )


def generate_tasks(
    *, run_seed, count, cfg, client_specialties=None, client_reward_mults=None, num_employees=10,
    tech_stack=None,
):
    """Generate market tasks with mix of ticket types.

    Generates:
    - 60% Feature Requests (from clients)
    - 25% Tech Debt cleanup (from employees)
    - 15% CVEs (random security issues)

    Args:
        client_specialties: list of specialty domain lists, one per client index.
            e.g. [["research", "training"], ["inference"]] for 2 clients.
        client_reward_mults: list of reward multipliers per client index.
            Task rewards are scaled by the client's multiplier.
        num_employees: number of employees for tech debt ticket assignment.
        tech_stack: the company's tech stack dict. Passed to CVE generation so
            rich CVE metadata can reference the company's languages/frameworks.
    """
    if count <= 0:
        return []

    streams = RngStreams(run_seed)
    num_clients = cfg.num_clients if cfg.num_clients > 0 else 1
    out = []
    
    for idx in range(1, count + 1):
        rng = streams.stream(f"task_{idx}")
        prestige = _sample_required_prestige(rng, cfg, index=idx - 1)
        
        # Determine ticket type: 60% feature, 25% tech debt, 15% CVE
        ticket_roll = rng.random()
        
        if ticket_roll < 0.60:  # Feature request
            client_index = (idx - 1) % num_clients
            spec_domains = (
                client_specialties[client_index % len(client_specialties)]
                if client_specialties
                else None
            )
            requirements = _sample_requirements(
                rng, cfg, prestige=prestige, specialty_domains=spec_domains
            )
            task = _make_task(
                rng,
                cfg,
                prestige,
                serial=idx,
                requirements=requirements,
                client_index=client_index,
            )
            # Apply client reward multiplier
            if client_reward_mults and client_index < len(client_reward_mults):
                mult = client_reward_mults[client_index]
                new_reward = int(task.reward_funds_cents * mult)
                task = GeneratedTask(**{**task.__dict__, "reward_funds_cents": new_reward})
                
        elif ticket_roll < 0.85:  # Tech debt cleanup
            requirements = _sample_requirements(
                rng, cfg, prestige=max(1, prestige - 1), specialty_domains=None
            )
            employee_index = (idx - 1) % num_employees
            task = _make_tech_debt_ticket(
                rng,
                cfg,
                prestige,
                serial=idx,
                requirements=requirements,
                employee_index=employee_index,
            )
            
        else:  # CVE
            # CVEs typically have smaller requirements (urgent fixes)
            k = min(_sample_domain_count(rng, cfg), 2)  # Max 2 domains for CVEs
            picked_domains = sample_without_replacement(rng, _ALL_DOMAINS, k)
            requirements = {
                domain: int(_sample_required_qty(rng, cfg) * 0.5)  # Half the size
                for domain in picked_domains
            }
            task = _make_cve_ticket(
                rng,
                cfg,
                prestige,
                serial=idx,
                requirements=requirements,
                tech_stack=tech_stack,
            )
        
        out.append(task)
    return out


def build_task_rows(*, run_seed, count, cfg):
    generated = generate_tasks(run_seed=run_seed, count=count, cfg=cfg)
    task_rows = []
    requirement_rows = []

    for task in generated:
        task_rows.append(
            {
                "title": task.title,
                "required_prestige": task.required_prestige,
                "reward_funds_cents": task.reward_funds_cents,
                "reward_prestige_delta": task.reward_prestige_delta,
                "skill_boost_pct": task.skill_boost_pct,
                "status": task.status,
                "company_id": task.company_id,
                "accepted_at": task.accepted_at,
                "deadline": task.deadline,
                "completed_at": task.completed_at,
                "success": task.success,
                "progress_milestone_pct": task.progress_milestone_pct,
                "client_index": task.client_index,
                "required_trust": task.required_trust,
                "ticket_type": task.ticket_type,
                "cve_severity": task.cve_severity,
                "time_to_breach_hours": task.time_to_breach_hours,
                "employee_index": task.employee_index,
                "technical_debt_delta": task.technical_debt_delta,
            }
        )
        for domain, qty in task.requirements.items():
            requirement_rows.append(
                {
                    "_task_title": task.title,
                    "domain": domain,
                    "required_qty": qty,
                    "completed_qty": 0,
                }
            )
    return task_rows, requirement_rows


def generate_replacement_task(
    *,
    run_seed,
    replenish_counter,
    replaced_prestige,
    replaced_client_index=0,
    cfg,
    specialty_domains=None,
):
    """Generate a replacement task with the same prestige and client as the accepted task."""
    streams = RngStreams(run_seed)
    rng = streams.stream(f"replenish_{replenish_counter}")
    requirements = _sample_requirements(
        rng, cfg, prestige=replaced_prestige, specialty_domains=specialty_domains
    )
    return _make_task(
        rng,
        cfg,
        replaced_prestige,
        serial=replenish_counter,
        requirements=requirements,
        client_index=replaced_client_index,
    )


__all__ = [
    "build_task_rows",
    "generate_replacement_task",
    "generate_tasks",
    "GeneratedTask",
]
