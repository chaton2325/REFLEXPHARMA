"""Construction du PDF « Bon d'entrée en stock » : un document par soumission
du panier "Nouvelle entrée en stock" (voir models/stock_entry_batch.py),
listant chaque ligne ajoutée. Même style/recette que bon_commande_pdf.py, pour
que les documents générés par l'application restent visuellement cohérents."""


def build_stock_entry_pdf(batch, target, tire_par, pharmacy_name):
    """Écrit le bon d'entrée en stock PDF de `batch` dans `target` (chemin ou
    buffer). tire_par : libellé « NOM Prénom » de la personne qui génère le
    document (pas forcément celle qui a fait l'entrée, voir batch.created_by_nom)."""
    from datetime import datetime

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    doc = SimpleDocTemplate(target, pagesize=A4, topMargin=24, bottomMargin=24, leftMargin=24, rightMargin=24)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('Small', parent=styles['Normal'], fontSize=8, leading=10))
    largeur_utile = A4[0] - doc.leftMargin - doc.rightMargin

    elements = [
        Paragraph(f'Bon d\'entrée en stock {batch.numero}', styles['Title']),
        Paragraph(
            f'{pharmacy_name} | Date du tirage : {datetime.now().strftime("%d/%m/%Y %H:%M")} | '
            f'Tiré par : {tire_par}',
            styles['Small']),
        Spacer(1, 10)
    ]

    infos = [
        ['Entrée le', batch.created_at.strftime('%d/%m/%Y %H:%M') if batch.created_at else '',
         'Saisie par', batch.created_by_nom or ''],
        ['Raison', batch.effective_reason or '-', '', ''],
    ]
    elements.append(Table(infos, colWidths=[largeur_utile * p for p in (0.15, 0.37, 0.15, 0.33)], style=TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F9FAFB')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('SPAN', (1, 1), (3, 1)),
    ])))
    elements.append(Spacer(1, 12))

    produit_style = ParagraphStyle('CelluleProduit', parent=styles['Normal'], fontSize=8, leading=10)

    colWidths = [largeur_utile * p for p in (0.30, 0.13, 0.15, 0.12, 0.10, 0.10, 0.10)]
    data = [['Produit', 'Code', 'N° BL', 'Péremption', 'Unités', 'Sous-U.', 'S/Sous-U.']]
    total_u = total_su = total_ssu = 0
    for m in batch.modifications:
        data.append([
            Paragraph(m.produit.nom if m.produit else '-', produit_style),
            m.produit.code_produit if m.produit else '-',
            m.numero_bl,
            m.date_peremption.strftime('%d/%m/%Y') if m.date_peremption else '',
            str(m.delta_quantite_unites),
            str(m.delta_quantite_sous_unites),
            str(m.delta_quantite_sous_sous_unites),
        ])
        total_u += m.delta_quantite_unites
        total_su += m.delta_quantite_sous_unites
        total_ssu += m.delta_quantite_sous_sous_unites
    data.append(['TOTAL', '', '', '', str(total_u), str(total_su), str(total_ssu)])

    elements.append(Table(data, colWidths=colWidths, repeatRows=1, style=TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F7FAFD')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EAF1F8')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (4, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ])))
    doc.build(elements)
