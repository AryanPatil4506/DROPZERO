"""Single source of truth for every version stamped on stored artifacts."""

APP_VERSION = "0.3.0"
TRANSCRIPT_SCHEMA_VERSION = "1.0"
SEGMENTER_VERSION = "1.0"
# Phase 3 adds text features. Bump on any change to feature definitions or their config.
# text-1.1: pauses between words, repeated three-word phrases (not used by the model).
FEATURE_SCHEMA_VERSION = "text-1.1"
# No retention model exists yet (Phase 5).
MODEL_VERSION: str | None = None
# Phase 4 audio + visual features (video uploads only).
# av-1.2: pitch range per segment (flat vs lively delivery).
AV_FEATURE_SCHEMA_VERSION = "av-1.2"
