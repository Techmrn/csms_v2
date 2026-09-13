"""Merge the two Asset Phase 2 development heads.

The repository accumulated two parallel Alembic revisions during Asset Phase 2:
- f7f8467a4dae, which descends from the earlier mapping-model migration
- 0009_asset_phase2_completion, which descends directly from 0008_assets

Both represent the same final Asset Phase 2 persistence work.  The 0009
revision is idempotent, so applying it after the f7 branch safely converges the
existing schema; this revision then records a single migration head.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010_merge_asset_phase2_heads"
down_revision: Union[str, Sequence[str], None] = (
    "0009_asset_phase2_completion",
    "f7f8467a4dae",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No schema operation is needed. The two parent revisions already contain
    # the required Asset Phase 2 structures; this revision only joins history.
    pass


def downgrade() -> None:
    # No schema operation. Downgrading the merge exposes the two parent heads.
    pass
