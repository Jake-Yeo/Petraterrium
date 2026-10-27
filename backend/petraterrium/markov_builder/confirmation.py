from .models import ChainDraft, ConfirmedChainGraph
from .validation import validate_chain_draft


class ChainConfirmationError(ValueError):
    def __init__(self, draft: ChainDraft):
        self.validation = validate_chain_draft(draft)
        messages = [
            issue.message for issue in self.validation.issues if issue.severity == "error"
        ]
        super().__init__("; ".join(messages) or "The chain draft cannot be confirmed")


def confirmed_chain_from_draft(
    draft: ChainDraft, user_confirmed: bool
) -> ConfirmedChainGraph:
    if not user_confirmed:
        raise ValueError("Explicit user confirmation is required before persistence")
    validation = validate_chain_draft(draft)
    if not validation.can_confirm or draft.entry_node is None:
        raise ChainConfirmationError(draft)
    return ConfirmedChainGraph(
        id=draft.id,
        name=draft.name,
        source_text=draft.source_text,
        entry_node=draft.entry_node,
        nodes=draft.nodes,
        transitions=draft.transitions,
        revision=draft.revision,
    )
