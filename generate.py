#!/usr/bin/env python3
"""Génère les portails locataires — 2 templates: France (EUR) + Maroc (MAD)."""
import json, os, sys, hashlib, random, shutil, base64
from datetime import datetime
from pathlib import Path

DIR = Path(__file__).parent
PUBLIC = DIR / 'public'
CONTRATS = DIR / 'contrats'
GED = Path(os.path.expanduser('~/Downloads/patrimoine-app/ged_documents'))
PUBLIC.mkdir(exist_ok=True)
CONTRATS.mkdir(exist_ok=True)

MOIS_FR = ['Janvier','Fevrier','Mars','Avril','Mai','Juin','Juillet','Aout','Septembre','Octobre','Novembre','Decembre']
MOIS_AR = ['يناير','فبراير','مارس','أبريل','ماي','يونيو','يوليوز','غشت','شتنبر','أكتوبر','نونبر','دجنبر']

LOCATAIRES_FALLBACK = [
    {'nom':'DRAA','prenom':'Abdelilah','loyer':400,'charges':50,'devise':'EUR',
     'date_debut':'2025-09-30','date_fin':'2026-06-30','bien':'EVRY','bail':''},
    {'nom':'MESBAH','prenom':'Abderahmane','loyer':400,'charges':50,'devise':'EUR',
     'date_debut':'2026-04-01','date_fin':'2027-04-01','bien':'EVRY','bail':''},
    {'nom':'EZZAHID','prenom':'Samir','loyer':400,'charges':50,'devise':'EUR',
     'date_debut':'2026-02-01','date_fin':'2027-02-01','bien':'EVRY','bail':''},
]

# Bails Maroc uniquement — les bails France sont générés dynamiquement depuis les données app
BAIL_FILES = {
    'MECHMOUM': '20260608_231719_nouveau document 2026-06-08 17.35.18.pdf',
    'MACHMOUM': '20260608_231719_nouveau document 2026-06-08 17.35.18.pdf',
}

EJS_KEY = '73LOazWxg3Xb82Xjk'
EJS_SVC = 'service_lwj64xp'
EJS_TPL = 'template_0xxr7zr'

# ═══════════════════════════════════════════════
# UTILITAIRES
# ═══════════════════════════════════════════════

def fmt_date(d):
    try: return datetime.strptime(d,'%Y-%m-%d').strftime('%d/%m/%Y')
    except: return d

def slug(nom, prenom=''):
    return (nom+'-'+prenom).lower().replace(' ','-').replace("'","") if prenom else nom.lower().replace(' ','-')

def get_pin(loc, old_manifest):
    nom = loc['nom']
    old = next((m for m in old_manifest if m.get('nom','').lower()==nom.lower()),{})
    return loc.get('portal_pin','') or loc.get('pin','') or old.get('pin','') or str(1000+random.randint(0,8999))

def copy_bail(loc, s):
    """Copie le bail PDF dans contrats/ si disponible."""
    bail_file = loc.get('bail','')
    bail_src = GED/bail_file if bail_file else None
    if bail_src and bail_src.is_file():
        shutil.copy2(bail_src, CONTRATS/f'{s}-bail.pdf')
        return f'../contrats/{s}-bail.pdf'
    return '#'

def quittances_html(loc, devise='EUR'):
    """Génère les lignes de quittances pour toutes les périodes."""
    rows = ''
    now = datetime.now()
    ds = devise
    periods = []
    for h in loc.get('contrats_historique', []):
        try:
            periods.append({
                'start': datetime.strptime(h['date_debut'],'%Y-%m-%d').replace(day=1),
                'end': datetime.strptime(h['date_fin'],'%Y-%m-%d'),
                'loyer': h.get('loyer', loc['loyer']),
                'charges': h.get('charges', loc['charges'])
            })
        except: pass
    try:
        periods.append({
            'start': datetime.strptime(loc['date_debut'],'%Y-%m-%d').replace(day=1),
            'end': now, 'loyer': loc['loyer'], 'charges': loc['charges']
        })
    except: pass

    seen = set()
    for p in periods:
        cur, end = p['start'], min(p['end'], now)
        loyer, charges, total = p['loyer'], p['charges'], p['loyer']+p['charges']
        while cur <= end:
            key = f'{cur.year}-{cur.month:02d}'
            if key not in seen:
                seen.add(key)
                ml = MOIS_FR[cur.month-1]+' '+str(cur.year)
                deb = f'01/{cur.month:02d}/{cur.year}'
                fin = f'{28 if cur.month==2 else 30}/{cur.month:02d}/{cur.year}'
                rows += f'<tr style="border-bottom:1px solid #2a3655"><td style="padding:8px;font-weight:600">{ml}</td><td style="text-align:right;padding:8px">{loyer} {ds}</td><td style="text-align:right;padding:8px">{charges} {ds}</td><td style="text-align:right;padding:8px;font-weight:700;color:#fbbf24">{total} {ds}</td><td style="text-align:center;padding:8px"><button onclick="_qpdf(\'{ml}\',\'{deb}\',\'{fin}\')" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:4px 10px;font-size:.72rem;cursor:pointer">PDF</button></td></tr>'
            cur = cur.replace(year=cur.year+1, month=1) if cur.month==12 else cur.replace(month=cur.month+1)
    return rows

def messages_html(loc):
    msgs = loc.get('portal_messages', [])
    if not msgs:
        return '<div style="color:#64748b;font-size:.82rem">Aucun message.</div>'
    return ''.join(f'<div style="padding:10px;background:#1a2236;border-radius:8px;margin-bottom:8px;border-left:3px solid #8b5cf6"><div style="font-size:.82rem">{m.get("text","")}</div><div style="font-size:.68rem;color:#64748b;margin-top:4px">{m.get("date","")}</div></div>' for m in msgs)

def load_from_backup():
    backup_dir = Path(os.path.expanduser('~/Downloads/patrimoine-app/backUp'))
    if not backup_dir.exists(): return None
    files = sorted(backup_dir.glob('patrimoine_*.json'))
    if not files: return None
    try:
        data = json.loads(files[-1].read_text())
        actifs = [l for l in data.get('_location',{}).get('locataires',[]) if l.get('actif')]
        if not actifs: return None
        result = []
        for l in actifs:
            nom_raw, prenom_raw = l.get('nom',''), l.get('prenom','')
            if not prenom_raw and ' ' in nom_raw:
                parts = nom_raw.split(' ', 1)
                nom_raw, prenom_raw = parts[0], parts[1]
            result.append({
                'nom': nom_raw, 'prenom': prenom_raw,
                'loyer': l.get('loyer',400), 'charges': l.get('charges',50),
                'devise': l.get('devise','EUR'),
                'date_debut': l.get('date_entree', l.get('date_debut','')),
                'date_fin': l.get('date_fin',''),
                'bien': l.get('bien','EVRY'),
                # Pour les bails Maroc seulement — France : bail généré dynamiquement
                'bail': BAIL_FILES.get(nom_raw.split()[0].upper(), '') if l.get('devise','EUR')=='MAD' else l.get('bail',''),
                'depot_garantie': l.get('depot_garantie', l.get('loyer',400)),
                'contrats_historique': l.get('contrats_historique',[]),
                'portal_messages': l.get('portal_messages',[]),
                'portal_pin': l.get('portal_pin',''),
                'signature_active': l.get('signature_active', True),
            })
        print(f"  Chargé {len(result)} locataires depuis backup")
        return result
    except Exception as e:
        print(f"  Erreur lecture backup: {e}")
        return None

# Styles communs
CSS_BASE = '''body{font-family:system-ui;background:#0b0f19;color:#e2e8f0;margin:0;min-height:100vh}
.po{position:fixed;inset:0;z-index:9999;background:#0b0f19;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:24px}
.pd{width:14px;height:14px;border-radius:50%;background:#243050;border:2px solid #2a3655;transition:.2s}.pd.f{background:#3b82f6}
.pb{width:64px;height:52px;border-radius:10px;background:#1a2236;border:1px solid #2a3655;color:#e2e8f0;font-size:1.2rem;font-weight:600;cursor:pointer}.pb:hover{background:#243050}'''

def pin_html():
    return '''<div id="pl" class="po"><div style="text-align:center"><div style="font-size:3rem">\U0001f3e0</div><h1 style="font-size:1.4rem;color:#fbbf24">Portail Locataire</h1><p style="color:#64748b;font-size:.85rem">Entrez votre code PIN</p></div>
<div style="display:flex;gap:12px"><div class="pd" id="d0"></div><div class="pd" id="d1"></div><div class="pd" id="d2"></div><div class="pd" id="d3"></div></div>
<div id="pe" style="color:#ef4444;font-size:.82rem;min-height:20px"></div>
<div style="display:grid;grid-template-columns:repeat(3,64px);gap:8px"><button class="pb" onclick="pk('1')">1</button><button class="pb" onclick="pk('2')">2</button><button class="pb" onclick="pk('3')">3</button><button class="pb" onclick="pk('4')">4</button><button class="pb" onclick="pk('5')">5</button><button class="pb" onclick="pk('6')">6</button><button class="pb" onclick="pk('7')">7</button><button class="pb" onclick="pk('8')">8</button><button class="pb" onclick="pk('9')">9</button><button class="pb" onclick="pk('clr')" style="font-size:.8rem">CLR</button><button class="pb" onclick="pk('0')">0</button><button class="pb" onclick="pk('del')" style="color:#ef4444">\u232b</button></div></div>'''

def pin_js(pin_hash):
    return f'''var _p='',_h='{pin_hash}';
async function _sha(t){{var e=new TextEncoder().encode(t);var h=await crypto.subtle.digest('SHA-256',e);return Array.from(new Uint8Array(h)).map(b=>b.toString(16).padStart(2,'0')).join('')}}
function pk(k){{if(k==='clr'){{_p='';ud();document.getElementById('pe').textContent='';return}}if(k==='del'){{_p=_p.slice(0,-1);ud();return}}if(_p.length>=4)return;_p+=k;ud();if(_p.length===4)_sha(_p).then(function(h){{if(h===_h){{document.getElementById('pl').style.display='none';document.getElementById('pc').style.display='block'}}else{{document.getElementById('pe').textContent='Code PIN incorrect';_p='';setTimeout(ud,300)}}}})}}
function ud(){{for(var i=0;i<4;i++){{var d=document.getElementById('d'+i);if(d)d.classList.toggle('f',i<_p.length)}}}}'''

def header_html(nom, prenom, bien, loyer, devise):
    ds = devise
    return f'''<div style="background:#111827;border-bottom:1px solid #2a3655;padding:16px 24px;display:flex;align-items:center;gap:12px">
<div style="width:42px;height:42px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#8b5cf6);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1.1rem">{nom[0]}</div>
<div><div style="font-weight:800;font-size:1rem">{nom} {prenom}</div><div style="font-size:.72rem;color:#64748b">Locataire - {bien}</div></div>
<div style="margin-left:auto;text-align:right"><div style="font-size:.68rem;color:#64748b">Loyer mensuel</div><div style="font-size:1.2rem;font-weight:800;color:#fbbf24">{loyer} {ds}</div></div></div>'''

def kpis_html(bien, dd_fmt, df_fmt, charges, devise):
    ds = devise
    return f'''<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:24px">
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Bien</div><div style="font-size:1rem;font-weight:700;margin-top:4px">{bien}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Debut contrat</div><div style="font-size:1rem;font-weight:700;margin-top:4px;color:#10b981">{dd_fmt}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Fin contrat</div><div style="font-size:1rem;font-weight:700;margin-top:4px;color:#f59e0b">{df_fmt}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Charges</div><div style="font-size:1rem;font-weight:700;margin-top:4px">{charges} {ds}/mois</div></div></div>'''

# ═══════════════════════════════════════════════
# BAIL HTML COMPLET (Chambre en colocation)
# ═══════════════════════════════════════════════

def gen_bail_html(loc):
    """Génère le bail de location meublée – Chambre en colocation en HTML complet."""
    nom = loc.get('nom', '')
    prenom = loc.get('prenom', '')
    loyer = loc.get('loyer', 0)
    charges = loc.get('charges', 0)
    total = loyer + charges
    depot = loc.get('depot_garantie', loc.get('depot', loyer))
    adresse = loc.get('adresse', '3 Allée du Pourquoi Pas, 91000 Évry')
    date_debut_raw = loc.get('date_debut', '')
    date_fin_raw = loc.get('date_fin', '')
    date_naissance = loc.get('date_naissance', '')
    lieu_naissance = loc.get('lieu_naissance', '')

    try:
        start = datetime.strptime(date_debut_raw[:10], '%Y-%m-%d')
    except:
        start = datetime.now()

    try:
        end = datetime.strptime(date_fin_raw[:10], '%Y-%m-%d') if date_fin_raw else start.replace(year=start.year + 1)
    except:
        end = start.replace(year=start.year + 1)

    duree_mois = round((end - start).days / 30.44)
    if duree_mois >= 12:
        duree_label = f"{duree_mois // 12} an{'s' if duree_mois // 12 > 1 else ''}"
    else:
        duree_label = f"{duree_mois} mois"
    etudiant = duree_mois <= 9

    naissance_line = ''
    if date_naissance or lieu_naissance:
        naissance_line = f"<p>Date et lieu de naissance : {date_naissance or '.....................'}{', né à ' + lieu_naissance if lieu_naissance else ''}</p>"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Bail — {nom} {prenom}</title>
<style>
  body{{font-family:'Segoe UI',Arial,sans-serif;max-width:800px;margin:0 auto;padding:32px;color:#111;font-size:10pt;line-height:1.5}}
  h1{{text-align:center;font-size:15pt;border-bottom:2px solid #333;padding-bottom:8px;margin-bottom:20px}}
  h2{{font-size:11pt;margin-top:18px;margin-bottom:6px;font-weight:700}}
  p{{margin:3px 0}}
  .parties{{border:1px solid #bbb;border-radius:4px;padding:12px 16px;margin-bottom:16px}}
  .parties h2{{margin-top:0}}
  .sig{{display:flex;justify-content:space-between;margin-top:40px;gap:20px}}
  .sig-box{{text-align:center;width:45%}}
  .sig-label{{font-size:9pt;font-weight:700;margin-bottom:6px}}
  .sig-area{{border:1px solid #ccc;border-radius:4px;height:80px;margin:8px 0;display:flex;align-items:flex-end;justify-content:center;padding-bottom:8px;background:#fafafa}}
  .sig-name{{font-family:'Brush Script MT',cursive,'Segoe Script',Georgia,serif;font-size:18pt;color:#1a1a6e;font-style:italic;line-height:1}}
  .sig-footer{{font-size:8.5pt;color:#444;margin-top:4px}}
  .legal{{font-size:8pt;color:#555;margin-top:24px;border-top:1px solid #ddd;padding-top:10px}}
  @media print{{body{{padding:16px}}button{{display:none}}}}
</style>
</head>
<body>
<button onclick="window.print()" style="float:right;padding:8px 18px;background:#3b82f6;color:#fff;border:none;border-radius:6px;font-weight:700;cursor:pointer;margin-bottom:12px">🖨️ Imprimer / Enregistrer PDF</button>
<h1>Bail de location meublée – Chambre en colocation</h1>

<p>Entre les soussignés :</p>
<div class="parties">
  <h2>Le bailleur (propriétaire)</h2>
  <p>Nom / Prénom : Monsieur Yassine EL OUARDI</p>
  <p>Adresse : 3 Allée du Pourquoi Pas, 91000 Évry</p>
  <p>Téléphone / Email : +33 621 35 64 07 — ing.elouardi@gmail.com</p>
</div>
<div class="parties">
  <h2>Et le locataire (colocataire)</h2>
  <p>Nom / Prénom : {nom} {prenom}</p>
  {naissance_line}
  <p>Adresse actuelle : {adresse}</p>
</div>

<h2>1. Identification des parties</h2>
<p><strong>Bailleur :</strong> Monsieur Yassine EL OUARDI — 3 Allée du Pourquoi Pas, 91000 Évry — 06.21.35.64.07 — ing.elouardi@gmail.com</p>
<p><strong>Locataire :</strong> {nom} {prenom}{' — né le ' + date_naissance if date_naissance else ''}{' à ' + lieu_naissance if lieu_naissance else ''}</p>

<h2>2. Désignation du logement</h2>
<p>Type : Chambre meublée</p>
<p>Adresse : 3 Allée du Pourquoi Pas, 91000 Évry</p>
<p>Surface habitable : 12 m²</p>
<p>Équipements communs : cuisine, salle de bain, WC</p>

<h2>3. Durée du bail</h2>
<p>Durée : {duree_label}, du {start.strftime('%d/%m/%Y')} au {end.strftime('%d/%m/%Y')}</p>
<p>{'Bail spécifique étudiant, non renouvelable automatiquement.' if etudiant else 'Renouvelable par tacite reconduction.'}</p>

<h2>4. Loyer et charges</h2>
<p>Loyer mensuel : {loyer},00 € (hors charges)</p>
<p>Charges mensuelles : {charges},00 € (forfaitaires)</p>
<p>Total mensuel : {total},00 €</p>
<p>Dépôt de garantie : {depot},00 €</p>
<p>Paiement : virement bancaire, le 5 de chaque mois</p>

<h2>5. Inventaire du mobilier</h2>
<p>Le logement contient au minimum : literie avec couette/couverture, occultation des fenêtres, plaques de cuisson, four ou micro-ondes, réfrigérateur avec congélation, vaisselle, ustensiles de cuisine, table, chaises, étagères de rangement.</p>

<h2>6. Obligations du locataire</h2>
<p>Le locataire s'engage à : payer le loyer et les charges aux termes convenus, user paisiblement des locaux, ne pas transformer les lieux sans accord écrit du bailleur, permettre l'accès au bailleur pour visites de contrôle avec préavis de 24h, souscrire une assurance habitation avant l'entrée dans les lieux.</p>

<h2>7. Obligations du bailleur</h2>
<p>Le bailleur s'engage à : délivrer un logement décent en bon état d'usage et de réparation, assurer la jouissance paisible du logement, entretenir les locaux et effectuer les réparations autres que locatives.</p>

<h2>8. Résiliation</h2>
<p>Le locataire peut résilier à tout moment avec un préavis d'1 mois (meublé). Le bailleur peut résilier avec un préavis de 3 mois pour reprise personnelle ou vente, ou en cas de manquement grave du locataire.</p>

<h2>9. Loi applicable</h2>
<p>Loi n° 89-462 du 6 juillet 1989 — Loi ALUR du 24 mars 2014 — Loi ELAN du 23 novembre 2018</p>

<div class="sig">
  <div class="sig-box">
    <div class="sig-label">Le bailleur (propriétaire)</div>
    <div class="sig-area"><span class="sig-name">Yassine EL OUARDI</span></div>
    <div class="sig-footer">EL OUARDI Yassine<br>Fait à Évry, le {datetime.now().strftime('%d/%m/%Y')}</div>
  </div>
  <div class="sig-box">
    <div class="sig-label">Le locataire (lu et approuvé)</div>
    <div class="sig-area"><span class="sig-name">{prenom} {nom}</span></div>
    <div class="sig-footer">{nom} {prenom}<br>Date : ................................</div>
  </div>
</div>
<div class="legal">Document établi conformément à la loi n° 89-462 du 6 juillet 1989 (article 21) — Conservation recommandée : 3 ans minimum après départ du logement.</div>
</body>
</html>"""


# ═══════════════════════════════════════════════
# PORTAIL FRANCE (EUR)
# ═══════════════════════════════════════════════

def gen_portal_france(loc, old_manifest):
    nom, prenom = loc['nom'], loc['prenom']
    s = slug(nom, prenom)
    pin = get_pin(loc, old_manifest); loc['pin'] = pin
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()
    bien, loyer, charges = loc.get('bien','EVRY'), loc['loyer'], loc['charges']
    depot = loc.get('depot_garantie') or loyer
    total = loyer + charges
    dd_fmt, df_fmt = fmt_date(loc['date_debut']), fmt_date(loc['date_fin'])
    bail_url = copy_bail(loc, s)
    q = quittances_html(loc, 'EUR')
    sig_active = 'true' if loc.get('signature_active', True) else 'false'

    # Documents section
    docs = f'<div style="display:flex;flex-direction:column;gap:8px">'
    docs += f'<div style="padding:10px;background:#1a2236;border-radius:8px;border-left:3px solid #10b981"><div style="display:flex;align-items:center;gap:10px"><span style="font-size:1.2rem">\U0001f4cb</span><div style="flex:1"><div style="font-weight:600;font-size:.82rem">Contrat de Bail actuel</div><div style="font-size:.7rem;color:#64748b">Du {dd_fmt} au {df_fmt} \u2014 {total} \u20ac/mois</div></div><button onclick="_contratPDF()" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;cursor:pointer;font-weight:600">\U0001f4e5 T\u00e9l\u00e9charger PDF</button><span id="sign-badge" style="padding:3px 8px;border-radius:4px;background:rgba(16,185,129,.13);color:#10b981;font-size:.68rem;font-weight:700">En cours</span></div>'
    # Signer / Commenter
    docs += f'<div id="sign-actions" style="margin-top:10px;padding-top:10px;border-top:1px solid #2a3655;display:flex;gap:8px;flex-wrap:wrap;align-items:center"><button onclick="_signerContrat()" id="btn-signer" style="background:#10b981;color:#fff;border:none;border-radius:6px;padding:8px 18px;font-size:.8rem;cursor:pointer;font-weight:700">\u2714 Signer le contrat</button><button onclick="document.getElementById(\'comment-zone\').style.display=\'block\'" style="background:#f59e0b;color:#fff;border:none;border-radius:6px;padding:8px 18px;font-size:.8rem;cursor:pointer;font-weight:600">\U0001f4ac Demander une modification</button></div>'
    docs += f'<div id="comment-zone" style="display:none;margin-top:10px"><textarea id="comment-text" rows="3" placeholder="Decrivez les modifications souhaitees..." style="width:100%;background:#0b0f19;color:#e2e8f0;border:1px solid #2a3655;border-radius:8px;padding:10px;font-size:.82rem;resize:vertical"></textarea><div style="display:flex;gap:8px;margin-top:8px"><button onclick="_envoyerCommentaire()" style="background:#f59e0b;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.78rem;cursor:pointer;font-weight:600">\U0001f4e8 Envoyer</button><button onclick="document.getElementById(\'comment-zone\').style.display=\'none\'" style="background:#334155;color:#e2e8f0;border:none;border-radius:6px;padding:6px 14px;font-size:.78rem;cursor:pointer">Annuler</button></div></div>'
    docs += '</div>'
    # Anciens contrats
    for i, c in enumerate(reversed(loc.get('contrats_historique', []))):
        c_deb, c_fin = fmt_date(c.get('date_debut','?')), fmt_date(c.get('date_fin','?'))
        c_total = c.get('loyer',0)+c.get('charges',0)
        docs += f'<div style="display:flex;align-items:center;gap:10px;padding:10px;background:#1a2236;border-radius:8px;border-left:3px solid #64748b"><span style="font-size:1.2rem">\U0001f4c4</span><div style="flex:1"><div style="font-weight:600;font-size:.82rem;color:#94a3b8">Ancien contrat #{len(loc.get("contrats_historique",[]))-i}</div><div style="font-size:.7rem;color:#64748b">Du {c_deb} au {c_fin} \u2014 {c_total} \u20ac/mois</div></div><a href="{bail_url}" target="_blank" style="background:#64748b;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;cursor:pointer;text-decoration:none;font-weight:600">\U0001f4e5 PDF</a></div>'
    docs += '</div>'

    # Bail HTML complet encodé base64 (évite les problèmes d'échappement)
    bail_html_b64 = base64.b64encode(gen_bail_html(loc).encode('utf-8')).decode('ascii')

    # JS fonctions France (signature, contrat PDF, quittance PDF)
    js_france = f'''
{pin_js(pin_hash)}
var _SIG_ACTIVE={sig_active};
var _BAIL_URL='{bail_url}';
var _BAIL_B64='{bail_html_b64}';
var _EJS_KEY='{EJS_KEY}';var _EJS_SVC='{EJS_SVC}';var _EJS_TPL='{EJS_TPL}';
try{{emailjs.init({{publicKey:_EJS_KEY}})}}catch(e){{}}
function _sendEmail(s,b){{try{{emailjs.send(_EJS_SVC,_EJS_TPL,{{subject:s,message:b,to_email:'ing.elouardi@gmail.com'}})}}catch(e){{}}}}
function _showSignedState(ds,ts){{var b=document.getElementById('sign-badge');b.textContent='\\u2714 Sign\u00e9 '+ds;b.style.background='rgba(16,185,129,.2)';b.style.color='#10b981';var a=document.getElementById('sign-actions');a.innerHTML='<div style="padding:8px 12px;background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.2);border-radius:8px;font-size:.82rem;color:#10b981">\\u2714 Contrat sign\u00e9 le '+ds+' \u00e0 '+ts+' par {nom} {prenom}</div>';}}
function _checkSignedOnLoad(){{var sg=localStorage.getItem('contrat_signe_{nom}');if(sg){{var sd=new Date(sg);_showSignedState(sd.toLocaleDateString('fr-FR'),sd.toLocaleTimeString('fr-FR',{{hour:'2-digit',minute:'2-digit'}}))}}else if(!_SIG_ACTIVE){{var btn=document.getElementById('btn-signer');if(btn){{btn.disabled=true;btn.style.opacity='.4'}}}}}}
function _signerContrat(){{if(localStorage.getItem('contrat_signe_{nom}'))return;if(!_SIG_ACTIVE){{alert('Signature non activ\u00e9e');return}}if(!confirm('Signer le contrat ?\\n{nom} {prenom}\\n{dd_fmt} au {df_fmt}\\n{total} \u20ac/mois'))return;var now=new Date();var ds=now.toLocaleDateString('fr-FR');var ts=now.toLocaleTimeString('fr-FR',{{hour:'2-digit',minute:'2-digit'}});localStorage.setItem('contrat_signe_{nom}',now.toISOString());_showSignedState(ds,ts);_sendEmail('Contrat sign\u00e9 - {nom}','{nom} {prenom} a sign\u00e9 le '+ds);_contratPDF()}}
function _envoyerCommentaire(){{var t=document.getElementById('comment-text').value.trim();if(!t)return;document.getElementById('comment-zone').style.display='none';_sendEmail('Commentaire contrat - {nom}','{nom}: '+t)}}
function _contratPDF(){{
  if(_BAIL_URL&&_BAIL_URL!=='#'){{window.open(_BAIL_URL,'_blank');return;}}
  var bytes=Uint8Array.from(atob(_BAIL_B64),function(c){{return c.charCodeAt(0);}});
  var html=new TextDecoder('utf-8').decode(bytes);
  var w=window.open('','_blank');
  if(w){{w.document.write(html);w.document.close();}}
}}
function _qpdf(mois,deb,fin){{try{{var d=new jspdf.jsPDF();var y=20;d.setFontSize(18);d.setFont('helvetica','bold');d.text('QUITTANCE DE LOYER',105,y,{{align:'center'}});y+=12;d.setFont('helvetica','normal');d.setFontSize(10);d.text('Bailleur: EL OUARDI Yassine',14,y);y+=5;d.text('Locataire: {nom} {prenom}',14,y);y+=5;d.text('Periode: du '+deb+' au '+fin,14,y);y+=10;d.setDrawColor(0);d.setLineWidth(1);d.rect(35,y,140,20);d.setFontSize(22);d.setFont('helvetica','bold');d.text('{total} EUR',105,y+14,{{align:'center'}});y+=28;d.setFontSize(9);d.setFont('helvetica','normal');d.text('Loyer: {loyer} EUR | Charges: {charges} EUR',14,y);y+=10;d.text('Fait a Evry, le '+new Date().toLocaleDateString('fr-FR'),14,y);d.save('Quittance_'+mois.replace(/ /g,'_')+'_{nom}.pdf')}}catch(e){{alert(e.message)}}}}'''

    html = f'''<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Portail - {nom}</title>
<script src="https://cdn.tailwindcss.com"></script><script src="https://unpkg.com/jspdf@2.5.2/dist/jspdf.umd.min.js"></script><script src="https://cdn.jsdelivr.net/npm/@emailjs/browser@4/dist/email.min.js"></script>
<style>{CSS_BASE}</style></head><body>
{pin_html()}
<div id="pc" style="display:none">
{header_html(nom, prenom, bien, loyer, 'EUR')}
<div style="max-width:900px;margin:24px auto;padding:0 16px">
{kpis_html(bien, dd_fmt, df_fmt, charges, 'EUR')}
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f4c4 Documents</h3></div><div style="padding:14px 18px">{docs}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f9fe Quittances de Loyer</h3></div><div style="padding:14px 18px"><table style="width:100%;border-collapse:collapse;font-size:.82rem"><thead><tr style="border-bottom:2px solid #2a3655"><th style="text-align:left;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Periode</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b">Loyer</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b">Charges</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b">Total</th><th style="text-align:center;padding:8px;font-size:.68rem;color:#64748b">PDF</th></tr></thead><tbody>{q}</tbody></table></div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden;border-left:3px solid #8b5cf6"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f4ac Messages du Proprietaire</h3></div><div style="padding:14px 18px">{messages_html(loc)}</div></div>
<div style="text-align:center;padding:20px;font-size:.7rem;color:#64748b">EL OUARDI PATRIMOINE - Portail Securise</div></div></div>
<script>{js_france}</script></body></html>'''

    (PUBLIC/f'{s}.html').write_text(html, encoding='utf-8')
    return {'nom':nom,'prenom':prenom,'pin':pin,'slug':s,
        'portal_url':f'https://ingelouardi-cloud.github.io/patrimoine/public/{s}.html',
        'contrat_url':f'https://ingelouardi-cloud.github.io/patrimoine/contrats/{s}-bail.pdf'}


# ═══════════════════════════════════════════════
# PORTAIL MAROC (MAD)
# ═══════════════════════════════════════════════

def gen_portal_maroc(loc, old_manifest):
    nom, prenom = loc['nom'], loc['prenom']
    s = slug(nom, prenom)
    pin = get_pin(loc, old_manifest); loc['pin'] = pin
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()
    bien, loyer, charges = loc.get('bien','Maroc'), loc['loyer'], loc['charges']
    total = loyer + charges
    dd_fmt, df_fmt = fmt_date(loc['date_debut']), fmt_date(loc['date_fin'])
    bail_url = copy_bail(loc, s)
    q = quittances_html(loc, 'MAD')

    # Documents section — PDF original + mention légalisation
    docs = f'<div style="display:flex;flex-direction:column;gap:8px">'
    docs += f'<div style="padding:10px;background:#1a2236;border-radius:8px;border-left:3px solid #10b981"><div style="display:flex;align-items:center;gap:10px"><span style="font-size:1.2rem">\U0001f4cb</span><div style="flex:1"><div style="font-weight:600;font-size:.82rem">عقد الكراء / Contrat de Bail</div><div style="font-size:.7rem;color:#64748b">Du {dd_fmt} au {df_fmt} \u2014 {total} MAD/mois</div></div>'
    if bail_url != '#':
        docs += f'<a href="{bail_url}" target="_blank" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;cursor:pointer;text-decoration:none;font-weight:600">\U0001f4e5 Ouvrir PDF original</a>'
    docs += f'<span style="padding:3px 8px;border-radius:4px;background:rgba(16,185,129,.13);color:#10b981;font-size:.68rem;font-weight:700">En cours</span></div>'
    docs += f'<div style="margin-top:8px;font-size:.75rem;color:#64748b">\U0001f4dd التوقيع أمام التصديق / Signature devant la l\u00e9galisation marocaine</div>'
    docs += '</div>'
    # Anciens contrats
    for i, c in enumerate(reversed(loc.get('contrats_historique', []))):
        c_deb, c_fin = fmt_date(c.get('date_debut','?')), fmt_date(c.get('date_fin','?'))
        c_total = c.get('loyer',0)+c.get('charges',0)
        docs += f'<div style="display:flex;align-items:center;gap:10px;padding:10px;background:#1a2236;border-radius:8px;border-left:3px solid #64748b"><span style="font-size:1.2rem">\U0001f4c4</span><div style="flex:1"><div style="font-weight:600;font-size:.82rem;color:#94a3b8">عقد قديم #{len(loc.get("contrats_historique",[]))-i}</div><div style="font-size:.7rem;color:#64748b">{c_deb} \u2014 {c_fin} \u2014 {c_total} MAD</div></div></div>'
    docs += '</div>'

    # JS Maroc — quittance en arabe, pas de signature électronique
    js_maroc = f'''
{pin_js(pin_hash)}
function _qpdf(mois,deb,fin){{try{{var d=new jspdf.jsPDF();var y=20;d.setFontSize(18);d.setFont('helvetica','bold');d.text('RECU DE LOYER / Wasl al-Kiraa',105,y,{{align:'center'}});y+=12;d.setFont('helvetica','normal');d.setFontSize(10);d.text('Bailleur: EL OUARDI Yassine',14,y);y+=5;d.text('Locataire: {nom} {prenom}',14,y);y+=5;d.text('Bien: {bien}',14,y);y+=5;d.text('Periode: du '+deb+' au '+fin,14,y);y+=10;d.setDrawColor(0);d.setLineWidth(1);d.rect(35,y,140,20);d.setFontSize(22);d.setFont('helvetica','bold');d.text('{total} MAD',105,y+14,{{align:'center'}});y+=28;d.setFontSize(9);d.setFont('helvetica','normal');d.text('Loyer: {loyer} MAD | Charges: {charges} MAD',14,y);y+=10;d.text('Fait a {bien}, le '+new Date().toLocaleDateString('fr-FR'),14,y);y+=8;d.setFontSize(7);d.text('Loi n. 67-12',14,y);d.save('Quittance_'+mois.replace(/ /g,'_')+'_{nom}.pdf')}}catch(e){{alert(e.message)}}}}'''

    html = f'''<!DOCTYPE html><html lang="ar"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>بوابة المكتري - {nom}</title>
<script src="https://cdn.tailwindcss.com"></script><script src="https://unpkg.com/jspdf@2.5.2/dist/jspdf.umd.min.js"></script>
<style>{CSS_BASE}</style></head><body>
{pin_html()}
<div id="pc" style="display:none">
{header_html(nom, prenom, bien, loyer, 'MAD')}
<div style="max-width:900px;margin:24px auto;padding:0 16px">
{kpis_html(bien, dd_fmt, df_fmt, charges, 'MAD')}
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f4c4 الوثائق / Documents</h3></div><div style="padding:14px 18px">{docs}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f9fe وصولات الكراء / Quittances</h3></div><div style="padding:14px 18px"><table style="width:100%;border-collapse:collapse;font-size:.82rem"><thead><tr style="border-bottom:2px solid #2a3655"><th style="text-align:left;padding:8px;font-size:.68rem;color:#64748b">Periode</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b">Loyer</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b">Charges</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b">Total</th><th style="text-align:center;padding:8px;font-size:.68rem;color:#64748b">PDF</th></tr></thead><tbody>{q}</tbody></table></div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden;border-left:3px solid #8b5cf6"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f4ac رسائل المالك / Messages</h3></div><div style="padding:14px 18px">{messages_html(loc)}</div></div>
<div style="text-align:center;padding:20px;font-size:.7rem;color:#64748b">EL OUARDI PATRIMOINE - بوابة المكتري</div></div></div>
<script>{js_maroc}</script></body></html>'''

    (PUBLIC/f'{s}.html').write_text(html, encoding='utf-8')
    return {'nom':nom,'prenom':prenom,'pin':pin,'slug':s,
        'portal_url':f'https://ingelouardi-cloud.github.io/patrimoine/public/{s}.html',
        'contrat_url':f'https://ingelouardi-cloud.github.io/patrimoine/contrats/{s}-bail.pdf'}


# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════

def main():
    locs = None
    if '--from-app' in sys.argv:
        inp = DIR/'_input_locataires.json'
        if inp.exists():
            raw = json.loads(inp.read_text())
            app_locs = raw.get('locataires', raw) if isinstance(raw, dict) else raw
            locs = []
            for a in app_locs:
                base = next((l for l in LOCATAIRES_FALLBACK if l['nom'].lower()==a.get('nom','').lower()), {})
                # Merger: app data prend priorité — 'bail' de l'app écrase toujours (même vide)
                merged = {**base, **{k:v for k,v in a.items() if v or isinstance(v,list)}, 'loyer':a.get('loyer',400), 'charges':a.get('charges',50), 'bail':a.get('bail','')}
                if 'date_debut' not in merged and 'date_entree' in merged:
                    merged['date_debut'] = merged['date_entree']
                merged.setdefault('date_debut', '')
                merged.setdefault('date_fin', '')
                merged.setdefault('devise', 'EUR')
                locs.append(merged)
            inp.unlink()

    backup_locs = load_from_backup()
    if backup_locs:
        if locs:
            for bl in backup_locs:
                bl_nom = bl['nom'].lower().split()[0]
                match = next((l for l in locs if l.get('nom','').lower().split()[0]==bl_nom), None)
                if match:
                    if not match.get('contrats_historique'): match['contrats_historique'] = bl.get('contrats_historique',[])
                    if not match.get('portal_messages'): match['portal_messages'] = bl.get('portal_messages',[])
                else:
                    locs.append(bl)
                    print(f"  + Ajouté depuis backup: {bl['nom']}")
        else:
            locs = backup_locs
    if not locs:
        locs = LOCATAIRES_FALLBACK

    old_manifest = []
    try: old_manifest = json.loads((DIR/'manifest.json').read_text())
    except: pass

    manifest = []
    for loc in locs:
        is_maroc = loc.get('devise') == 'MAD'
        if is_maroc:
            r = gen_portal_maroc(loc, old_manifest)
        else:
            r = gen_portal_france(loc, old_manifest)
        manifest.append(r)
        flag = '\U0001f1f2\U0001f1e6' if is_maroc else '\U0001f1eb\U0001f1f7'
        print(f"  {flag} {r['nom']} {r['prenom']} PIN:{r['pin']} {'MAD' if is_maroc else 'EUR'}")

    (DIR/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    dst = Path(os.path.expanduser('~/Downloads/patrimoine-app/portail-locataires/manifest.json'))
    if dst.parent.exists(): shutil.copy2(DIR/'manifest.json', dst)
    os.system(f'cd {DIR} && git add -A && git commit -m "MAJ portails" 2>/dev/null')
    os.system(f'cd {DIR} && git push origin main 2>/dev/null')
    print(f"  {len(manifest)} portails generes")

if __name__=='__main__': main()
