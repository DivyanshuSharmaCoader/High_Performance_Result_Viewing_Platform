"""Imports every module's models so ``Base.metadata`` is complete (Alembic, tests)."""

from app.core import tables as _core_tables  # noqa: F401
from app.core.models import Base
from app.modules.academics import models as _academics  # noqa: F401
from app.modules.audit import models as _audit  # noqa: F401
from app.modules.branding import models as _branding  # noqa: F401
from app.modules.directory import models as _directory  # noqa: F401
from app.modules.entitlements import models as _entitlements  # noqa: F401
from app.modules.examinations import models as _examinations  # noqa: F401
from app.modules.files import models as _files  # noqa: F401
from app.modules.grading import models as _grading  # noqa: F401
from app.modules.identity import models as _identity  # noqa: F401
from app.modules.ingestion import models as _ingestion  # noqa: F401
from app.modules.marks import models as _marks  # noqa: F401
from app.modules.tenancy import models as _tenancy  # noqa: F401

metadata = Base.metadata
