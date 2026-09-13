"""Shared test double for houston.model_runner.ModelRunner, used by
test_agent.py and test_fix_agent.py -- both agents inject the same port."""
from houston.model_runner import ModelOutcome, ModelRun


class FakeRunner:
    def __init__(
        self,
        outcome: ModelOutcome,
        raises: BaseException | None = None,
    ) -> None:
        self.calls: list[ModelRun] = []
        self.outcome = outcome
        self.raises = raises

    def run(self, request: ModelRun) -> ModelOutcome:
        self.calls.append(request)
        if self.raises is not None:
            raise self.raises
        return self.outcome


def outcome(stdout: str, returncode: int = 0, stderr: str = "") -> ModelOutcome:
    return ModelOutcome(returncode=returncode, stdout=stdout, stderr=stderr)
