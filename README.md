# <img src="imgs/yc_bench.png" alt="YC-Bench logo" width="40" /> Ticket Triage Bench

[![Website](https://img.shields.io/badge/Website-YC--Bench-E8864A)](https://collinear-ai.github.io/yc-bench/)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

A long-horizon deterministic benchmark for LLM agents managing ticket triage for a software project. The agent triages and resolves three types of tickets — client feature requests, technical debt cleanup, and security vulnerabilities (CVEs) — over a one-year horizon through a CLI interface backed by SQLite.

The benchmark tests whether agents can balance competing priorities: client contract renewals, accumulating technical debt, and critical security patches — sustained over hundreds of turns.

<p align="center">
  <img src="docs/static/images/system_architecture.png" alt="Ticket Triage Bench System Architecture" width="800" />
</p>

## How it works

### Core loop

1. Agent calls `sim resume` to advance the clock to the next event (task checkpoint, payroll, security breach, contract renewal, or horizon end).
2. The engine processes task progress, fires due events, and deducts monthly payroll.
3. Agent receives a status summary with events since the last turn, then issues observe and act commands.
4. Repeat until bankruptcy (funds < 0) or the one-year horizon ends.

Between time advances, the agent may issue arbitrarily many actions within a single turn. Work progresses only during business hours (weekdays), and payroll is deducted on the first business day of each month.

### Key mechanics

#### Ticket Types

- **Feature Requests** (60% of tickets): From clients with strict deadlines. Success = merged PR (which adds technical debt). Failure = client tracks missed features, may not renew contract.
- **Technical Debt Cleanup** (25% of tickets): Submitted by developers. Reduce accumulated technical debt. No direct payment but small prestige boost.
- **CVEs** (15% of tickets): Security vulnerabilities with severity levels (CRITICAL/HIGH/MEDIUM/LOW). Have a time-to-breach countdown. If not fixed in time:
  - Become security breaches
  - Affect all clients (exposure count increases)
  - May trigger lawsuits (probability based on severity)
  - Can cause clients to not renew contracts

#### Technical Debt

- Every merged PR (completed feature request) adds ~10% of work quantity as technical debt
- Accumulated technical debt slows down feature development (up to 50% slowdown at 100k debt units)
- Tech debt cleanup tickets reduce the debt pool

#### Payment Model

- **Quarterly Retainers**: Clients pay retainer fees every 3 months ($40k-$75k per client based on tier)
- **Completion Bonuses**: Feature requests pay 10% of listed value as delivery bonus
- **Strategic Impact**: Retainers are the main revenue source; losing a contract = losing recurring revenue

#### Client Contracts

- Clients have 3-month contracts that come up for renewal
- Renewal decisions based on:
  - Failed features count (>3 failures = likely non-renewal)
  - Security breach exposure (each breach reduces renewal chance by 15%)
  - Overall performance score
- Lost contracts mean losing that client's quarterly retainer payments

#### Security & Lawsuits

- Unpatched CVEs breach after time-to-breach expires (based on severity)
- Security breaches have lawsuit probability:
  - CRITICAL: 80% chance
  - HIGH: 50% chance
  - MEDIUM: 20% chance
  - LOW: 5% chance
- Lawsuit costs range from $5k (LOW) to $100k (CRITICAL)

#### Employees & Domains

The agent manages employees across 4 technical domains — `training · inference · research · data engineering`. Each employee has per-domain productivity levels. Successful completions grant productivity boosts and salary bumps. Payroll grows monotonically.

#### Client Trust & Prestige

- Completing tasks for a client builds trust, which unlocks higher-tier tasks
- Higher prestige unlocks higher-reward tasks and scales payouts
- Failing deadlines incurs prestige penalties

### Agent CLI

All commands return JSON. The agent interacts via `run_command("yc-bench <cmd>")`.

| Category | Command                                 | Effect                                       |
| -------- | --------------------------------------- | -------------------------------------------- |
| Observe  | `company status`                        | Funds, prestige, payroll                     |
| Observe  | `employee list`                         | Names, tiers, salaries, productivity         |
| Observe  | `market browse`                         | Available tasks with client, reward, domains |
| Observe  | `task list`                             | Accepted tasks with status and progress      |
| Observe  | `task inspect --task-id T`              | Per-domain progress, deadline, assignments   |
| Observe  | `client list`                           | Client trust levels and tiers                |
| Observe  | `client history`                        | Per-client success/failure counts            |
| Observe  | `client contracts`                      | Active contracts with quarterly retainers    |
| Observe  | `finance ledger`                        | Full transaction history                     |
| Task     | `task accept --task-id T`               | Accept from market; starts deadline          |
| Task     | `task assign --task-id T --employees E` | Assign employees to task                     |
| Task     | `task dispatch --task-id T`             | Begin work on assigned task                  |
| Task     | `task cancel --task-id T --reason R`    | Abandon task; prestige penalty               |
| Sim      | `sim resume`                            | Advance clock to next event                  |
| Memory   | `scratchpad write --content C`          | Overwrite persistent notes                   |
| Memory   | `scratchpad append --content C`         | Append to persistent notes                   |

---

## Setup

### Prerequisites

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv)

### Install

```bash
git clone https://github.com/collinear-ai/yc-bench.git
cd yc-bench
uv sync
```

### API key

```bash
# .env  (any LiteLLM-compatible provider)
ANTHROPIC_API_KEY="sk-ant-..."     # for anthropic/claude-*
GEMINI_API_KEY="AIza..."           # for gemini/gemini-*
OPENROUTER_API_KEY="sk-or-v1-..."  # for openrouter/*
OPENAI_API_KEY="sk-..."            # for openai/*
```

### Run

```bash
uv run yc-bench run \
  --model gemini/gemini-3-flash-preview \
  --seed 1 \
  --config default
```

Outputs a SQLite DB in `db/` and a JSON rollout in `results/`.

### Run multiple models in parallel

```bash
bash scripts/run_benchmark.sh --seeds "1 2 3" --config default
```

---

## Configuration

Experiment presets live in `src/yc_bench/config/presets/` as TOML files. Pass the preset name via `--config`.

See `default.toml` for the full list of tunable parameters.

---

## Benchmark results

<p align="center">
  <img src="docs/static/images/funds_averaged_main.png" alt="Average funds over time" width="700" />
</p>

---

Please cite our work if you find it useful!

```bibtex
@misc{collinear-ai2025ycbench,
  author    = {He, Muyu and Jain, Adit and Kumar, Anand and Tu, Vincent and Bakshi, Soumyadeep and Patro, Sachin and Rajani, Nazneen},
  title     = {{YC-Bench}: Benchmarking {AI} Agents for Long-Term Planning and Consistent Execution},
  year      = {2025},
  howpublished = {\url{https://github.com/collinear-ai/yc-bench}},
}
```
