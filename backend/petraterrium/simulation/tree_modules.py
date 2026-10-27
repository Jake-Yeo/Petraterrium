from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..markov.models import IdentifierPattern


class TreeModuleModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


TreeStatus = Literal["draft", "ready", "blocked", "deprecated"]
TreeNodeKind = Literal["decision", "action", "terminal", "module_reference"]
TreeProposalOrigin = Literal["ai", "deterministic", "manual"]


class DecisionTreeProposalAudit(TreeModuleModel):
    origin: TreeProposalOrigin
    source_id: str = Field(min_length=1)
    source_label: str = Field(min_length=1)
    model: str = Field(min_length=1)
    generated_at: str | None = None
    prompt_version: str = Field(min_length=1)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    message: str = Field(min_length=1)


class DecisionTreeNode(TreeModuleModel):
    id: str = Field(pattern=IdentifierPattern)
    label: str = Field(min_length=1)
    kind: TreeNodeKind
    description: str = ""
    target_module_id: str | None = Field(default=None, pattern=IdentifierPattern)

    @model_validator(mode="after")
    def valid_reference_target(self):
        if self.kind == "module_reference" and self.target_module_id is None:
            raise ValueError("Module reference nodes require a target module")
        if self.kind != "module_reference" and self.target_module_id is not None:
            raise ValueError("Only module reference nodes can target a module")
        return self


class DecisionTreeEdge(TreeModuleModel):
    id: str = Field(pattern=IdentifierPattern)
    from_node: str = Field(pattern=IdentifierPattern)
    to_node: str = Field(pattern=IdentifierPattern)
    label: str = ""
    condition: str = ""
    decision_id: str | None = Field(default=None, pattern=IdentifierPattern)
    evidence_edge_id: str | None = Field(default=None, pattern=IdentifierPattern)

    @model_validator(mode="after")
    def complete_evidence_link(self):
        if (self.decision_id is None) != (self.evidence_edge_id is None):
            raise ValueError(
                "Decision tree edges must provide both decision_id and evidence_edge_id"
            )
        return self


class DecisionTreeModule(TreeModuleModel):
    id: str = Field(pattern=IdentifierPattern)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    entry_node: str = Field(pattern=IdentifierPattern)
    nodes: list[DecisionTreeNode] = Field(min_length=1)
    edges: list[DecisionTreeEdge] = Field(default_factory=list)
    source: str = Field(min_length=1)
    status: TreeStatus
    proposal_audit: DecisionTreeProposalAudit | None = None


class DecisionTreeDefinition(TreeModuleModel):
    id: str = Field(pattern=IdentifierPattern)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    root_module_id: str = Field(pattern=IdentifierPattern)
    agent_type_ids: list[str] = Field(default_factory=list)
    place_ids: list[str] = Field(default_factory=list)
    source: str = Field(min_length=1)
    status: TreeStatus
    proposal_audit: DecisionTreeProposalAudit | None = None


class DecisionTreeRegistryDefinition(TreeModuleModel):
    version: str = Field(min_length=1)
    trees: list[DecisionTreeDefinition]
    modules: list[DecisionTreeModule]


class TreeModuleIssue(TreeModuleModel):
    code: str
    path: str
    message: str


class BrokenModuleReference(TreeModuleModel):
    module_id: str
    node_id: str
    target_module_id: str


class TreeRegistryValidation(TreeModuleModel):
    valid: bool
    issues: list[TreeModuleIssue]
    broken_references: list[BrokenModuleReference]
    reference_cycles: list[list[str]]
    unreachable_nodes: dict[str, list[str]]


class ModuleReferenceLocation(TreeModuleModel):
    kind: Literal["tree_root", "module_node"]
    id: str
    name: str
    node_id: str | None = None


class ModuleReferences(TreeModuleModel):
    module_id: str
    references: list[ModuleReferenceLocation]


class TreeFilter(TreeModuleModel):
    agent_type_id: str | None = None
    place_id: str | None = None
    source: str | None = None
    status: TreeStatus | None = None


class TreeSearchMatch(TreeModuleModel):
    tree_id: str
    tree_name: str
    module_id: str
    module_name: str
    node_id: str | None = None
    node_label: str | None = None


class TreeSearchResult(TreeModuleModel):
    query: str
    matches: list[TreeSearchMatch]


class ModuleNavigation(TreeModuleModel):
    tree: DecisionTreeDefinition
    module: DecisionTreeModule
    validation: TreeRegistryValidation


class DecisionTreeModuleRegistry:
    def __init__(self, definition: DecisionTreeRegistryDefinition):
        self.definition = definition
        self._trees = {tree.id: tree for tree in definition.trees}
        self._modules = {module.id: module for module in definition.modules}
        self._validation = self._validate()

    @property
    def validation(self) -> TreeRegistryValidation:
        return self._validation

    def root(self, tree_id: str) -> ModuleNavigation:
        tree = self._trees.get(tree_id)
        if tree is None:
            raise KeyError(f"Unknown decision tree: {tree_id}")
        module = self._modules.get(tree.root_module_id)
        if module is None:
            raise KeyError(
                f"Decision tree {tree_id} has missing root module {tree.root_module_id}"
            )
        return ModuleNavigation(tree=tree, module=module, validation=self._validation)

    def referenced_module(self, module_id: str, node_id: str) -> DecisionTreeModule:
        module = self._modules.get(module_id)
        if module is None:
            raise KeyError(f"Unknown decision tree module: {module_id}")
        node = next((item for item in module.nodes if item.id == node_id), None)
        if node is None:
            raise KeyError(f"Unknown node {node_id} in module {module_id}")
        if node.kind != "module_reference" or node.target_module_id is None:
            raise ValueError(f"Node {module_id}.{node_id} is not a module reference")
        target = self._modules.get(node.target_module_id)
        if target is None:
            raise KeyError(
                f"Node {module_id}.{node_id} references missing module {node.target_module_id}"
            )
        return target

    def references_for(self, module_id: str) -> ModuleReferences:
        references = [
            ModuleReferenceLocation(kind="tree_root", id=tree.id, name=tree.name)
            for tree in self.definition.trees
            if tree.root_module_id == module_id
        ]
        references.extend(
            ModuleReferenceLocation(
                kind="module_node",
                id=module.id,
                name=module.name,
                node_id=node.id,
            )
            for module in self.definition.modules
            for node in module.nodes
            if node.target_module_id == module_id
        )
        return ModuleReferences(
            module_id=module_id,
            references=sorted(
                references,
                key=lambda item: (item.kind, item.name.casefold(), item.node_id or ""),
            ),
        )

    def search(self, query: str = "", filters: TreeFilter | None = None) -> TreeSearchResult:
        selected = filters or TreeFilter()
        needle = query.strip().casefold()
        matches: list[TreeSearchMatch] = []
        for tree in self.definition.trees:
            if not self._tree_matches(tree, selected):
                continue
            reachable = self._reachable_modules(tree.root_module_id)
            tree_matches = not needle or needle in f"{tree.name} {tree.description}".casefold()
            if tree_matches and tree.root_module_id in self._modules:
                root = self._modules[tree.root_module_id]
                matches.append(
                    TreeSearchMatch(
                        tree_id=tree.id,
                        tree_name=tree.name,
                        module_id=root.id,
                        module_name=root.name,
                    )
                )
            for module_id in sorted(reachable):
                module = self._modules.get(module_id)
                if module is None:
                    continue
                module_matches = needle and needle in (
                    f"{module.name} {module.description} {module.source}".casefold()
                )
                if module_matches:
                    matches.append(
                        TreeSearchMatch(
                            tree_id=tree.id,
                            tree_name=tree.name,
                            module_id=module.id,
                            module_name=module.name,
                        )
                    )
                for node in module.nodes:
                    if needle and needle not in f"{node.label} {node.description}".casefold():
                        continue
                    if not needle:
                        continue
                    matches.append(
                        TreeSearchMatch(
                            tree_id=tree.id,
                            tree_name=tree.name,
                            module_id=module.id,
                            module_name=module.name,
                            node_id=node.id,
                            node_label=node.label,
                        )
                    )
        return TreeSearchResult(query=query, matches=matches)

    def _tree_matches(self, tree: DecisionTreeDefinition, selected: TreeFilter) -> bool:
        return all(
            (
                selected.agent_type_id is None
                or selected.agent_type_id in tree.agent_type_ids,
                selected.place_id is None or selected.place_id in tree.place_ids,
                selected.source is None or selected.source == tree.source,
                selected.status is None or selected.status == tree.status,
            )
        )

    def _reachable_modules(self, root_module_id: str) -> set[str]:
        found: set[str] = set()
        pending = [root_module_id]
        while pending:
            module_id = pending.pop()
            if module_id in found:
                continue
            found.add(module_id)
            module = self._modules.get(module_id)
            if module is None:
                continue
            pending.extend(
                node.target_module_id
                for node in module.nodes
                if node.target_module_id is not None
            )
        return found

    def _validate(self) -> TreeRegistryValidation:
        issues: list[TreeModuleIssue] = []
        broken: list[BrokenModuleReference] = []
        unreachable: dict[str, list[str]] = {}
        self._duplicates("trees", [tree.id for tree in self.definition.trees], issues)
        self._duplicates("modules", [module.id for module in self.definition.modules], issues)
        for tree in self.definition.trees:
            if tree.root_module_id not in self._modules:
                issues.append(
                    TreeModuleIssue(
                        code="missing_root_module",
                        path=f"trees.{tree.id}.root_module_id",
                        message=f"Root module {tree.root_module_id} does not exist",
                    )
                )
        for module in self.definition.modules:
            self._validate_module(module, issues, broken, unreachable)
        cycles = self._reference_cycles()
        issues.extend(
            TreeModuleIssue(
                code="module_reference_cycle",
                path=f"modules.{cycle[0]}",
                message=f"Module reference cycle: {' -> '.join(cycle)}",
            )
            for cycle in cycles
        )
        return TreeRegistryValidation(
            valid=not issues,
            issues=issues,
            broken_references=broken,
            reference_cycles=cycles,
            unreachable_nodes=unreachable,
        )

    def _validate_module(
        self,
        module: DecisionTreeModule,
        issues: list[TreeModuleIssue],
        broken: list[BrokenModuleReference],
        unreachable: dict[str, list[str]],
    ) -> None:
        node_ids = [node.id for node in module.nodes]
        edge_ids = [edge.id for edge in module.edges]
        self._duplicates(f"modules.{module.id}.nodes", node_ids, issues)
        self._duplicates(f"modules.{module.id}.edges", edge_ids, issues)
        known_nodes = set(node_ids)
        if module.entry_node not in known_nodes:
            issues.append(
                TreeModuleIssue(
                    code="missing_entry_node",
                    path=f"modules.{module.id}.entry_node",
                    message=f"Entry node {module.entry_node} does not exist",
                )
            )
        for edge in module.edges:
            if module.status == "ready" and edge.condition:
                issues.append(
                    TreeModuleIssue(
                        code="free_text_condition_non_executable",
                        path=f"modules.{module.id}.edges.{edge.id}.condition",
                        message=(
                            "Ready modules cannot execute free-text conditions; attach "
                            "typed evidence predicates"
                        ),
                    )
                )
            for field, node_id in (("from_node", edge.from_node), ("to_node", edge.to_node)):
                if node_id not in known_nodes:
                    issues.append(
                        TreeModuleIssue(
                            code="broken_edge",
                            path=f"modules.{module.id}.edges.{edge.id}.{field}",
                            message=f"Edge endpoint {node_id} does not exist",
                        )
                    )
        for node in module.nodes:
            target = node.target_module_id
            if target is not None and target not in self._modules:
                broken.append(
                    BrokenModuleReference(
                        module_id=module.id,
                        node_id=node.id,
                        target_module_id=target,
                    )
                )
                issues.append(
                    TreeModuleIssue(
                        code="broken_module_reference",
                        path=f"modules.{module.id}.nodes.{node.id}.target_module_id",
                        message=f"Referenced module {target} does not exist",
                    )
                )
        reachable = self._reachable_nodes(module)
        missing = sorted(known_nodes - reachable)
        if missing:
            unreachable[module.id] = missing
            issues.append(
                TreeModuleIssue(
                    code="unreachable_nodes",
                    path=f"modules.{module.id}.nodes",
                    message=f"Unreachable nodes: {', '.join(missing)}",
                )
            )

    def _reachable_nodes(self, module: DecisionTreeModule) -> set[str]:
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in module.edges:
            adjacency[edge.from_node].append(edge.to_node)
        found: set[str] = set()
        pending = [module.entry_node]
        while pending:
            node_id = pending.pop()
            if node_id in found:
                continue
            found.add(node_id)
            pending.extend(adjacency[node_id])
        return found

    def _reference_cycles(self) -> list[list[str]]:
        adjacency = {
            module.id: sorted(
                {
                    node.target_module_id
                    for node in module.nodes
                    if node.target_module_id in self._modules
                }
            )
            for module in self.definition.modules
        }
        cycles: set[tuple[str, ...]] = set()

        def visit(module_id: str, path: list[str], positions: dict[str, int]) -> None:
            if module_id in positions:
                cycle = path[positions[module_id] :] + [module_id]
                core = cycle[:-1]
                rotations = [tuple(core[index:] + core[:index]) for index in range(len(core))]
                canonical = min(rotations)
                cycles.add((*canonical, canonical[0]))
                return
            if module_id not in adjacency:
                return
            next_positions = {**positions, module_id: len(path)}
            next_path = [*path, module_id]
            for target in adjacency[module_id]:
                visit(target, next_path, next_positions)

        for module_id in sorted(adjacency):
            visit(module_id, [], {})
        return [list(cycle) for cycle in sorted(cycles)]

    @staticmethod
    def _duplicates(path: str, identifiers: list[str], issues: list[TreeModuleIssue]) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for identifier in identifiers:
            if identifier in seen:
                duplicates.add(identifier)
            seen.add(identifier)
        issues.extend(
            TreeModuleIssue(
                code="duplicate_id",
                path=path,
                message=f"Duplicate id: {identifier}",
            )
            for identifier in sorted(duplicates)
        )
