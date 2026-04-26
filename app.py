from __future__ import annotations

import json
from typing import List, Set

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
