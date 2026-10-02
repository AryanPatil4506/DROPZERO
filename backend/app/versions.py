"""Single source of truth for every version stamped on stored artifacts."""

APP_VERSION = "0.3.0"
TRANSCRIPT_SCHEMA_VERSION = "1.0"
SEGMENTER_VERSION = "1.0"
# Phase 3 adds text features. Bump on any change to feature definitions or their config.
FEATURE_SCHEMA_VERSION = "text-1.0"
# No retention model exists yet (Phase 5).
MODEL_VERSION: str | None = None
# Phase 4 audio + visual features (video uploads only).
AV_FEATURE_SCHEMA_VERSION = "av-1.0"
