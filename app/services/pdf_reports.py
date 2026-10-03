from __future__ import annotations
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def make_register_pdf(title: str, columns: list[tuple[str, str]], rows: list[dict], subtitle: str | None = None) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles['Title'])]
    if subtitle:
        story += [Paragraph(subtitle, styles['Normal']), Spacer(1, 8)]
    data = [[heading for _, heading in columns]]
    for row in rows:
        data.append([str(row.get(key, '') if row.get(key, '') is not None else '') for key, _ in columns])
    if len(data) == 1:
        data.append(['No records found'] + [''] * (len(columns) - 1))
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e9ecef')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return buffer


def make_transfer_gate_pass_pdf(info: dict, items: list[dict]) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=32,
        leftMargin=32,
        topMargin=28,
        bottomMargin=28,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "GPTitle",
        parent=styles["Title"],
        fontSize=14,
        leading=17,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f172a"),
        alignment=1,
    )
    subtitle_style = ParagraphStyle(
        "GPSubtitle",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=13,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f766e"),
        alignment=1,
        spaceAfter=10,
    )
    meta_k_style = ParagraphStyle(
        "GPMetaK",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#475569"),
    )
    meta_v_style = ParagraphStyle(
        "GPMetaV",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
    )
    cell_style = ParagraphStyle(
        "GPCell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
    )
    cell_bold_style = ParagraphStyle(
        "GPCellBold",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1e293b"),
    )
    decl_style = ParagraphStyle(
        "GPDecl",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#334155"),
        fontName="Helvetica-Oblique",
    )
    sig_title_style = ParagraphStyle(
        "GPSigTitle",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9.5,
        alignment=1,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0f172a"),
    )
    sig_sub_style = ParagraphStyle(
        "GPSigSub",
        parent=styles["Normal"],
        fontSize=6.5,
        leading=8.5,
        alignment=1,
        textColor=colors.HexColor("#64748b"),
    )

    story = [
        Paragraph("DIRECTORATE OF PRINTING &amp; STATIONERY — CENTRAL STORE", title_style),
        Paragraph("OUTWARD GATE PASS / DISPATCH VOUCHER", subtitle_style),
    ]

    meta_table_data = [
        [
            Paragraph("Gate Pass / Transfer No.:", meta_k_style),
            Paragraph(str(info.get("transfer_no", "—")), meta_v_style),
            Paragraph("Dispatch Date:", meta_k_style),
            Paragraph(str(info.get("transfer_date", "—")), meta_v_style),
        ],
        [
            Paragraph("Requisition Ref No.:", meta_k_style),
            Paragraph(str(info.get("requisition_no", "—")), meta_v_style),
            Paragraph("Requisition Date:", meta_k_style),
            Paragraph(str(info.get("requisition_date", "—")), meta_v_style),
        ],
        [
            Paragraph("Source Store:", meta_k_style),
            Paragraph(str(info.get("source_store", "Central Store")), meta_v_style),
            Paragraph("Financial Year:", meta_k_style),
            Paragraph(str(info.get("fy_name", "—")), meta_v_style),
        ],
        [
            Paragraph("Destination Store:", meta_k_style),
            Paragraph(str(info.get("destination_store", "—")), meta_v_style),
            Paragraph("Destination Office:", meta_k_style),
            Paragraph(str(info.get("destination_office", "—")), meta_v_style),
        ],
        [
            Paragraph("Vehicle Number:", meta_k_style),
            Paragraph(str(info.get("vehicle_no") or "— (Not specified / Hand Delivery)"), meta_v_style),
            Paragraph("Received By / Carrier:", meta_k_style),
            Paragraph(str(info.get("received_by_name") or "—"), meta_v_style),
        ],
    ]

    meta_table = Table(
        meta_table_data,
        colWidths=[110, 155, 110, 155],
    )
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    headers = [
        Paragraph("#", cell_bold_style),
        Paragraph("Item Code", cell_bold_style),
        Paragraph("Item Name &amp; Description", cell_bold_style),
        Paragraph("Unit", cell_bold_style),
        Paragraph("Dispatched Qty", cell_bold_style),
        Paragraph("Remarks / Assets", cell_bold_style),
    ]
    items_table_data = [headers]

    for idx, item in enumerate(items, start=1):
        items_table_data.append([
            Paragraph(str(idx), cell_style),
            Paragraph(str(item.get("item_code", "—")), cell_bold_style),
            Paragraph(str(item.get("item_name", "—")), cell_style),
            Paragraph(str(item.get("unit_code", "—")), cell_style),
            Paragraph(str(item.get("quantity", "0")), cell_bold_style),
            Paragraph(str(item.get("remarks") or item.get("asset_numbers") or "—"), cell_style),
        ])

    if len(items_table_data) == 1:
        items_table_data.append([
            Paragraph("—", cell_style),
            Paragraph("No items dispatched", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
            Paragraph("", cell_style),
        ])

    items_table = Table(
        items_table_data,
        colWidths=[24, 75, 205, 55, 75, 96],
        repeatRows=1,
    )
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#94a3b8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 10))

    cert_box = Table(
        [[
            Paragraph(
                "<b>Security &amp; Gate Declaration:</b> Certified that the materials/items listed above have been verified, "
                "properly accounted for in the Central Store ledger, and authorized for outward transit to the destination branch store "
                "under the referenced requisition. The security personnel at the gate are authorized to permit outward passage.",
                decl_style,
            )
        ]],
        colWidths=[530],
    )
    cert_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(cert_box)
    story.append(Spacer(1, 14))

    dispatched_by_label = info.get("dispatched_by_name") or "Central Storekeeper"
    sig_data = [
        [
            Paragraph(f"<br/><br/><br/>______________________<br/><b>{dispatched_by_label}</b>", sig_title_style),
            Paragraph("<br/><br/><br/>______________________<br/><b>Security / Gate Officer</b>", sig_title_style),
            Paragraph(f"<br/><br/><br/>______________________<br/><b>{info.get('received_by_name') or 'Carrier / Driver'}</b>", sig_title_style),
            Paragraph("<br/><br/><br/>______________________<br/><b>Branch Storekeeper</b>", sig_title_style),
        ],
        [
            Paragraph("Prepared &amp; Dispatched By<br/>(Central Store)", sig_sub_style),
            Paragraph("Outward Verification &amp; Seal<br/>(Gate Pass Control)", sig_sub_style),
            Paragraph("Received For Transit<br/>(Carrier / Vehicle Driver)", sig_sub_style),
            Paragraph("Received In Good Condition<br/>(Branch Acknowledgment)", sig_sub_style),
        ],
    ]
    sig_table = Table(sig_data, colWidths=[132, 133, 132, 133])
    sig_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(sig_table)

    doc.build(story)
    buffer.seek(0)
    return buffer

