from app.paper_store.schemas.item import PaperItemBase, PaperItemCreate, PaperItemRead
from app.paper_store.schemas.receipt import (
    PaperReceiptCreate,
    PaperReceiptLineCreate,
    PaperReceiptLineRead,
    PaperReceiptRead,
)
from app.paper_store.schemas.indent_issue import (
    PaperIndentLineCreate,
    PaperIndentLineRead,
    PaperIndentRead,
    PaperIssueLineRead,
    PaperIssueRead,
    PaperManualIndentCreate,
    PaperOnlineIndentCreate,
)
from app.paper_store.schemas.transfer import (
    PaperTransferCreateRequest,
    PaperTransferDispatchLine,
    PaperTransferDispatchRequest,
    PaperTransferLineCreate,
    PaperTransferLineRead,
    PaperTransferRead,
    PaperTransferReceiveLine,
    PaperTransferReceiveRequest,
)

__all__ = [
    "PaperItemBase",
    "PaperItemCreate",
    "PaperItemRead",
    "PaperReceiptCreate",
    "PaperReceiptLineCreate",
    "PaperReceiptLineRead",
    "PaperReceiptRead",
    "PaperIndentLineCreate",
    "PaperIndentLineRead",
    "PaperIndentRead",
    "PaperIssueLineRead",
    "PaperIssueRead",
    "PaperManualIndentCreate",
    "PaperOnlineIndentCreate",
    "PaperTransferCreateRequest",
    "PaperTransferDispatchLine",
    "PaperTransferDispatchRequest",
    "PaperTransferLineCreate",
    "PaperTransferLineRead",
    "PaperTransferRead",
    "PaperTransferReceiveLine",
    "PaperTransferReceiveRequest",
]
