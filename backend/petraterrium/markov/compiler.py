from collections import defaultdict

from .evidence import resolve_probability
from .models import (
    CompilationContext,
    CompilationResult,
    CompiledModule,
    CompiledTransition,
    EvidenceCatalog,
    MarkovProgram,
    OutgoingProbabilityTotal,
    ValidationIssue,
)
from .validation import validate_program


def compile_program(
    program: MarkovProgram,
    evidence: EvidenceCatalog,
    context: CompilationContext,
) -> CompilationResult:
    validation = validate_program(program)
    if not validation.valid:
        return CompilationResult(
            context=context,
            executable=False,
            issues=validation.issues,
            modules=[],
            probabilities=[],
            outgoing_totals=[],
            missing_requirements=[],
        )
    issues: list[ValidationIssue] = []
    probabilities = []
    missing = []
    compiled_modules = []
    outgoing_totals = []
    for module in program.modules:
        state_indices = {state.id: index for index, state in enumerate(module.states)}
        compiled_transitions = []
        module_probabilities: dict[str, list] = defaultdict(list)
        partition_inputs: set[str] = set()
        for transition in module.transitions:
            resolved, requirement = resolve_probability(module, transition, evidence, context)
            probability_index = len(probabilities)
            probabilities.append(resolved)
            module_probabilities[transition.from_state].append(resolved)
            partition_inputs.update(transition.probability.predictor_inputs)
            if requirement is not None:
                missing.append(requirement)
                issues.append(
                    ValidationIssue(
                        code="missing_probability_evidence",
                        path=f"modules.{module.id}.transitions.{transition.id}",
                        message=requirement.requirement,
                    )
                )
            compiled_transitions.append(
                CompiledTransition(
                    id=transition.id,
                    source_index=state_indices[transition.from_state],
                    target_index=state_indices[transition.to_state],
                    probability_index=probability_index,
                    condition=transition.condition,
                )
            )
        for state in module.states:
            if state.id in module.exit_states:
                continue
            resolved = module_probabilities[state.id]
            complete = bool(resolved) and all(item.probability is not None for item in resolved)
            total = sum(item.probability or 0 for item in resolved)
            sums_to_one = complete and abs(total - 1) <= 1e-9
            outgoing_totals.append(
                OutgoingProbabilityTotal(
                    module_id=module.id,
                    state_id=state.id,
                    total=total,
                    complete=complete,
                    sums_to_one=sums_to_one,
                )
            )
            if complete and not sums_to_one:
                issues.append(
                    ValidationIssue(
                        code="outgoing_probability_sum",
                        path=f"modules.{module.id}.states.{state.id}",
                        message=(
                            f"Outgoing probabilities for {module.id}.{state.id} sum to "
                            f"{total:.12g}, not 1"
                        ),
                    )
                )
        compiled_modules.append(
            CompiledModule(
                id=module.id,
                version=module.version,
                entry_index=state_indices[module.entry_state],
                state_indices=state_indices,
                exit_indices=[state_indices[state_id] for state_id in module.exit_states],
                transitions=compiled_transitions,
                partition_inputs=sorted(partition_inputs),
            )
        )
    unique_missing = {item.key: item for item in missing}
    ordered_missing = [unique_missing[key] for key in sorted(unique_missing)]
    return CompilationResult(
        context=context,
        executable=not issues,
        issues=issues,
        modules=compiled_modules,
        probabilities=probabilities,
        outgoing_totals=outgoing_totals,
        missing_requirements=ordered_missing,
    )
