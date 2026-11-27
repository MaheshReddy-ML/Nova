from io import BytesIO

MEDIA = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
DOC_SECTIONS = {
    "proposal": ("Website Improvement Proposal", ("Observations", "Scope", "Estimate", "Verification", "Limitations")),
    "audit": ("Website Audit Report", ("Observations", "Verification", "Limitations")),
    "scope": ("Draft Website Statement of Work", ("Scope", "Estimate", "Delivery stages", "Limitations")),
    "delivery": ("Website Concept Handoff", ("Verification", "Delivery stages", "Limitations")),
}


def sections(proposal):
    return {
        "Observations": proposal.get("observations", []),
        "Scope": proposal.get("scope", []),
        "Estimate": [
            f"INR {proposal['proposed_price_inr']:,} for {proposal['effort_hours']} estimated hours.",
            proposal["rate_basis"],
        ],
        "Verification": [
            *proposal.get("demonstrated", []),
            f"Recorded preview checks covered {', '.join(proposal.get('verification', []))}.",
        ],
        "Limitations": proposal.get("limitations", []),
        "Delivery stages": [
            "Confirm scope, content, and asset rights.",
            "Implement the agreed changes and obtain approval for the revised preview.",
            "Confirm delivery arrangements and provide operating notes.",
        ],
    }


def document(proposal, kind):
    from docx import Document
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    title, included = DOC_SECTIONS[kind]
    doc = Document()
    for margin in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(doc.sections[0], margin, Inches(.85))
    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10.5)
    for name in ("Title", "Subtitle", "Heading 1"):
        style = doc.styles[name]
        style.font.name = "Arial"
        style.font.color.rgb = RGBColor(0, 0, 0) if name == "Title" else RGBColor(20, 37, 57)
        style.font.italic = False
        properties = style.element.find(qn("w:pPr"))
        if properties is not None:
            border = properties.find(qn("w:pBdr"))
            if border is not None:
                properties.remove(border)
    doc.add_paragraph(title, "Title")
    doc.add_paragraph(proposal["business"], "Subtitle")
    doc.add_paragraph("Prepared by NOVA for private review. Scope and pricing are draft estimates.")
    report = sections(proposal)
    for heading in included:
        if not report[heading]:
            continue
        doc.add_heading(heading, level=1)
        for text in report[heading]:
            doc.add_paragraph(text, "List Bullet" if len(report[heading]) > 1 else None)
    doc.add_paragraph("Public source")
    doc.add_paragraph(proposal["source"])
    target = BytesIO()
    doc.save(target)
    return target.getvalue()


def workbook(proposal):
    from xlsxwriter import Workbook

    target = BytesIO()
    with Workbook(target, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False}) as book:
        sheet = book.add_worksheet("Draft estimate")
        body = {"font_name": "Arial", "font_size": 11, "valign": "vcenter", "align": "left", "text_wrap": True}
        plain = book.add_format(body)
        header = book.add_format({**body, "bold": True, "bg_color": "#18304A", "font_color": "#FFFFFF"})
        input_number = book.add_format({**body, "font_color": "#24518A"})
        rate = book.add_format({**body, "font_color": "#24518A", "num_format": '"INR "#,##0.00'})
        total = book.add_format({**body, "bold": True, "bg_color": "#E6F0EB", "num_format": '"INR "#,##0.00'})
        sheet.set_column("A:A", 35)
        sheet.set_column("B:B", 39)
        sheet.set_default_row(27)
        sheet.set_row(0, 42)
        sheet.set_row(6, 42)
        sheet.write_row("A1", ["Website project estimate", proposal["business"]], header)
        sheet.write_row("A2", ["Status", "Draft for private review"], plain)
        sheet.write("A3", "Estimated effort in hours", plain)
        sheet.write_number("B3", proposal["effort_hours"], input_number)
        sheet.write("A4", "Planning rate in INR per hour", plain)
        sheet.write_number("B4", proposal["proposed_price_inr"] / proposal["effort_hours"], rate)
        sheet.write("A5", "Estimated fee in INR", total)
        sheet.write_formula("B5", "=B3*B4", total, proposal["proposed_price_inr"])
        sheet.write_row("A6", ["Public source", proposal["source"]], plain)
        sheet.write_row("A7", ["Assumptions", proposal["rate_basis"]], plain)
        sheet.merge_range("A8:B8", "Proposed work", header)
        for index, item in enumerate(proposal.get("scope", []), start=8):
            sheet.set_row(index, 34)
            sheet.merge_range(index, 0, index, 1, item, plain)
        sheet.freeze_panes(2, 0)
        sheet.fit_to_pages(1, 1)
    return target.getvalue()


def deck(proposal):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    slides = Presentation()
    slides.slide_width = Inches(13.333)
    slides.slide_height = Inches(7.5)
    report = sections(proposal)

    def page(title, lines):
        slide = slides.slides.add_slide(slides.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor.from_string("F0F3F5")
        title_frame = slide.shapes.add_textbox(Inches(.85), Inches(.8), Inches(11.6), Inches(1.1)).text_frame
        title_frame.word_wrap = True
        heading = title_frame.paragraphs[0]
        heading.text = title
        heading.font.name = "Arial"
        heading.font.size = Pt(35)
        heading.font.bold = True
        heading.font.color.rgb = RGBColor.from_string("18304A")
        body = slide.shapes.add_textbox(Inches(.9), Inches(2.2), Inches(11.5), Inches(4.25)).text_frame
        body.word_wrap = True
        for index, value in enumerate(lines[:5]):
            line = body.paragraphs[0] if index == 0 else body.add_paragraph()
            line.text = value
            line.font.name = "Arial"
            line.font.size = Pt(22)
            line.font.color.rgb = RGBColor.from_string("263B50")
            line.space_after = Pt(20)

    page("Website improvement concept", [proposal["business"], "Private NOVA review draft", proposal["source"]])
    page("What the review found", report["Observations"])
    page("Proposed changes", report["Scope"])
    page("Preview verification", report["Verification"])
    page("Draft estimate and next steps", [report["Estimate"][0], "Confirm scope, content, and delivery requirements before quoting."])
    target = BytesIO()
    slides.save(target)
    return target.getvalue()
