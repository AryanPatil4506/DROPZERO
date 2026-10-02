"""Print a fresh DROPZERO_MEDIA_KEY (32 random bytes, base64). Put it in .env; never commit it.
Losing the key makes existing encrypted media and artifacts unreadable."""

import base64
import os

print(f"DROPZERO_MEDIA_KEY={base64.b64encode(os.urandom(32)).decode()}")
