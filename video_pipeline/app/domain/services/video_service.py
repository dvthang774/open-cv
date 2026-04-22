class VideoService:
    """
    POC-level state machine.
    """

    allowed = {
        "UPLOADING": {"UPLOADED"},
        "UPLOADED": {"SEGMENTING"},
        "SEGMENTING": {"SEGMENTED", "FAILED"},
        "SEGMENTED": {"AI_PROCESSING"},
        "AI_PROCESSING": {"DONE", "FAILED"},
        "DONE": set(),
        "FAILED": set(),
    }

    def can_transition(self, from_status: str, to_status: str) -> bool:
        return to_status in self.allowed.get(from_status, set())

