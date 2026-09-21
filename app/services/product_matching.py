from app.services.normalization import normalize_lookup_key

# Deliberately small and reviewed. These are known Arc'teryx renames, not fuzzy matches.
_MODEL_ALIASES = {
    "atomlthoody": "atomhoody",
    "atomheavyweighthoody": "atomsvhoody",
    "atomarhoody": "atomsvhoody",
}


def canonical_model_key(model_name: str) -> str:
    key = normalize_lookup_key(model_name)
    return _MODEL_ALIASES.get(key, key)
