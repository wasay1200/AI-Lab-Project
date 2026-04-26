from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, List, Set, Tuple

import pandas as pd
import streamlit as st

from csp_engine import AreaNeed, DisasterReliefCSP, Resource


def parse_csv_set(raw: str) -> Set[str]:
    values = [item.strip() for item in raw.split(",")]
    return {item for item in values if item}


def load_resources(df: pd.DataFrame) -> List[Resource]:
    resources: List[Resource] = []
    for _, row in df.iterrows():
        resources.append(
            Resource(
                name=str(row["name"]).strip(),
                resource_type=str(row["type"]).strip(),
                capacity=int(row["capacity"]),
                inaccessible_areas=parse_csv_set(str(row["inaccessible_areas"])),
                skills=parse_csv_set(str(row["skills"])),
            )
        )
    return resources


def load_needs(df: pd.DataFrame) -> List[AreaNeed]:
    needs: List[AreaNeed] = []
    for _, row in df.iterrows():
        required_skill = str(row["required_skill"]).strip()
        needs.append(
            AreaNeed(
                area=str(row["area"]).strip(),
                required_type=str(row["required_type"]).strip(),
                required_units=int(row["required_units"]),
                required_skill=required_skill if required_skill else None,
            )
        )
    return needs


def validate_input(resources: List[Resource], needs: List[AreaNeed]) -> List[str]:
    errors: List[str] = []
    resource_names = [resource.name for resource in resources]
    if len(resource_names) != len(set(resource_names)):
        errors.append("Resource names must be unique.")
    area_names = [need.area for need in needs]
    if len(area_names) != len(set(area_names)):
        errors.append("Area names must be unique.")
    if any(resource.capacity <= 0 for resource in resources):
        errors.append("Every resource capacity must be greater than zero.")
    if any(need.required_units <= 0 for need in needs):
        errors.append("Every area required_units value must be greater than zero.")
    return errors


def to_step_table(steps) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "action": step.action,
                "area": step.variable,
                "resource": step.choice if step.choice else "-",
                "detail": step.detail,
            }
            for step in steps
        ]
    )


def diagnose_failure(
    solver: DisasterReliefCSP,
    needs: List[AreaNeed],
    resources: List[Resource],
) -> Tuple[List[str], List[Dict[str, str]]]:
    headline_reasons: List[str] = []
    per_area_rows: List[Dict[str, str]] = []

    demand_by_requirement: Dict[Tuple[str, str], int] = defaultdict(int)
    for need in needs:
        key = (need.required_type, need.required_skill or "")
        demand_by_requirement[key] += need.required_units

    for (req_type, req_skill), demanded in demand_by_requirement.items():
        matching = [
            resource
            for resource in resources
            if resource.resource_type == req_type
            and (not req_skill or req_skill in resource.skills)
        ]
        total_capacity = sum(resource.capacity for resource in matching)
        if total_capacity < demanded:
            skill_part = f" with skill '{req_skill}'" if req_skill else ""
            headline_reasons.append(
                f"Capacity shortfall: type '{req_type}'{skill_part} has total capacity "
                f"{total_capacity}, but combined demand is {demanded} units."
            )

    empty_areas = [area for area, domain in solver.domains.items() if not domain]
    for area in empty_areas:
        need = solver.need_lookup[area]
        type_matches = [r for r in resources if r.resource_type == need.required_type]

        if not type_matches:
            per_area_rows.append(
                {
                    "area": area,
                    "blocked_by": "type",
                    "detail": f"No resource of type '{need.required_type}' exists.",
                }
            )
            continue

        for resource in type_matches:
            if area in resource.inaccessible_areas:
                reason = f"{resource.name} cannot reach {area} (inaccessible)."
                blocked_by = "accessibility"
            elif need.required_skill and need.required_skill not in resource.skills:
                reason = f"{resource.name} lacks required skill '{need.required_skill}'."
                blocked_by = "skill"
            elif resource.capacity < need.required_units:
                reason = (
                    f"{resource.name} capacity {resource.capacity} < required "
                    f"{need.required_units} units."
                )
                blocked_by = "capacity"
            else:
                reason = (
                    f"{resource.name} pruned during propagation "
                    f"(capacity contention with another area)."
                )
                blocked_by = "contention"
            per_area_rows.append(
                {"area": area, "blocked_by": blocked_by, "detail": reason}
            )

    if not headline_reasons and not per_area_rows:
        headline_reasons.append(
            "Per-area constraints are individually satisfiable, but no joint assignment "
            "respects all pairwise capacity constraints. Increase a resource's capacity "
            "or add another matching resource."
        )

    return headline_reasons, per_area_rows


def build_demo_scenarios() -> dict:
    balanced_resources = pd.DataFrame(
        [
            {"name": "RescueTeam_A", "type": "rescue_team", "capacity": 2, "inaccessible_areas": "Zone_D", "skills": "water_rescue"},
            {"name": "RescueTeam_B", "type": "rescue_team", "capacity": 1, "inaccessible_areas": "", "skills": "mountain_rescue"},
            {"name": "Ambulance_1", "type": "ambulance", "capacity": 2, "inaccessible_areas": "Zone_C", "skills": "critical_care"},
            {"name": "Shelter_Alpha", "type": "shelter", "capacity": 2, "inaccessible_areas": "", "skills": ""},
        ]
    )
    balanced_needs = pd.DataFrame(
        [
            {"area": "Zone_A", "required_type": "rescue_team", "required_units": 1, "required_skill": "water_rescue"},
            {"area": "Zone_B", "required_type": "ambulance", "required_units": 1, "required_skill": ""},
            {"area": "Zone_C", "required_type": "shelter", "required_units": 1, "required_skill": ""},
        ]
    )
    high_pressure_resources = pd.DataFrame(
        [
            {"name": "RescueTeam_A", "type": "rescue_team", "capacity": 1, "inaccessible_areas": "Zone_C", "skills": "water_rescue"},
            {"name": "Ambulance_1", "type": "ambulance", "capacity": 1, "inaccessible_areas": "Zone_D", "skills": "critical_care"},
            {"name": "Shelter_Alpha", "type": "shelter", "capacity": 1, "inaccessible_areas": "", "skills": ""},
        ]
    )
    high_pressure_needs = pd.DataFrame(
        [
            {"area": "Zone_A", "required_type": "rescue_team", "required_units": 1, "required_skill": "water_rescue"},
            {"area": "Zone_B", "required_type": "rescue_team", "required_units": 1, "required_skill": ""},
            {"area": "Zone_C", "required_type": "ambulance", "required_units": 1, "required_skill": ""},
            {"area": "Zone_D", "required_type": "shelter", "required_units": 1, "required_skill": ""},
        ]
    )
    return {
        "Balanced Demo": (balanced_resources, balanced_needs),
        "High Pressure Demo": (high_pressure_resources, high_pressure_needs),
    }


def main() -> None:
    st.set_page_config(page_title="Disaster Relief CSP Allocator", layout="wide")
    st.title("AI-Based Disaster Relief Resource Allocation")
    st.write("Constraint Satisfaction Problem solver with visual assignment and backtracking steps.")

    scenarios = build_demo_scenarios()

    if "resources_data" not in st.session_state:
        st.session_state["resources_data"] = scenarios["Balanced Demo"][0].copy()
    if "needs_data" not in st.session_state:
        st.session_state["needs_data"] = scenarios["Balanced Demo"][1].copy()
    if "scenario_version" not in st.session_state:
        st.session_state["scenario_version"] = 0

    controls_col, _ = st.columns([2, 5])
    with controls_col:
        selected_scenario = st.selectbox("Quick Scenario", options=list(scenarios.keys()))
        if st.button("Load Scenario", use_container_width=True):
            st.session_state["resources_data"] = scenarios[selected_scenario][0].copy()
            st.session_state["needs_data"] = scenarios[selected_scenario][1].copy()
            st.session_state["scenario_version"] += 1
            st.rerun()

    version = st.session_state["scenario_version"]

    left, right = st.columns(2)

    with left:
        st.subheader("Resources")
        resources_df = st.data_editor(
            st.session_state["resources_data"],
            num_rows="dynamic",
            use_container_width=True,
            key=f"resources_table_{version}",
        )

    with right:
        st.subheader("Area Needs")
        needs_df = st.data_editor(
            st.session_state["needs_data"],
            num_rows="dynamic",
            use_container_width=True,
            key=f"needs_table_{version}",
        )

    if st.button("Run CSP Allocation", type="primary", use_container_width=True):
        try:
            resources = load_resources(resources_df)
            needs = load_needs(needs_df)
        except Exception:
            st.error("Input values are invalid. Ensure numeric columns contain valid numbers.")
            return

        errors = validate_input(resources, needs)
        if errors:
            for error in errors:
                st.error(error)
            return

        solver = DisasterReliefCSP(needs=needs, resources=resources)
        solved, assignment, steps = solver.solve()

        domain_data = {area: domain for area, domain in solver.domains.items()}
        st.subheader("Domains by Area")
        st.json(domain_data)

        if solved:
            st.success("Valid allocation found.")
            assignment_table = pd.DataFrame(
                [{"area": area, "resource": resource} for area, resource in assignment.items()]
            )
            st.subheader("Final Allocation")
            st.dataframe(assignment_table, use_container_width=True)
        else:
            st.error("No valid allocation found. The constraints below blocked it:")
            headline_reasons, per_area_rows = diagnose_failure(solver, needs, resources)

            for reason in headline_reasons:
                st.warning(reason)

            if per_area_rows:
                st.subheader("Blocked Areas")
                blocked_df = pd.DataFrame(per_area_rows)
                st.dataframe(blocked_df, use_container_width=True)

            dead_end_steps = [step for step in steps if step.action == "dead_end"]
            if dead_end_steps:
                with st.expander("Solver dead-end events"):
                    dead_end_df = pd.DataFrame(
                        [
                            {"area": step.variable, "detail": step.detail}
                            for step in dead_end_steps
                        ]
                    )
                    st.dataframe(dead_end_df, use_container_width=True)

        step_table = to_step_table(steps)
        action_counts = step_table["action"].value_counts().rename_axis("action").reset_index(name="count")
        metrics_col1, metrics_col2, metrics_col3, metrics_col4 = st.columns(4)
        metrics_col1.metric("Total Steps", len(step_table))
        metrics_col2.metric("Assignments", int((step_table["action"] == "assign").sum()))
        metrics_col3.metric("Rejections", int((step_table["action"] == "reject").sum()))
        metrics_col4.metric("Backtracks", int((step_table["action"] == "backtrack").sum()))

        st.subheader("Solver Analytics")
        st.bar_chart(action_counts.set_index("action"))

        st.subheader("Solver Steps")
        selected_actions = st.multiselect(
            "Filter step actions",
            options=sorted(step_table["action"].unique().tolist()),
            default=sorted(step_table["action"].unique().tolist()),
        )
        st.dataframe(step_table[step_table["action"].isin(selected_actions)], use_container_width=True)

        st.subheader("Allocation JSON")
        allocation_json = json.dumps(assignment, indent=2)
        st.code(allocation_json, language="json")


if __name__ == "__main__":
    main()
