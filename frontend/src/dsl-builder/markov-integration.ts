import type { DSLConfig, MarkovProgram } from '../contracts.generated';
import type { ConfirmedChainGraph } from '../markov-builder/types';

const conditionInputId = (transitionId: string): string => `condition_${transitionId}`;

const programFromChain = (chain: ConfirmedChainGraph): MarkovProgram => {
  const moduleId = chain.id;
  const conditionalTransitions = chain.transitions.filter(
    (transition) => transition.condition?.trim().toLowerCase() !== 'always',
  );
  return {
    id: chain.id,
    version: `draft-${chain.revision + 1}`,
    entry_module: moduleId,
    modules: [
      {
        id: moduleId,
        version: `draft-${chain.revision + 1}`,
        name: chain.name,
        entry_state: chain.entry_node,
        exit_states: chain.nodes.filter((node) => node.terminal).map((node) => node.id),
        inputs: [
          { id: 'place', kind: 'place', value_type: 'identifier', required: true },
          { id: 'time', kind: 'time', value_type: 'categorical', required: true },
          ...conditionalTransitions.map((transition) => ({
            id: conditionInputId(transition.id),
            kind: 'context' as const,
            value_type: 'boolean' as const,
            required: true,
          })),
        ],
        outputs: [],
        states: chain.nodes.map((node) => ({ id: node.id, label: node.label, effects: [] })),
        transitions: chain.transitions.map((transition) => {
          const unconditional = transition.condition?.trim().toLowerCase() === 'always';
          return {
            id: transition.id,
            from_state: transition.from_node,
            to_state: transition.to_node,
            condition: unconditional
              ? { mode: 'always' as const, clauses: [] }
              : {
                  mode: 'all' as const,
                  clauses: [
                    {
                      input_id: conditionInputId(transition.id),
                      operator: 'eq' as const,
                      value: true,
                    },
                  ],
                },
            probability: {
              outcome_id: transition.to_node,
              conditioning_id: `${chain.id}-${transition.id}`,
              place_input: 'place',
              time_input: 'time',
              predictor_inputs: [],
              allowed_evidence: ['measured_choice', 'measured_joint', 'fitted_choice'] as const,
            },
          };
        }),
      },
    ],
    links: [],
    terminal_exits: chain.nodes
      .filter((node) => node.terminal)
      .map((node) => ({ module_id: moduleId, state_id: node.id })),
    external_inputs: [],
  };
};

const replaceById = <T extends { id: string }>(items: T[], replacement: T): T[] => [
  ...items.filter((item) => item.id !== replacement.id),
  replacement,
];

export function integrateConfirmedChain(
  dsl: DSLConfig,
  chain: ConfirmedChainGraph,
): DSLConfig {
  return {
    ...dsl,
    markov_chain_drafts: replaceById(dsl.markov_chain_drafts ?? [], chain),
    markov_programs: replaceById(dsl.markov_programs ?? [], programFromChain(chain)),
  };
}
