"""Closed local task and robustness evidence records."""

from .model import ComparisonResidual, FaultDisposition, MetricSummary, TaskEvidenceFinding, TaskEvidenceReport
from .protocol import TaskProtocol, validate_task_protocol
from .evaluator import evaluate_task_packages

__all__ = ["ComparisonResidual", "FaultDisposition", "MetricSummary", "TaskEvidenceFinding", "TaskEvidenceReport", "TaskProtocol", "validate_task_protocol", "evaluate_task_packages"]
