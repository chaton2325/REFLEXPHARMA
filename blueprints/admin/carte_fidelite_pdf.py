"""Construction du PDF des cartes de fidélité (format ID-1, 85.6 x 54 mm), envoyé en
pièce jointe à l'imprimeur lors d'une demande d'impression. Une carte par client,
plusieurs cartes par page en grille centrée automatiquement sur la page A4.

Le dégradé (voir _card_gradient_image) reproduit fidèlement, en direction ET en
couleurs, celui utilisé dans l'aperçu HTML de la carte (linear-gradient(135deg, ...)
dans templates/admin/clients/carte_fidelite_apercu.html) : les deux rendus doivent
rester visuellement identiques, seul le moteur de dessin diffère (CSS vs PDF)."""

from reportlab.lib import colors

CARD_WIDTH_MM = 85.6
CARD_HEIGHT_MM = 54.0

# Vert -> jaune (meme degrade, meme sens 135deg, que la carte affichee dans l'app).
_COLOR_START = colors.HexColor('#1b5e20')
_COLOR_END = colors.HexColor('#c9a227')

_GRADIENT_IMAGE_CACHE = {}


def _color_rgb255(color):
    return (
        int(round(color.red * 255)),
        int(round(color.green * 255)),
        int(round(color.blue * 255)),
    )


def _card_gradient_image(px_per_mm=4):
    """Image PIL (mise en cache) du dégradé diagonal haut-gauche -> bas-droite aux
    couleurs de la carte : équivalent visuel de CSS `linear-gradient(135deg, ...)`,
    généré une seule fois puis réutilisé pour toutes les cartes d'un même PDF."""
    key = (px_per_mm, str(_COLOR_START), str(_COLOR_END))
    cached = _GRADIENT_IMAGE_CACHE.get(key)
    if cached is not None:
        return cached

    import numpy as np
    from PIL import Image

    width_px = max(int(CARD_WIDTH_MM * px_per_mm), 2)
    height_px = max(int(CARD_HEIGHT_MM * px_per_mm), 2)
    xs = np.linspace(0.0, 1.0, width_px)
    ys = np.linspace(0.0, 1.0, height_px)
    grid_x, grid_y = np.meshgrid(xs, ys)
    # Diagonale haut-gauche (t=0) -> bas-droite (t=1) : equivalent visuel de 135deg.
    t = (grid_x + grid_y) / 2.0

    start_rgb, end_rgb = _color_rgb255(_COLOR_START), _color_rgb255(_COLOR_END)
    channels = [
        (start_rgb[i] + (end_rgb[i] - start_rgb[i]) * t).astype(np.uint8)
        for i in range(3)
    ]
    image = Image.fromarray(np.stack(channels, axis=-1), mode='RGB')
    _GRADIENT_IMAGE_CACHE[key] = image
    return image


def _draw_gradient_round_rect(c, x, y, width, height, radius):
    """Remplit le rectangle arrondi avec le dégradé diagonal de marque de la carte."""
    from reportlab.lib.utils import ImageReader

    c.saveState()
    path = c.beginPath()
    path.roundRect(x, y, width, height, radius)
    c.clipPath(path, stroke=0, fill=0)
    c.drawImage(ImageReader(_card_gradient_image()), x, y, width=width, height=height)
    c.restoreState()


def _shrink_font_to_fit(c, text, font_name, max_width, start_size, min_size=6.5):
    """Renvoie la plus grande taille de police (entre min_size et start_size, par pas de
    0.5) telle que `text` tienne dans `max_width` — évite tout chevauchement/débordement
    quel que soit le nom du client ou de la pharmacie, plutôt que de deviner une longueur
    de troncature fixe."""
    size = start_size
    while size > min_size and c.stringWidth(text, font_name, size) > max_width:
        size -= 0.5
    return size


def _truncate_to_fit(c, text, font_name, size, max_width):
    """Tronque `text` avec une ellipse si besoin pour tenir dans `max_width`, mesuré
    précisément (plutôt qu'une coupe a un nombre de caracteres arbitraire)."""
    if c.stringWidth(text, font_name, size) <= max_width:
        return text
    while text and c.stringWidth(text + '…', font_name, size) > max_width:
        text = text[:-1]
    return f'{text}…' if text else '…'


def draw_carte_fidelite(c, x, y, client, pharmacy_name):
    """Dessine une carte de fidélité sur le canvas reportlab `c`, coin bas-gauche à
    (x, y). x/y/dimensions sont attendus en points reportlab (déjà convertis)."""
    from reportlab.lib.units import mm
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics import renderPDF

    width, height = CARD_WIDTH_MM * mm, CARD_HEIGHT_MM * mm
    radius = 4 * mm
    pad = 5 * mm

    _draw_gradient_round_rect(c, x, y, width, height, radius)

    # Cercle décoratif (même esprit que les en-têtes de page de l'application)
    c.saveState()
    clip = c.beginPath()
    clip.roundRect(x, y, width, height, radius)
    c.clipPath(clip, stroke=0, fill=0)
    c.setFillColor(colors.Color(1, 1, 1, alpha=0.07))
    c.circle(x + width - 4 * mm, y + height + 6 * mm, 20 * mm, stroke=0, fill=1)
    c.restoreState()

    # Bordure fine
    c.saveState()
    c.setStrokeColor(colors.HexColor('#1a1a2e'))
    c.setLineWidth(0.6)
    c.roundRect(x, y, width, height, radius, stroke=1, fill=0)
    c.restoreState()

    c.saveState()

    # Bloc QR (fond blanc, coin bas-droit) — dessiné avant le texte pour connaître la
    # largeur disponible pour la colonne de gauche (nom, matricule, contact).
    qr_size = 19 * mm
    qr_zone_width = qr_size + 3 * mm
    qr_x = x + width - pad - qr_size
    qr_y = y + pad
    c.setFillColor(colors.white)
    c.roundRect(qr_x - 1.5 * mm, qr_y - 1.5 * mm, qr_zone_width, qr_zone_width, 1.5 * mm, stroke=0, fill=1)

    widget = qr.QrCodeWidget(client.matricule)
    bounds = widget.getBounds()
    qw, qh = bounds[2] - bounds[0], bounds[3] - bounds[1]
    drawing = Drawing(qr_size, qr_size, transform=[qr_size / qw, 0, 0, qr_size / qh, 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, c, qr_x, qr_y)

    left_col_width = width - 2 * pad - qr_zone_width - 3

    # En-tête : nom de la pharmacie (a gauche) + libellé (a droite), chacun retreci si
    # besoin pour ne jamais se chevaucher quelle que soit la longueur du nom configure.
    label = 'CARTE DE FIDÉLITÉ'
    label_size = 6
    label_width = c.stringWidth(label, 'Helvetica', label_size)
    header_name = (pharmacy_name or 'REFLEXPHARMA').upper()
    header_max_width = width - 2 * pad - label_width - 6
    header_size = _shrink_font_to_fit(c, header_name, 'Helvetica-Bold', header_max_width, 9, min_size=6.5)
    header_name = _truncate_to_fit(c, header_name, 'Helvetica-Bold', header_size, header_max_width)

    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', header_size)
    c.drawString(x + pad, y + height - pad - 2, header_name)
    c.setFont('Helvetica', label_size)
    c.setFillColor(colors.Color(1, 1, 1, alpha=0.8))
    c.drawRightString(x + width - pad, y + height - pad - 2, label)

    c.setStrokeColor(colors.Color(1, 1, 1, alpha=0.3))
    c.setLineWidth(0.5)
    c.line(x + pad, y + height - pad - 5.5, x + width - pad, y + height - pad - 5.5)

    # Nom du client (colonne de gauche, taille adaptative pour ne jamais chevaucher le
    # QR ni la ligne du matricule en dessous).
    nom_complet = f'{client.prenom} {client.nom}'.strip()
    name_size = _shrink_font_to_fit(c, nom_complet, 'Helvetica-Bold', left_col_width, 12, min_size=8)
    nom_complet = _truncate_to_fit(c, nom_complet, 'Helvetica-Bold', name_size, left_col_width)
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', name_size)
    c.drawString(x + pad, y + height - pad - 17, nom_complet)

    # Matricule (10pt sous le nom : marge suffisante pour eviter tout chevauchement
    # meme avec les descendantes d'une police 12pt en gras)
    c.setFont('Helvetica', 7.5)
    c.setFillColor(colors.Color(1, 1, 1, alpha=0.85))
    c.drawString(x + pad, y + height - pad - 27, client.matricule)

    # Contact
    contact = client.telephone or client.email or 'Non renseigné'
    contact_text = _truncate_to_fit(c, f'Contact : {contact}', 'Helvetica', 7, left_col_width)
    c.setFont('Helvetica', 7)
    c.setFillColor(colors.Color(1, 1, 1, alpha=0.75))
    c.drawString(x + pad, y + pad + 6, contact_text)

    # Membre depuis
    date_creation = client.created_at.strftime('%d/%m/%Y') if client.created_at else '-'
    c.setFont('Helvetica', 6.5)
    c.setFillColor(colors.Color(1, 1, 1, alpha=0.6))
    c.drawString(x + pad, y + pad, f'Membre depuis le {date_creation}')

    c.restoreState()


def build_cartes_fidelite_pdf(target, clients, pharmacy_name):
    """Écrit dans `target` (chemin ou buffer) un PDF A4 contenant la carte de
    fidélité de chaque client fourni, en grille de 2 x 4 cartes par page, centrée."""
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    c = pdfcanvas.Canvas(target, pagesize=A4)
    page_width, page_height = A4

    cols, rows = 2, 4
    gap_x, gap_y = 8 * mm, 8 * mm
    card_w, card_h = CARD_WIDTH_MM * mm, CARD_HEIGHT_MM * mm

    grid_width = cols * card_w + (cols - 1) * gap_x
    grid_height = rows * card_h + (rows - 1) * gap_y
    margin_x = (page_width - grid_width) / 2
    margin_y = (page_height - grid_height) / 2

    per_page = cols * rows
    for index, client in enumerate(clients):
        position = index % per_page
        if index > 0 and position == 0:
            c.showPage()
        col = position % cols
        row = position // cols
        x = margin_x + col * (card_w + gap_x)
        y = page_height - margin_y - card_h - row * (card_h + gap_y)
        draw_carte_fidelite(c, x, y, client, pharmacy_name)

    c.save()
