import os

from hypothesis import settings

settings.register_profile("dev")
settings.register_profile("ci", deadline=None, print_blob=True, max_examples=200)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
