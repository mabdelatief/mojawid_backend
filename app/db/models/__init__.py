"""Every ORM model, imported here so the metadata below covers the whole schema. Alembic takes
its target metadata from this module, which guarantees every model is registered."""

from app.db.base import Base
from app.db.models.analysis import Analysis
from app.db.models.rate_limit import RateLimitCounter
from app.db.models.recitation import Recitation, RecitationAyahTiming

metadata = Base.metadata

__all__ = ["Analysis", "RateLimitCounter", "Recitation", "RecitationAyahTiming", "metadata"]
