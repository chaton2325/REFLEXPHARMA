"""Construction du PDF « Bon de commande », partagée entre l'export du module
Commandes et l'assistant IA : les deux passent par build_bon_commande_pdf(),
ce qui garantit des documents strictement identiques (styles, largeurs, contenu)."""

from datetime import datetime

COMMANDE_STATUT_LABELS = {'en_cours': 'En cours', 'livree': 'Livrée', 'annulee': 'Annulée'}


def build_bon_commande_pdf(commande, target, tire_par, pharmacy_name):
    """Écrit le bon de commande PDF de `commande` dans `target` (chemin ou buffer).

    tire_par : libellé « NOM Prénom » de la personne qui génère le document.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    livree = commande.statut == 'livree'

    doc = SimpleDocTemplate(target, pagesize=A4, topMargin=24, bottomMargin=24, leftMargin=24, rightMargin=24)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('Small', parent=styles['Normal'], fontSize=8, leading=10))
    # Les tableaux occupent presque toute la largeur utile de la page A4
    largeur_utile = A4[0] - doc.leftMargin - doc.rightMargin

    elements = [
        Paragraph(f'Bon de commande {commande.numero}', styles['Title']),
        Paragraph(
            f'{pharmacy_name} | Date du tirage : {datetime.now().strftime("%d/%m/%Y %H:%M")} | '
            f'Tire par : {tire_par}',
            styles['Small']),
        Spacer(1, 10)
    ]

    infos = [
        ['Fournisseur', commande.fournisseur_nom, 'Statut', COMMANDE_STATUT_LABELS.get(commande.statut, commande.statut)],
        ['Creee le', commande.created_at.strftime('%d/%m/%Y %H:%M') if commande.created_at else '', 'Creee par', commande.created_by_nom or ''],
    ]
    if commande.relance_de_numero:
        infos.append(['Relance de', commande.relance_de_numero, '', ''])
    if livree:
        infos.append(['Livree le', commande.livree_at.strftime('%d/%m/%Y %H:%M') if commande.livree_at else '',
                      'Receptionnee par', commande.livree_by_nom or ''])
    if commande.note:
        infos.append(['Note', commande.note, '', ''])
    elements.append(Table(infos, colWidths=[largeur_utile * p for p in (0.15, 0.37, 0.15, 0.33)], style=TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F9FAFB')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
    ])))
    elements.append(Spacer(1, 12))

    produit_style = ParagraphStyle('CelluleProduit', parent=styles['Normal'], fontSize=8, leading=10)

    if livree:
        colWidths = [largeur_utile * p for p in (0.33, 0.13, 0.10, 0.11, 0.08, 0.11, 0.14)]
        data = [['Produit', 'Code', 'Qte cmd', 'Qte livree', 'Ecart', 'Prix U. HT', 'Montant HT']]
        for l in commande.lignes:
            data.append([
                Paragraph(l.produit_nom, produit_style), l.produit_code or '',
                str(l.quantite_commandee or 0),
                str(l.quantite_livree) if l.quantite_livree is not None else '',
                str(l.ecart) if l.ecart else '',
                f'{(l.prix_unite_ht or 0):.2f}', f'{l.montant_commande_ht:.2f}',
            ])
        data.append(['TOTAL', '', str(commande.total_commande), str(commande.total_livre),
                     str(-commande.total_manquant) if commande.total_manquant else '',
                     '', f'{commande.montant_commande_ht:.2f}'])
    else:
        colWidths = [largeur_utile * p for p in (0.46, 0.16, 0.13, 0.11, 0.14)]
        data = [['Produit', 'Code', 'Qte commandee', 'Prix U. HT', 'Montant HT']]
        for l in commande.lignes:
            data.append([
                Paragraph(l.produit_nom, produit_style), l.produit_code or '',
                str(l.quantite_commandee or 0),
                f'{(l.prix_unite_ht or 0):.2f}', f'{l.montant_commande_ht:.2f}',
            ])
        data.append(['TOTAL', '', str(commande.total_commande), '', f'{commande.montant_commande_ht:.2f}'])

    elements.append(Table(data, colWidths=colWidths, repeatRows=1, style=TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F7FAFD')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EAF1F8')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ])))
    doc.build(elements)
