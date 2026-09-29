"""
Generates the authoritative CSMS V2 OCI Deployment & Maintenance Manifest in PDF format.
Uses ReportLab with high-fidelity corporate typography, running headers/footers, and clean tables.
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
    Preformatted,
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
            # Suppress header on cover page
            return

        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#475569"))

        # Running Header
        self.drawString(
            40,
            A4[1] - 32,
            "CSMS V2 — OCI Production Deployment & Maintenance Manifest",
        )
        self.drawRightString(
            A4[0] - 40,
            A4[1] - 32,
            "CONFIDENTIAL / PRODUCTION OPS",
        )
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.6)
        self.line(40, A4[1] - 36, A4[0] - 40, A4[1] - 36)

        # Running Footer
        self.line(40, 36, A4[0] - 40, 36)
        self.drawString(
            40,
            24,
            "Central Store Management System V2 • Oracle Cloud Infrastructure (Ampere A1 / 24GB)",
        )
        self.drawRightString(
            A4[0] - 40,
            24,
            f"Page {self._pageNumber} of {page_count}",
        )
        self.restoreState()


def build_pdf(output_path: str):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=46,
        bottomMargin=46,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CoverTitle",
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    )
    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        fontName="Helvetica",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#334155"),
        spaceAfter=14,
    )
    badge_style = ParagraphStyle(
        "BadgeText",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e40af"),
    )
    h1_style = ParagraphStyle(
        "H1",
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True,
    )
    h2_style = ParagraphStyle(
        "H2",
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "Body",
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )
    body_bold = ParagraphStyle(
        "BodyBold",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#0f172a"),
    )
    code_inline = ParagraphStyle(
        "CodeInline",
        fontName="Courier",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#0f172a"),
    )
    code_block = ParagraphStyle(
        "CodeBlock",
        fontName="Courier",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
    )
    table_cell = ParagraphStyle(
        "TableCell",
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1e293b"),
    )
    table_cell_bold = ParagraphStyle(
        "TableCellBold",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#0f172a"),
    )
    table_cell_code = ParagraphStyle(
        "TableCellCode",
        fontName="Courier",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
    )

    story = []

    # =========================================================================
    # COVER / HEADER
    # =========================================================================
    story.append(Spacer(1, 10))
    story.append(Paragraph("CENTRAL STORE MANAGEMENT SYSTEM V2", badge_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph("Production Deployment & Operations Manifest", title_style))
    story.append(
        Paragraph(
            "Authoritative Infrastructure, Architecture Topology, Secrets Register & Maintenance Standard Operating Procedures (SOP)",
            subtitle_style,
        )
    )

    metadata_data = [
        [
            Paragraph("<b>Target Host:</b> Oracle Cloud (Ampere A1 Flex)", table_cell),
            Paragraph("<b>Production Domain:</b> https://pdsms.online", table_cell_bold),
        ],
        [
            Paragraph("<b>Compute Specs:</b> 4 OCPUs (ARM64) • 24 GB RAM", table_cell),
            Paragraph("<b>Public IP:</b> 129.225.122.78", table_cell),
        ],
        [
            Paragraph("<b>Database:</b> PostgreSQL 18 (4GB Shared Buffers)", table_cell),
            Paragraph("<b>Reverse Proxy:</b> Nginx Alpine (Ports 80 & 443 SSL)", table_cell),
        ],
        [
            Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%d %B %Y')}", table_cell),
            Paragraph("<b>Security Classification:</b> STRICTLY CONFIDENTIAL", table_cell_bold),
        ],
    ]
    t_meta = Table(metadata_data, colWidths=[260, 255])
    t_meta.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_meta)
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284c7"), spaceAfter=10))

    # =========================================================================
    # SECTION 1: ARCHITECTURE TOPOLOGY
    # =========================================================================
    story.append(Paragraph("1. System Architecture & Component Boundaries", h1_style))
    story.append(
        Paragraph(
            "The CSMS V2 production instance on Oracle Cloud Infrastructure is organized into a strictly isolated, 3-tier containerized stack running on Docker Engine. "
            "Public ingress traffic is accepted exclusively by Nginx on ports 80 and 8000. All backend application workers and database processes communicate across a private, internal Docker bridge network (<code>csms_internal_network</code>) with zero outside internet exposure.",
            body_style,
        )
    )

    topo_data = [
        [
            Paragraph("<b>Tier</b>", table_cell_bold),
            Paragraph("<b>Container Name</b>", table_cell_bold),
            Paragraph("<b>Image & Runtime</b>", table_cell_bold),
            Paragraph("<b>Exposed Ports / Network Scope</b>", table_cell_bold),
            Paragraph("<b>Key Responsibilities</b>", table_cell_bold),
        ],
        [
            Paragraph("<b>Tier 1<br/>Edge Proxy</b>", table_cell),
            Paragraph("<code>csms_nginx</code>", table_cell_code),
            Paragraph("<code>nginx:alpine</code>", table_cell_code),
            Paragraph("<b>Host 80:80<br/>Host 8000:8000</b>", table_cell_bold),
            Paragraph("Rate limiting (anti-brute-force), SSL termination readiness, client buffering, security headers, Gzip compression.", table_cell),
        ],
        [
            Paragraph("<b>Tier 2<br/>Application</b>", table_cell),
            Paragraph("<code>csms_app</code>", table_cell_code),
            Paragraph("Python 3.12 (Bookworm)<br/>FastAPI / Uvicorn (4 workers)", table_cell),
            Paragraph("<b>Internal:8000</b><br/>(No host ports)", table_cell),
            Paragraph("Business domain logic, transaction postings, inventory ledgers, JWT authentication, PDF reporting.", table_cell),
        ],
        [
            Paragraph("<b>Tier 3<br/>Database</b>", table_cell),
            Paragraph("<code>csms_db</code>", table_cell_code),
            Paragraph("PostgreSQL 18<br/>4GB Shared Buffers", table_cell),
            Paragraph("<b>Internal:5432</b><br/>Loopback 127.0.0.1:5432", table_cell),
            Paragraph("Authoritative ACID stock movement ledger, persistent volume <code>csms_v2_pgdata</code>, 14GB RAM ceiling.", table_cell),
        ],
    ]
    t_topo = Table(topo_data, colWidths=[65, 80, 115, 110, 145])
    t_topo.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#94a3b8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(t_topo)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 2: SERVER-ONLY VS GITHUB MANIFEST
    # =========================================================================
    story.append(Paragraph("2. Asset Manifest: Server-Only vs. GitHub Repository", h1_style))
    story.append(
        Paragraph(
            "To safeguard confidential production credentials and maintain operational integrity, repository code is strictly segregated from host-specific production artifacts. The following matrix specifies where every component lives and its confidentiality level:",
            body_style,
        )
    )

    manifest_data = [
        [
            Paragraph("<b>File / Component Path</b>", table_cell_bold),
            Paragraph("<b>Location</b>", table_cell_bold),
            Paragraph("<b>In GitHub?</b>", table_cell_bold),
            Paragraph("<b>Purpose & Security Classification</b>", table_cell_bold),
        ],
        [
            Paragraph("<code>/opt/csms_v2/.env</code>", table_cell_code),
            Paragraph("Server Only", table_cell_bold),
            Paragraph("<font color='#dc2626'><b>NEVER</b></font>", table_cell),
            Paragraph("Contains live PostgreSQL credentials, DB passwords, and cryptographic JWT secret key.", table_cell),
        ],
        [
            Paragraph("<code>/opt/csms_v2/docker-compose.prod.yml</code>", table_cell_code),
            Paragraph("Server Only", table_cell_bold),
            Paragraph("<font color='#d97706'><b>NO</b></font>", table_cell),
            Paragraph("3-tier production orchestration definition tailored for OCI 4 OCPU / 24GB instance.", table_cell),
        ],
        [
            Paragraph("<code>/opt/csms_v2/nginx/default.conf</code>", table_cell_code),
            Paragraph("Server Only", table_cell_bold),
            Paragraph("<font color='#d97706'><b>NO</b></font>", table_cell),
            Paragraph("Nginx reverse proxy with catch-all scanner drop rules (444 / reject handshake), rate limits, and SSL.", table_cell),
        ],
        [
            Paragraph("<code>/opt/csms_v2/certbot/conf/</code>", table_cell_code),
            Paragraph("Server Only", table_cell_bold),
            Paragraph("<font color='#dc2626'><b>NEVER</b></font>", table_cell),
            Paragraph("Let's Encrypt live SSL/TLS certificates and cryptographic private keys.", table_cell),
        ],
        [
            Paragraph("<code>/opt/csms_v2/certbot/www/</code>", table_cell_code),
            Paragraph("Server Only", table_cell_bold),
            Paragraph("<font color='#d97706'><b>NO</b></font>", table_cell),
            Paragraph("ACME challenge webroot directory enabling zero-downtime certificate renewals.", table_cell),
        ],
        [
            Paragraph("<code>/opt/csms_v2/scripts/backup_db.sh</code>", table_cell_code),
            Paragraph("Server Only", table_cell_bold),
            Paragraph("<font color='#d97706'><b>NO</b></font>", table_cell),
            Paragraph("Automated nightly database backup script with 14-day retention policy.", table_cell),
        ],
        [
            Paragraph("<code>/opt/csms_v2/backups/*.sql.gz</code>", table_cell_code),
            Paragraph("Server Only", table_cell_bold),
            Paragraph("<font color='#dc2626'><b>NEVER</b></font>", table_cell),
            Paragraph("Physical compressed SQL database dumps created daily at 02:00 AM.", table_cell),
        ],
        [
            Paragraph("Docker Volume <code>csms_v2_pgdata</code>", table_cell_code),
            Paragraph("Server Only", table_cell_bold),
            Paragraph("<font color='#dc2626'><b>NEVER</b></font>", table_cell),
            Paragraph("PostgreSQL 18 physical cluster mounted to <code>/var/lib/postgresql</code> on NVMe disk.", table_cell),
        ],
        [
            Paragraph("<code>/app</code> (Application Source)", table_cell_code),
            Paragraph("Server & GitHub", table_cell),
            Paragraph("<font color='#16a34a'><b>YES</b></font>", table_cell),
            Paragraph("Core FastAPI Python codebase, web UI routes, Jinja templates, service layer, posting engine.", table_cell),
        ],
        [
            Paragraph("<code>/alembic</code> (Migrations)", table_cell_code),
            Paragraph("Server & GitHub", table_cell),
            Paragraph("<font color='#16a34a'><b>YES</b></font>", table_cell),
            Paragraph("Database schema version history (Migrations 0001 through 0018).", table_cell),
        ],
        [
            Paragraph("<code>/scripts</code> (Seed & Maintenance)", table_cell_code),
            Paragraph("Server & GitHub", table_cell),
            Paragraph("<font color='#16a34a'><b>YES</b></font>", table_cell),
            Paragraph("Base organization, store, role seeds, and diagnostic verification scripts.", table_cell),
        ],
        [
            Paragraph("<code>Dockerfile</code> & <code>pyproject.toml</code>", table_cell_code),
            Paragraph("Server & GitHub", table_cell),
            Paragraph("<font color='#16a34a'><b>YES</b></font>", table_cell),
            Paragraph("Standard container build packaging and Python dependency declarations.", table_cell),
        ],
        [
            Paragraph("<code>docker-compose.yml</code>", table_cell_code),
            Paragraph("Server & GitHub", table_cell),
            Paragraph("<font color='#16a34a'><b>YES</b></font>", table_cell),
            Paragraph("Original single-container baseline preserved for Google Cloud e2-micro compatibility.", table_cell),
        ],
    ]
    t_man = Table(manifest_data, colWidths=[150, 85, 75, 205])
    t_man.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#94a3b8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(t_man)

    # Force page break for clean formatting
    story.append(PageBreak())

    # =========================================================================
    # SECTION 3: PRODUCTION CONFIGURATION & SECRETS REGISTER
    # =========================================================================
    story.append(Paragraph("3. Production Configuration & Secrets Register", h1_style))
    story.append(
        Paragraph(
            "Below is the exact, unredacted production configuration reference active on <code>fastapi-production</code> (129.225.122.78). "
            "Use these exact values when performing disaster recovery or server replication.",
            body_style,
        )
    )

    story.append(Paragraph("3.1 Environment File: <code>/opt/csms_v2/.env</code>", h2_style))
    env_content = """# ==============================================================================
# CSMS V2 - Production Environment (OCI Ampere VM)
# ==============================================================================
APP_NAME="CSMS V2"
DEBUG=False

WEB_CONCURRENCY=4

POSTGRES_DB=csms_v2
POSTGRES_USER=csms_user
POSTGRES_PASSWORD=Harshitha@2019

DATABASE_URL="postgresql+asyncpg://csms_user:Harshitha%402019@db:5432/csms_v2"

JWT_SECRET_KEY="62184502c7cbc4290cfdd0b4a580689efa74b14d78efd93b21068d76f08516fa"
JWT_ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=480"""
    t_env = Table([[Preformatted(env_content, code_block)]], colWidths=[515])
    t_env.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_env)
    story.append(Spacer(1, 8))

    story.append(Paragraph("3.2 PostgreSQL 18 Hardware Memory Tuning Parameters", h2_style))
    pg_params = [
        [Paragraph("<b>Parameter</b>", table_cell_bold), Paragraph("<b>Configured Value</b>", table_cell_bold), Paragraph("<b>Production Purpose & Rationale</b>", table_cell_bold)],
        [Paragraph("<code>shared_buffers</code>", table_cell_code), Paragraph("<b>4GB</b>", table_cell), Paragraph("Allocates dedicated RAM for caching table pages and inventory indexes.", table_cell)],
        [Paragraph("<code>effective_cache_size</code>", table_cell_code), Paragraph("<b>10GB</b>", table_cell), Paragraph("Planner advisory indicating total memory available in OS cache + shared buffers.", table_cell)],
        [Paragraph("<code>work_mem</code>", table_cell_code), Paragraph("<b>32MB</b>", table_cell), Paragraph("Per-sort/hash allocation; protects against OOM spikes under 100 max connections.", table_cell)],
        [Paragraph("<code>maintenance_work_mem</code>", table_cell_code), Paragraph("<b>1GB</b>", table_cell), Paragraph("Accelerates VACUUM, CREATE INDEX, and large Alembic migration operations.", table_cell)],
        [Paragraph("<code>shm_size</code> (Docker)", table_cell_code), Paragraph("<b>1GB</b>", table_cell), Paragraph("Expands POSIX /dev/shm; eliminates parallel worker allocation failures.", table_cell)],
        [Paragraph("<code>random_page_cost</code>", table_cell_code), Paragraph("<b>1.1</b>", table_cell), Paragraph("Optimized for OCI NVMe/SSD block storage; favors fast index lookups.", table_cell)],
        [Paragraph("<code>effective_io_concurrency</code>", table_cell_code), Paragraph("<b>200</b>", table_cell), Paragraph("Enables deep asynchronous I/O pipelining for bitmap index heap scans.", table_cell)],
        [Paragraph("<code>statement_timeout</code>", table_cell_code), Paragraph("<b>60s</b>", table_cell), Paragraph("Terminates runaway queries while allowing sufficient window for migrations.", table_cell)],
        [Paragraph("<code>idle_in_transaction_...</code>", table_cell_code), Paragraph("<b>60s</b>", table_cell), Paragraph("Automatically breaks abandoned sessions holding locks on stock movement tables.", table_cell)],
        [Paragraph("<code>log_min_duration_statement</code>", table_cell_code), Paragraph("<b>500ms</b>", table_cell), Paragraph("Observability: captures any query taking >500ms in container logs.", table_cell)],
    ]
    t_pg = Table(pg_params, colWidths=[140, 75, 300])
    t_pg.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#94a3b8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t_pg)

    # Force page break for clean formatting
    story.append(PageBreak())

    # =========================================================================
    # SECTION 4: STANDARD OPERATING PROCEDURES (SOP)
    # =========================================================================
    story.append(Paragraph("4. Standard Maintenance Operating Procedures (SOP)", h1_style))
    story.append(
        Paragraph(
            "All operational and maintenance procedures must be performed from the root deployment directory <code>/opt/csms_v2</code> on the host VM.",
            body_style,
        )
    )

    story.append(Paragraph("SOP-1: Deploying Code Updates from GitHub (Zero DB Downtime)", h2_style))
    sop1_content = """cd /opt/csms_v2

# 1. Pull latest application code from GitHub
git pull origin main

# 2. Execute new Alembic database migrations (if any were committed)
docker compose -f docker-compose.prod.yml run --rm app alembic upgrade head

# 3. Rebuild the application container image using cached Docker layers
docker compose -f docker-compose.prod.yml build app

# 4. Gracefully restart the app container without touching or restarting PostgreSQL
docker compose -f docker-compose.prod.yml up -d --no-deps app"""
    t_sop1 = Table([[Preformatted(sop1_content, code_block)]], colWidths=[515])
    t_sop1.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_sop1)
    story.append(Spacer(1, 6))

    story.append(Paragraph("SOP-2: Automated and Manual Database Backups", h2_style))
    story.append(
        Paragraph(
            "Backups are executed via an automated cron job every night at <b>02:00 AM</b> using <code>/opt/csms_v2/scripts/backup_db.sh</code> with a rolling 14-day deletion policy. "
            "To trigger an on-demand manual backup before system maintenance:",
            body_style,
        )
    )
    sop2_content = """# Trigger immediate manual backup
/opt/csms_v2/scripts/backup_db.sh

# Verify backup creation, file size, and timestamp
ls -lh /opt/csms_v2/backups/"""
    t_sop2 = Table([[Preformatted(sop2_content, code_block)]], colWidths=[515])
    t_sop2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_sop2)
    story.append(Spacer(1, 6))

    story.append(Paragraph("SOP-3: Restoring Database from Compressed Backup", h2_style))
    sop3_content = """# Restore compressed database dump into csms_v2 database
gunzip -c /opt/csms_v2/backups/csms_v2_YYYYMMDD_HHMMSS.sql.gz | \\
  docker exec -i csms_db psql -U csms_user -d csms_v2"""
    t_sop3 = Table([[Preformatted(sop3_content, code_block)]], colWidths=[515])
    t_sop3.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_sop3)
    story.append(Spacer(1, 6))

    story.append(Paragraph("SOP-4: System Monitoring, Log Inspection & Health Verification", h2_style))
    sop4_content = """# Check live health status of all 3 containers
docker compose -f docker-compose.prod.yml ps

# Monitor real-time CPU & RAM consumption across containers
docker stats csms_db csms_app csms_nginx

# Follow live application logs with per-request processing times
docker compose -f docker-compose.prod.yml logs -f app

# Follow Nginx access logs and rate-limiting activity
docker compose -f docker-compose.prod.yml logs -f nginx

# Follow PostgreSQL logs (slow queries >500ms, lock alerts)
docker compose -f docker-compose.prod.yml logs -f db"""
    t_sop4 = Table([[Preformatted(sop4_content, code_block)]], colWidths=[515])
    t_sop4.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_sop4)
    story.append(Spacer(1, 6))

    story.append(Paragraph("SOP-5: Zero-Downtime SSL Certificate Renewal (Webroot)", h2_style))
    story.append(
        Paragraph(
            "SSL certificates are renewed automatically every Monday at <b>03:00 AM</b> via webroot challenge without stopping Nginx. "
            "To simulate and verify a dry-run renewal at any time:",
            body_style,
        )
    )
    sop5_content = """# Test simulated zero-downtime renewal against Let's Encrypt staging
docker run --rm \\
  -v /opt/csms_v2/certbot/www:/var/www/certbot \\
  -v /opt/csms_v2/certbot/conf:/etc/letsencrypt \\
  certbot/certbot renew --webroot -w /var/www/certbot --dry-run

# Active crontab schedule:
# 0 3 * * 1 docker run --rm -v /opt/csms_v2/certbot/www:/var/www/certbot -v /opt/csms_v2/certbot/conf:/etc/letsencrypt certbot/certbot renew --webroot -w /var/www/certbot --quiet && docker compose -f /opt/csms_v2/docker-compose.prod.yml exec nginx nginx -s reload"""
    t_sop5 = Table([[Preformatted(sop5_content, code_block)]], colWidths=[515])
    t_sop5.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_sop5)

    # Force page break for clean formatting
    story.append(PageBreak())

    # =========================================================================
    # SECTION 5: SEEDED OPERATIONAL USERS & ACCESS REGISTER
    # =========================================================================
    story.append(Paragraph("5. Seeded System Accounts & Access Register", h1_style))
    story.append(
        Paragraph(
            "All initial system accounts have been hashed using <b>Argon2id</b>. "
            "The initial default password for all seeded accounts is: <b><code>Password@1</code></b>. "
            "Individual user passwords should be changed upon first login through user management administration.",
            body_style,
        )
    )

    user_data = [
        [
            Paragraph("<b>Username</b>", table_cell_bold),
            Paragraph("<b>Full Name / Designation</b>", table_cell_bold),
            Paragraph("<b>Role Code</b>", table_cell_bold),
            Paragraph("<b>Assigned Store Scope</b>", table_cell_bold),
            Paragraph("<b>Operational Permissions & Authority</b>", table_cell_bold),
        ],
        [
            Paragraph("<b>dev_admin</b>", table_cell_bold),
            Paragraph("System Administrator", table_cell),
            Paragraph("<code>SYSTEM_ADMIN</code>", table_cell_code),
            Paragraph("Directorate Level<br/>(Global Masters)", table_cell),
            Paragraph("Full organization, office, store, item master administration, inventory policy, user setup.", table_cell),
        ],
        [
            Paragraph("<b>dev_director</b>", table_cell_bold),
            Paragraph("Director / Superintendent", table_cell),
            Paragraph("<code>DIRECTOR</code>", table_cell_code),
            Paragraph("Directorate", table_cell),
            Paragraph("High-level oversight, executive audit reports, directorate policy approval.", table_cell),
        ],
        [
            Paragraph("<b>dev_deputy</b>", table_cell_bold),
            Paragraph("Deputy Superintendent, Stock & Stores", table_cell),
            Paragraph("<code>DEPUTY_SUPDT_STORES</code>", table_cell_code),
            Paragraph("Central Store<br/>(CENTRAL)", table_cell),
            Paragraph("Central Store controlling officer; authorizes stock verifications, adjustments, returns, petty purchases.", table_cell),
        ],
        [
            Paragraph("<b>dev_general_sk</b>", table_cell_bold),
            Paragraph("General Storekeeper", table_cell),
            Paragraph("<code>GENERAL_STOREKEEPER</code>", table_cell_code),
            Paragraph("Central Store<br/>(CENTRAL)", table_cell),
            Paragraph("Executes stock receipts, issues, manual indents, stock verification counts, ledger reviews.", table_cell),
        ],
        [
            Paragraph("<b>dev_assistant_sk</b>", table_cell_bold),
            Paragraph("Assistant Storekeeper", table_cell),
            Paragraph("<code>ASSISTANT_STOREKEEPER</code>", table_cell_code),
            Paragraph("Central Store<br/>(CENTRAL)", table_cell),
            Paragraph("Assists General Storekeeper; stock entry, manual indents, physical counts against Central Store.", table_cell),
        ],
        [
            Paragraph("<b>dev_press_head</b>", table_cell_bold),
            Paragraph("Central Press Branch Head", table_cell),
            Paragraph("<code>BRANCH_HEAD</code>", table_cell_code),
            Paragraph("Central Press<br/>(PRESS-STORE)", table_cell),
            Paragraph("Branch office controlling officer; approves branch requisitions, verifications, adjustments.", table_cell),
        ],
        [
            Paragraph("<b>dev_press_sk</b>", table_cell_bold),
            Paragraph("Central Press Storekeeper", table_cell),
            Paragraph("<code>BRANCH_STOREKEEPER</code>", table_cell_code),
            Paragraph("Central Press<br/>(PRESS-STORE)", table_cell),
            Paragraph("Executes branch stock transactions, issues, receipts from Central Store, petty purchases.", table_cell),
        ],
    ]
    t_users = Table(user_data, colWidths=[80, 105, 110, 85, 135])
    t_users.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#94a3b8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(t_users)
    story.append(Spacer(1, 16))

    # Sign-off box
    signoff_data = [
        [
            Paragraph("<b>DOCUMENT CONTROL & HANDOVER VERIFICATION</b>", table_cell_bold),
            Paragraph("<b>STATUS: PRODUCTION CERTIFIED</b>", table_cell_bold),
        ],
        [
            Paragraph("<b>Handover Date:</b> 28 September 2026", table_cell),
            Paragraph("<b>Verified Platform:</b> Oracle Cloud Infrastructure (Ampere A1 Flex)", table_cell),
        ],
        [
            Paragraph("<b>Database Engine:</b> PostgreSQL 18.x (Tuned 14GB)", table_cell),
            Paragraph("<b>Application Server:</b> FastAPI Uvicorn (4 Workers / Nginx)", table_cell),
        ],
    ]
    t_sign = Table(signoff_data, colWidths=[260, 255])
    t_sign.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#0284c7")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_sign)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated PDF at: {output_path}")


if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, "CSMS_V2_OCI_Deployment_Manifest.pdf")
    build_pdf(pdf_path)
