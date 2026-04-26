from __future__ import annotations

from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Set, Tuple
from collections import deque


@dataclass
class Resource:
    name: str
    resource_type: str
    capacity: int = 1
    inaccessible_areas: Set[str] = field(default_factory=set)
    skills: Set[str] = field(default_factory=set)


@dataclass
class AreaNeed:
    area: str
    required_type: str
    required_units: int
    required_skill: Optional[str] = None


@dataclass
class SolverStep:
    action: str
    variable: str
    choice: Optional[str]
    detail: str


class DisasterReliefCSP:
    def __init__(self, needs: List[AreaNeed], resources: List[Resource]) -> None:
        self.needs = needs
        self.resources = resources
        self.steps: List[SolverStep] = []
        self.domains: Dict[str, List[str]] = self._build_domains()
        self.usage: Dict[str, int] = {resource.name: 0 for resource in resources}
        self.resource_lookup: Dict[str, Resource] = {resource.name: resource for resource in resources}
        self.need_lookup: Dict[str, AreaNeed] = {need.area: need for need in needs}
        self.neighbors: Dict[str, Set[str]] = self._build_neighbors()

    def solve(self) -> Tuple[bool, Dict[str, str], List[SolverStep]]:
        assignments: Dict[str, str] = {}
        current_domains = {area: list(domain) for area, domain in self.domains.items()}
        if not self._enforce_arc_consistency(current_domains, assignments):
            return False, assignments, self.steps
        solved = self._backtrack(assignments, current_domains)
        self.domains = current_domains
        return solved, assignments, self.steps

    def _build_domains(self) -> Dict[str, List[str]]:
        domains: Dict[str, List[str]] = {}
        for need in self.needs:
            domain = []
            for resource in self.resources:
                if resource.resource_type != need.required_type:
                    continue
                if need.area in resource.inaccessible_areas:
                    continue
                if need.required_skill and need.required_skill not in resource.skills:
                    continue
                domain.append(resource.name)
            domains[need.area] = domain
        return domains

    def _select_unassigned_area(self, assignments: Dict[str, str]) -> Optional[str]:
        unassigned = [need.area for need in self.needs if need.area not in assignments]
        if not unassigned:
            return None
        return min(unassigned, key=lambda area: len(self.domains.get(area, [])))

    def _build_neighbors(self) -> Dict[str, Set[str]]:
        neighbors: Dict[str, Set[str]] = {need.area: set() for need in self.needs}
        areas = [need.area for need in self.needs]
        for index, area_a in enumerate(areas):
            for area_b in areas[index + 1 :]:
                neighbors[area_a].add(area_b)
                neighbors[area_b].add(area_a)
        return neighbors

    def _is_consistent(self, area: str, resource_name: str) -> Tuple[bool, str]:
        need = self.need_lookup[area]
        resource = self.resource_lookup[resource_name]
        used = self.usage[resource_name]
        if used + need.required_units > resource.capacity:
            return False, f"{resource_name} has no remaining capacity."
        if resource.resource_type != need.required_type:
            return False, f"{resource_name} type mismatch for {area}."
        if area in resource.inaccessible_areas:
            return False, f"{resource_name} cannot reach {area}."
        if need.required_skill and need.required_skill not in resource.skills:
            return False, f"{resource_name} lacks required skill {need.required_skill}."
        return True, "valid assignment"

    def _is_pairwise_consistent(self, area_a: str, resource_a: str, area_b: str, resource_b: str) -> bool:
        if resource_a != resource_b:
            return True
        need_a = self.need_lookup[area_a]
        need_b = self.need_lookup[area_b]
        resource = self.resource_lookup[resource_a]
        return (need_a.required_units + need_b.required_units) <= resource.capacity

    def _has_capacity_available(self, area: str, resource_name: str) -> bool:
        need = self.need_lookup[area]
        resource = self.resource_lookup[resource_name]
        return self.usage[resource_name] + need.required_units <= resource.capacity

    def _forward_check(
        self,
        assigned_area: str,
        domains: Dict[str, List[str]],
        assignments: Dict[str, str],
    ) -> bool:
        for need in self.needs:
            area = need.area
            if area in assignments:
                continue
            original = list(domains[area])
            filtered = [candidate for candidate in original if self._has_capacity_available(area, candidate)]
            if filtered != original:
                removed = sorted(set(original) - set(filtered))
                for candidate in removed:
                    self.steps.append(
                        SolverStep(
                            action="prune",
                            variable=area,
                            choice=candidate,
                            detail=f"Forward checking pruned {candidate} after assigning {assigned_area}.",
                        )
                    )
                domains[area] = filtered
            if not domains[area]:
                self.steps.append(
                    SolverStep(
                        action="dead_end",
                        variable=area,
                        choice=None,
                        detail=f"Forward checking removed all candidates for {area}.",
                    )
                )
                return False
        return True

    
    def _revise(
        self,
        area_a: str,
        area_b: str,
        domains: Dict[str, List[str]],
        assignments: Dict[str, str],
    ) -> bool:
        if area_a in assignments:
            return False
        revised = False
        original_domain = list(domains[area_a])
        filtered_domain: List[str] = []

        for candidate in original_domain:
            if not self._has_capacity_available(area_a, candidate):
                continue
            has_support = any(
                self._is_pairwise_consistent(area_a, candidate, area_b, other_candidate)
                for other_candidate in domains[area_b]
            )
            if has_support:
                filtered_domain.append(candidate)
                continue
            revised = True
            self.steps.append(
                SolverStep(
                    action="prune",
                    variable=area_a,
                    choice=candidate,
                    detail=f"AC-3 pruned {candidate} from {area_a}: no support from {area_b}.",
                )
            )

        if filtered_domain != original_domain:
            domains[area_a] = filtered_domain
        return revised

    def _enforce_arc_consistency(
        self,
        domains: Dict[str, List[str]],
        assignments: Dict[str, str],
    ) -> bool:
        queue: Deque[Tuple[str, str]] = deque(
            (area_a, area_b)
            for area_a, neighbors in self.neighbors.items()
            for area_b in neighbors
            if area_a != area_b
        )

        while queue:
            area_a, area_b = queue.popleft()
            if self._revise(area_a, area_b, domains, assignments):
                if not domains[area_a]:
                    self.steps.append(
                        SolverStep(
                            action="dead_end",
                            variable=area_a,
                            choice=None,
                            detail=f"Arc consistency emptied the domain for {area_a}.",
                        )
                    )
                    return False
                for area_c in self.neighbors[area_a]:
                    if area_c != area_b:
                        queue.append((area_c, area_a))
        return True
