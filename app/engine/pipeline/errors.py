"""Expected failures of an analysis, each with the stable code the API returns."""


class AnalysisError(ValueError):
    """An analysis that can't produce a result, for a reason the reciter can act on."""

    code = "analysis_failed"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidReadingSettings(AnalysisError):
    code = "invalid_reading_settings"


class InvalidTextSelection(AnalysisError):
    code = "invalid_text_selection"


class NoRecitationHeard(AnalysisError):
    code = "no_recitation_heard"


class AyahNotRecognised(AnalysisError):
    code = "ayah_not_recognised"
