"""System prompt and user-message builders for the Ticket Triage Bench agent."""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are managing ticket triage for a software project. Balance three types of tickets: client feature requests, technical debt cleanup, and security vulnerabilities (CVEs).

All actions use `yc-bench` CLI commands via `run_command`. All return JSON.

## Core Workflow (repeat every turn)

**You must always have active tickets running. Every turn, follow this loop:**

1. `yc-bench market browse` — view available tickets
2. `yc-bench task accept --task-id Task-42` — accept a ticket (feature/tech debt/CVE)
3. `yc-bench task assign --task-id Task-42 --employees Emp_1,Emp_4,Emp_7` — assign developers
4. `yc-bench task dispatch --task-id Task-42` — start work
5. `yc-bench sim resume` — advance to next event

Run multiple tickets concurrently when possible. Accept → assign → dispatch multiple tickets before calling sim resume.

**Use `yc-bench scratchpad write`** to save strategy notes — your conversation history is truncated after 20 turns, but scratchpad persists. Track CVE deadlines, tech debt levels, and client contract status.

## Ticket Types

### Feature Requests (60% of tickets, `ticket_type: "feature_request"`)
- **Source**: Clients submit feature requests
- **Reward**: Pay money on successful completion
- **Deadline**: Strict — completion after deadline = FAILURE
- **Success**: Adds technical debt (~10% of work quantity)
- **Failure**: Client's failed_features_count increases → may not renew contract

### Technical Debt Cleanup (25% of tickets, `ticket_type: "tech_debt"`)
- **Source**: Developers submit cleanup requests
- **Reward**: No payment, small prestige boost (+0.1)
- **Purpose**: Reduces accumulated technical_debt
- **Impact**: Tech debt slows feature development (up to 50% at 100k debt)

### CVEs (15% of tickets, `ticket_type: "cve"`)
- **Source**: Security vulnerabilities appear randomly
- **Severity**: CRITICAL/HIGH/MEDIUM/LOW
- **Time to breach**: Countdown timer (CRITICAL: 1-3 days, LOW: 14-30 days)
- **Success**: Patch applied, no consequences
- **Failure**: Security breach occurs → affects all clients → may trigger lawsuit
  - Lawsuit costs: CRITICAL=$100k, HIGH=$50k, MEDIUM=$20k, LOW=$5k
  - Clients track breach exposure → reduces contract renewal likelihood

## Key Mechanics

#### Payment Model: Retainer Contracts

- **Retainer payments**: Clients pay every 3 months (at contract start/renewal)
  - Payment amount based on client tier ($50k-$150k/quarter)
  - Main revenue source - not individual task payments
- **Completion bonuses**: Feature requests pay small bonuses (10% of listed value) on successful completion
- **Contracts renew quarterly** based on performance:
  - >3 failed features → likely non-renewal (-20% per failure)
  - Security breach exposures → reduced renewal chance (-15% per breach)
  - Lost contracts = lost retainer revenue stream

#### Ticket Types

- **Feature Requests** (60% of tickets, `ticket_type: "feature_request"`)
  - **Source**: Clients submit feature requests
  - **Reward**: Small completion bonus (10% of listed value), scaled by on-time grade
  - **Deadline grace curve** (mirrors real-world slippage tolerance):
    - On time → 100% reward, full prestige/trust gain (grade `on_time`)
    - ≤24h late → 80% reward, 80% prestige/trust gain (grade `late_24h`)
    - ≤72h late → 50% reward, 50% prestige/trust gain (grade `late_72h`)
    - >72h late → 0 reward, prestige/trust penalty, counts as failure (grade `failed`)
  - **Only `failed` grade** increments client's `failed_features_count` (affects renewal)
  - **Success** (grades on_time/late_24h/late_72h): Adds technical debt (~10% of work quantity)

- **Technical Debt Cleanup** (25% of tickets, `ticket_type: "tech_debt"`)
  - **Source**: Developers submit cleanup requests
  - **Reward**: No payment, small prestige boost (+0.1)
  - **Purpose**: Reduces accumulated technical_debt
  - **Impact**: Tech debt slows feature development (up to 50% at 100k debt)

- **CVEs** (15% of tickets, `ticket_type: "cve"`)
  - **Source**: Security vulnerabilities appear randomly
  - **Severity**: CRITICAL/HIGH/MEDIUM/LOW (may be hidden — see reasoning note below)
  - **Time to breach**: Countdown timer (CRITICAL: 1-3 days, LOW: 14-30 days) — may be hidden
  - **Rich metadata** (`cve_metadata`): every CVE now carries a description, CWE
    category, CVSS-style vector (attack_vector, attack_complexity, privileges_required,
    user_interaction_required, confidentiality/integrity/availability impacts,
    exploit_available), and exposure flags (`affects_language`,
    `affects_framework`, `requires_internet_exposure`, `targets_data_type`).
  - **Company tech stack** (`yc-bench company tech-stack`): languages, frameworks,
    data stores, externally-exposed surfaces, and data types handled. A CVE that
    names a language your company doesn't use is far less urgent than one that
    hits your primary framework on an internet-facing surface.
  - **Reasoning pattern**: combine the CVSS vector (how exploitable) + CWE
    (what kind of damage) + exposure flags (does it touch OUR stack?) +
    internet-exposure overlap to decide real urgency. Pattern-matching on any
    single field will miss cases (a CRITICAL CVE in a Java package we don't
    use is low real risk; a MEDIUM CVE in our primary internet-facing
    framework is high real risk).
  - **Breach timer runs from first appearance in the market, NOT from acceptance.**
    Ignoring a CVE doesn't protect you — it breaches on schedule whether you
    accepted it or not. Accepting and completing a CVE before its breach time
    is how you *prevent* the breach.
  - **Success**: Patch applied before the timer fires → breach event is skipped.
  - **Failure**: Security breach occurs → affects all clients → may trigger lawsuit
    - Lawsuit costs: CRITICAL=$100k, HIGH=$50k, MEDIUM=$20k, LOW=$5k
    - Clients track breach exposure → reduces contract renewal likelihood

#### Other Mechanics

- **Technical Debt**: Every merged PR (completed feature) adds debt. Accumulated debt slows features (not CVEs/tech debt).
  - At 100k debt: features take 50% longer
  - Cleanup tickets reduce debt by 500-5000 units each
  
- **CVE Time-to-Breach**: Starts when accepted, not when generated
  - If fixed before breach: no consequences
  - If breached: triggers security breach event → affects all clients
  
- **Payroll**: Deducted monthly. Funds < 0 = bankruptcy.

- **Employee throughput split**: employees on multiple tasks split their rate (rate/N).

- **Contractor hiring**: You can hire short-term contractors in one domain when capacity is tight.
  - `yc-bench employee hire-contractor --domain <d> --weeks <n>` (1-12 weeks, max 2 active at once)
  - Paid upfront (mid-tier monthly salary × weeks/4 × 1.5). No ongoing payroll.
  - Productive only in their hired domain. Auto-retires at term end (rate → 0).

## Strategy Tips

- **Protect retainer revenue**: Lost contracts = lost quarterly payments
- **Prioritize CVEs by severity**: CRITICAL/HIGH CVEs should be top priority
- **Manage tech debt**: Regular cleanup prevents velocity loss on features
- **Balance client deadlines**: Missing too many features loses clients
- **Watch contract renewals**: Check client history for at-risk relationships

## Commands

### Observe
- `yc-bench company status` — funds, technical_debt, security_breach_count, payroll, active_cves
- `yc-bench company tech-stack` — languages, frameworks, data stores, exposed surfaces, data handled
- `yc-bench employee list` — developers with skill rates per domain
- `yc-bench market browse` — available tickets (shows ticket_type, cve_severity, time_to_breach_hours, etc.)
- `yc-bench task list [--status X]` — your tickets
- `yc-bench task inspect --task-id Task-42` — ticket details
- `yc-bench client list` — clients with trust levels and contract status
- `yc-bench client history` — per-client success/failure rates
- `yc-bench client contracts` — active contracts with quarterly retainer values
- `yc-bench finance ledger` — financial history

### Act
- `yc-bench task accept --task-id Task-42` — accept ticket from market
- `yc-bench task assign --task-id Task-42 --employees Emp_1,Emp_4` — assign developers
- `yc-bench task dispatch --task-id Task-42` — start work
- `yc-bench task cancel --task-id Task-42 --reason "text"` — cancel (prestige penalty)
- `yc-bench employee hire-contractor --domain research --weeks 4` — hire contractor (costs upfront cash)
- `yc-bench sim resume` — advance time
- `yc-bench scratchpad write --content "text"` — save notes
- `yc-bench scratchpad append --content "text"` — append notes
"""


def build_turn_context(
    turn_number: int,
    sim_time: str,
    horizon_end: str,
    funds_cents: int,
    active_tasks: int,
    planned_tasks: int,
    employee_count: int,
    monthly_payroll_cents: int,
    bankrupt: bool,
    last_wake_events: list | None = None,
    scratchpad: str | None = None,
) -> str:
    """Build per-turn context message injected as user input."""
    runway_months = (
        round(funds_cents / monthly_payroll_cents, 1)
        if monthly_payroll_cents > 0
        else None
    )
    runway_str = (
        f"~{runway_months} months" if runway_months is not None else "∞ (no payroll)"
    )

    history_limit = 20
    turns_until_truncation = max(0, history_limit - turn_number)

    if turns_until_truncation > 0:
        memory_note = f"Your context window holds {history_limit} turns. {turns_until_truncation} turns before oldest messages start dropping. Use scratchpad to persist important observations."
    else:
        memory_note = f"Your context window holds {history_limit} turns. Older messages have been dropped. Use scratchpad to persist important observations."

    parts = [
        f"## Turn {turn_number} — Simulation State",
        f"- **Current time**: {sim_time}",
        f"- **Horizon end**: {horizon_end}",
        f"- **Funds**: ${funds_cents / 100:,.2f} ({funds_cents} cents)",
        f"- **Monthly payroll**: ${monthly_payroll_cents / 100:,.2f}",
        f"- **Runway**: {runway_str}",
        f"- **Employees**: {employee_count}",
        f"- **Active tasks**: {active_tasks}",
        f"- **Planned tasks**: {planned_tasks}",
        f"- **Memory**: {memory_note}",
    ]

    if bankrupt:
        parts.append("\n**WARNING: Company is bankrupt. Run will terminate.**")

    if last_wake_events:
        parts.append("\n### Events since last turn:")
        for ev in last_wake_events:
            ev_type = ev.get("type", "unknown")
            if ev_type == "task_completed":
                success = ev.get("success", False)
                title = ev.get("task_title") or ev.get("task_id", "?")
                client = ev.get("client_name", "")
                client_str = f" (client: {client})" if client else ""
                funds = ev.get("funds_delta", 0)
                funds_str = f" +${funds/100:,.0f}" if success and funds else ""
                margin = ev.get("deadline_margin", "")
                margin_str = f" [{margin}]" if margin else ""
                n_emp = ev.get("employees_assigned", 0)
                bump = ev.get("salary_bump_total_cents", 0)
                bump_str = (
                    f" | {n_emp} employees, +${bump/100:,.0f}/mo payroll"
                    if bump > 0
                    else f" | {n_emp} employees" if n_emp else ""
                )
                if success:
                    parts.append(
                        f"- {title}{client_str}: SUCCESS{funds_str}{margin_str}{bump_str}"
                    )
                else:
                    parts.append(
                        f"- {title}{client_str}: FAILED — missed deadline{margin_str}, no reward"
                    )
            elif ev_type == "task_half":
                pct = ev.get("milestone_pct", "?")
                parts.append(
                    f"- Task {ev.get('task_id', '?')}: {pct}% progress reached"
                )
            elif ev_type == "payment_dispute":
                clawback = ev.get("clawback_cents", 0)
                client_name = ev.get("client_name", "unknown")
                parts.append(
                    f"- PAYMENT DISPUTE from {client_name}: -${clawback / 100:,.2f} clawed back"
                )
            elif ev_type == "security_breach":
                task_id = ev.get("task_id", "?")
                severity = ev.get("cve_severity", "unknown")
                affected = ev.get("affected_clients", 0)
                lawsuit = ev.get("lawsuit_scheduled", False)
                lawsuit_str = " | LAWSUIT INCOMING" if lawsuit else ""
                parts.append(
                    f"- ⚠️ SECURITY BREACH: {task_id} (severity: {severity.upper()}) | {affected} clients affected{lawsuit_str}"
                )
            elif ev_type == "lawsuit_filed":
                breach_id = ev.get("breach_task_id", "?")
                severity = ev.get("severity", "unknown")
                cost = ev.get("lawsuit_cost", 0)
                parts.append(
                    f"- ⚖️ LAWSUIT FILED for breach {breach_id} ({severity.upper()}): -${cost / 100:,.2f}"
                )
            elif ev_type == "contract_renewal":
                client_name = ev.get("client_name", "unknown")
                renewed = ev.get("renewed", False)
                reason = ev.get("reason", "")
                if renewed:
                    parts.append(
                        f"- ✅ Contract RENEWED: {client_name}"
                    )
                else:
                    parts.append(
                        f"- ❌ Contract NOT RENEWED: {client_name} ({reason})"
                    )
            elif ev_type == "contract_payment":
                client_name = ev.get("client_name", "unknown")
                value = ev.get("contract_value", 0)
                active = ev.get("active_contracts", 0)
                parts.append(
                    f"- 💰 Contract Payment: {client_name} +${value / 100:,.2f} ({active} active contracts)"
                )
            elif ev_type == "horizon_end":
                parts.append("- **Horizon end reached. Simulation complete.**")
            elif ev_type == "bankruptcy":
                parts.append("- **BANKRUPTCY. Simulation terminated.**")
            else:
                parts.append(f"- Event: {ev_type}")

    if active_tasks == 0 and planned_tasks == 0:
        parts.append(
            "\n**ACTION REQUIRED**: No tasks are running. "
            "Do NOT call `sim resume` — it will just burn payroll with zero revenue. "
            "Accept a task, assign employees to it, and dispatch it first."
        )
    elif planned_tasks > 0 and active_tasks == 0:
        parts.append(
            "\n**ACTION REQUIRED**: You have planned tasks but none are dispatched. "
            "Do NOT call `sim resume` yet — dispatch first or you'll just burn payroll. "
            "Assign employees and dispatch now."
        )
    else:
        parts.append(
            "\nDecide your next actions. Use `run_command` to execute CLI commands."
        )

    # Scratchpad is injected in the system prompt, not here (avoids duplication
    # across the 20-turn history window).

    return "\n".join(parts)


def build_initial_user_prompt(
    sim_time: str,
    horizon_end: str,
    funds_cents: int,
    active_tasks: int,
    planned_tasks: int,
    employee_count: int,
    monthly_payroll_cents: int,
    bankrupt: bool,
    episode: int = 1,
    scratchpad: str | None = None,
) -> str:
    """Build the one-time initial user message at run start."""
    runway_months = (
        round(funds_cents / monthly_payroll_cents, 1)
        if monthly_payroll_cents > 0
        else float("inf")
    )

    runway_months = (
        round(funds_cents / monthly_payroll_cents, 1)
        if monthly_payroll_cents > 0
        else None
    )
    runway_str = f"~{runway_months} months" if runway_months is not None else "∞"

    lines = []
    if episode > 1:
        lines.extend(
            [
                f"## Episode {episode} — Restarting After Bankruptcy",
                "",
                f"You went bankrupt in episode {episode - 1}. The simulation has been reset,",
                "but your **scratchpad notes from the previous episode are preserved**.",
                "Check your scratchpad notes for strategy from the previous episode.",
                "and learn from past mistakes before taking action.",
                "",
            ]
        )
    lines.extend(
        [
            "## Simulation Start — Take Immediate Action",
            f"- current_time: {sim_time}",
            f"- horizon_end: {horizon_end}",
            f"- funds: ${funds_cents / 100:,.2f}",
            f"- monthly_payroll: ${monthly_payroll_cents / 100:,.2f}",
            f"- runway: {runway_str}",
            f"- employees: {employee_count}",
            f"- active_tasks: {active_tasks}",
            f"- planned_tasks: {planned_tasks}",
            "",
            "**Your immediate priority**: generate revenue before payroll drains your runway.",
            "Complete these steps now (multiple commands per turn are fine):",
            "1. `yc-bench market browse` — see available tasks",
            "2. `yc-bench task accept --task-id Task-42` — accept a task",
            "3. `yc-bench task assign-all --task-id Task-42` — assign employees (or use `task assign` to pick individuals)",
            "4. `yc-bench task dispatch --task-id Task-42` — start work",
            "5. `yc-bench sim resume` — advance time",
            "",
            "**IMPORTANT**: Check each command's result before proceeding to the next.",
            "If `task accept` fails (trust or prestige too low), try a different task.",
            "Do NOT call `sim resume` unless you have at least one active task — it will skip forward with zero revenue.",
        ]
    )
    if bankrupt:
        lines.append("WARNING: company is already bankrupt at initialization.")
    return "\n".join(lines)


__all__ = ["SYSTEM_PROMPT", "build_turn_context", "build_initial_user_prompt"]
