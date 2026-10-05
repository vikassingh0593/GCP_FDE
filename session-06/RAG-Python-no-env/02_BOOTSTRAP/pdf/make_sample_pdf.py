"""Create a sample PDF with text and tables to test Docling ingestion."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

OUT = Path(__file__).parent / "safety_stock_standard.pdf"

styles = getSampleStyleSheet()
TITLE, H2, BODY = styles["Title"], styles["Heading2"], styles["BodyText"]


def grid_table(rows):
    table = Table(rows, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    return table


story = [
    Paragraph("Safety Stock and Reorder Point Standard", TITLE),

    Paragraph("2.1 Purpose", H2),
    Paragraph("This standard defines how much safety stock each store must hold and when "
              "a replenishment order must be raised for each product category.", BODY),

    Paragraph("3.1 Safety Stock Definition", H2),
    Paragraph("Safety stock is the minimum buffer held to absorb demand spikes during the "
              "supplier lead time. Safety stock must never be used for promotions.", BODY),

    Paragraph("5.1 Reorder Points by Category", H2),
    Paragraph("Raise a replenishment order when on-hand inventory falls to or below the "
              "reorder point.", BODY),
    grid_table([
        ["Category", "Reorder Point (units)", "Safety Stock (units)", "Lead Time (days)"],
        ["Dairy", "40", "15", "2"],
        ["Bakery", "30", "10", "1"],
        ["Frozen", "25", "12", "5"],
        ["Beverages", "60", "20", "3"],
        ["Household", "20", "8", "7"],
    ]),

    PageBreak(),

    Paragraph("6.2 Escalation Matrix", H2),
    Paragraph("When projected days of cover drop, follow this escalation path.", BODY),
    grid_table([
        ["Days of Cover", "Action", "Approver"],
        ["Less than 1 day", "Emergency inter-store transfer", "Regional Manager"],
        ["1 to 3 days", "Expedite the open purchase order", "Store Manager"],
        ["More than 3 days", "No action", "Not required"],
    ]),

    Paragraph("7.2 Seasonal Override", H2),
    Paragraph("SKU-4410 (holiday hamper) uses a reorder point of 120 units from "
              "1 November to 31 December, overriding the category table.", BODY),
]

SimpleDocTemplate(str(OUT), pagesize=A4).build(story)
print(f"Wrote {OUT}")