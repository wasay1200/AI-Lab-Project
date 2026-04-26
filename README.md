# AI-Based Disaster Relief Resource Allocation System

This project implements a Constraint Satisfaction Problem solver for disaster relief resource allocation with a Streamlit GUI.

## Features

- Defines affected areas as variables and resources as domains
- Enforces constraints for resource type, capacity, required skills, and inaccessible areas
- Uses backtracking search to find valid allocations
- Displays final assignments, rejected choices, and backtracking steps

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```
