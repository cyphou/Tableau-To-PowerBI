"""Sprint 130.1 — Self-Healing Migration v2: pluggable repair strategies.

Promotes the existing :mod:`recovery_report` from passive log to active
repair loop. When a validation gate (DAX, M, TMDL, PBIR) fails, repair
strategies are tried in order:

  1. Deterministic strategies (cheap, predictable, no API cost)
  2. LLM strategies (optional, cost-bounded, requires --llm-refine)

Each strategy implements ``attempt(artifact, issues, context)`` and
returns a :class:`RepairResult` describing whether/how the artifact was
repaired.

The registry orchestrates strategy execution and writes per-attempt
breadcrumbs to a :class:`RecoveryReport` so the operator can audit the
self-healing decisions.

Design goals:
  * Deterministic strategies always run first — they're free and
    predictable. LLM is a fallback only when deterministic fails.
  * Strategies are *pure*: they never raise; they return a result with
    ``status='unchanged'`` if they don't apply.
  * Strategies are *additive*: a chain may stack multiple repairs.
  * Original artifact is always preserved when no strategy succeeds.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


logger = logging.getLogger(__name__)


__all__ = [
    'RepairResult',
    'RepairStrategy',
    'RepairRegistry',
    'balanced_paren_strategy',
    'tableau_leak_strip_strategy',
    'parameter_resolution_strategy',
    'llm_dax_repair_strategy',
    'default_dax_registry',
    'default_m_registry',
]


# ════════════════════════════════════════════════════════════════════
#  Result + base strategy
# ════════════════════════════════════════════════════════════════════


@dataclass
class RepairResult:
    """Outcome of a single strategy attempt.

    Attributes:
        status: 'repaired' | 'unchanged' | 'rejected' | 'error'
        artifact: post-repair artifact (or original if unchanged/rejected)
        strategy: name of the strategy that produced this result
        issues_before: validation issues at start of attempt
        issues_after: validation issues after attempt
        notes: human-readable explanation
        cost: dollar cost (LLM strategies only)
    """
    status: str
    artifact: str
    strategy: str
    issues_before: List[str] = field(default_factory=list)
    issues_after: List[str] = field(default_factory=list)
    notes: str = ''
    cost: float = 0.0


# A strategy is a callable. Wrap deterministic functions in RepairStrategy
# for a uniform .attempt() interface.
class RepairStrategy:
    """Wrap a callable as a named, categorized repair strategy.

    The callable signature is::

        fn(artifact, issues, context) -> (new_artifact, notes)

    where ``new_artifact`` may be the same object (no change) or a new
    string (repair attempted), and ``notes`` is a short human-readable
    explanation.
    """

    DETERMINISTIC = 'deterministic'
    LLM = 'llm'

    def __init__(self, name: str, fn: Callable, *,
                 category: str = DETERMINISTIC,
                 applies_to: str = 'dax'):
        self.name = name
        self.fn = fn
        self.category = category
        self.applies_to = applies_to  # 'dax' | 'm' | 'tmdl' | 'pbir'

    def attempt(self, artifact: str, issues: List[str],
                context: Optional[Dict] = None) -> RepairResult:
        context = context or {}
        try:
            new_artifact, notes = self.fn(artifact, issues, context)
        except Exception as exc:  # noqa: BLE001 — strategies must never raise
            logger.warning("Strategy %s raised: %s", self.name, exc)
            return RepairResult(
                status='error', artifact=artifact, strategy=self.name,
                issues_before=list(issues), issues_after=list(issues),
                notes=f'strategy raised: {exc}',
            )

        if new_artifact == artifact:
            return RepairResult(
                status='unchanged', artifact=artifact, strategy=self.name,
                issues_before=list(issues), issues_after=list(issues),
                notes=notes or 'strategy did not apply',
            )

        # Re-validate
        validator = context.get('validator')
        new_issues = validator(new_artifact) if validator else []
        cost = context.pop('_last_cost', 0.0) if context else 0.0
        if new_issues:
            return RepairResult(
                status='rejected', artifact=artifact, strategy=self.name,
                issues_before=list(issues), issues_after=new_issues,
                notes=notes + ' (post-repair validation still failed)',
                cost=cost,
            )
        return RepairResult(
            status='repaired', artifact=new_artifact, strategy=self.name,
            issues_before=list(issues), issues_after=[],
            notes=notes, cost=cost,
        )


# ════════════════════════════════════════════════════════════════════
#  Built-in deterministic strategies
# ════════════════════════════════════════════════════════════════════


def _balanced_paren_repair(artifact: str, issues: List[str],
                           context: Dict):
    """Append/prepend matching parens when the only issue is paren imbalance.

    Conservative: never modifies the artifact unless paren imbalance is
    the *sole* class of issue.
    """
    paren_issues = [i for i in issues if 'paren' in i.lower()]
    if not paren_issues or len(paren_issues) != len(issues):
        return artifact, ''

    depth = 0
    for ch in artifact:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1

    if depth > 0:
        return artifact + (')' * depth), f'appended {depth} closing paren(s)'
    if depth < 0:
        # Leading unmatched closes are very unusual in generated DAX; we
        # don't trim them blindly — too dangerous.
        return artifact, ''
    return artifact, ''


balanced_paren_strategy = RepairStrategy(
    'balanced_paren', _balanced_paren_repair,
    category=RepairStrategy.DETERMINISTIC, applies_to='dax',
)


_TABLEAU_LEAKS = [
    (r'\bIFNULL\s*\(', 'IF(ISBLANK('),
    (r'\bZN\s*\(', 'IF(ISBLANK('),  # ZN(x) → IF(ISBLANK(x), 0, x) — closer below
    (r'\bATTR\s*\(\s*', ''),         # strip ATTR( and matching )
]


def _tableau_leak_strip(artifact: str, issues: List[str],
                        context: Dict):
    """Strip residual Tableau function calls that leaked through.

    This is a *cosmetic* repair — it removes the function wrapper but
    cannot recover the full Tableau semantics. Use only when the
    alternative is shipping invalid DAX.
    """
    leak_issues = [i for i in issues if 'tableau' in i.lower()]
    if not leak_issues:
        return artifact, ''

    new = artifact
    notes = []

    # ATTR(x) → x  (Tableau's "this dim is consistent" assertion has no DAX)
    attr_re = re.compile(r'\bATTR\s*\(\s*([^()]+?)\s*\)')
    if attr_re.search(new):
        new = attr_re.sub(r'\1', new)
        notes.append('stripped ATTR() wrapper(s)')

    # IFNULL(x, y) → IF(ISBLANK(x), y, x)
    ifnull_re = re.compile(r'\bIFNULL\s*\(\s*([^,()]+?)\s*,\s*([^()]+?)\s*\)')
    if ifnull_re.search(new):
        new = ifnull_re.sub(r'IF(ISBLANK(\1), \2, \1)', new)
        notes.append('rewrote IFNULL → IF(ISBLANK)')

    # ZN(x) → IF(ISBLANK(x), 0, x)
    zn_re = re.compile(r'\bZN\s*\(\s*([^()]+?)\s*\)')
    if zn_re.search(new):
        new = zn_re.sub(r'IF(ISBLANK(\1), 0, \1)', new)
        notes.append('rewrote ZN → IF(ISBLANK,0)')

    return new, '; '.join(notes)


tableau_leak_strip_strategy = RepairStrategy(
    'tableau_leak_strip', _tableau_leak_strip,
    category=RepairStrategy.DETERMINISTIC, applies_to='dax',
)


def _parameter_resolution(artifact: str, issues: List[str],
                          context: Dict):
    """Resolve unresolved ``[Parameters].[X]`` refs using a parameter map.

    Context must provide ``parameters`` dict (param_name → value).
    Replaces ``[Parameters].[Name]`` with the literal value (string
    quoted, numeric inline).
    """
    param_issues = [i for i in issues if 'parameter' in i.lower()]
    if not param_issues:
        return artifact, ''

    params = context.get('parameters') or {}
    if not params:
        return artifact, ''

    new = artifact
    replaced = []
    for name, value in params.items():
        ref_pattern = re.compile(
            r'\[Parameters\]\.\[' + re.escape(name) + r'\]'
        )
        if not ref_pattern.search(new):
            continue
        if isinstance(value, str) and not value.replace('.', '', 1).isdigit():
            literal = '"' + value.replace('"', '""') + '"'
        else:
            literal = str(value)
        new = ref_pattern.sub(literal, new)
        replaced.append(name)

    if replaced:
        return new, f'inlined parameter(s): {", ".join(replaced)}'
    return artifact, ''


parameter_resolution_strategy = RepairStrategy(
    'parameter_resolution', _parameter_resolution,
    category=RepairStrategy.DETERMINISTIC, applies_to='dax',
)


# ════════════════════════════════════════════════════════════════════
#  LLM-backed strategy (Sprint 130.2 — fallback only)
# ════════════════════════════════════════════════════════════════════


_LLM_REPAIR_SYSTEM = (
    'You are a DAX expert. The user will give you a DAX expression that '
    'failed validation, plus the list of validation issues. Return ONLY '
    'the corrected DAX expression — no prose, no markdown fences, no '
    'commentary. Preserve the original semantics as closely as possible.'
)

_LLM_REPAIR_USER = (
    'Original DAX:\n```dax\n{artifact}\n```\n\n'
    'Validation issues:\n{issues}\n\n'
    'Return the corrected DAX only.'
)


def _llm_dax_repair(artifact: str, issues: List[str], context: Dict):
    """LLM-backed repair. Requires ``context['llm_client']`` to be a
    :class:`LLMClient` instance (see Sprint 112)."""
    client = context.get('llm_client')
    if client is None:
        return artifact, ''
    if not issues:
        return artifact, ''

    issues_block = '\n'.join(f'  - {i}' for i in issues)
    user = _LLM_REPAIR_USER.format(artifact=artifact, issues=issues_block)
    resp = client.call(_LLM_REPAIR_SYSTEM, user)

    # Track cost for the registry to bubble up
    cost = resp.get('cost', 0)
    context['_last_cost'] = cost

    if resp.get('error'):
        return artifact, f'LLM error: {resp["error"]}'

    text = (resp.get('text') or '').strip()
    if not text:
        return artifact, 'LLM returned empty response'

    # Strip markdown fences if present (mirrors llm_client behavior)
    if text.startswith('```'):
        text = re.sub(r'^```(?:dax)?\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)
        text = text.strip()

    if text == artifact:
        return artifact, 'LLM returned identical text'
    return text, 'LLM-refined repair'


llm_dax_repair_strategy = RepairStrategy(
    'llm_dax_repair', _llm_dax_repair,
    category=RepairStrategy.LLM, applies_to='dax',
)


# ════════════════════════════════════════════════════════════════════
#  Registry
# ════════════════════════════════════════════════════════════════════


class RepairRegistry:
    """Ordered collection of strategies. ``run()`` invokes them in order
    until one succeeds (or all are exhausted).

    Deterministic strategies always run before LLM strategies regardless
    of insertion order — this guarantees the cheap path is tried first.
    """

    def __init__(self, strategies: Optional[List[RepairStrategy]] = None):
        self.strategies: List[RepairStrategy] = list(strategies or [])

    def add(self, strategy: RepairStrategy) -> None:
        self.strategies.append(strategy)

    def _ordered(self) -> List[RepairStrategy]:
        det = [s for s in self.strategies
               if s.category == RepairStrategy.DETERMINISTIC]
        llm = [s for s in self.strategies if s.category == RepairStrategy.LLM]
        return det + llm

    def run(self, artifact: str, issues: List[str],
            context: Optional[Dict] = None,
            *, recovery_report=None,
            item_name: str = '') -> List[RepairResult]:
        """Try strategies in order; stop on the first ``status='repaired'``.

        Args:
            artifact: failing artifact text (DAX, M, etc.)
            issues: validation issues from the gate
            context: shared context dict (``validator`` callable required
                for accept/reject; ``parameters``, ``llm_client``,
                ``tables`` optional)
            recovery_report: optional :class:`RecoveryReport` for breadcrumbs
            item_name: label for recovery report entries

        Returns:
            List of :class:`RepairResult` (one per strategy actually
            attempted, in order). The final entry has the winning
            artifact if any strategy succeeded.
        """
        context = dict(context or {})
        results: List[RepairResult] = []
        current = artifact
        current_issues = list(issues)

        for strategy in self._ordered():
            if strategy.applies_to and context.get('artifact_kind') and \
               strategy.applies_to != context['artifact_kind']:
                continue
            res = strategy.attempt(current, current_issues, context)
            results.append(res)
            if recovery_report is not None:
                recovery_report.record(
                    category=strategy.applies_to or 'unknown',
                    repair_type=f'auto_repair_{res.status}',
                    description=f'{strategy.name}: {res.notes}',
                    action=f'strategy={strategy.name} status={res.status}',
                    severity='info' if res.status == 'repaired' else 'warning',
                    item_name=item_name,
                    original_value=artifact[:200] if res.status == 'repaired' else '',
                    repaired_value=res.artifact[:200] if res.status == 'repaired' else '',
                )
            if res.status == 'repaired':
                # Success — stop here
                return results
            # If a strategy produced new text but failed validation, we
            # roll back to the original for the next strategy attempt.
            current = artifact
            current_issues = list(issues)

        return results


# ════════════════════════════════════════════════════════════════════
#  Default registries
# ════════════════════════════════════════════════════════════════════


def default_dax_registry(*, llm_client=None) -> RepairRegistry:
    """Default DAX repair registry. LLM strategy added only if a client
    is supplied."""
    reg = RepairRegistry([
        balanced_paren_strategy,
        tableau_leak_strip_strategy,
        parameter_resolution_strategy,
    ])
    if llm_client is not None:
        reg.add(llm_dax_repair_strategy)
    return reg


def default_m_registry() -> RepairRegistry:
    """Default M repair registry. Currently only the paren-balance
    strategy applies (M shares paren grammar with DAX)."""
    return RepairRegistry([
        RepairStrategy(
            'balanced_paren_m',
            _balanced_paren_repair,
            category=RepairStrategy.DETERMINISTIC,
            applies_to='m',
        ),
    ])
