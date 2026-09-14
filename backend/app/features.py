"""The 21 BRFSS input features.

FEATURE_ORDER is the exact column order the saved StandardScaler was fitted
on (verified against `scaler.feature_names_in_`). Every DataFrame we build for
inference must use this order, so it lives in one place and is imported
everywhere rather than re-typed.

Ranges come from the BRFSS 2015 codebook and are enforced by the API so that
out-of-domain values are rejected instead of being scaled into nonsense.
"""

FEATURE_ORDER = [
    "HighBP",
    "HighChol",
    "CholCheck",
    "BMI",
    "Smoker",
    "Stroke",
    "HeartDiseaseorAttack",
    "PhysActivity",
    "Fruits",
    "Veggies",
    "HvyAlcoholConsump",
    "AnyHealthcare",
    "NoDocbcCost",
    "GenHlth",
    "MentHlth",
    "PhysHlth",
    "DiffWalk",
    "Sex",
    "Age",
    "Education",
    "Income",
]

# Binary 0/1 indicators.
BINARY_FEATURES = [
    "HighBP",
    "HighChol",
    "CholCheck",
    "Smoker",
    "Stroke",
    "HeartDiseaseorAttack",
    "PhysActivity",
    "Fruits",
    "Veggies",
    "HvyAlcoholConsump",
    "AnyHealthcare",
    "NoDocbcCost",
    "DiffWalk",
    "Sex",
]

# Features with a wider ordinal / continuous domain: (min, max, description).
RANGED_FEATURES = {
    "BMI": (12, 98, "Body mass index"),
    "GenHlth": (1, 5, "General health, 1=excellent to 5=poor"),
    "MentHlth": (0, 30, "Days of poor mental health in the last 30"),
    "PhysHlth": (0, 30, "Days of poor physical health in the last 30"),
    "Age": (1, 13, "Age band, 1=18-24 ... 13=80+"),
    "Education": (1, 6, "Education level, 1=never attended to 6=college graduate"),
    "Income": (1, 8, "Income band, 1=<$10k to 8=>$75k"),
}

TARGET_COLUMN = "Diabetes_binary"

# Bumped whenever preprocessing changes; stored with every inference so an old
# prediction can be reproduced exactly.
PREPROCESSING_VERSION = "v1"


def feature_bounds(name: str) -> tuple[int, int]:
    """Inclusive (min, max) for a feature."""
    if name in RANGED_FEATURES:
        low, high, _ = RANGED_FEATURES[name]
        return low, high
    return 0, 1
