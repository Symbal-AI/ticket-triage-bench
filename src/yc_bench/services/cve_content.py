"""Synthetic CVE content + company tech-stack generation.

The packages and CVE IDs here are fabricated. Descriptions mimic NVD language
on invented libraries so the agent reasons about the content rather than
recalling memorized real CVEs.
"""

from __future__ import annotations

from typing import Any, Dict, List


# Synthetic package names grouped by ecosystem.
_PACKAGES_BY_LANGUAGE: Dict[str, List[str]] = {
    "python": ["orbital-queue", "lumen-cache", "helix-auth-py", "vertex-router"],
    "typescript": ["spectrum-web", "prism-client-ts", "nova-forms", "echo-middleware"],
    "go": ["atlas-mesh", "cobalt-rpc", "nimbus-store"],
    "rust": ["crystal-edge", "tungsten-sync"],
    "java": ["keystone-orm", "arcade-xml-parser"],
}

_FRAMEWORKS_BY_LANGUAGE: Dict[str, List[str]] = {
    "python": ["fastapi", "django", "flask"],
    "typescript": ["express", "nextjs", "nestjs"],
    "go": ["gin", "echo"],
    "rust": ["axum", "actix-web"],
    "java": ["spring-boot", "quarkus"],
}

_DATA_STORES = ["postgres", "redis", "kafka", "s3", "elasticsearch", "mongodb"]

_EXTERNAL_SURFACES = [
    "public-api",
    "admin-console",
    "webhook-receiver",
    "customer-portal",
    "partner-integrations",
]

_DATA_CATEGORIES = [
    "user-pii",
    "payment-tokens",
    "session-keys",
    "internal-metrics",
    "audit-logs",
]


# CWE catalog with severity bias + description templates.
# The severity bias is used during sampling so the taxonomy roughly tracks
# ground-truth severity, but with noise (agent can't just pattern-match CWE to
# severity).
_CWE_CATALOG = [
    {
        "cwe": "CWE-89",
        "title_fmt": "SQL injection in {pkg}'s {component}",
        "desc_fmt": (
            "SQL injection in {pkg}'s {component}. User-controlled input flows into "
            "raw query construction without parameterization. Exploitable when the "
            "vulnerable endpoint accepts unauthenticated POST bodies."
        ),
        "components": ["query builder", "filter parser", "report generator"],
        "bias_critical": 0.20,
        "bias_high": 0.40,
        "bias_medium": 0.30,
        "bias_low": 0.10,
    },
    {
        "cwe": "CWE-79",
        "title_fmt": "Stored XSS in {pkg}'s {component}",
        "desc_fmt": (
            "Stored cross-site scripting in {pkg}'s {component}. User-submitted content "
            "is rendered back into administrative dashboards without output encoding. "
            "Exploitation requires an admin to view the attacker's content."
        ),
        "components": ["comment widget", "profile renderer", "notification feed"],
        "bias_critical": 0.05,
        "bias_high": 0.25,
        "bias_medium": 0.45,
        "bias_low": 0.25,
    },
    {
        "cwe": "CWE-22",
        "title_fmt": "Path traversal in {pkg}'s {component}",
        "desc_fmt": (
            "Path traversal in {pkg}'s {component}. File-path parameters accept "
            "unrestricted '../' sequences. Can read arbitrary files within the service's "
            "filesystem permissions."
        ),
        "components": ["file download handler", "template loader", "asset server"],
        "bias_critical": 0.10,
        "bias_high": 0.40,
        "bias_medium": 0.35,
        "bias_low": 0.15,
    },
    {
        "cwe": "CWE-502",
        "title_fmt": "Unsafe deserialization in {pkg}'s {component}",
        "desc_fmt": (
            "Unsafe deserialization in {pkg}'s {component}. Input passed through the "
            "library's decode path can trigger arbitrary class instantiation, leading "
            "to remote code execution on the host."
        ),
        "components": ["session decoder", "cache reader", "message unpacker"],
        "bias_critical": 0.55,
        "bias_high": 0.35,
        "bias_medium": 0.10,
        "bias_low": 0.00,
    },
    {
        "cwe": "CWE-287",
        "title_fmt": "Authentication bypass in {pkg} under {edge}",
        "desc_fmt": (
            "Authentication bypass in {pkg} when {edge}. A specific request shape "
            "causes the session validator to return success without verifying the "
            "token signature."
        ),
        "components": ["edge case"],
        "edges": [
            "the Authorization header contains only whitespace",
            "the user-agent string exceeds 8KB",
            "the body is a well-formed but empty JWT",
        ],
        "bias_critical": 0.50,
        "bias_high": 0.40,
        "bias_medium": 0.10,
        "bias_low": 0.00,
    },
    {
        "cwe": "CWE-918",
        "title_fmt": "Server-side request forgery in {pkg}'s {component}",
        "desc_fmt": (
            "SSRF in {pkg}'s {component}. URL parameters are fetched server-side "
            "without denylisting internal address ranges. Attackers can reach internal "
            "services and cloud metadata endpoints."
        ),
        "components": ["URL preview generator", "webhook dispatcher", "image proxy"],
        "bias_critical": 0.25,
        "bias_high": 0.50,
        "bias_medium": 0.20,
        "bias_low": 0.05,
    },
    {
        "cwe": "CWE-94",
        "title_fmt": "Code injection in {pkg} via {component}",
        "desc_fmt": (
            "Arbitrary code execution in {pkg} via {component}. Untrusted input flows "
            "into a code-evaluation sink with no sandboxing."
        ),
        "components": ["template engine", "expression evaluator", "plugin loader"],
        "bias_critical": 0.60,
        "bias_high": 0.30,
        "bias_medium": 0.10,
        "bias_low": 0.00,
    },
    {
        "cwe": "CWE-352",
        "title_fmt": "Cross-site request forgery in {pkg}",
        "desc_fmt": (
            "CSRF in {pkg}. State-changing endpoints omit origin validation and accept "
            "session cookies from third-party contexts."
        ),
        "components": ["admin actions endpoint"],
        "bias_critical": 0.00,
        "bias_high": 0.15,
        "bias_medium": 0.50,
        "bias_low": 0.35,
    },
    {
        "cwe": "CWE-400",
        "title_fmt": "Denial of service in {pkg}'s {component}",
        "desc_fmt": (
            "Resource exhaustion in {pkg}'s {component}. A malformed but small payload "
            "can trigger unbounded memory allocation or CPU loops, affecting the "
            "availability of services that depend on it."
        ),
        "components": ["regex compiler", "message parser", "batch decoder"],
        "bias_critical": 0.05,
        "bias_high": 0.20,
        "bias_medium": 0.50,
        "bias_low": 0.25,
    },
    {
        "cwe": "CWE-312",
        "title_fmt": "Sensitive data in logs from {pkg}",
        "desc_fmt": (
            "{pkg} writes {data_hint} to debug logs under certain error paths. "
            "Log access controls become the de-facto access control for that data."
        ),
        "components": ["(logging subsystem)"],
        "bias_critical": 0.05,
        "bias_high": 0.20,
        "bias_medium": 0.40,
        "bias_low": 0.35,
    },
]


def generate_tech_stack(rng) -> Dict[str, Any]:
    """Generate a company's tech stack. Called once per world seed."""
    # 1-2 languages; if 2, the second is a distinct pick
    languages = rng.sample(list(_PACKAGES_BY_LANGUAGE.keys()), k=rng.choice([1, 2]))

    frameworks: List[str] = []
    for lang in languages:
        if lang in _FRAMEWORKS_BY_LANGUAGE:
            frameworks.append(rng.choice(_FRAMEWORKS_BY_LANGUAGE[lang]))

    data_stores = rng.sample(_DATA_STORES, k=rng.choice([2, 3]))
    externally_exposed = rng.sample(_EXTERNAL_SURFACES, k=rng.choice([1, 2]))
    data_handled = rng.sample(_DATA_CATEGORIES, k=rng.choice([2, 3]))

    return {
        "languages": languages,
        "frameworks": frameworks,
        "data_stores": data_stores,
        "externally_exposed": externally_exposed,
        "data_handled": data_handled,
    }


def _sample_cwe_for_severity(rng, severity: str) -> Dict[str, Any]:
    """Pick a CWE whose bias aligns with the true severity. Noisy by design."""
    key = f"bias_{severity}"
    weights = [entry.get(key, 0.1) for entry in _CWE_CATALOG]
    # Add a floor so every CWE has a nonzero chance — keeps the signal noisy.
    weights = [max(w, 0.05) for w in weights]
    return rng.choices(_CWE_CATALOG, weights=weights, k=1)[0]


def _derive_cvss_vector(rng, severity: str) -> Dict[str, str]:
    """Sample CVSS v3-style taxonomy fields keyed to ground-truth severity.

    The distributions drift with severity but overlap — the agent has to reason
    about the COMBINATION of fields, not pattern-match any single one.
    """

    def pick(weights_by_sev):
        return rng.choices(
            list(weights_by_sev[severity].keys()),
            weights=list(weights_by_sev[severity].values()),
            k=1,
        )[0]

    attack_vector = pick(
        {
            "critical": {"network": 0.75, "adjacent": 0.15, "local": 0.08, "physical": 0.02},
            "high":     {"network": 0.55, "adjacent": 0.25, "local": 0.18, "physical": 0.02},
            "medium":   {"network": 0.30, "adjacent": 0.30, "local": 0.35, "physical": 0.05},
            "low":      {"network": 0.15, "adjacent": 0.25, "local": 0.45, "physical": 0.15},
        }
    )
    attack_complexity = pick(
        {
            "critical": {"low": 0.85, "high": 0.15},
            "high":     {"low": 0.70, "high": 0.30},
            "medium":   {"low": 0.50, "high": 0.50},
            "low":      {"low": 0.30, "high": 0.70},
        }
    )
    privileges_required = pick(
        {
            "critical": {"none": 0.70, "low": 0.25, "high": 0.05},
            "high":     {"none": 0.40, "low": 0.45, "high": 0.15},
            "medium":   {"none": 0.20, "low": 0.50, "high": 0.30},
            "low":      {"none": 0.10, "low": 0.35, "high": 0.55},
        }
    )
    user_interaction = pick(
        {
            "critical": {"none": 0.75, "required": 0.25},
            "high":     {"none": 0.60, "required": 0.40},
            "medium":   {"none": 0.40, "required": 0.60},
            "low":      {"none": 0.25, "required": 0.75},
        }
    )
    conf_impact = pick(
        {
            "critical": {"high": 0.80, "low": 0.15, "none": 0.05},
            "high":     {"high": 0.55, "low": 0.30, "none": 0.15},
            "medium":   {"high": 0.20, "low": 0.55, "none": 0.25},
            "low":      {"high": 0.05, "low": 0.35, "none": 0.60},
        }
    )
    integ_impact = pick(
        {
            "critical": {"high": 0.75, "low": 0.20, "none": 0.05},
            "high":     {"high": 0.50, "low": 0.35, "none": 0.15},
            "medium":   {"high": 0.20, "low": 0.45, "none": 0.35},
            "low":      {"high": 0.05, "low": 0.25, "none": 0.70},
        }
    )
    avail_impact = pick(
        {
            "critical": {"high": 0.60, "low": 0.30, "none": 0.10},
            "high":     {"high": 0.40, "low": 0.40, "none": 0.20},
            "medium":   {"high": 0.25, "low": 0.45, "none": 0.30},
            "low":      {"high": 0.10, "low": 0.30, "none": 0.60},
        }
    )
    exploit_available = pick(
        {
            "critical": {"weaponized": 0.35, "poc": 0.45, "none": 0.20},
            "high":     {"weaponized": 0.15, "poc": 0.50, "none": 0.35},
            "medium":   {"weaponized": 0.05, "poc": 0.35, "none": 0.60},
            "low":      {"weaponized": 0.02, "poc": 0.18, "none": 0.80},
        }
    )
    return {
        "attack_vector": attack_vector,
        "attack_complexity": attack_complexity,
        "privileges_required": privileges_required,
        "user_interaction_required": user_interaction,
        "confidentiality_impact": conf_impact,
        "integrity_impact": integ_impact,
        "availability_impact": avail_impact,
        "exploit_available": exploit_available,
    }


def _choose_package(rng, tech_stack: Dict[str, Any], relevant: bool) -> Dict[str, str]:
    """Pick an affected package + language. If `relevant`, pick one matching the
    company's stack; otherwise pick an unrelated language/package.
    """
    if tech_stack is None:
        tech_stack = {"languages": ["python"], "frameworks": []}

    company_langs = tech_stack.get("languages", [])
    company_fws = tech_stack.get("frameworks", [])
    all_langs = list(_PACKAGES_BY_LANGUAGE.keys())

    if relevant and company_langs:
        lang = rng.choice(company_langs)
    else:
        off_langs = [lg for lg in all_langs if lg not in company_langs]
        lang = rng.choice(off_langs) if off_langs else all_langs[0]

    pkg = rng.choice(_PACKAGES_BY_LANGUAGE[lang])
    # Match a framework about half the time when relevant.
    matching_frameworks = [
        fw for fw in _FRAMEWORKS_BY_LANGUAGE.get(lang, []) if fw in company_fws
    ]
    if relevant and matching_frameworks and rng.random() < 0.5:
        affects_framework = rng.choice(matching_frameworks)
    elif lang in _FRAMEWORKS_BY_LANGUAGE and rng.random() < 0.5:
        affects_framework = rng.choice(_FRAMEWORKS_BY_LANGUAGE[lang])
    else:
        affects_framework = None

    return {
        "affects_language": lang,
        "affects_framework": affects_framework,
        "package": pkg,
    }


def build_cve_metadata(
    rng,
    *,
    cve_id: str,
    true_severity: str,
    tech_stack: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Build one rich CVE entry. true_severity is the sim's ground truth."""
    cwe_entry = _sample_cwe_for_severity(rng, true_severity)
    # 55% chance the CVE actually touches the company's stack. The remainder
    # are "distractors" — CVEs in languages/frameworks the company doesn't use.
    relevant_to_stack = rng.random() < 0.55
    pkg_info = _choose_package(rng, tech_stack or {}, relevant_to_stack)

    # Build the title and description
    comp_options = cwe_entry.get("components", ["(component)"])
    edges = cwe_entry.get("edges")
    title_component = rng.choice(comp_options)
    title = cwe_entry["title_fmt"].format(
        pkg=pkg_info["package"],
        component=title_component,
        edge=rng.choice(edges) if edges else "",
    )
    data_hint_options = ["session tokens", "API keys", "user email addresses", "internal trace IDs"]
    description = cwe_entry["desc_fmt"].format(
        pkg=pkg_info["package"],
        component=title_component,
        edge=rng.choice(edges) if edges else "",
        data_hint=rng.choice(data_hint_options),
    )

    cvss = _derive_cvss_vector(rng, true_severity)

    # Exposure flags — independent signal for the agent to reason over
    company_data = (tech_stack or {}).get("data_handled", [])
    targets_data_type = (
        rng.choice(company_data) if (company_data and rng.random() < 0.45) else None
    )
    # Network-vector CVEs that touch web layers usually require internet exposure
    requires_internet_exposure = (
        cvss["attack_vector"] == "network" and rng.random() < 0.75
    )

    return {
        "cve_id": cve_id,
        "title": title,
        "description": description,
        "cwe_category": cwe_entry["cwe"],
        "affected_package": pkg_info["package"],
        "affects_language": pkg_info["affects_language"],
        "affects_framework": pkg_info["affects_framework"],
        "requires_internet_exposure": requires_internet_exposure,
        "targets_data_type": targets_data_type,
        **cvss,
    }
