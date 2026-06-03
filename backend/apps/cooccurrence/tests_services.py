"""Convention-named discovery shim for apps/cooccurrence/services.py.

The mutation gate only discovers a file named ``tests_<stem>.py`` in the same
directory as ``<stem>.py``. The real, proven coverage for ``services.py`` lives
in the historically-misnamed ``tests_services_helpers.py`` next to this file.
Rather than duplicate ~470 lines of asserted behaviour (which would drift), this
shim re-exports every test class from that module under the discoverable name so
the same assertions run when the gate collects ``tests_services.py``.

All re-exported tests are ``SimpleTestCase`` and touch no database, network, or
filesystem — the GA4 fetch helpers are mocked in the source module — so this is
hang-safe for the mutation gate.
"""

from __future__ import annotations

from apps.cooccurrence.tests_services_helpers import (  # noqa: F401
    BuildAdjacencyGraphTests,
    BuildCooccurrenceCountsTests,
    ComputeLogLikelihoodTests,
    ComputeMemberStrengthsTests,
    ComputePairScoresTests,
    ComputeWeightedScoreTests,
    DisabledCoSignalTests,
    ExtractContentSignalsTests,
    ExtractCoSettingsTests,
    ExtractSignalWeightsTests,
    FallbackSignalDiagnosticsTests,
    FetchGa4NoCredentialsSkipTests,
    FindConnectedComponentsTests,
    LlrSigmoidTests,
    MakeGa4ReportBodyTests,
    ProcessGa4RowsTests,
)

__all__ = [
    "BuildAdjacencyGraphTests",
    "BuildCooccurrenceCountsTests",
    "ComputeLogLikelihoodTests",
    "ComputeMemberStrengthsTests",
    "ComputePairScoresTests",
    "ComputeWeightedScoreTests",
    "DisabledCoSignalTests",
    "ExtractContentSignalsTests",
    "ExtractCoSettingsTests",
    "ExtractSignalWeightsTests",
    "FallbackSignalDiagnosticsTests",
    "FetchGa4NoCredentialsSkipTests",
    "FindConnectedComponentsTests",
    "LlrSigmoidTests",
    "MakeGa4ReportBodyTests",
    "ProcessGa4RowsTests",
]
