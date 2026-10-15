#!/usr/bin/env python3
"""Génère les portails locataires — 2 templates: France (EUR) + Maroc (MAD)."""
import json, os, sys, hashlib, secrets, shutil, base64, calendar, re, subprocess
from html import escape as _escape
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    sys.exit("Module 'cryptography' manquant : pip3 install cryptography")
from datetime import datetime
from pathlib import Path

DIR = Path(__file__).parent
PUBLIC = DIR / 'public'
CONTRATS = DIR / 'contrats'
GED = Path(os.path.expanduser('~/Downloads/patrimoine-app/ged_documents'))
PUBLIC.mkdir(exist_ok=True)
CONTRATS.mkdir(exist_ok=True)
# PINs : jamais publiés. Stockés hors git (.gitignore) + copie privée du manifest dans Downloads.
PINS_FILE = DIR / '.pins.json'
PRIVATE_MANIFEST = Path(os.path.expanduser('~/Downloads/patrimoine-app/portail-locataires/manifest.json'))
PBKDF2_ITER = 600000

MOIS_FR = ['Janvier','Fevrier','Mars','Avril','Mai','Juin','Juillet','Aout','Septembre','Octobre','Novembre','Decembre']
MOIS_AR = ['يناير','فبراير','مارس','أبريل','ماي','يونيو','يوليوز','غشت','شتنبر','أكتوبر','نونبر','دجنبر']

# Données personnelles des locataires (CIN, téléphone, naissance…) : jamais dans git.
# Fichier local locataires.local.json (gitignoré) : {"locataires_fallback": [...], "bail_files": {...}}
LOCAL_DATA_FILE = DIR / 'locataires.local.json'
try: _LOCAL = json.loads(LOCAL_DATA_FILE.read_text(encoding='utf-8'))
except Exception: _LOCAL = {}
LOCATAIRES_FALLBACK = _LOCAL.get('locataires_fallback', [])

# Bails Maroc uniquement — les bails France sont générés dynamiquement depuis les données app
BAIL_FILES = _LOCAL.get('bail_files', {})

EJS_KEY = '73LOazWxg3Xb82Xjk'
EJS_SVC = 'service_lwj64xp'
EJS_TPL = 'template_0xxr7zr'

# ═══════════════════════════════════════════════
# UTILITAIRES
# ═══════════════════════════════════════════════

def esc(v):
    """Échappe une valeur insérée dans du HTML (texte ou attribut)."""
    return _escape('' if v is None else str(v), quote=True)

def js_val(v):
    """Valeur Python -> littéral JS sûr (apostrophes, guillemets, </script>…)."""
    return json.dumps(v, ensure_ascii=False).replace('</', '<\\/').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')

def fmt_date(d):
    try: return datetime.strptime(d,'%Y-%m-%d').strftime('%d/%m/%Y')
    except: return d

def slug(nom, prenom=''):
    return (nom+'-'+prenom).lower().replace(' ','-').replace("'","") if prenom else nom.lower().replace(' ','-')

PIN_MIN_LEN = 8
_PIN_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'

def get_pin(loc, known_pins):
    """Code d'accès du portail (longueur libre, alphanumérique, sensible à la casse).
    Ordre : code de l'app > code déjà connu ; à défaut seulement, un code de 8 caractères."""
    nom = loc['nom'].lower()
    pin = str(loc.get('portal_pin','') or loc.get('pin','') or known_pins.get(nom,'')).strip() \
        or ''.join(secrets.choice(_PIN_ALPHABET) for _ in range(PIN_MIN_LEN))
    known_pins[nom] = pin
    if len(pin) < PIN_MIN_LEN:
        print(f"  \u26a0 {loc.get('nom','')} {loc.get('prenom','')} : code d'acc\u00e8s trop court ({len(pin)} caract\u00e8res, {PIN_MIN_LEN} minimum conseill\u00e9s) \u2014 r\u00e9g\u00e9n\u00e9rer un code depuis l'app")
    return pin

def load_known_pins():
    """PINs connus : .pins.json, puis anciens manifests (migration des PINs déjà distribués)."""
    pins = {}
    for src in (DIR/'manifest.json', PRIVATE_MANIFEST):
        try:
            for m in json.loads(src.read_text()):
                if m.get('pin') and m.get('nom'): pins.setdefault(m['nom'].lower(), m['pin'])
        except Exception: pass
    try: pins.update(json.loads(PINS_FILE.read_text()))
    except Exception: pass
    return pins

def encrypt_payload(pin, payload):
    """AES-256-GCM, clé dérivée du PIN par PBKDF2-SHA256 — déchiffré dans le navigateur (WebCrypto)."""
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = hashlib.pbkdf2_hmac('sha256', pin.encode(), salt, PBKDF2_ITER, 32)
    ct = AESGCM(key).encrypt(iv, json.dumps(payload, ensure_ascii=False).encode('utf-8'), None)
    b64 = lambda b: base64.b64encode(b).decode('ascii')
    return {'s': b64(salt), 'i': b64(iv), 'c': b64(ct)}

def locked_page(head, pin, content_html, page_js, ar=False):
    """Page publique : seul l'écran de code est en clair, le contenu et ses scripts sont chiffrés."""
    enc = encrypt_payload(pin, {'h': content_html, 'j': page_js})
    return f'''{head}<body>
{pin_html(ar)}
<div id="pc" style="display:none"></div>
<script>{pin_js(enc)}</script></body></html>'''

def copy_bail(loc, s):
    """Bail PDF encodé en base64, intégré au contenu chiffré du portail (jamais publié en clair)."""
    bail_file = loc.get('bail','')
    bail_src = GED/bail_file if bail_file else None
    if bail_src and bail_src.is_file():
        return base64.b64encode(bail_src.read_bytes()).decode('ascii')
    return ''

def old_bails(loc, s):
    """PDF des anciens contrats (même ordre que contrats_historique) — '' si fichier absent."""
    return [copy_bail(c, s) for c in loc.get('contrats_historique', [])]

# Ouvre un PDF intégré (bail actuel _BAIL_PDF, ou ancien contrat _OLD_PDFS[i]) via une URL blob
PDF_JS = """function _openPdfData(d){if(!d){alert('Contrat non disponible');return}var b=Uint8Array.from(atob(d),function(c){return c.charCodeAt(0)});window.open(URL.createObjectURL(new Blob([b],{type:'application/pdf'})),'_blank')}
function _openPdf(){_openPdfData(_BAIL_PDF)}
function _openOldPdf(i){_openPdfData(_OLD_PDFS[i])}
function _esc(v){return String(v==null?'':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}"""

def est_resilie(loc):
    return not loc.get('actif', True) or bool(loc.get('resilie'))

def fin_location(loc):
    """Date de sortie d'un locataire résilié (None si bail en cours)."""
    if not est_resilie(loc): return None
    try: return datetime.strptime((loc.get('date_sortie') or loc.get('date_fin') or '')[:10], '%Y-%m-%d')
    except ValueError: return None

def _month_add(d):
    return d.replace(year=d.year+1, month=1) if d.month==12 else d.replace(month=d.month+1)

def _num(v, default=None):
    try: return float(v)
    except (TypeError, ValueError): return default

def _amount(v):
    """Montant affiché : entier si rond."""
    return int(v) if float(v) == int(v) else round(float(v), 2)

def paiements_par_mois(loc):
    """{'YYYY-MM': {'date': 'YYYY-MM-DD'|None, 'montant': float|None}} depuis loc['paiements'] (None si champ absent)."""
    if 'paiements' not in loc or loc.get('paiements') is None:
        return None
    res = {}
    for p in loc.get('paiements') or []:
        if not isinstance(p, dict): continue
        mois = str(p.get('mois') or '')[:7]
        if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', mois): continue
        date = str(p.get('date') or '')[:10]
        try: datetime.strptime(date, '%Y-%m-%d')
        except ValueError: date = None
        r = res.setdefault(mois, {'date': None, 'montant': 0.0, 'montant_connu': False})
        m = _num(p.get('montant'))
        if m is not None:
            r['montant'] += m; r['montant_connu'] = True
        if date and (not r['date'] or date > r['date']): r['date'] = date
    return res

def quittances_data(loc):
    """Mois du bail (jusqu'à aujourd'hui / la sortie) + mois payés, avec leur statut de paiement.
    Une quittance n'est délivrée que pour un mois intégralement payé (champ 'paiements' de l'app)."""
    now = datetime.now()
    periods = []
    for h in loc.get('contrats_historique', []):
        try:
            periods.append({
                'start': datetime.strptime(h['date_debut'][:10],'%Y-%m-%d').replace(day=1),
                'end': datetime.strptime(h['date_fin'][:10],'%Y-%m-%d'),
                'loyer': h.get('loyer', loc['loyer']),
                'charges': h.get('charges', loc['charges'])
            })
        except: pass
    try:
        periods.append({
            'start': datetime.strptime(loc['date_debut'][:10],'%Y-%m-%d').replace(day=1),
            'end': fin_location(loc) or now, 'loyer': loc['loyer'], 'charges': loc['charges']
        })
    except: pass

    pay = paiements_par_mois(loc) or {}
    months = {}
    for p in periods:
        cur, end = p['start'], min(p['end'], now)
        while cur <= end:
            months.setdefault(f'{cur.year}-{cur.month:02d}', (p['loyer'], p['charges']))
            cur = _month_add(cur)
    for key in pay:   # mois payé hors période connue (ex. avance) : conditions du bail en cours
        if key not in months:
            lc = next(((p['loyer'], p['charges']) for p in periods if p['start'].strftime('%Y-%m') <= key <= p['end'].strftime('%Y-%m')), (loc['loyer'], loc['charges']))
            months[key] = lc

    # Mois antérieurs au premier paiement enregistré : non listés (historique de paiements incomplet dans l'app)
    premier = min(pay) if pay else None
    out = []
    for key in sorted(months):
        if premier and key < premier: continue
        y, m = int(key[:4]), int(key[5:])
        loyer, charges = months[key]
        total = loyer + charges
        p = pay.get(key)
        paye = bool(p) and (not p['montant_connu'] or p['montant'] + 0.005 >= total)
        out.append({
            'mois': MOIS_FR[m-1]+' '+str(y), 'mois_ar': MOIS_AR[m-1]+' '+str(y),
            'deb': f'01/{m:02d}/{y}', 'fin': f'{calendar.monthrange(y, m)[1]:02d}/{m:02d}/{y}',
            'loyer': loyer, 'charges': charges, 'total': total,
            'paye': paye, 'partiel': _amount(p['montant']) if p and p['montant_connu'] and not paye and p['montant'] > 0 else None,
            'date_paiement': fmt_date(p['date']) if paye and p['date'] else (f'01/{m:02d}/{y}' if paye else ''),
        })
    return out

def quittances_html(loc, devise='EUR'):
    """Lignes du tableau des quittances + données JS (_Q) des quittances délivrables."""
    ds = esc(devise)
    maroc = devise == 'MAD'
    if not paiements_par_mois(loc):   # champ absent ou aucun paiement enregistré
        msg = 'Les quittances appara\u00eetront ici d\u00e8s que le paiement du loyer aura \u00e9t\u00e9 enregistr\u00e9.'
        if maroc: msg += '<div dir="rtl" style="margin-top:4px">\u0633\u062a\u0638\u0647\u0631 \u0648\u0635\u0648\u0644\u0627\u062a \u0627\u0644\u0643\u0631\u0627\u0621 \u0647\u0646\u0627 \u0628\u0645\u062c\u0631\u062f \u062a\u0633\u062c\u064a\u0644 \u0627\u0644\u0623\u062f\u0627\u0621.</div>'
        return f'<tr><td colspan="5" style="padding:12px;text-align:center;color:#64748b;font-size:.78rem">{msg}</td></tr>', []
    rows, q = '', []
    a_payer = '\u00c0 payer' + (' / \u0645\u0633\u062a\u062d\u0642' if maroc else '')
    for e in quittances_data(loc):
        if e['paye']:
            q.append({k: e[k] for k in ('mois','mois_ar','deb','fin','loyer','charges','total','date_paiement')})
            action = f'<button onclick="_qpdf({len(q)-1})" title="Pay\u00e9 le {esc(e["date_paiement"])}" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:4px 10px;font-size:.72rem;cursor:pointer">PDF</button>'
        else:
            partiel = f'<div style="font-size:.65rem;color:#94a3b8;margin-top:2px">Vers\u00e9 {esc(e["partiel"])} {ds}</div>' if e['partiel'] else ''
            action = f'<span style="padding:3px 8px;border-radius:4px;background:rgba(239,68,68,.13);color:#ef4444;font-size:.68rem;font-weight:700;white-space:nowrap">{a_payer}</span>{partiel}'
        rows += f'<tr style="border-bottom:1px solid #2a3655"><td style="padding:8px;font-weight:600">{esc(e["mois"])}</td><td style="text-align:right;padding:8px">{esc(e["loyer"])} {ds}</td><td style="text-align:right;padding:8px">{esc(e["charges"])} {ds}</td><td style="text-align:right;padding:8px;font-weight:700;color:#fbbf24">{esc(e["total"])} {ds}</td><td style="text-align:center;padding:8px">{action}</td></tr>'
    if not rows:
        rows = '<tr><td colspan="5" style="padding:12px;text-align:center;color:#64748b;font-size:.78rem">Aucune p\u00e9riode \u00e0 afficher.</td></tr>'
    return rows, q

def message_texte(m):
    """Texte d'un message propriétaire, quel que soit le nom du champ utilisé par l'app."""
    if isinstance(m, str): return m.strip()
    if not isinstance(m, dict): return ''
    for k in ('texte', 'message', 'text', 'contenu'):
        v = m.get(k)
        if isinstance(v, str) and v.strip(): return v.strip()
    return ''

def messages_html(loc):
    msgs = [(message_texte(m), m.get('date','') if isinstance(m, dict) else '') for m in loc.get('portal_messages') or []]
    msgs = [(t, d) for t, d in msgs if t]
    if not msgs:
        return '<div style="color:#64748b;font-size:.82rem">Aucun message.</div>'
    return ''.join(f'<div style="padding:10px;background:#1a2236;border-radius:8px;margin-bottom:8px;border-left:3px solid #8b5cf6"><div style="font-size:.82rem;white-space:pre-wrap">{esc(t)}</div><div style="font-size:.68rem;color:#64748b;margin-top:4px">{esc(fmt_date(str(d)[:10]) if d else "")}</div></div>' for t, d in msgs)

def _fmt_dh(v):
    """Formate un montant DH : entier si rond, 1 décimale sinon."""
    return f'{v:,.1f}' if v != int(v) else f'{int(v):,}'

def cagnotte_html(loc):
    """Section cagnotte charges variables pour le portail locataire."""
    cag = loc.get('cagnotte') or {}
    if not cag or (not cag.get('solde_initial') and not cag.get('mouvements')):
        return ''
    solde_initial = cag.get('solde_initial', 0)
    mouvements = sorted(cag.get('mouvements', []), key=lambda m: m.get('date',''), reverse=True)
    total_dep = sum(m.get('montant', 0) for m in mouvements)
    solde_restant = solde_initial - total_dep
    couleur = '#10b981' if solde_restant >= 0 else '#ef4444'
    pct = max(0, min(100, int(solde_restant / solde_initial * 100))) if solde_initial > 0 else 0

    rows = ''
    running = solde_initial
    for m in mouvements:
        running_after = running - m.get('montant', 0)
        justif_html = ''
        if m.get('justif'):
            justif_html = f'<br><img src="{esc(m["justif"])}" style="max-width:120px;max-height:80px;object-fit:cover;border-radius:6px;margin-top:6px;border:1px solid #2a3655;cursor:pointer" onclick="window.open(this.src,\'_blank\')" title="Voir justificatif">'
        rows += f'''<tr style="border-bottom:1px solid #2a3655">
          <td style="padding:8px 10px;font-size:.78rem;color:#94a3b8">{esc(m.get('date',''))}</td>
          <td style="padding:8px 10px;font-size:.82rem">{esc(m.get('libelle',''))}{justif_html}</td>
          <td style="padding:8px 10px;font-size:.82rem;text-align:right;color:#ef4444;font-weight:700">−{_fmt_dh(m.get('montant',0))} DH</td>
          <td style="padding:8px 10px;font-size:.82rem;text-align:right;color:{("#10b981" if running_after>=0 else "#ef4444")};font-weight:700">{_fmt_dh(running_after)} DH</td>
        </tr>'''
        running = running_after

    if not mouvements:
        rows = '<tr><td colspan="4" style="padding:12px;text-align:center;color:#64748b;font-size:.78rem">لا توجد استهلاكات — Aucune imputation</td></tr>'

    return f'''<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden;border-left:3px solid #f59e0b">
  <div style="padding:14px 18px;border-bottom:1px solid #2a3655;display:flex;justify-content:space-between;align-items:center">
    <h3 style="font-size:.9rem;font-weight:700;margin:0">💰 صندوق الأعباء / Cagnotte Charges Variables</h3>
  </div>
  <div style="padding:14px 18px">
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
      <div style="flex:1;min-width:130px;background:#1a2236;border-radius:8px;padding:12px;border-left:3px solid #3b82f6">
        <div style="font-size:.65rem;text-transform:uppercase;letter-spacing:1px;color:#64748b;margin-bottom:4px">رصيد البداية / Dépôt initial</div>
        <div style="font-size:1.2rem;font-weight:800;color:#3b82f6">{_fmt_dh(solde_initial)} DH</div>
      </div>
      <div style="flex:1;min-width:130px;background:#1a2236;border-radius:8px;padding:12px;border-left:3px solid #ef4444">
        <div style="font-size:.65rem;text-transform:uppercase;letter-spacing:1px;color:#64748b;margin-bottom:4px">مجموع الاستهلاك / Total consommé</div>
        <div style="font-size:1.2rem;font-weight:800;color:#ef4444">{_fmt_dh(total_dep)} DH</div>
      </div>
      <div style="flex:1;min-width:130px;background:#1a2236;border-radius:8px;padding:12px;border-left:3px solid {couleur}">
        <div style="font-size:.65rem;text-transform:uppercase;letter-spacing:1px;color:#64748b;margin-bottom:4px">الرصيد المتبقي / Solde restant</div>
        <div style="font-size:1.2rem;font-weight:800;color:{couleur}">{_fmt_dh(solde_restant)} DH</div>
        <div style="margin-top:6px;background:#0f172a;border-radius:4px;height:6px;overflow:hidden"><div style="height:100%;width:{pct}%;background:{couleur};border-radius:4px"></div></div>
      </div>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:.82rem">
      <thead><tr style="border-bottom:2px solid #2a3655">
        <th style="padding:8px 10px;text-align:left;font-size:.65rem;color:#64748b;text-transform:uppercase">التاريخ / Date</th>
        <th style="padding:8px 10px;text-align:left;font-size:.65rem;color:#64748b;text-transform:uppercase">البيان / Libellé</th>
        <th style="padding:8px 10px;text-align:right;font-size:.65rem;color:#64748b;text-transform:uppercase">المبلغ / Montant</th>
        <th style="padding:8px 10px;text-align:right;font-size:.65rem;color:#64748b;text-transform:uppercase">الرصيد / Solde</th>
      </tr></thead>
      <tbody>
        <tr style="border-bottom:1px solid #2a3655;background:#1a2236">
          <td style="padding:8px 10px;font-size:.78rem;color:#94a3b8">—</td>
          <td style="padding:8px 10px;font-size:.82rem;font-weight:700;color:#3b82f6">رصيد البداية / Cagnotte initiale</td>
          <td style="padding:8px 10px;text-align:right;color:#3b82f6;font-weight:700">+{int(solde_initial):,} DH</td>
          <td style="padding:8px 10px;text-align:right;color:#3b82f6;font-weight:700">{int(solde_initial):,} DH</td>
        </tr>
        {rows}
      </tbody>
    </table>
  </div>
</div>'''

def load_from_backup():
    backup_dir = Path(os.path.expanduser('~/Downloads/patrimoine-app/backUp'))
    if not backup_dir.exists(): return None
    files = sorted(backup_dir.glob('patrimoine_*.json'))
    if not files: return None
    try:
        data = json.loads(files[-1].read_text())
        actifs = [l for l in data.get('_location',{}).get('locataires',[]) if l.get('actif')]
        if not actifs: return None
        pays = data.get('_location',{}).get('paiements')
        result = []
        for l in actifs:
            nom_raw, prenom_raw = l.get('nom',''), l.get('prenom','')
            if not prenom_raw and ' ' in nom_raw:
                parts = nom_raw.split(' ', 1)
                nom_raw, prenom_raw = parts[0], parts[1]
            # Fallback uniquement pour les champs absents du backup (l'app a toujours priorité)
            fb = next((f for f in LOCATAIRES_FALLBACK if f['nom'].upper()==nom_raw.split()[0].upper()), {})
            result.append({
                'nom': nom_raw, 'prenom': prenom_raw,
                'loyer': l.get('loyer') or fb.get('loyer', 400),
                'charges': l['charges'] if 'charges' in l else fb.get('charges', 0),
                'adresse': l.get('adresse') or fb.get('adresse',''),
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
                'cagnotte': l.get('cagnotte'),
                'paiements': [p for p in pays if isinstance(p, dict) and p.get('locataire_id')==l.get('id')] if isinstance(pays, list) and l.get('id') else None,
            })
        print(f"  Chargé {len(result)} locataires depuis backup")
        return result
    except Exception as e:
        print(f"  Erreur lecture backup: {e}")
        return None

# Styles communs
CSS_BASE = '''body{font-family:system-ui;background:#0b0f19;color:#e2e8f0;margin:0;min-height:100vh}
.po{position:fixed;inset:0;z-index:9999;background:#0b0f19;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:24px}
.pi{width:260px;max-width:80vw;height:48px;border-radius:10px;background:#1a2236;border:1px solid #2a3655;color:#e2e8f0;font-size:1.1rem;text-align:center;letter-spacing:.08em;outline:none}.pi:focus{border-color:#3b82f6}
.pb{width:260px;max-width:80vw;height:46px;border-radius:10px;background:#3b82f6;border:none;color:#fff;font-size:1rem;font-weight:700;cursor:pointer}.pb:hover{background:#2563eb}.pb:disabled{opacity:.5;cursor:wait}'''

def pin_html(ar=False):
    sub = '<p style="color:#64748b;font-size:.85rem;margin:2px 0" dir="rtl">\u0623\u062f\u062e\u0644 \u0631\u0645\u0632 \u0627\u0644\u062f\u062e\u0648\u0644</p>' if ar else ''
    return '''<div id="pl" class="po"><div style="text-align:center"><div style="font-size:3rem">\U0001f3e0</div><h1 style="font-size:1.4rem;color:#fbbf24">Portail Locataire</h1><p style="color:#64748b;font-size:.85rem;margin:2px 0">Entrez votre code d'acc\u00e8s</p>''' + sub + '''</div>
<form id="pf" onsubmit="pk();return false" style="display:flex;flex-direction:column;align-items:center;gap:12px">
<input id="pi" class="pi" type="text" name="code" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" aria-label="Code d'acc\u00e8s" placeholder="Code d'acc\u00e8s" autofocus>
<button id="pbtn" class="pb" type="submit">Ouvrir</button></form>
<div id="pe" role="status" style="color:#ef4444;font-size:.82rem;min-height:20px"></div></div>'''

def pin_js(enc):
    return f'''var _busy=false,_E={json.dumps(enc)};
function _b(s){{return Uint8Array.from(atob(s),function(c){{return c.charCodeAt(0)}})}}
async function _dec(pin){{var km=await crypto.subtle.importKey('raw',new TextEncoder().encode(pin),'PBKDF2',false,['deriveKey']);var k=await crypto.subtle.deriveKey({{name:'PBKDF2',salt:_b(_E.s),iterations:{PBKDF2_ITER},hash:'SHA-256'}},km,{{name:'AES-GCM',length:256}},false,['decrypt']);var pt=await crypto.subtle.decrypt({{name:'AES-GCM',iv:_b(_E.i)}},k,_b(_E.c));return JSON.parse(new TextDecoder().decode(pt))}}
function _open(d){{var pc=document.getElementById('pc');pc.innerHTML=d.h;var sc=document.createElement('script');sc.textContent=d.j;document.body.appendChild(sc);document.getElementById('pl').style.display='none';pc.style.display='block'}}
function pk(){{if(_busy)return;var pi=document.getElementById('pi'),pe=document.getElementById('pe'),bt=document.getElementById('pbtn');var code=pi.value.trim();if(!code){{pi.focus();return}}_busy=true;bt.disabled=true;pe.style.color='#64748b';pe.textContent='V\u00e9rification\u2026';_dec(code).then(function(d){{_busy=false;bt.disabled=false;pe.textContent='';_open(d)}},function(){{_busy=false;bt.disabled=false;pe.style.color='#ef4444';pe.textContent='Code incorrect (attention aux majuscules/minuscules)';pi.select()}})}}'''

def resiliation_banner(loc):
    """Bandeau rouge « contrat résilié » pour un locataire inactif (quittances toujours disponibles)."""
    if not est_resilie(loc):
        return ''
    sortie = fmt_date((loc.get('date_sortie') or loc.get('date_fin') or '')[:10])
    return ('<div style="background:#7f1d1d;border-bottom:3px solid #ef4444;color:#fff;text-align:center;padding:14px 16px">'
        f'<div style="font-size:1.25rem;font-weight:900;letter-spacing:.06em">\u26d4 INACTIF \u2014 CONTRAT R\u00c9SILI\u00c9 le {sortie}</div>'
        f'<div style="font-size:1.1rem;font-weight:800;margin-top:4px" dir="rtl">\u0639\u0642\u062f \u0627\u0644\u0643\u0631\u0627\u0621 \u0645\u0646\u062a\u0647\u064a \u2014 \u062a\u0645 \u0641\u0633\u062e \u0627\u0644\u0639\u0642\u062f \u0628\u062a\u0627\u0631\u064a\u062e {sortie}</div>'
        '<div style="font-size:.78rem;opacity:.85;margin-top:4px">Les quittances restent t\u00e9l\u00e9chargeables ci-dessous \u2014 \u064a\u0645\u0643\u0646\u0643\u0645 \u062a\u062d\u0645\u064a\u0644 \u0648\u0635\u0648\u0644\u0627\u062a \u0627\u0644\u0643\u0631\u0627\u0621 \u0623\u0633\u0641\u0644\u0647</div>'
        '</div>')

def header_html(nom, prenom, bien, loyer, devise):
    ds = esc(devise)
    initiale, nom, prenom, bien, loyer = esc((nom or '?')[:1]), esc(nom), esc(prenom), esc(bien), esc(loyer)
    return f'''<div style="background:#111827;border-bottom:1px solid #2a3655;padding:16px 24px;display:flex;align-items:center;gap:12px">
<div style="width:42px;height:42px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#8b5cf6);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1.1rem">{initiale}</div>
<div><div style="font-weight:800;font-size:1rem">{nom} {prenom}</div><div style="font-size:.72rem;color:#64748b">Locataire - {bien}</div></div>
<div style="margin-left:auto;text-align:right"><div style="font-size:.68rem;color:#64748b">Loyer mensuel</div><div style="font-size:1.2rem;font-weight:800;color:#fbbf24">{loyer} {ds}</div></div></div>'''

def kpis_html(bien, dd_fmt, df_fmt, charges, devise):
    ds = esc(devise)
    bien, dd_fmt, df_fmt, charges = esc(bien), esc(dd_fmt), esc(df_fmt), esc(charges)
    return f'''<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:24px">
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Bien</div><div style="font-size:1rem;font-weight:700;margin-top:4px">{bien}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Debut contrat</div><div style="font-size:1rem;font-weight:700;margin-top:4px;color:#10b981">{dd_fmt}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Fin contrat</div><div style="font-size:1rem;font-weight:700;margin-top:4px;color:#f59e0b">{df_fmt}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Charges</div><div style="font-size:1rem;font-weight:700;margin-top:4px">{charges} {ds}/mois</div></div></div>'''

# ═══════════════════════════════════════════════
# BAIL HTML COMPLET (Chambre en colocation)
# ═══════════════════════════════════════════════

def _sig_image(v):
    """Signature fournie sous forme d'image (data:image/… base64) — sinon None."""
    return v if isinstance(v, str) and re.match(r'data:image/(png|jpe?g|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=\s]+$', v) else None

def signatures_bail(loc):
    """(case bailleur, case locataire, date de signature locataire) du bail généré.
    Aucune signature n'est simulée : une case reste vide tant qu'aucune signature réelle n'est fournie."""
    vide = '<span class="sig-empty">Non signé</span>'
    sb = _sig_image(loc.get('signature_bailleur'))
    sig_bailleur = f'<img src="{esc(sb)}" alt="Signature du bailleur">' if sb else vide
    sl = _sig_image(loc.get('signature'))
    signe_le = str(loc.get('signe_le') or loc.get('date_signature') or '')[:10]
    signe_le = fmt_date(signe_le) if signe_le else ''
    if sl:
        sig_loc = f'<img src="{esc(sl)}" alt="Signature du locataire">'
    elif signe_le:
        sig_loc = f'<span style="font-size:9pt;color:#1a1a6e">Signé électroniquement</span>'
    else:
        sig_loc = vide
    return sig_bailleur, sig_loc, signe_le

def gen_bail_html(loc):
    """Génère le bail de location meublée – Chambre en colocation en HTML complet."""
    nom = loc.get('nom', '')
    prenom = loc.get('prenom', '')
    loyer = loc.get('loyer', 0)
    charges = loc.get('charges', 0)
    total = loyer + charges
    depot = loc.get('depot_garantie', loc.get('depot', loyer))
    adresse = loc.get('adresse', '3 Allée du Pourquoi Pas, 91000 Évry')
    date_debut_raw = loc.get('date_entree', loc.get('date_debut', ''))
    date_fin_raw = loc.get('date_fin', '')
    date_naissance = loc.get('date_naissance', '')
    lieu_naissance = loc.get('lieu_naissance', '')
    sig_bailleur, sig_loc, signe_le = signatures_bail(loc)

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

    nom, prenom, adresse = esc(nom), esc(prenom), esc(adresse)
    loyer, charges, total, depot = esc(loyer), esc(charges), esc(total), esc(depot)
    date_naissance, lieu_naissance = esc(date_naissance), esc(lieu_naissance)
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
  .sig-area img{{max-height:72px;max-width:100%;object-fit:contain}}
  .sig-empty{{font-size:8.5pt;color:#999;font-style:italic}}
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
    <div class="sig-area">{sig_bailleur}</div>
    <div class="sig-footer">EL OUARDI Yassine{('<br>Fait à Évry, le ' + start.strftime('%d/%m/%Y')) if sig_bailleur.startswith('<img') else ''}</div>
  </div>
  <div class="sig-box">
    <div class="sig-label">Le locataire (lu et approuvé)</div>
    <div class="sig-area">{sig_loc}</div>
    <div class="sig-footer">{nom} {prenom}<br>{('Signé le ' + esc(signe_le)) if signe_le else 'Non signé'}</div>
  </div>
</div>
<div class="legal">Document établi conformément à la loi n° 89-462 du 6 juillet 1989 (article 21) — Conservation recommandée : 3 ans minimum après départ du logement.</div>
</body>
</html>"""


# ═══════════════════════════════════════════════
# PORTAIL FRANCE (EUR)
# ═══════════════════════════════════════════════

def gen_portal_france(loc, known_pins):
    nom, prenom = loc['nom'], loc['prenom']
    s = slug(nom, prenom)
    pin = get_pin(loc, known_pins); loc['pin'] = pin
    bien, loyer, charges = loc.get('bien','EVRY'), loc['loyer'], loc['charges']
    depot = loc.get('depot_garantie') or loyer
    total = loyer + charges
    dd_fmt, df_fmt = fmt_date(loc['date_debut']), fmt_date(loc['date_fin'])
    bail_url = copy_bail(loc, s)
    old_pdfs = old_bails(loc, s)
    q, q_data = quittances_html(loc, 'EUR')
    sig_active = bool(loc.get('signature_active', True))

    # Documents section
    docs = f'<div style="display:flex;flex-direction:column;gap:8px">'
    docs += f'<div style="padding:10px;background:#1a2236;border-radius:8px;border-left:3px solid #10b981"><div style="display:flex;align-items:center;gap:10px"><span style="font-size:1.2rem">\U0001f4cb</span><div style="flex:1"><div style="font-weight:600;font-size:.82rem">Contrat de Bail actuel</div><div style="font-size:.7rem;color:#64748b">Du {esc(dd_fmt)} au {esc(df_fmt)} — {esc(total)} €/mois</div></div><button onclick="_contratPDF()" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;cursor:pointer;font-weight:600">\U0001f4e5 Télécharger PDF</button><span id="sign-badge" style="padding:3px 8px;border-radius:4px;background:rgba(16,185,129,.13);color:#10b981;font-size:.68rem;font-weight:700">En cours</span></div>'
    # Signer / Commenter
    docs += f'<div id="sign-actions" style="margin-top:10px;padding-top:10px;border-top:1px solid #2a3655;display:flex;gap:8px;flex-wrap:wrap;align-items:center"><button onclick="_signerContrat()" id="btn-signer" style="background:#10b981;color:#fff;border:none;border-radius:6px;padding:8px 18px;font-size:.8rem;cursor:pointer;font-weight:700">✔ Signer le contrat</button><button onclick="_ouvrirCommentaire()" style="background:#f59e0b;color:#fff;border:none;border-radius:6px;padding:8px 18px;font-size:.8rem;cursor:pointer;font-weight:600">\U0001f4ac Demander une modification</button></div>'
    docs += '<div id="sign-msg" role="status" style="display:none;margin-top:8px;padding:8px 12px;border-radius:8px;font-size:.8rem"></div>'
    docs += f'<div id="comment-zone" style="display:none;margin-top:10px"><textarea id="comment-text" rows="3" placeholder="Decrivez les modifications souhaitees..." style="width:100%;background:#0b0f19;color:#e2e8f0;border:1px solid #2a3655;border-radius:8px;padding:10px;font-size:.82rem;resize:vertical"></textarea><div style="display:flex;gap:8px;margin-top:8px"><button id="btn-comment" onclick="_envoyerCommentaire()" style="background:#f59e0b;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.78rem;cursor:pointer;font-weight:600">\U0001f4e8 Envoyer</button><button onclick="document.getElementById(\'comment-zone\').style.display=\'none\'" style="background:#334155;color:#e2e8f0;border:none;border-radius:6px;padding:6px 14px;font-size:.78rem;cursor:pointer">Annuler</button></div></div>'
    docs += '<div id="comment-msg" role="status" style="display:none;margin-top:8px;padding:8px 12px;border-radius:8px;font-size:.8rem"></div>'
    docs += '</div>'
    # Anciens contrats — bouton PDF seulement si le fichier de cet ancien bail existe
    hist = loc.get('contrats_historique', [])
    for i in reversed(range(len(hist))):
        c = hist[i]
        c_deb, c_fin = fmt_date(c.get('date_debut','?')), fmt_date(c.get('date_fin','?'))
        c_total = c.get('loyer',0)+c.get('charges',0)
        btn = f'<a href="#" onclick="_openOldPdf({i});return false" style="background:#64748b;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;cursor:pointer;text-decoration:none;font-weight:600">\U0001f4e5 PDF</a>' if old_pdfs[i] else ''
        docs += f'<div style="display:flex;align-items:center;gap:10px;padding:10px;background:#1a2236;border-radius:8px;border-left:3px solid #64748b"><span style="font-size:1.2rem">\U0001f4c4</span><div style="flex:1"><div style="font-weight:600;font-size:.82rem;color:#94a3b8">Ancien contrat #{i+1}</div><div style="font-size:.7rem;color:#64748b">Du {esc(c_deb)} au {esc(c_fin)} — {esc(c_total)} €/mois</div></div>{btn}</div>'
    docs += '</div>'

    # Bail HTML complet encodé base64 (évite les problèmes d'échappement)
    bail_html_b64 = base64.b64encode(gen_bail_html(loc).encode('utf-8')).decode('ascii')

    # Toutes les valeurs passent par un objet JSON (_D) : aucun nom/montant n'est collé tel quel dans le code JS
    data = {'nom': nom, 'prenom': prenom, 'dd': dd_fmt, 'df': df_fmt, 'loyer': loyer, 'charges': charges, 'total': total, 'q': q_data}

    # JS fonctions France (signature, contrat PDF, quittance PDF)
    js_france = f'''
var _D={js_val(data)};
var _SIG_ACTIVE={js_val(sig_active)};
var _SIG_KEY={js_val('contrat_signe_' + nom)};
var _BAIL_PDF={js_val(bail_url)};
var _OLD_PDFS={js_val(old_pdfs)};
{PDF_JS}
var _BAIL_B64={js_val(bail_html_b64)};
var _EJS_KEY={js_val(EJS_KEY)};var _EJS_SVC={js_val(EJS_SVC)};var _EJS_TPL={js_val(EJS_TPL)};
try{{emailjs.init({{publicKey:_EJS_KEY}})}}catch(e){{}}
function _sendEmail(s,b){{try{{if(typeof emailjs==='undefined')return Promise.reject(new Error('service indisponible'));return Promise.resolve(emailjs.send(_EJS_SVC,_EJS_TPL,{{subject:s,message:b,to_email:'ing.elouardi@gmail.com'}}))}}catch(e){{return Promise.reject(e)}}}}
function _msg(id,ok,txt){{var m=document.getElementById(id);if(!m)return;m.style.display='block';m.style.background=ok?'rgba(16,185,129,.08)':'rgba(239,68,68,.1)';m.style.border='1px solid '+(ok?'rgba(16,185,129,.3)':'rgba(239,68,68,.35)');m.style.color=ok?'#10b981':'#ef4444';m.textContent=txt}}
function _busyBtn(b,on,txt){{if(!b)return;if(on){{b._t=b.textContent;b.textContent=txt;b.disabled=true;b.style.opacity='.6';b.style.cursor='wait'}}else{{if(b._t)b.textContent=b._t;b.disabled=false;b.style.opacity='';b.style.cursor='pointer'}}}}
function _showSignedState(ds,ts){{var b=document.getElementById('sign-badge');b.textContent='\\u2714 Signé '+ds;b.style.background='rgba(16,185,129,.2)';b.style.color='#10b981';var a=document.getElementById('sign-actions');a.innerHTML='<div style="padding:8px 12px;background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.2);border-radius:8px;font-size:.82rem;color:#10b981">\\u2714 Contrat signé le '+_esc(ds)+' à '+_esc(ts)+' par '+_esc(_D.nom+' '+_D.prenom)+'</div>';}}
function _checkSignedOnLoad(){{var sg=null;try{{sg=localStorage.getItem(_SIG_KEY)}}catch(e){{}}if(sg){{var sd=new Date(sg);_showSignedState(sd.toLocaleDateString('fr-FR'),sd.toLocaleTimeString('fr-FR',{{hour:'2-digit',minute:'2-digit'}}))}}else if(!_SIG_ACTIVE){{var btn=document.getElementById('btn-signer');if(btn){{btn.disabled=true;btn.style.opacity='.4'}}}}}}
function _signerContrat(){{var btn=document.getElementById('btn-signer');if(!btn||btn.disabled)return;try{{if(localStorage.getItem(_SIG_KEY))return}}catch(e){{}}if(!_SIG_ACTIVE){{alert('Signature non activée');return}}if(!confirm('Signer le contrat ?\\n'+_D.nom+' '+_D.prenom+'\\n'+_D.dd+' au '+_D.df+'\\n'+_D.total+' €/mois'))return;var now=new Date();var ds=now.toLocaleDateString('fr-FR');var ts=now.toLocaleTimeString('fr-FR',{{hour:'2-digit',minute:'2-digit'}});_busyBtn(btn,true,'Envoi en cours…');_sendEmail('Contrat signé - '+_D.nom,_D.nom+' '+_D.prenom+' a signé le '+ds+' à '+ts).then(function(){{try{{localStorage.setItem(_SIG_KEY,now.toISOString())}}catch(e){{}}_showSignedState(ds,ts);_msg('sign-msg',true,'\\u2714 Signature envoyée au propriétaire.')}},function(){{_busyBtn(btn,false);_msg('sign-msg',false,'\\u26a0 La signature n\\u2019a pas pu être envoyée au propriétaire. Vérifiez votre connexion et réessayez, ou contactez-le directement.')}})}}
function _ouvrirCommentaire(){{document.getElementById('comment-zone').style.display='block';document.getElementById('comment-msg').style.display='none';document.getElementById('comment-text').focus()}}
function _envoyerCommentaire(){{var ta=document.getElementById('comment-text'),btn=document.getElementById('btn-comment');var t=ta.value.trim();if(!t){{_msg('comment-msg',false,'Veuillez décrire la modification souhaitée.');return}}if(btn.disabled)return;_busyBtn(btn,true,'Envoi…');_sendEmail('Commentaire contrat - '+_D.nom,_D.nom+' '+_D.prenom+': '+t).then(function(){{_busyBtn(btn,false);ta.value='';document.getElementById('comment-zone').style.display='none';_msg('comment-msg',true,'\\u2714 Demande envoyée au propriétaire.')}},function(){{_busyBtn(btn,false);_msg('comment-msg',false,'\\u26a0 La demande n\\u2019a pas pu être envoyée. Vérifiez votre connexion et réessayez.')}})}}
function _contratPDF(){{
  if(_BAIL_PDF){{_openPdf();return;}}
  var bytes=Uint8Array.from(atob(_BAIL_B64),function(c){{return c.charCodeAt(0);}});
  var html=new TextDecoder('utf-8').decode(bytes);
  var w=window.open('','_blank');
  if(w){{w.document.write(html);w.document.close();}}
}}
function _qpdf(i){{var e=_D.q[i];if(!e)return;try{{var d=new jspdf.jsPDF();var y=20;d.setFontSize(18);d.setFont('helvetica','bold');d.text('QUITTANCE DE LOYER',105,y,{{align:'center'}});y+=12;d.setFont('helvetica','normal');d.setFontSize(10);d.text('Bailleur: EL OUARDI Yassine',14,y);y+=5;d.text('Locataire: '+_D.nom+' '+_D.prenom,14,y);y+=5;d.text('Periode: du '+e.deb+' au '+e.fin,14,y);y+=5;d.text('Paiement recu le '+e.date_paiement,14,y);y+=10;d.setDrawColor(0);d.setLineWidth(1);d.rect(35,y,140,20);d.setFontSize(22);d.setFont('helvetica','bold');d.text(e.total+' EUR',105,y+14,{{align:'center'}});y+=28;d.setFontSize(9);d.setFont('helvetica','normal');d.text('Loyer: '+e.loyer+' EUR | Charges: '+e.charges+' EUR',14,y);y+=10;d.text('Fait a Evry, le '+e.date_paiement,14,y);d.save('Quittance_'+e.mois.replace(/ /g,'_')+'_'+_D.nom.replace(/[^A-Za-z0-9_-]+/g,'_')+'.pdf')}}catch(err){{alert(err.message)}}}}
_checkSignedOnLoad();'''

    html = f'''<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Portail Locataire</title>
<script src="https://cdn.tailwindcss.com"></script><script src="https://unpkg.com/jspdf@2.5.2/dist/jspdf.umd.min.js"></script><script src="https://cdn.jsdelivr.net/npm/@emailjs/browser@4/dist/email.min.js"></script>
<style>{CSS_BASE}</style></head>'''
    content = f'''{resiliation_banner(loc)}{header_html(nom, prenom, bien, loyer, 'EUR')}
<div style="max-width:900px;margin:24px auto;padding:0 16px">
{kpis_html(bien, dd_fmt, df_fmt, charges, 'EUR')}
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f4c4 Documents</h3></div><div style="padding:14px 18px">{docs}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f9fe Quittances de Loyer</h3></div><div style="padding:14px 18px"><table style="width:100%;border-collapse:collapse;font-size:.82rem"><thead><tr style="border-bottom:2px solid #2a3655"><th style="text-align:left;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Periode</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b">Loyer</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b">Charges</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b">Total</th><th style="text-align:center;padding:8px;font-size:.68rem;color:#64748b">PDF</th></tr></thead><tbody>{q}</tbody></table></div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden;border-left:3px solid #8b5cf6"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f4ac Messages du Proprietaire</h3></div><div style="padding:14px 18px">{messages_html(loc)}</div></div>
<div style="text-align:center;padding:20px;font-size:.7rem;color:#64748b">EL OUARDI PATRIMOINE - Portail Securise</div></div>'''
    html = locked_page(html, pin, content, js_france)

    (PUBLIC/f'{s}.html').write_text(html, encoding='utf-8')
    return {'nom':nom,'prenom':prenom,'pin':pin,'slug':s,
        'portal_url':f'https://ingelouardi-cloud.github.io/patrimoine/public/{s}.html'}


# ═══════════════════════════════════════════════
# PORTAIL MAROC (MAD)
# ═══════════════════════════════════════════════

def gen_portal_maroc(loc, known_pins):
    nom, prenom = loc['nom'], loc['prenom']
    s = slug(nom, prenom)
    pin = get_pin(loc, known_pins); loc['pin'] = pin
    bien, loyer, charges = loc.get('bien','Maroc'), loc['loyer'], loc['charges']
    adresse_bien = loc.get('adresse', bien)
    total = loyer + charges
    cin_loc = loc.get('cin', '..................')
    tel_loc = loc.get('tel', '')
    depot_loc = loc.get('depot_garantie', loc.get('depot', loyer))
    dd_fmt, df_fmt = fmt_date(loc['date_debut']), fmt_date(loc['date_fin'])
    bail_url = copy_bail(loc, s)
    old_pdfs = old_bails(loc, s)
    q, q_data = quittances_html(loc, 'MAD')
    cag_block = cagnotte_html(loc)

    # Documents section — PDF original + mention légalisation
    docs = f'<div style="display:flex;flex-direction:column;gap:8px">'
    docs += f'<div style="padding:10px;background:#1a2236;border-radius:8px;border-left:3px solid #10b981"><div style="display:flex;align-items:center;gap:10px"><span style="font-size:1.2rem">\U0001f4cb</span><div style="flex:1"><div style="font-weight:600;font-size:.82rem">عقد الكراء / Contrat de Bail</div><div style="font-size:.7rem;color:#64748b">Du {esc(dd_fmt)} au {esc(df_fmt)} \u2014 {esc(total)} MAD/mois</div></div>'
    if bail_url:
        docs += f'<a href="#" onclick="_openPdf();return false" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;cursor:pointer;text-decoration:none;font-weight:600">\U0001f4e5 Télécharger le contrat signé</a>'
    badge = '<span style="padding:3px 8px;border-radius:4px;background:rgba(239,68,68,.13);color:#ef4444;font-size:.68rem;font-weight:700">Résilié</span>' if est_resilie(loc) else '<span style="padding:3px 8px;border-radius:4px;background:rgba(16,185,129,.13);color:#10b981;font-size:.68rem;font-weight:700">En cours</span>'
    docs += f'{badge}</div>'
    docs += f'<div style="margin-top:8px;font-size:.75rem;color:#64748b">\U0001f4dd التوقيع أمام التصديق / Signature devant la l\u00e9galisation marocaine</div>'
    docs += '</div>'
    # Anciens contrats
    hist = loc.get('contrats_historique', [])
    for i in reversed(range(len(hist))):
        c = hist[i]
        c_deb, c_fin = fmt_date(c.get('date_debut','?')), fmt_date(c.get('date_fin','?'))
        c_total = c.get('loyer',0)+c.get('charges',0)
        btn = f'<a href="#" onclick="_openOldPdf({i});return false" style="background:#64748b;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;cursor:pointer;text-decoration:none;font-weight:600">\U0001f4e5 PDF</a>' if old_pdfs[i] else ''
        docs += f'<div style="display:flex;align-items:center;gap:10px;padding:10px;background:#1a2236;border-radius:8px;border-left:3px solid #64748b"><span style="font-size:1.2rem">\U0001f4c4</span><div style="flex:1"><div style="font-weight:600;font-size:.82rem;color:#94a3b8">عقد قديم #{i+1}</div><div style="font-size:.7rem;color:#64748b">{esc(c_deb)} \u2014 {esc(c_fin)} \u2014 {esc(c_total)} MAD</div></div>{btn}</div>'
    docs += '</div>'

    # JS Maroc — quittance bilingue FR+AR (HTML dans nouvelle fenêtre, jsPDF ne supporte pas l'arabe)
    data = {'nom': nom, 'prenom': prenom, 'bien': bien, 'adresse': adresse_bien, 'q': q_data}
    js_maroc = f'''
var _D={js_val(data)};
var _BAIL_PDF={js_val(bail_url)};
var _OLD_PDFS={js_val(old_pdfs)};
{PDF_JS}
function _qpdf(i){{
  var e=_D.q[i];if(!e)return;
  var mois=_esc(e.mois+' / '+e.mois_ar),deb=_esc(e.deb),fin=_esc(e.fin),today=_esc(e.date_paiement);
  var html='<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>وصل الكراء</title><style>'
  +'body{{font-family:Arial,sans-serif;margin:0;padding:30px;background:#fff;color:#111;direction:rtl}}'
  +'.page{{max-width:700px;margin:0 auto;border:2px solid #1a5276;border-radius:10px;padding:30px;position:relative}}'
  +'.header{{text-align:center;border-bottom:3px double #1a5276;padding-bottom:18px;margin-bottom:22px}}'
  +'.header h1{{font-size:1.6rem;color:#1a5276;margin:0 0 4px}}'
  +'.header h2{{font-size:1.1rem;color:#555;font-weight:400;margin:0}}'
  +'.logo{{font-size:.78rem;color:#888;margin-top:6px;letter-spacing:1px}}'
  +'.row{{display:flex;justify-content:space-between;margin-bottom:10px;font-size:.92rem}}'
  +'.label{{color:#555;font-weight:600;min-width:140px}}'
  +'.value{{font-weight:700;text-align:left}}'
  +'.montant-box{{border:3px solid #1a5276;border-radius:8px;text-align:center;padding:18px 0;margin:22px 0}}'
  +'.montant-box .mont{{font-size:2.4rem;font-weight:900;color:#1a5276;letter-spacing:2px}}'
  +'.montant-box .sub{{font-size:.82rem;color:#555;margin-top:4px}}'
  +'.detail{{background:#f0f4f8;border-radius:8px;padding:12px 18px;margin-bottom:18px;font-size:.88rem;display:flex;justify-content:space-around;text-align:center}}'
  +'.detail span{{display:block;font-size:1rem;font-weight:800;color:#1a5276}}'
  +'.sig{{display:flex;justify-content:space-between;margin-top:30px;gap:30px}}'
  +'.sig-box{{flex:1;text-align:center;border-top:1px solid #aaa;padding-top:10px;font-size:.82rem;color:#555}}'
  +'.sig-name{{font-family:\"Dancing Script\",\"Brush Script MT\",cursive;font-size:1.9rem;color:#1a5276;display:block;margin:8px 0 2px;font-weight:700}}'
  +'.legal{{font-size:.72rem;color:#888;text-align:center;margin-top:20px;border-top:1px solid #eee;padding-top:10px}}'
  +'.ar{{font-size:1.05em;direction:rtl}}.fr{{direction:ltr}}'
  +'@media print{{body{{padding:10px}}.page{{border:2px solid #000}}}}'
  +'</style></head><body><div class="page">'
  +'<div class="header">'
  +'<h1 class="ar">وصل الكراء</h1>'
  +'<h2 class="fr">REÇU DE LOYER / QUITTANCE</h2>'
  +'<div class="logo">EL OUARDI PATRIMOINE — Bailleur privé</div>'
  +'</div>'
  +'<div class="row"><span class="label ar">المؤجر / Bailleur</span><span class="value fr">EL OUARDI Yassine</span></div>'
  +'<div class="row"><span class="label ar">المكتري / Locataire</span><span class="value fr">'+_esc(_D.nom+' '+_D.prenom)+'</span></div>'
  +'<div class="row"><span class="label ar">العقار / Bien</span><span class="value fr">'+_esc(_D.bien)+'</span></div>'
  +'<div class="row"><span class="label ar">العنوان / Adresse</span><span class="value fr" style="font-size:.82rem">'+_esc(_D.adresse)+'</span></div>'
  +'<div class="row"><span class="label ar">الشهر / Mois</span><span class="value fr">'+mois+'</span></div>'
  +'<div class="row"><span class="label ar">الفترة / Période</span><span class="value fr">'+deb+' — '+fin+'</span></div>'
  +'<div class="montant-box">'
  +'<div class="mont">'+_esc(e.total)+' MAD</div>'
  +'<div class="sub ar">المبلغ المُؤدَّى / Montant acquitté</div>'
  +'</div>'
  +'<div class="detail">'
  +'<div><div class="ar" style="font-size:.78rem;color:#555">الكراء / Loyer</div><span>'+_esc(e.loyer)+' MAD</span></div>'
  +'<div style="border-left:1px solid #ccc;border-right:1px solid #ccc;padding:0 20px"><div class="ar" style="font-size:.78rem;color:#555">الأعباء / Charges</div><span>'+_esc(e.charges)+' MAD</span></div>'
  +'<div><div class="ar" style="font-size:.78rem;color:#555">المجموع / Total</div><span style="color:#1a5276">'+_esc(e.total)+' MAD</span></div>'
  +'</div>'
  +'<div class="row" style="margin-top:8px"><span class="label ar">تاريخ الأداء / Payé le</span><span class="value fr">'+today+'</span></div>'
  +'<div style="font-size:.85rem;margin:14px 0;color:#333;text-align:center" class="ar">'
  +'أُعطي هذا الوصل إقراراً بالأداء الكامل للمبلغ أعلاه — Ce reçu atteste du paiement intégral du montant ci-dessus.'
  +'</div>'
  +'<link href=\"https://fonts.googleapis.com/css2?family=Dancing+Script:wght@700&display=swap\" rel=\"stylesheet\">'
  +'<div class="sig">'
  +'<div class="sig-box"><div class="ar">توقيع المؤجر</div><div class="fr" style="font-size:.75rem">Signature du bailleur</div><span class="sig-name">Yassine EL OUARDI</span><div style="font-size:.72rem;color:#888">EL OUARDI Yassine — signé le '+today+'</div></div>'
  +'<div class="sig-box"><div class="ar">توقيع المكتري</div><div class="fr" style="font-size:.75rem">Signature du locataire</div><div style="margin-top:25px;font-style:italic;font-weight:700">'+_esc(_D.nom+' '+_D.prenom)+'</div></div>'
  +'</div>'
  +'<div class="legal">وفق القانون رقم 67-12 المتعلق بعقود الكراء السكني — Conformément à la Loi n° 67-12 relative aux baux d\\'habitation au Maroc</div>'
  +'</div>'
  +'<div style="text-align:center;margin-top:14px"><button onclick="window.print()" style="padding:10px 28px;background:#1a5276;color:#fff;border:none;border-radius:6px;font-size:.9rem;cursor:pointer;font-weight:700">🖨️ Imprimer / طباعة</button></div>'
  +'</body></html>';
  var w=window.open('','_blank');w.document.write(html);w.document.close();
}}'''

    html = f'''<!DOCTYPE html><html lang="ar"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>بوابة المكتري - Portail Locataire</title>
<script src="https://cdn.tailwindcss.com"></script><script src="https://unpkg.com/jspdf@2.5.2/dist/jspdf.umd.min.js"></script>
<style>{CSS_BASE}</style></head>'''
    content = f'''{resiliation_banner(loc)}{header_html(nom, prenom, bien, loyer, 'MAD')}
<div style="max-width:900px;margin:24px auto;padding:0 16px">
{kpis_html(bien, dd_fmt, df_fmt, charges, 'MAD')}
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f4c4 الوثائق / Documents</h3></div><div style="padding:14px 18px">{docs}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f9fe وصولات الكراء / Quittances</h3></div><div style="padding:14px 18px"><table style="width:100%;border-collapse:collapse;font-size:.82rem"><thead><tr style="border-bottom:2px solid #2a3655"><th style="text-align:left;padding:8px;font-size:.68rem;color:#64748b">Periode</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b">Loyer</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b">Charges</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b">Total</th><th style="text-align:center;padding:8px;font-size:.68rem;color:#64748b">PDF</th></tr></thead><tbody>{q}</tbody></table></div></div>
{cag_block}<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden;border-left:3px solid #8b5cf6"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f4ac رسائل المالك / Messages</h3></div><div style="padding:14px 18px">{messages_html(loc)}</div></div>
<div style="text-align:center;padding:20px;font-size:.7rem;color:#64748b">EL OUARDI PATRIMOINE - بوابة المكتري</div></div>'''
    html = locked_page(html, pin, content, js_maroc, ar=True)

    (PUBLIC/f'{s}.html').write_text(html, encoding='utf-8')
    return {'nom':nom,'prenom':prenom,'pin':pin,'slug':s,
        'portal_url':f'https://ingelouardi-cloud.github.io/patrimoine/public/{s}.html'}


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
                merged = {**base, **{k:v for k,v in a.items() if v or isinstance(v,list)}, 'loyer':a.get('loyer',400), 'charges':a['charges'] if 'charges' in a else 0, 'bail':a.get('bail','')}
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
                    if not match.get('cagnotte') and bl.get('cagnotte'): match['cagnotte'] = bl['cagnotte']
                    if match.get('paiements') is None and bl.get('paiements') is not None: match['paiements'] = bl['paiements']
                else:
                    locs.append(bl)
                    print(f"  + Ajouté depuis backup: {bl['nom']}")
        else:
            locs = backup_locs
    if not locs:
        locs = LOCATAIRES_FALLBACK

    known_pins = load_known_pins()

    manifest, generated = [], []
    for loc in locs:
        is_maroc = loc.get('devise') == 'MAD'
        if is_maroc:
            r = gen_portal_maroc(loc, known_pins)
        else:
            r = gen_portal_france(loc, known_pins)
        manifest.append(r)
        generated.append(PUBLIC/f"{r['slug']}.html")
        flag = '\U0001f1f2\U0001f1e6' if is_maroc else '\U0001f1eb\U0001f1f7'
        print(f"  {flag} {r['nom']} {r['prenom']} {'MAD' if is_maroc else 'EUR'}")

    PINS_FILE.write_text(json.dumps(known_pins, indent=2, ensure_ascii=False))
    os.chmod(PINS_FILE, 0o600)
    # Manifest public (repo) sans PIN ; copie privée locale avec PIN pour l'app
    public_manifest = [{k:v for k,v in m.items() if k!='pin'} for m in manifest]
    (DIR/'manifest.json').write_text(json.dumps(public_manifest, indent=2, ensure_ascii=False))
    if PRIVATE_MANIFEST.parent.exists():
        PRIVATE_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"  {len(manifest)} portails generes")
    return 0 if git_publish(generated) else 1

def _git(*args):
    """Lance git dans le repo ; affiche l'erreur (au lieu de la masquer) et renvoie le résultat."""
    r = subprocess.run(['git', *args], cwd=DIR, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  \u2717 git {args[0]} a \u00e9chou\u00e9 : {(r.stderr or r.stdout).strip()}")
    return r

def git_publish(paths):
    """Commit + push uniquement des portails générés (public/<slug>.html) — jamais de « git add -A »
    (pas de manifest, d'index listant les locataires ni de fichier local ajouté par erreur)."""
    rel = sorted({str(p.relative_to(DIR)) for p in paths})
    if not rel:
        print("  Aucun portail \u00e0 publier"); return True
    if _git('add', '--', *rel).returncode != 0: return False
    if subprocess.run(['git', 'diff', '--cached', '--quiet', '--', *rel], cwd=DIR).returncode == 0:
        print("  Portails inchang\u00e9s \u2014 rien \u00e0 committer")
    elif _git('commit', '-m', 'MAJ portails', '--', *rel).returncode != 0:
        return False
    if _git('push', 'origin', 'main').returncode != 0: return False
    print("  Portails publi\u00e9s (git push origin main)")
    return True

if __name__=='__main__': sys.exit(main())
