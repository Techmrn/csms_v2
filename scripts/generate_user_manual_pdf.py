"""
Script to generate the comprehensive CSMS V2 User Operations Manual in PDF format.
Uses ReportLab 4.x with professional typography, running headers/footers, and structured layout.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and print total page numbers and running headers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        if self._pageNumber == 1:
            # Suppress running header/footer on cover page
            return

        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#475569"))

        # Running Header
        self.drawString(
            40,
            A4[1] - 32,
            "CSMS V2 — Central Store Management System | User Operations Manual",
        )
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(40, A4[1] - 36, A4[0] - 40, A4[1] - 36)

        # Running Footer
        self.line(40, 40, A4[0] - 40, 40)
        self.drawString(
            40,
            28,
            "CONFIDENTIAL — Internal Government Directorate / Central Store Document",
        )
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(A4[0] - 40, 28, page_str)
        self.restoreState()


def build_pdf(filename: str) -> None:
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=48,
        bottomMargin=48,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary_color = colors.HexColor("#1e3a8a")  # Deep Navy
    secondary_color = colors.HexColor("#0f766e")  # Dark Teal
    text_color = colors.HexColor("#1e293b")  # Slate 800
    subtext_color = colors.HexColor("#64748b")  # Slate 500

    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=26,
        leading=32,
        textColor=primary_color,
        alignment=0,
    )

    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=13,
        leading=18,
        textColor=secondary_color,
        alignment=0,
    )

    h1_style = ParagraphStyle(
        "SectionH1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=primary_color,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )

    h2_style = ParagraphStyle(
        "SectionH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=secondary_color,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "BodyTextCustom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=text_color,
        spaceBefore=2,
        spaceAfter=4,
    )

    bullet_style = ParagraphStyle(
        "BulletCustom",
        parent=body_style,
        leftIndent=14,
        firstLineIndent=-10,
        spaceBefore=1,
        spaceAfter=2,
    )

    callout_style = ParagraphStyle(
        "CalloutText",
        parent=body_style,
        fontName="Helvetica-Oblique",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1e3a8a"),
    )

    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )

    table_cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=text_color,
    )

    table_code_style = ParagraphStyle(
        "TableCode",
        parent=table_cell_style,
        fontName="Courier",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#0f172a"),
    )

    story = []

    # =========================================================================
    # COVER PAGE
    # =========================================================================
    story.append(Spacer(1, 40))
    story.append(Paragraph("CENTRAL STORE MANAGEMENT SYSTEM", title_style))
    story.append(Paragraph("CSMS V2 — Standard User Operations Manual", subtitle_style))
    story.append(Spacer(1, 8))
    story.append(
        HRFlowable(
            width="100%",
            thickness=3,
            color=primary_color,
            spaceBefore=4,
            spaceAfter=14,
        )
    )

    story.append(
        Paragraph(
            "<b>Document Classification:</b> Official Government Operational Manual<br/>"
            f"<b>Effective Date:</b> Financial Year 2026-27 | Generated: {datetime.now().strftime('%B %d, %Y')}<br/>"
            "<b>System Version:</b> 2.0 (Clean Architecture Rebuild)<br/>"
            "<b>Applicable Entities:</b> Directorate Central Store, Central Press, and Authorized Branch Offices",
            body_style,
        )
    )
    story.append(Spacer(1, 20))

    # Executive Overview Box
    exec_text = """<b>Operational Notice:</b> This manual outlines the daily execution, approval hierarchies, stock movement protocols, and master administration for CSMS V2. All operations strictly observe single-ledger immutability: stock is never directly edited; every change is captured via an atomic, audit-compliant transaction in the official stock register."""
    story.append(
        Table(
            [[Paragraph(exec_text, callout_style)]],
            colWidths=[515],
            style=[
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdfa")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#0d9488")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ],
        )
    )

    story.append(Spacer(1, 30))

    # Table of Contents Preview
    story.append(Paragraph("<b>TABLE OF CONTENTS</b>", h2_style))
    toc_data = [
        ["1.", "System Architecture & Core Business Principles", "Page 2"],
        ["2.", "User Roles, Responsibilities & Access Control", "Page 2"],
        ["3.", "System Navigation, Dashboard & Store Context", "Page 3"],
        ["4.", "Opening Stock Setup (One-Time / Annual Migration)", "Page 3"],
        ["5.", "Manual Physical Indents & Immediate Issue Finalization", "Page 4"],
        ["6.", "Online Section Indents & Approval Workflows", "Page 4"],
        ["7.", "Branch Requisitions & Central Store Dispatches", "Page 5"],
        ["8.", "Supplier Receipts & Asset Acceptance", "Page 5"],
        ["9.", "Petty Purchase (Consumables Only)", "Page 6"],
        ["10.", "Stock Verification, Discrepancies & Adjustments", "Page 6"],
        ["11.", "Unserviceable Consumables & Asset Lifecycles", "Page 7"],
        ["12.", "Official Stock Registers, Audit Trails & PDF Reports", "Page 7"],
    ]
    toc_table = Table(
        [
            [
                Paragraph(f"<b>{c[0]}</b>", body_style),
                Paragraph(c[1], body_style),
                Paragraph(f"<i>{c[2]}</i>", body_style),
            ]
            for c in toc_data
        ],
        colWidths=[30, 420, 65],
    )
    toc_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                (
                    "LINEBELOW",
                    (0, 0),
                    (-1, -1),
                    0.25,
                    colors.HexColor("#e2e8f0"),
                ),
            ]
        )
    )
    story.append(toc_table)

    story.append(PageBreak())

    # =========================================================================
    # SECTION 1: SYSTEM ARCHITECTURE & NON-NEGOTIABLE PRINCIPLES
    # =========================================================================
    story.append(
        Paragraph("1. System Architecture & Core Business Principles", h1_style)
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=primary_color,
            spaceBefore=1,
            spaceAfter=8,
        )
    )
    story.append(
        Paragraph(
            "CSMS V2 is built around rigorous governmental inventory accounting standards. All users must understand these foundational principles:",
            body_style,
        )
    )

    principles = [
        "<b>Stock Belongs to Store, Not to Offices, Sections, or Users:</b> All balances are held by a Store. Directorate has Central Store; Central Press is an independent Branch Office with its own Store.",
        "<b>Consumable vs Asset Category Rules:</b> Items are strictly categorised as either <font color='#1e3a8a'><b>CONSUMABLE</b></font> or <font color='#0f766e'><b>ASSET</b></font>. The legacy term 'MATERIAL' is obsolete.",
        "<b>Consumable Identity is (Store + Financial Year + Item):</b> Consumable ledger balances are tracked per financial year. Assets have a continuous, multi-year lifecycle identified by serial/asset number.",
        "<b>The StockMovement Ledger is the Single Source of Truth:</b> Current stock is derived from immutable transaction entries. Direct database balance overwrites are strictly prohibited.",
        "<b>Compensating Transactions Only:</b> Once an issue, receipt, or transfer is posted, it cannot be modified or deleted. Errors are corrected via authorized compensating transactions.",
        "<b>Atomic Concurrency:</b> Every transaction verifies real-time stock balances inside an atomic database lock to prevent negative stock balances during concurrent operations.",
    ]
    for p in principles:
        story.append(Paragraph(f"• {p}", bullet_style))

    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 2: USER ROLES & ACCESS CONTROL
    # =========================================================================
    story.append(
        Paragraph(
            "2. User Roles, Responsibilities & Access Control", h1_style
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=primary_color,
            spaceBefore=1,
            spaceAfter=8,
        )
    )
    story.append(
        Paragraph(
            "Access to actions within CSMS V2 is controlled by explicit role permissions, organizational scope, and multi-eye verification rules:",
            body_style,
        )
    )

    roles_data = [
        [
            Paragraph("Role Name", table_header_style),
            Paragraph("System Code", table_header_style),
            Paragraph("Scope & Key Responsibilities", table_header_style),
            Paragraph("Test Login", table_header_style),
        ],
        [
            Paragraph("<b>System Administrator</b>", table_cell_style),
            Paragraph("SYSTEM_ADMIN", table_code_style),
            Paragraph(
                "System-wide setup: items, offices, stores, sections, units, roles, and user memberships.",
                table_cell_style,
            ),
            Paragraph("dev_admin", table_code_style),
        ],
        [
            Paragraph("<b>Director / Superintendent</b>", table_cell_style),
            Paragraph("DIRECTOR", table_code_style),
            Paragraph(
                "Executive oversight, institutional requisitions approval, and policy governance.",
                table_cell_style,
            ),
            Paragraph("dev_director", table_code_style),
        ],
        [
            Paragraph(
                "<b>Deputy Superintendent, Stock & Stores</b>", table_cell_style
            ),
            Paragraph("DEPUTY_SUPDT_STORES", table_code_style),
            Paragraph(
                "Central Store Controlling Officer: authorizes stock verifications, adjustments, and branch transfers.",
                table_cell_style,
            ),
            Paragraph("dev_deputy", table_code_style),
        ],
        [
            Paragraph("<b>General Storekeeper</b>", table_cell_style),
            Paragraph("GENERAL_STOREKEEPER", table_code_style),
            Paragraph(
                "Central Store stock custodian: records opening stock, posts manual indents, supplier receipts, and petty purchases.",
                table_cell_style,
            ),
            Paragraph("dev_general_sk", table_code_style),
        ],
        [
            Paragraph("<b>Assistant Storekeeper</b>", table_cell_style),
            Paragraph("ASSISTANT_STOREKEEPER", table_code_style),
            Paragraph(
                "Executes stock entries, receipts, and issues in Central Store alongside the General Storekeeper.",
                table_cell_style,
            ),
            Paragraph("dev_assistant_sk", table_code_style),
        ],
        [
            Paragraph("<b>Branch Head</b>", table_cell_style),
            Paragraph("BRANCH_HEAD", table_code_style),
            Paragraph(
                "Branch Office Controlling Officer (e.g. Central Press): authorizes branch indents, verifications, and adjustments.",
                table_cell_style,
            ),
            Paragraph("dev_press_head", table_code_style),
        ],
        [
            Paragraph("<b>Branch Storekeeper</b>", table_cell_style),
            Paragraph("BRANCH_STOREKEEPER", table_code_style),
            Paragraph(
                "Branch Store stock custodian: handles branch stock movements, branch receipts, and local indents.",
                table_cell_style,
            ),
            Paragraph("dev_press_sk", table_code_style),
        ],
    ]

    r_table = Table(roles_data, colWidths=[120, 100, 215, 80])
    r_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), primary_color),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
            ]
        )
    )
    story.append(r_table)
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "<b>Default Development Password for all test users:</b> <code>Password@1</code>",
            callout_style,
        )
    )

    story.append(PageBreak())

    # =========================================================================
    # SECTION 3 & 4: DASHBOARD, NAVIGATION & OPENING STOCK
    # =========================================================================
    story.append(
        Paragraph(
            "3. System Navigation, Dashboard & Store Context", h1_style
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=primary_color,
            spaceBefore=1,
            spaceAfter=8,
        )
    )
    story.append(
        Paragraph(
            "Upon logging in, users are taken to the <b>Dashboard (/app)</b>. The top header provides critical contextual selectors:",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Active Store Selector:</b> Storekeepers and officers assigned to multiple stores must select the store they are currently operating. All registers, stock counts, and transactions filter by this selection.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Financial Year (FY) Selector:</b> Displays transactions for the selected accounting year (e.g., 2026-27). Closed financial years are read-only.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Real-time Metrics Cards:</b> Displays Current Total Consumable Units in Stock, Active Catalogued Items, and Number of Managed Physical Assets.",
            bullet_style,
        )
    )

    story.append(Spacer(1, 14))

    story.append(
        Paragraph(
            "4. Opening Stock Setup (One-Time / Annual Migration)", h1_style
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=primary_color,
            spaceBefore=1,
            spaceAfter=8,
        )
    )
    story.append(
        Paragraph(
            "Opening stock establishes initial system balances for a store at inception or at the start of an accounting period:",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>No Authorisation Overhead:</b> Storekeepers assigned to a store may enter opening stock directly without Deputy Superintendent or Branch Head pre-approval.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Consumables vs Assets in Single Document:</b> Opening stock entries support mixed items in a single form. Consumable lines post an <code>OPENING</code> StockMovement. Asset lines register the physical asset numbers and create <code>AssetMovement(OPENING)</code> records.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Atomic Posting Guarantee:</b> If any asset serial already exists or a line is invalid, the entire opening stock voucher rolls back atomically.",
            bullet_style,
        )
    )
    story.append(
        Paragraph(
            "• <b>Procedure:</b> Navigate to <b>Stock > Opening Stock</b> > Click <i>+ New Opening Stock</i> > Select Store & FY > Add Items, Units, and Quantities > Click <i>Post Opening Stock</i>.",
            bullet_style,
        )
    )

    story.append(Spacer(1, 14))

    # =========================================================================
    # SECTION 5: MANUAL PHYSICAL INDENTS & ISSUES
    # =========================================================================
    story.append(
        Paragraph(
            "5. Manual Physical Indents & Immediate Issue Finalization", h1_style
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=primary_color,
            spaceBefore=1,
            spaceAfter=8,
        )
    )
    story.append(
        Paragraph(
            "<b>The Physical Voucher Workflow:</b> When an indenting officer arrives at the store with a signed physical paper indent, the Storekeeper records it using the <b>Manual Indent</b> screen.",
            body_style,
        )
    )

    manual_steps = [
        "<b>No Draft State:</b> An approved physical indent is already an authorized document. Saving it in CSMS V2 <b>atomically creates and finalizes the Issue</b> in one step.",
        "<b>Key Data Fields:</b> Item, Unit, <i>Requested Qty</i> (from paper indent), <i>Available Qty</i> (auto-derived by server), <i>Issued Qty</i> (actual quantity physically handed over), and Remarks.",
        "<b>Zero and Partial Issues Permitted:</b> If the requested quantity is 50 but store only has 30, entering Issued=30 is valid. If stock is zero, Issued=0 is valid.",
        "<b>Shortage Rule:</b> Shortages close the manual indent at the actual dispatched quantity. The system <b>does not</b> create a phantom pending balance.",
        "<b>Stock Deduction:</b> Saving the voucher immediately writes an immutable <code>ISSUE</code> entry in the StockMovement ledger and produces an Outward Pass.",
    ]
    for s in manual_steps:
        story.append(Paragraph(f"• {s}", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 6 & 7: ONLINE INDENTS & REQUISITIONS
    # =========================================================================
    story.append(
        Paragraph("6. Online Section Indents & Approval Workflows", h1_style)
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=primary_color,
            spaceBefore=1,
            spaceAfter=8,
        )
    )
    story.append(
        Paragraph(
            "Online Indents allow section users or officers to submit digital demands through the system:",
            body_style,
        )
    )

    online_flow = [
        "<b>Step 1: Submission:</b> Section user creates an indent specifying target store, required items, and demanded quantities (Status: <code>SUBMITTED</code>).",
        "<b>Step 2: Verification / Approval:</b> The Controlling Officer (Deputy Superintendent for Central Store; Branch Head for Branch Store) reviews the request. They may approve, reduce quantities, or reject (Status: <code>APPROVED</code>).",
        "<b>Step 3: Issue Finalization:</b> An assigned Storekeeper opens the approved indent, enters the actual physical quantities issued, and clicks <i>Finalize Issue</i>. Stock is deducted and an Outward Gate Pass is generated.",
    ]
    for f in online_flow:
        story.append(Paragraph(f, body_style))

    story.append(Spacer(1, 14))

    story.append(
        Paragraph(
            "7. Branch Requisitions & Central Store Dispatches", h1_style
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=primary_color,
            spaceBefore=1,
            spaceAfter=8,
        )
    )
    story.append(
        Paragraph(
            "Inter-store transfers between Central Store (Directorate) and Branch Stores (e.g., Central Press) use the **Requisition & Transfer** module:",
            body_style,
        )
    )

    req_flow = [
        "<b>Requisition Creation:</b> Branch Storekeeper raises a Requisition targeting Central Store for needed supplies.",
        "<b>Branch Head Approval:</b> The Branch Head verifies and submits the requisition to Central Store.",
        "<b>Central Store Authorization:</b> The Deputy Superintendent, Stock & Stores reviews and authorizes the requisition.",
        "<b>Dispatch / Issue:</b> Central Store General Storekeeper dispatches the accepted quantities. A <code>TRANSFER_OUT</code> stock movement is posted.",
        "<b>Receipt at Branch:</b> Branch Storekeeper acknowledges receipt of the shipment. A <code>TRANSFER_IN</code> stock movement is automatically posted into the branch store ledger.",
    ]
    for rf in req_flow:
        story.append(Paragraph(f"• {rf}", bullet_style))

    story.append(Spacer(1, 14))

    # =========================================================================
    # SECTION 8: SUPPLIER RECEIPTS & ASSET ACCEPTANCE
    # =========================================================================
    story.append(Paragraph("8. Supplier Receipts & Asset Acceptance", h1_style))
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=primary_color,
            spaceBefore=1,
            spaceAfter=8,
        )
    )
    story.append(
        Paragraph(
            "External procurement items entering the store are accepted via the **Receipts** module:",
            body_style,
        )
    )

    receipt_rules = [
        "<b>Accepted Quantity Enters Stock:</b> If 100 units arrive from a vendor, 10 are rejected during inspection, and 90 are accepted, <b>only the 90 accepted units</b> enter stock.",
        "<b>Consumables:</b> Posted as <code>RECEIPT</code> movements with batch and unit cost details.",
        "<b>Assets:</b> Individual serial/asset identification tags must be entered for each accepted unit. The asset record is created in <code>IN_STORE</code> status.",
    ]
    for rr in receipt_rules:
        story.append(Paragraph(f"• {rr}", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 9 & 10: PETTY PURCHASE & STOCK VERIFICATION
    # =========================================================================
    story.append(
        Paragraph(
            "9. Petty Purchase (Consumables Only — Asset Petty Purchase Prohibited)",
            h1_style,
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=primary_color,
            spaceBefore=1,
            spaceAfter=8,
        )
    )
    story.append(
        Paragraph(
            "Petty Purchase is an acquisition mechanism for urgent consumable purchases. Non-negotiable rules:",
            body_style,
        )
    )

    pp_rules = [
        "<b>Strictly Consumable Only:</b> Asset petty purchase is prohibited by system policy.",
        "<b>Two-Man Rule:</b> Created by the assigned Storekeeper; verified/authorized by the Controlling Officer (Deputy Superintendent for Central Store; Branch Head for branch store).",
        "<b>Immediate Issue Option:</b> If items were bought to satisfy an existing approved indent, immediate issue can be toggled. Purchased IN and Issue OUT are posted <b>atomically</b> under the same posting group ID.",
        "<b>Temporary Items:</b> If an item is not in the permanent master catalog, it is entered as a temporary item (<code>is_temporary=true</code>) to allow stock tracking without delaying operations. It can be promoted to a permanent master item later.",
    ]
    for ppr in pp_rules:
        story.append(Paragraph(f"• {ppr}", bullet_style))

    story.append(Spacer(1, 14))

    story.append(
        Paragraph(
            "10. Stock Verification, Discrepancies & Adjustments", h1_style
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=primary_color,
            spaceBefore=1,
            spaceAfter=8,
        )
    )
    story.append(
        Paragraph(
            "Stock verification enforces periodic physical audits against ledger balances:",
            body_style,
        )
    )

    verif_steps = [
        "<b>1. Count Entry:</b> Storekeeper counts stock and records physical balances against the system snapshot. <i>A stock verification does not change stock balances.</i>",
        "<b>2. Separation of Duties:</b> The person who records the verification count <b>cannot</b> authorize it.",
        "<b>3. Zero Variance:</b> If physical count equals system stock, the verification closes upon authorization with status <code>VERIFIED_MATCH</code>.",
        "<b>4. Variance Handling:</b> If physical count differs, authorizing it places it in <code>AUTHORIZED</code> status, unlocking controlled <b>Adjustment In</b> or <b>Adjustment Out</b> records.",
        "<b>5. Snapshot Re-check:</b> Before an adjustment is posted, the system checks whether stock balances changed after the verification was taken. If stock changed, the adjustment is rejected to prevent false reconciliations.",
    ]
    for vs in verif_steps:
        story.append(Paragraph(f"• {vs}", bullet_style))

    story.append(Spacer(1, 14))

    # =========================================================================
    # SECTION 11 & 12: UNSERVICEABLE & REGISTERS
    # =========================================================================
    story.append(
        Paragraph(
            "11. Unserviceable Consumables & Asset Lifecycles", h1_style
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=primary_color,
            spaceBefore=1,
            spaceAfter=8,
        )
    )
    story.append(
        Paragraph(
            "• <b>Consumables:</b> Damaged or expired consumables are surveyed, authorized by the Controlling Officer, and written off using <code>UNSERVICEABLE</code> stock OUT movements.<br/>"
            "• <b>Assets:</b> Assets move through explicit lifecycle states: <code>IN_STORE</code> $\\rightarrow$ <code>ISSUED</code> $\\rightarrow$ <code>UNDER_REPAIR</code> $\\rightarrow$ <code>UNSERVICEABLE</code> $\\rightarrow$ <code>DISPOSED</code>.",
            body_style,
        )
    )

    story.append(Spacer(1, 14))

    story.append(
        Paragraph(
            "12. Official Stock Registers, Audit Trails & PDF Reports", h1_style
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=primary_color,
            spaceBefore=1,
            spaceAfter=8,
        )
    )
    story.append(
        Paragraph(
            "Every transaction in CSMS V2 is audit-traceable. Users can export standard government register sheets:",
            body_style,
        )
    )

    reports = [
        "<b>Current Stock Register:</b> Real-time balances of all items per store and financial year.",
        "<b>Item Ledger / Daybook:</b> Chronological running balance of all IN and OUT movements for any item.",
        "<b>Asset Register:</b> Complete ledger of physical assets, serials, locations, and current holders.",
        "<b>Outward Gate Pass:</b> Official printable pass with security reference number for dispatched items.",
    ]
    for rp in reports:
        story.append(Paragraph(f"• {rp}", bullet_style))

    story.append(Spacer(1, 20))

    # Sign-off box
    signoff_data = [
        [
            Paragraph("<b>Prepared By:</b>", table_cell_style),
            Paragraph("Central Store Management Rebuild Team", table_cell_style),
            Paragraph("<b>Approved By:</b>", table_cell_style),
            Paragraph(
                "Directorate Stock & Stores Authority", table_cell_style
            ),
        ],
        [
            Paragraph("<b>Version:</b>", table_cell_style),
            Paragraph("2.0 Production Clean Architecture", table_cell_style),
            Paragraph("<b>Status:</b>", table_cell_style),
            Paragraph("Active & Adopted", table_cell_style),
        ],
    ]
    sign_table = Table(signoff_data, colWidths=[90, 165, 90, 170])
    sign_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#94a3b8")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(sign_table)

    # Build the document using NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated User Manual PDF at: {filename}")


if __name__ == "__main__":
    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs"
    )
    os.makedirs(out_dir, exist_ok=True)
    out_pdf = os.path.join(out_dir, "CSMS_V2_User_Operations_Manual.pdf")
    build_pdf(out_pdf)
