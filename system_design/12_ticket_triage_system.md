# Ticket Triage System

**New design for YC-Bench**: Transform from startup CEO simulator to ticket triage agent benchmark.

## Overview

Agents triage and resolve tickets for a software project, managing three distinct types of work. **Revenue model**: Clients pay quarterly retainer fees, with small completion bonuses for delivered features.

1. **Feature Requests** - Client-submitted features with strict deadlines (10% completion bonus)
2. **Technical Debt** - Developer-submitted cleanup tasks (no direct payment)
3. **CVEs** - Random security vulnerabilities with breach timelines (no payment)

## Ticket Types

### Feature Requests (60% of tickets)

**Source**: Clients submit feature requests
**Characteristics**:

- Have strict deadlines based on task complexity
- Pay 10% completion bonus (retainer covers the rest)
- Award prestige on success
- Every completed feature = merged PR = adds technical debt (~10% of work quantity)

**Failure consequences**:

- Client's `failed_features_count` increments
- At contract renewal, clients with >3 failed features likely won't renew
- Prestige penalty
- Trust penalty with that client

### Technical Debt Cleanup (25% of tickets)

**Source**: Developers (employees) submit cleanup requests
**Characteristics**:

- Lower prestige requirements than feature requests
- No direct monetary reward
- Small prestige boost (+0.1) on completion
- Reduces `technical_debt` by 500-5000 units on completion

**Purpose**:

- Counterbalances debt accumulation from feature merges
- Essential for maintaining development velocity
- Each ticket is "from" a specific employee

### CVEs (15% of tickets)

**Source**: Random generation (appear in marketplace)
**Characteristics**:

- Severity levels: CRITICAL, HIGH, MEDIUM, LOW
- No monetary reward
- `time_to_breach` countdown starts when accepted:
  - CRITICAL: 1-3 days
  - HIGH: 3-7 days
  - MEDIUM: 7-14 days
  - LOW: 14-30 days

**Success**: CVE is patched, no consequences

**Failure** (breach occurs):

1. CVE status → `SECURITY_BREACH`
2. Company `security_breach_count` increments
3. All clients' `security_breach_exposure_count` increments
4. Lawsuit event scheduled with probability:
   - CRITICAL: 80%
   - HIGH: 50%
   - MEDIUM: 20%
   - LOW: 5%

## Technical Debt System

### Accumulation

- Every completed feature request adds debt: `debt += task_work_qty * 0.10`
- Debt accumulates indefinitely if not addressed

### Impact

- Technical debt slows feature development (not CVEs or tech debt cleanup)
- Slowdown formula: `rate_multiplier = 1.0 - min(0.5, debt / 100000)`
- At 100k debt units, features take 50% longer to complete
- Applied during progress calculation in `flush_progress()`

### Reduction

- Only reduced by completing tech debt cleanup tickets
- Each cleanup ticket removes 500-5000 units

## Contract Renewal System

### Contract Structure

- Each client has a 3-month contract (90 days)
- `ClientContract` tracks: start, end, active status, renewal status
- Initial contracts created during world seeding
- Renewal check events scheduled at contract end

### Renewal Decision

Evaluated at contract end based on:

```python
renewal_score = 1.0
renewal_score -= min(0.8, failed_features * 0.2)      # -20% per failed feature
renewal_score -= min(0.5, security_exposures * 0.15)   # -15% per breach exposure

renewed = renewal_score > 0.5  # with some randomness
```

**If renewed**:

- Reset `failed_features_count` and `security_breach_exposure_count` to 0
- Extend contract by 90 days
- Schedule next renewal check event

**If not renewed**:

- Contract marked inactive
- Client stops offering new feature requests
- Lost revenue stream for remainder of simulation

## Payment Model

### Quarterly Retainer Fees

**Primary revenue source**: Clients pay retainer fees every 3 months

- Base retainer: $50,000 per quarter
- Scaled by client tier (`reward_multiplier`): 0.8x - 1.5x
- Typical range: $40,000 - $75,000 per quarter per client
- Payment events scheduled at contract start and each renewal

### Completion Bonuses

**Secondary revenue**: Small bonuses for delivered work

- Feature requests: 10% of listed task value
- Technical debt cleanup: No payment (internal work)
- CVEs: No payment (security maintenance)

### Income Sources

```
Total Revenue = (Active Contracts × Quarterly Retainer) + (Completed Features × 10% Bonus)
```

**Strategic implications**:
- Retainers provide stable baseline income
- Feature bonuses encourage quality delivery
- Contract renewals are critical (losing a contract = losing recurring revenue)
- Failed features and security breaches risk contract non-renewal

## Security & Lawsuits

### Breach Mechanics

1. CVE ticket accepted → security breach event scheduled at `accepted_at + time_to_breach_hours`
2. If CVE completed before breach time → breach event is skipped
3. If breach event fires:
   - Task status → `SECURITY_BREACH`
   - Company and all clients track exposure
   - Lawsuit may be filed

### Lawsuit Costs

- CRITICAL: $100,000
- HIGH: $50,000
- MEDIUM: $20,000
- LOW: $5,000

Deducted from company funds, may trigger bankruptcy.

## Event Types

New events added to `EventType`:

- `CVE_GENERATED` - (future) periodic CVE generation
- `SECURITY_BREACH` - unpatched CVE breaches
- `LAWSUIT_FILED` - lawsuit from breach
- `CONTRACT_RENEWAL_CHECK` - client contract renewal decision
- `CONTRACT_PAYMENT` - quarterly retainer payment from client

## Database Schema Changes

### Task Model

**New fields**:

- `ticket_type` - enum: feature_request | tech_debt | cve
- `cve_severity` - enum: critical | high | medium | low (nullable)
- `time_to_breach_hours` - int (nullable)
- `breached_at` - timestamp (nullable)
- `technical_debt_delta` - int (negative for cleanup tickets)
- `employee_id` - FK to employee (for tech debt tickets)

**New status**:

- `SECURITY_BREACH` - CVE that breached

### Company Model

**New fields**:

- `technical_debt` - bigint (accumulated debt units)
- `security_breach_count` - bigint (total breaches)

### Client Model

**New fields**:

- `failed_features_count` - int (failures since last renewal)
- `security_breach_exposure_count` - int (active breaches affecting client)

### ClientContract Model (NEW)

- `company_id` - FK
- `client_id` - FK
- `contract_start` - timestamp
- `contract_end` - timestamp
- `contract_value_cents` - bigint (quarterly retainer amount in cents)
- `active` - boolean
- `renewed` - boolean

## Agent Interface Changes

### Updated Commands

**`company status`** - now shows:

- `technical_debt` - current debt level
- `security_breach_count` - total breaches
- `risk.active_cves` - count of accepted but unfixed CVEs

**`market browse`** - now shows per ticket:

- `ticket_type` - feature_request | tech_debt | cve
- `employee_name` - for tech debt tickets
- `cve_severity` - for CVE tickets
- `time_to_breach_hours` - for CVE tickets
- `technical_debt_delta` - for tech debt tickets

## Strategy Implications

Agents must balance:

1. **Contracts** - Quarterly retainers are main revenue; must keep clients happy
2. **Velocity** - Must manage tech debt to maintain dev speed
3. **Security** - CVEs are unpaid but breaches risk contract non-renewals
4. **Bonuses** - Feature completions add 10% bonus income

Optimal strategy likely involves:

- Prioritizing critical CVEs immediately (breach = client exposure = renewal risk)
- Regular tech debt cleanup to prevent velocity loss
- Careful feature selection to meet deadlines (>3 failures = contract lost)
- Managing client relationships to ensure renewals (recurring revenue)

**Key insight**: Losing a contract means losing quarterly retainer payments for the rest of the simulation, making contract renewals more important than individual task bonuses.

## Performance Metrics

Success can be measured by:

- **Financial**: Funds at horizon end (as before)
- **Client retention**: Number of active contracts at end
- **Security**: Total breach count, lawsuit costs
- **Velocity**: Technical debt level over time
- **Completion rate**: Features completed vs. failed per client
