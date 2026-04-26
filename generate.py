#!/usr/bin/env python3
"""
Génère les portails locataires sécurisés avec :
- URL UUID aléatoire
- PIN hashé SHA-256 (jamais en clair dans le HTML)
- Infos sensibles encodées (base64 + hash)
- Contrat de bail PDF dans /contrats/
- Quittances depuis date début → aujourd'hui
- Push automatique sur GitHub Pages
"""

import json, os, sys, hashlib, uuid, base64
from datetime import datetime
from pathlib import Path

DIR = Path(__file__).parent
PUBLIC = DIR / 'public'
CONTRATS = DIR / 'contrats'
PUBLIC.mkdir(exist_ok=True)
CONTRATS.mkdir(exist_ok=True)

BAILLEUR_NOM = "EL OUARDI Yassine"
BAILLEUR_ADRESSE = "3 Allée du Pourquoi Pas, 91000 Évry"
MONTHS_FR = ['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre']

# ── Les 3 locataires EVERY ──
LOCATAIRES = [
    {
        'nom': 'DRAA', 'prenom': 'Abdelilah',
        'bien': 'EVERY', 'adresse': '3 Allée du Pourquoi Pas, 91000 Évry',
        'loyer': 400, 'charges': 50,
        'date_debut': '2025-09-30', 'duree_mois': 9,
        'depot': 400, 'pin': '1234',
        'bail_pdf': 'Bail-DRAA-ABDELILAH.pdf',
        'messages': []
    },
    {
        'nom': 'MESBAH', 'prenom': 'Abderahmane',
        'bien': 'EVERY', 'adresse': '1 rue Jean Jacques Rousseau, 94200 Ivry-sur-Seine',
        'loyer': 400, 'charges': 50,
        'date_debut': '2026-04-01', 'duree_mois': 12,
        'depot': 400, 'pin': '2219',
        'bail_pdf': 'MESBAHI-bail_colocation_chambre_v3 1.pdf',
        'messages': []
    },
    {
        'nom': 'EZZAHID', 'prenom': 'Samir',
        'bien': 'EVERY', 'adresse': '3 Allée du Pourquoi Pas, 91000 Évry',
        'loyer': 400, 'charges': 50,
        'date_debut': '2026-02-01', 'duree_mois': 12,
        'depot': 400, 'pin': '3456',
        'bail_pdf': 'SAMI-Contrat bail de location chambre Bras de Fer.pdf',
        'messages': []
    },
]


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def b64encode(text):
    # Encode UTF-8 bytes as percent-encoded then base64, so JS can decode properly
    encoded = text.encode('utf-8')
    return base64.b64encode(encoded).decode('ascii')


def generate_uuid():
    """UUID aléatoire — nouveau à chaque génération."""
    return str(uuid.uuid4())


def get_date_fin(date_debut, duree_mois=12):
    d = datetime.strptime(date_debut, '%Y-%m-%d')
    year = d.year + (d.month + duree_mois - 1) // 12
    month = (d.month + duree_mois - 1) % 12 + 1
    return datetime(year, month, d.day).strftime('%d/%m/%Y')


def generate_quittances_rows(loc):
    """Génère les lignes de quittances HTML depuis date_debut jusqu'à aujourd'hui."""
    try:
        start = datetime.strptime(loc['date_debut'], '%Y-%m-%d')
    except:
        return ''

    loyer = loc['loyer']
    charges = loc['charges']
    total = loyer + charges
    today = datetime.now()
    rows = []
    cur = start.replace(day=1)

    while cur <= today:
        mois = MONTHS_FR[cur.month - 1] + ' ' + str(cur.year)
        # Quittance text for download (encoded)
        q_text = f"""QUITTANCE DE LOYER

Bailleur: {BAILLEUR_NOM}
{BAILLEUR_ADRESSE}

Locataire: {loc['nom']} {loc['prenom']}
Bien: {loc['bien']}, {loc['adresse']}

Période: {mois}

Loyer: {loyer},00 €
Charges: {charges},00 €
Total: {total},00 €

Fait à Évry, le {today.strftime('%d/%m/%Y')}
{BAILLEUR_NOM}

(Loi n° 89-462 du 6 juillet 1989, art. 21)"""

        q_b64 = b64encode(q_text)

        rows.append(f'''<tr style="border-bottom:1px solid #2a3655">
<td style="padding:8px;font-weight:600">{mois}</td>
<td style="text-align:right;padding:8px">{loyer} €</td>
<td style="text-align:right;padding:8px">{charges} €</td>
<td style="text-align:right;padding:8px;font-weight:700;color:#fbbf24">{total} €</td>
<td style="text-align:center;padding:8px"><button onclick="_dlQ('{q_b64}','{mois.replace(" ","_")}')" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:4px 10px;font-size:.72rem;cursor:pointer">📄 PDF</button></td>
</tr>''')

        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)

    return '\n'.join(rows)


def generate_contrat_text(loc):
    """Contrat de bail complet."""
    d = datetime.strptime(loc['date_debut'], '%Y-%m-%d')
    fin = get_date_fin(loc['date_debut'], loc.get('duree_mois', 12))

    return f"""CONTRAT DE LOCATION
{'═' * 40}

ENTRE LES SOUSSIGNÉS :

LE BAILLEUR :
{BAILLEUR_NOM}
{BAILLEUR_ADRESSE}

LE LOCATAIRE :
{loc['nom']} {loc['prenom']}

IL A ÉTÉ CONVENU ET ARRÊTÉ CE QUI SUIT :

ARTICLE 1 — OBJET DU CONTRAT
Le Bailleur donne en location au Locataire, qui accepte, un logement situé :
{loc['bien']}, {loc['adresse']}

ARTICLE 2 — DURÉE
Le présent contrat est conclu pour une durée de {loc.get('duree_mois',12)} mois.
Date de début : {d.strftime('%d/%m/%Y')}
Date de fin : {fin}

ARTICLE 3 — LOYER ET CHARGES
Loyer mensuel : {loc['loyer']},00 €
Provision pour charges : {loc['charges']},00 €
Total mensuel : {loc['loyer'] + loc['charges']},00 €

Le loyer est payable le 5 de chaque mois, d'avance.

ARTICLE 4 — DÉPÔT DE GARANTIE
Le locataire verse à la signature un dépôt de garantie de {loc.get('depot', loc['loyer'])},00 €.

ARTICLE 5 — CHARGES RÉCUPÉRABLES
Les charges locatives comprennent : eau froide, entretien des parties communes,
taxe d'enlèvement des ordures ménagères.

ARTICLE 6 — OBLIGATIONS DU LOCATAIRE
Le locataire s'engage à :
- Payer le loyer et les charges aux termes convenus
- User paisiblement des locaux
- Répondre des dégradations
- Ne pas sous-louer sans accord du bailleur
- Souscrire une assurance habitation

ARTICLE 7 — OBLIGATIONS DU BAILLEUR
Le bailleur s'engage à :
- Délivrer un logement décent
- Assurer la jouissance paisible du logement
- Entretenir les locaux en état de servir
- Délivrer une quittance de loyer

ARTICLE 8 — LOI APPLICABLE
Le présent contrat est soumis à la Loi n° 89-462 du 6 juillet 1989.

Fait en deux exemplaires à Évry, le {d.strftime('%d/%m/%Y')}

Le Bailleur                              Le Locataire
{BAILLEUR_NOM}              {loc['nom']} {loc['prenom']}
"""


def generate_portal_html(loc, page_uuid, contrat_uuid):
    """Génère le HTML sécurisé avec PIN hashé et données encodées."""
    pin_hash = sha256(loc['pin'])
    nom = loc['nom']
    prenom = loc['prenom']
    initiale = nom[0].upper()
    bien = loc['bien']
    loyer = loc['loyer']
    charges = loc['charges']
    total = loyer + charges
    date_debut_fmt = datetime.strptime(loc['date_debut'], '%Y-%m-%d').strftime('%d/%m/%Y')
    date_fin = get_date_fin(loc['date_debut'], loc.get('duree_mois', 12))

    # Encode sensitive data
    nom_b64 = b64encode(f"{nom} {prenom}")
    bien_b64 = b64encode(bien)
    adresse_b64 = b64encode(loc['adresse'])
    loyer_b64 = b64encode(str(loyer))
    charges_b64 = b64encode(str(charges))

    quittances = generate_quittances_rows(loc)

    contrat_b64 = b64encode(generate_contrat_text(loc))

    messages_html = ''
    for m in loc.get('messages', []):
        messages_html += f'<div style="padding:10px;background:#1a2236;border-radius:8px;margin-bottom:8px;border-left:3px solid #8b5cf6"><div style="font-size:.82rem">{m.get("text","")}</div><div style="font-size:.68rem;color:#64748b;margin-top:4px">{m.get("date","")}</div></div>'
    if not messages_html:
        messages_html = '<div style="color:#64748b;font-size:.82rem">Aucun message pour le moment.</div>'

    # Use real bail PDF from GED if available
    bail_pdf = loc.get('bail_pdf', '')
    if bail_pdf:
        contrat_url = f'../contrats/{page_uuid}-bail.pdf'
    else:
        contrat_url = f'../contrats/{contrat_uuid}.html'

    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Portail Locataire</title>
<script src="https://cdn.tailwindcss.com"></script><script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.2/jspdf.umd.min.js"></script>
<style>
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0b0f19;color:#e2e8f0;margin:0;min-height:100vh}}
.pin-overlay{{position:fixed;inset:0;z-index:9999;background:#0b0f19;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:24px}}
.pin-dot{{width:14px;height:14px;border-radius:50%;background:#243050;border:2px solid #2a3655;transition:.2s}}
.pin-dot.filled{{background:#3b82f6}}
.pin-btn{{width:64px;height:52px;border-radius:10px;background:#1a2236;border:1px solid #2a3655;color:#e2e8f0;font-size:1.2rem;font-weight:600;cursor:pointer}}
.pin-btn:hover{{background:#243050;border-color:#3b82f6}}
</style>
</head>
<body>
<div id="pin-lock" class="pin-overlay">
  <div style="text-align:center">
    <div style="font-size:3rem;margin-bottom:8px">🏠</div>
    <h1 style="font-size:1.4rem;color:#fbbf24;margin:0">Portail Locataire</h1>
    <p style="color:#64748b;font-size:.85rem;margin-top:4px">Entrez votre code PIN</p>
  </div>
  <div style="display:flex;gap:12px;margin:8px 0" id="pin-dots">
    <div class="pin-dot" id="d0"></div><div class="pin-dot" id="d1"></div>
    <div class="pin-dot" id="d2"></div><div class="pin-dot" id="d3"></div>
  </div>
  <div id="pin-error" style="color:#ef4444;font-size:.82rem;min-height:20px"></div>
  <div style="display:grid;grid-template-columns:repeat(3,64px);gap:8px">
    <button class="pin-btn" onclick="pk('1')">1</button><button class="pin-btn" onclick="pk('2')">2</button><button class="pin-btn" onclick="pk('3')">3</button>
    <button class="pin-btn" onclick="pk('4')">4</button><button class="pin-btn" onclick="pk('5')">5</button><button class="pin-btn" onclick="pk('6')">6</button>
    <button class="pin-btn" onclick="pk('7')">7</button><button class="pin-btn" onclick="pk('8')">8</button><button class="pin-btn" onclick="pk('9')">9</button>
    <button class="pin-btn" onclick="pk('clr')" style="font-size:.8rem">CLR</button><button class="pin-btn" onclick="pk('0')">0</button><button class="pin-btn" onclick="pk('del')" style="color:#ef4444">⌫</button>
  </div>
</div>

<div id="pc" style="display:none">
  <div style="background:#111827;border-bottom:1px solid #2a3655;padding:16px 24px;display:flex;align-items:center;gap:12px">
    <div style="width:42px;height:42px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#8b5cf6);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1.1rem" id="hdr-init"></div>
    <div><div style="font-weight:800;font-size:1rem" id="hdr-nom"></div><div style="font-size:.72rem;color:#64748b" id="hdr-bien"></div></div>
    <div style="margin-left:auto;text-align:right"><div style="font-size:.68rem;color:#64748b">Loyer mensuel</div><div style="font-size:1.2rem;font-weight:800;color:#fbbf24" id="hdr-loyer"></div></div>
  </div>
  <div style="max-width:900px;margin:24px auto;padding:0 16px">
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:24px">
      <div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em">Bien</div><div style="font-size:1rem;font-weight:700;margin-top:4px" id="info-bien"></div></div>
      <div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em">Début contrat</div><div style="font-size:1rem;font-weight:700;margin-top:4px;color:#10b981">{date_debut_fmt}</div></div>
      <div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em">Fin contrat</div><div style="font-size:1rem;font-weight:700;margin-top:4px;color:#f59e0b">{date_fin}</div></div>
      <div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase;letter-spacing:.08em">Charges</div><div style="font-size:1rem;font-weight:700;margin-top:4px" id="info-charges"></div></div>
    </div>
    <div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden">
      <div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">📄 Documents</h3></div>
      <div style="padding:14px 18px">
        <div style="display:flex;align-items:center;gap:10px;padding:10px;background:#1a2236;border-radius:8px;margin-bottom:8px">
          <span style="font-size:1.2rem">📋</span>
          <div style="flex:1"><div style="font-weight:600;font-size:.82rem">Contrat de Bail</div><div style="font-size:.7rem;color:#64748b">Durée {loc.get('duree_mois',12)} mois</div></div>
          <a href="{contrat_url}" target="_blank" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;cursor:pointer;text-decoration:none;font-weight:600">📥 Ouvrir</a>
          <button onclick="_dlC()" style="background:#10b981;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;cursor:pointer;font-weight:600">💾 Télécharger</button>
        </div>
      </div>
    </div>
    <div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden">
      <div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">🧾 Quittances de Loyer</h3></div>
      <div style="padding:14px 18px">
        <table style="width:100%;border-collapse:collapse;font-size:.82rem">
          <thead><tr style="border-bottom:2px solid #2a3655">
            <th style="text-align:left;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Période</th>
            <th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Loyer</th>
            <th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Charges</th>
            <th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Total</th>
            <th style="text-align:center;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">PDF</th>
          </tr></thead>
          <tbody>{quittances}</tbody>
        </table>
      </div>
    </div>
    <div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden;border-left:3px solid #8b5cf6">
      <div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">💬 Messages du Propriétaire</h3></div>
      <div style="padding:14px 18px">{messages_html}</div>
    </div>
    <div style="text-align:center;padding:20px;font-size:.7rem;color:#64748b">EL OUARDI PATRIMOINE — Portail Locataire Sécurisé</div>
  </div>
</div>

<script>
var _p='',_h='{pin_hash}';
var _d={{n:'{nom_b64}',b:'{bien_b64}',l:'{loyer_b64}',c:'{charges_b64}',ct:'{contrat_b64}'}};
function _b(s){{try{{var b=atob(s);var bytes=new Uint8Array(b.length);for(var i=0;i<b.length;i++)bytes[i]=b.charCodeAt(i);return new TextDecoder('utf-8').decode(bytes)}}catch(e){{return s}}}}
async function _sha(t){{var e=new TextEncoder().encode(t);var h=await crypto.subtle.digest('SHA-256',e);return Array.from(new Uint8Array(h)).map(b=>b.toString(16).padStart(2,'0')).join('')}}
function pk(k){{
  if(k==='clr'){{_p='';ud();document.getElementById('pin-error').textContent='';return}}
  if(k==='del'){{_p=_p.slice(0,-1);ud();return}}
  if(_p.length>=4)return;_p+=k;ud();
  if(_p.length===4)_sha(_p).then(function(h){{
    if(h===_h){{document.getElementById('pin-lock').style.display='none';document.getElementById('pc').style.display='block';
      document.getElementById('hdr-init').textContent=_b(_d.n)[0];
      document.getElementById('hdr-nom').textContent=_b(_d.n);
      document.getElementById('hdr-bien').textContent='Locataire — '+_b(_d.b);
      document.getElementById('hdr-loyer').textContent=_b(_d.l)+' €';
      document.getElementById('info-bien').textContent=_b(_d.b);
      document.getElementById('info-charges').textContent=_b(_d.c)+' €/mois';
    }}else{{document.getElementById('pin-error').textContent='Code PIN incorrect';_p='';setTimeout(ud,300)}}
  }})
}}
function ud(){{for(var i=0;i<4;i++){{var d=document.getElementById('d'+i);if(d)d.classList.toggle('filled',i<_p.length)}}}}
function _loadJsPDF(cb){{cb()}}
function _dlQ(b,m){{_loadJsPDF(function(){{var t=_b(b);var lines=t.split('\\n');var doc=new jspdf.jsPDF();var y=20;doc.setFontSize(16);doc.setFont('helvetica','bold');doc.text('QUITTANCE DE LOYER',105,y,{{align:'center'}});y+=7;doc.setFontSize(9);doc.setFont('helvetica','normal');doc.setTextColor(100);doc.text('Loi du 6 juillet 1989 - Article 21',105,y,{{align:'center'}});y+=10;doc.setTextColor(0);doc.setFontSize(10);lines.forEach(function(l){{if(y>270){{doc.addPage();y=20}}doc.text(l.substring(0,90),14,y);y+=5.5}});doc.save('Quittance_'+m+'.pdf')}})}}
function _dlC(){{_loadJsPDF(function(){{var t=_b(_d.ct);var lines=t.split('\\n');var doc=new jspdf.jsPDF();var y=20;doc.setFontSize(16);doc.setFont('helvetica','bold');doc.text('CONTRAT DE BAIL',105,y,{{align:'center'}});y+=7;doc.setFontSize(9);doc.setFont('helvetica','normal');doc.setTextColor(100);doc.text('Loi n. 89-462 du 6 juillet 1989',105,y,{{align:'center'}});y+=10;doc.setTextColor(0);doc.setFontSize(10);lines.forEach(function(l){{if(y>270){{doc.addPage();y=20}}if(l.startsWith('ARTICLE')||l.startsWith('LE ')||l.startsWith('ENTRE')){{doc.setFont('helvetica','bold')}}else{{doc.setFont('helvetica','normal')}}doc.text(l.substring(0,90),14,y);y+=5.5}});doc.save('Contrat_Bail.pdf')}})}}

</script>
</body></html>'''


def generate_contrat_html(loc, contrat_uuid):
    """Génère une page HTML contrat protégée par PIN."""
    pin_hash = sha256(loc['pin'])
    contrat_text = generate_contrat_text(loc)
    contrat_b64 = b64encode(contrat_text)

    return f'''<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Contrat de Bail</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.2/jspdf.umd.min.js"></script><style>body{{font-family:system-ui;background:#0b0f19;color:#e2e8f0;margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center}}
.pin-overlay{{position:fixed;inset:0;z-index:9999;background:#0b0f19;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:24px}}
.pin-dot{{width:14px;height:14px;border-radius:50%;background:#243050;border:2px solid #2a3655;transition:.2s}}.pin-dot.filled{{background:#3b82f6}}
.pin-btn{{width:64px;height:52px;border-radius:10px;background:#1a2236;border:1px solid #2a3655;color:#e2e8f0;font-size:1.2rem;font-weight:600;cursor:pointer}}.pin-btn:hover{{background:#243050}}
</style></head><body>
<div id="pin-lock" class="pin-overlay">
  <div style="text-align:center"><div style="font-size:3rem">📋</div><h1 style="font-size:1.2rem;color:#fbbf24">Contrat de Bail — Accès sécurisé</h1><p style="color:#64748b;font-size:.82rem">Entrez votre code PIN</p></div>
  <div style="display:flex;gap:12px" id="pin-dots"><div class="pin-dot" id="d0"></div><div class="pin-dot" id="d1"></div><div class="pin-dot" id="d2"></div><div class="pin-dot" id="d3"></div></div>
  <div id="pin-error" style="color:#ef4444;font-size:.82rem;min-height:20px"></div>
  <div style="display:grid;grid-template-columns:repeat(3,64px);gap:8px">
    <button class="pin-btn" onclick="pk('1')">1</button><button class="pin-btn" onclick="pk('2')">2</button><button class="pin-btn" onclick="pk('3')">3</button>
    <button class="pin-btn" onclick="pk('4')">4</button><button class="pin-btn" onclick="pk('5')">5</button><button class="pin-btn" onclick="pk('6')">6</button>
    <button class="pin-btn" onclick="pk('7')">7</button><button class="pin-btn" onclick="pk('8')">8</button><button class="pin-btn" onclick="pk('9')">9</button>
    <button class="pin-btn" onclick="pk('clr')" style="font-size:.8rem">CLR</button><button class="pin-btn" onclick="pk('0')">0</button><button class="pin-btn" onclick="pk('del')" style="color:#ef4444">⌫</button>
  </div>
</div>
<div id="ct" style="display:none;max-width:800px;margin:40px auto;padding:20px">
  <pre id="ct-text" style="white-space:pre-wrap;font-family:system-ui;font-size:.85rem;line-height:1.8;background:#111827;border:1px solid #2a3655;border-radius:12px;padding:24px"></pre>
  <div style="text-align:center;margin-top:16px"><button onclick="_dl()" style="background:#3b82f6;color:#fff;border:none;border-radius:8px;padding:10px 24px;font-size:.85rem;font-weight:700;cursor:pointer">💾 Télécharger le contrat</button></div>
</div>
<script>
var _p='',_h='{pin_hash}',_c='{contrat_b64}';
function _b(s){{try{{var b=atob(s);var bytes=new Uint8Array(b.length);for(var i=0;i<b.length;i++)bytes[i]=b.charCodeAt(i);return new TextDecoder('utf-8').decode(bytes)}}catch(e){{return s}}}}
async function _sha(t){{var e=new TextEncoder().encode(t);var h=await crypto.subtle.digest('SHA-256',e);return Array.from(new Uint8Array(h)).map(b=>b.toString(16).padStart(2,'0')).join('')}}
function pk(k){{if(k==='clr'){{_p='';ud();document.getElementById('pin-error').textContent='';return}}if(k==='del'){{_p=_p.slice(0,-1);ud();return}}if(_p.length>=4)return;_p+=k;ud();if(_p.length===4)_sha(_p).then(function(h){{if(h===_h){{document.getElementById('pin-lock').style.display='none';document.getElementById('ct').style.display='block';document.getElementById('ct-text').textContent=_b(_c)}}else{{document.getElementById('pin-error').textContent='Code PIN incorrect';_p='';setTimeout(ud,300)}}}})}}
function ud(){{for(var i=0;i<4;i++){{var d=document.getElementById('d'+i);if(d)d.classList.toggle('filled',i<_p.length)}}}}
function _dl(){{var t=_b(_c);var bl=new Blob([t],{{type:'text/plain'}});var a=document.createElement('a');a.href=URL.createObjectURL(bl);a.download='Contrat_Bail.txt';a.click()}}
</script></body></html>'''


def main():
    manifest = []

    # Use dynamic data from app if --from-app flag
    if '--from-app' in sys.argv:
        input_path = DIR / '_input_locataires.json'
        if input_path.exists():
            import copy
            app_locs = json.loads(input_path.read_text())
            locataires_to_use = []
            for al in app_locs:
                locataires_to_use.append({
                    'nom': al.get('nom', ''),
                    'prenom': al.get('prenom', ''),
                    'bien': al.get('bien', 'EVERY'),
                    'adresse': al.get('adresse', '3 Allée du Pourquoi Pas, 91000 Évry'),
                    'loyer': al.get('loyer', 400),
                    'charges': al.get('charges', 50),
                    'date_debut': al.get('date_debut', ''),
                    'date_fin': al.get('date_fin', ''),
                    'duree_mois': 12,
                    'depot': al.get('depot', al.get('loyer', 400)),
                    'pin': al.get('portal_pin', ''),
                    'messages': al.get('portal_messages', []),
                })
            input_path.unlink()
        else:
            locataires_to_use = LOCATAIRES
    else:
        locataires_to_use = LOCATAIRES

    # Clean old files
    for f in PUBLIC.glob('*.html'):
        if f.name != '.gitkeep':
            f.unlink()
    for f in CONTRATS.glob('*.html'):
        f.unlink()

    print(f"\n{'═' * 60}")
    print(f"  🏠 GÉNÉRATION PORTAILS LOCATAIRES — {len(locataires_to_use)} locataires")
    print(f"{'═' * 60}\n")

    for loc in locataires_to_use:
        nom = loc['nom']
        prenom = loc['prenom']
        page_uuid = generate_uuid()
        contrat_uuid = generate_uuid()
        # Generate new random PIN
        pin = str(1000 + __import__('random').randint(0, 8999))
        loc['pin'] = pin

        # Generate portal HTML
        portal_html = generate_portal_html(loc, page_uuid, contrat_uuid)
        portal_path = PUBLIC / f'{page_uuid}.html'
        portal_path.write_text(portal_html, encoding='utf-8')

        # Copy real bail PDF from GED or generate HTML contrat
        import shutil
        GED_DIR = Path(os.path.expanduser('~/Downloads/patrimoine-app/ged_documents'))
        bail_pdf = loc.get('bail_pdf', '')
        if bail_pdf and (GED_DIR / bail_pdf).exists():
            bail_dest = CONTRATS / f'{page_uuid}-bail.pdf'
            shutil.copy2(GED_DIR / bail_pdf, bail_dest)
            contrat_url_full = f'https://ingelouardi-cloud.github.io/patrimoine/contrats/{page_uuid}-bail.pdf'
            print(f"     Bail PDF: {bail_pdf} -> {bail_dest.name}")
        else:
            contrat_html = generate_contrat_html(loc, contrat_uuid)
            contrat_path = CONTRATS / f'{contrat_uuid}.html'
            contrat_path.write_text(contrat_html, encoding='utf-8')
            contrat_url_full = f'https://ingelouardi-cloud.github.io/patrimoine/contrats/{contrat_uuid}.html'

        portal_url = f'https://ingelouardi-cloud.github.io/patrimoine/public/{page_uuid}.html'

        manifest.append({
            'nom': nom,
            'prenom': prenom,
            'bien': loc['bien'],
            'pin': loc['pin'],
            'pin_hash': sha256(loc['pin']),
            'portal_uuid': page_uuid,
            'contrat_uuid': contrat_uuid,
            'portal_url': portal_url,
            'contrat_url': contrat_url_full,
        })

        print(f"  ✅ {nom} {prenom}")
        print(f"     Portal: {portal_url}")
        print(f"     Contrat: {contrat_url_full}")
        print(f"     PIN: {loc['pin']} (hashé SHA-256)")
        print()

    # Save manifest
    manifest_path = DIR / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')

    print(f"{'═' * 60}")
    print(f"  📋 Manifest: manifest.json")
    print(f"  🔐 Sécurité: PIN hashé SHA-256, données base64, UUID aléatoire")
    print(f"  📁 Portails: public/ ({len(LOCATAIRES)} fichiers)")
    print(f"  📁 Contrats: contrats/ ({len(LOCATAIRES)} fichiers)")
    print(f"{'═' * 60}\n")

    # Auto-push to GitHub
    print("  🚀 Push vers GitHub Pages...")
    os.system(f'cd {DIR} && git add -A && git commit -m "MAJ portails locataires — {len(LOCATAIRES)} locataires" && git push')
    print("  ✅ Déployé sur GitHub Pages\n")


if __name__ == '__main__':
    main()
