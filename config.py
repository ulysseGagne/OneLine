# config.py
import re
import unicodedata

# The main neighborhood to map
LOCATION = "Cap-Rouge, Québec, Canada"

def get_slug():
    """Derive a filename-safe slug from LOCATION (uses first part before comma)."""
    name = LOCATION.split(",")[0].strip()
    # Normalize unicode (é → e, etc.)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = name.lower().replace(" ", "-")
    name = re.sub(r"[^a-z0-9\-]", "", name)
    return name

SLUG = get_slug()

# OpenStreetMap filter to only keep drivable/runnable roads
CUSTOM_FILTER = (
    '["highway"]["area"!~"yes"]'
    '["highway"!~"bridleway|bus_guideway|bus_stop|construction|cycleway|elevator|'
    'footway|motorway|motorway_junction|motorway_link|escalator|proposed|construction|'
    'platform|raceway|rest_area|path|service"]'
    '["access"!~"customers|no|private"]'
    '["public_transport"!~"platform"]'
    '["fee"!~"yes"]["foot"!~"no"]'
    '["service"!~"drive-through|driveway|parking_aisle"]'
    '["toll"!~"yes"]'
)

# Total compute time budget in minutes
TIME_BUDGET_MINUTES = 30

# Random seed for reproducibility
SEED = 42

# How far beyond the main neighborhood boundary to include (meters).
# This creates a buffer of secondary nodes around the main area.
MARGIN_METERS = 250
