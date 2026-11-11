import os

# Use an in-memory DB for tests before the app module is imported.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
