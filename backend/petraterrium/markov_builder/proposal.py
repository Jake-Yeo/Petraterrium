import hashlib
import re
import unicodedata
from typing import Any

from ..llm_gateway import (
    AIProviderError,
    SelectedAIProvider,
    selected_provider_identity,
)
from .models import (
    ChainDraft,
    ChainNodeDraft,
    ChainProposalRequest,
    ChainProposalResult,
    ChainTransitionDraft,
    LLMGraphProposal,
    ProposalAudit,
)
from .validation import validate_chain_draft

PROMPT_VERSION = "markov-chain-proposal-v1"
PROMPT = """Convert the user's description into an editable Markov-chain draft.
Return only states and directed transitions that the text states or directly entails as a choice.
Every state and transition needs an exact source_excerpt copied from the user's text.
Never invent a transition. Never assign equal probabilities. A probability must be null unless
the text gives that exact number. A condition must be null unless the text gives it. Set terminal
true only when the text explicitly says a state ends or terminates the chain. The result is only a
proposal and will require human editing and confirmation before persistence."""

_SELECTED_PROPOSAL_CACHE: dict[str, tuple[LLMGraphProposal, Any]] = {}


def slugify(value: str, fallback: str = "state") -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    identity = re.sub(r"[^a-z0-9]+", "_", normalized.casefold()).strip("_")
    if not identity:
        identity = fallback
    if not identity[0].isalpha():
        identity = f"{fallback}_{identity}"
    return identity[:80].rstrip("_")


def _unique_id(preferred: str, used: set[str]) -> str:
    identity = preferred
    suffix = 2
    while identity in used:
        identity = f"{preferred}_{suffix}"
        suffix += 1
    used.add(identity)
    return identity


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _is_exact_excerpt(excerpt: str, text: str) -> bool:
    return bool(excerpt.strip()) and _normalized(excerpt) in _normalized(text)


def _explicit_probability(excerpt: str, proposed: float | None) -> float | None:
    if proposed is None:
        return None
    candidates: list[float] = []
    for match in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)\s*%", excerpt):
        candidates.append(float(match.group(1)) / 100)
    for match in re.finditer(
        r"(?:probability|chance|p)\s*(?:is|=|:)\s*(0(?:\.\d+)?|1(?:\.0+)?)\b",
        excerpt,
        re.IGNORECASE,
    ):
        candidates.append(float(match.group(1)))
    return proposed if any(abs(candidate - proposed) <= 1e-9 for candidate in candidates) else None


def _explicit_condition(excerpt: str, proposed: str | None) -> str | None:
    if not proposed or not proposed.strip():
        return None
    condition = proposed.strip()
    if _normalized(condition) in _normalized(excerpt):
        return condition
    return None


def _explicit_terminal(excerpt: str, proposed: bool) -> bool:
    if not proposed:
        return False
    return bool(
        re.search(
            r"\b(?:terminal|terminates?|ending|ends?|final|absorbing|stops?)\b",
            excerpt,
            re.IGNORECASE,
        )
    )


def _choice_draft(request: ChainProposalRequest) -> ChainDraft | None:
    match = re.search(
        r"\b(?:decides?|chooses?)\s+whether\s+to\s+(.+?)\s+or\s+(.+?)(?:[.!?]|$)",
        request.text,
        re.IGNORECASE,
    )
    if not match:
        return None
    first = match.group(1).strip(" ,")
    second = match.group(2).strip(" ,")
    if not first or not second:
        return None
    used: set[str] = set()
    entry_id = _unique_id("decision", used)
    first_id = _unique_id(slugify(first), used)
    second_id = _unique_id(slugify(second), used)
    excerpt = match.group(0)
    name = request.name or f"{first.title()} or {second.title()}"
    identity = request.chain_id or slugify(name, "chain")
    nodes = [
        ChainNodeDraft(
            id=entry_id,
            label="Decision",
            terminal=False,
            origin="structural",
            source_excerpt=excerpt,
        ),
        ChainNodeDraft(
            id=first_id,
            label=first,
            terminal=False,
            origin="user_explicit",
            source_excerpt=first,
        ),
        ChainNodeDraft(
            id=second_id,
            label=second,
            terminal=False,
            origin="user_explicit",
            source_excerpt=second,
        ),
    ]
    transitions = [
        ChainTransitionDraft(
            id=f"{entry_id}_to_{first_id}"[:80],
            from_node=entry_id,
            to_node=first_id,
            probability=None,
            condition=None,
            origin="user_explicit",
            source_excerpt=excerpt,
        ),
        ChainTransitionDraft(
            id=f"{entry_id}_to_{second_id}"[:80],
            from_node=entry_id,
            to_node=second_id,
            probability=None,
            condition=None,
            origin="user_explicit",
            source_excerpt=excerpt,
        ),
    ]
    return ChainDraft(
        id=identity,
        name=name,
        source_text=request.text,
        entry_node=entry_id,
        nodes=nodes,
        transitions=transitions,
    )


def _arrow_draft(request: ChainProposalRequest) -> ChainDraft | None:
    rows = [item.strip() for item in re.split(r"[\n;]+", request.text) if item.strip()]
    parsed: list[tuple[str, str, float | None, str | None, str]] = []
    pattern = re.compile(r"^(.+?)\s*(?:->|→)\s*([^|:]+?)(?:\s*(?:\||:)\s*(.*))?$")
    for row in rows:
        match = pattern.match(row)
        if not match:
            continue
        source = match.group(1).strip()
        target = match.group(2).strip()
        metadata = (match.group(3) or "").strip()
        probability = None
        percent = re.search(r"(?<![\w.])(\d+(?:\.\d+)?)\s*%", metadata)
        decimal = re.search(
            r"(?:probability|chance|p)\s*(?:is|=|:)\s*(0(?:\.\d+)?|1(?:\.0+)?)\b",
            metadata,
            re.IGNORECASE,
        )
        if percent:
            probability = float(percent.group(1)) / 100
        elif decimal:
            probability = float(decimal.group(1))
        condition_match = re.search(
            r"(?:condition\s*(?:is|=|:)|if|when)\s+(.+)$", metadata, re.IGNORECASE
        )
        condition = condition_match.group(1).strip() if condition_match else None
        parsed.append((source, target, probability, condition, row))
    if not parsed:
        return None
    labels: list[str] = []
    for source, target, *_ in parsed:
        for label in (source, target):
            cleaned = re.sub(r"\s*\[(?:terminal|end)\]\s*$", "", label, flags=re.I).strip()
            if cleaned not in labels:
                labels.append(cleaned)
    used: set[str] = set()
    ids = {label: _unique_id(slugify(label), used) for label in labels}
    terminal_labels = {
        re.sub(r"\s*\[(?:terminal|end)\]\s*$", "", target, flags=re.I).strip()
        for _, target, *_ in parsed
        if re.search(r"\[(?:terminal|end)\]\s*$", target, re.I)
    }
    nodes = [
        ChainNodeDraft(
            id=ids[label],
            label=label,
            terminal=label in terminal_labels,
            origin="user_explicit",
            source_excerpt=label,
        )
        for label in labels
    ]
    transition_ids: set[str] = set()
    transitions = []
    for source, target, probability, condition, excerpt in parsed:
        source_label = re.sub(r"\s*\[(?:terminal|end)\]\s*$", "", source, flags=re.I).strip()
        target_label = re.sub(r"\s*\[(?:terminal|end)\]\s*$", "", target, flags=re.I).strip()
        preferred = f"{ids[source_label]}_to_{ids[target_label]}"[:72]
        transitions.append(
            ChainTransitionDraft(
                id=_unique_id(preferred, transition_ids),
                from_node=ids[source_label],
                to_node=ids[target_label],
                probability=probability,
                condition=condition,
                origin="user_explicit",
                source_excerpt=excerpt,
            )
        )
    name = request.name or labels[0].title()
    return ChainDraft(
        id=request.chain_id or slugify(name, "chain"),
        name=name,
        source_text=request.text,
        entry_node=ids[labels[0]],
        nodes=nodes,
        transitions=transitions,
    )


def deterministic_proposal(request: ChainProposalRequest) -> ChainDraft:
    draft = _arrow_draft(request) or _choice_draft(request)
    if draft:
        return draft
    name = request.name or "Markov chain draft"
    return ChainDraft(
        id=request.chain_id or slugify(name, "chain"),
        name=name,
        source_text=request.text,
        entry_node=None,
        nodes=[],
        transitions=[],
    )


def _llm_draft(request: ChainProposalRequest, proposal: LLMGraphProposal) -> ChainDraft:
    valid_nodes = [
        item for item in proposal.nodes if _is_exact_excerpt(item.source_excerpt, request.text)
    ]
    valid_transitions = [
        item
        for item in proposal.transitions
        if _is_exact_excerpt(item.source_excerpt, request.text)
    ]
    labels = []
    for item in valid_nodes:
        if item.label not in labels:
            labels.append(item.label)
    for item in valid_transitions:
        for label in (item.from_label, item.to_label):
            if label not in labels:
                labels.append(label)
    used: set[str] = set()
    ids = {label: _unique_id(slugify(label), used) for label in labels}
    proposal_by_label = {item.label: item for item in valid_nodes}
    nodes = []
    for label in labels:
        item = proposal_by_label.get(label)
        excerpt = (
            item.source_excerpt
            if item
            else next(
                transition.source_excerpt
                for transition in valid_transitions
                if label in {transition.from_label, transition.to_label}
            )
        )
        nodes.append(
            ChainNodeDraft(
                id=ids[label],
                label=label,
                terminal=_explicit_terminal(excerpt, item.terminal) if item else False,
                origin="model_proposal",
                source_excerpt=excerpt,
            )
        )
    transition_ids: set[str] = set()
    transitions = []
    for item in valid_transitions:
        preferred = f"{ids[item.from_label]}_to_{ids[item.to_label]}"[:72]
        transitions.append(
            ChainTransitionDraft(
                id=_unique_id(preferred, transition_ids),
                from_node=ids[item.from_label],
                to_node=ids[item.to_label],
                probability=_explicit_probability(item.source_excerpt, item.probability),
                condition=_explicit_condition(item.source_excerpt, item.condition),
                origin="model_proposal",
                source_excerpt=item.source_excerpt,
            )
        )
    entry = ids.get(proposal.entry_label or "")
    if entry is None and transitions:
        entry = transitions[0].from_node
    name = request.name or proposal.name
    return ChainDraft(
        id=request.chain_id or slugify(name, "chain"),
        name=name,
        source_text=request.text,
        entry_node=entry,
        nodes=nodes,
        transitions=transitions,
    )


def propose_chain(
    request: ChainProposalRequest,
    ai_provider: SelectedAIProvider | None = None,
) -> ChainProposalResult:
    if not request.use_llm:
        draft = deterministic_proposal(request)
        audit = ProposalAudit(
            provider="deterministic-parser",
            model="none",
            prompt_version=PROMPT_VERSION,
            message=(
                "Only explicit choices and arrow syntax were extracted. Unknown "
                "probabilities, conditions, and terminal states remain unresolved."
            ),
        )
        draft = draft.model_copy(update={"proposal_audit": audit})
        return ChainProposalResult(
            draft=draft,
            validation=validate_chain_draft(draft),
            audit=audit,
        )
    if ai_provider is None:
        raise AIProviderError(
            "ai_provider_unavailable",
            "No AI source is configured. Choose OpenAI CLI or OpenAI API in AI Settings; "
            "no fallback was attempted.",
        )
    selected_source, selected_model = selected_provider_identity(ai_provider)
    cache_key = hashlib.sha256(
        f"{selected_source}\0{selected_model}\0{PROMPT_VERSION}\0{request.text}".encode()
    ).hexdigest()
    cached = _SELECTED_PROPOSAL_CACHE.get(cache_key)
    if cached is None:
        generated = ai_provider.generate_structured(
            request.text,
            LLMGraphProposal,
            system_prompt=PROMPT,
            prompt_version=PROMPT_VERSION,
        )
        cached = (generated.output, generated.provenance)
        _SELECTED_PROPOSAL_CACHE[cache_key] = cached
    proposal, provenance = cached
    draft = _llm_draft(request, proposal)
    audit = ProposalAudit(
        provider=provenance.source,
        model=provenance.model,
        prompt_version=provenance.prompt_version,
        generated_at=provenance.generated_at,
        input_tokens=provenance.input_tokens or 0,
        output_tokens=provenance.output_tokens or 0,
        message=(
            f"Unsaved proposal generated {provenance.generated_at.isoformat()} via "
            f"{provenance.source_label}. Model-proposed elements are labelled, and "
            "unsupported probabilities and conditions remain unknown."
        ),
    )
    draft = draft.model_copy(update={"proposal_audit": audit})
    return ChainProposalResult(
        draft=draft,
        validation=validate_chain_draft(draft),
        audit=audit,
    )
