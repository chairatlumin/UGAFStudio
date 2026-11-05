# Evidence-Traceable Research Ledger

## Overview

The Research Trajectory Ledger is a persistent state store that records hypotheses, gate outcomes, failure constraints, and evidence pointers for the Hermes auto-researcher workflow.

## Architecture

- **ResearchLedger:** Persistent JSON state
- **LTLf Contracts:** Formal workflow contracts
- **ResearchVerifier:** Deterministic trace verification
- **FailureLearner:** Constraint learning from failures

## Usage

### Verify a trace
```bash
python -m qa_framework.research.cli verify trace.json
```

### Record actions in code
```python
from qa_framework.research.integration import ResearchWorkflow

workflow = ResearchWorkflow()
workflow.record_brief_exists("brief-001")
workflow.record_dispatch("task-001")
result = workflow.verify()
workflow.save()
```
