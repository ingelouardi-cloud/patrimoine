#!/usr/bin/env python3
"""Génère les portails locataires - noms fixes, jsPDF, vrais bails PDF."""
import json, os, sys, hashlib, random, shutil
from datetime import datetime
from pathlib import Path

DIR = Path(__file__).parent
PUBLIC = DIR / 'public'
CONTRATS = DIR / 'contrats'
GED = Path(os.path.expanduser('~/Downloads/patrimoine-app/ged_documents'))
PUBLIC.mkdir(exist_ok=True)
CONTRATS.mkdir(exist_ok=True)

MOIS = ['Janvier','Fevrier','Mars','Avril','Mai','Juin','Juillet','Aout','Septembre','Octobre','Novembre','Decembre']

LOCATAIRES_FALLBACK = [
    {'nom':'DRAA','prenom':'Abdelilah','loyer':400,'charges':50,
     'date_debut':'2025-09-30','date_fin':'2026-06-30','bien':'EVRY',
     'bail':'20260422_164010_Bail-DRAA-ABDELILAH.pdf'},
    {'nom':'MESBAH','prenom':'Abderahmane','loyer':400,'charges':50,
     'date_debut':'2026-04-01','date_fin':'2027-04-01','bien':'EVRY',
     'bail':'20260422_163919_MESBAHI-bail_colocation_chambre_v3 1.pdf'},
    {'nom':'EZZAHID','prenom':'Samir','loyer':400,'charges':50,
     'date_debut':'2026-02-01','date_fin':'2027-02-01','bien':'EVRY',
     'bail':'20260422_163919_SAMI-Contrat bail de location chambre Bras de Fer.pdf'},
]

# Bails PDF par nom (pour retrouver le fichier bail)
BAIL_FILES = {
    'DRAA': '20260422_164010_Bail-DRAA-ABDELILAH.pdf',
    'MESBAH': '20260422_163919_MESBAHI-bail_colocation_chambre_v3 1.pdf',
    'EZZAHID': '20260422_163919_SAMI-Contrat bail de location chambre Bras de Fer.pdf',
    'MECHMOUM': '20260608_231719_nouveau document 2026-06-08 17.35.18.pdf',
}

def load_from_backup():
    """Lit les données locataires depuis le dernier backup de l'app."""
    backup_dir = Path(os.path.expanduser('~/Downloads/patrimoine-app/backUp'))
    if not backup_dir.exists():
        return None
    files = sorted(backup_dir.glob('patrimoine_*.json'))
    if not files:
        return None
    try:
        data = json.loads(files[-1].read_text())
        locs = data.get('_location', {}).get('locataires', [])
        actifs = [l for l in locs if l.get('actif', False)]
        if not actifs:
            return None
        result = []
        for l in actifs:
            nom_raw = l.get('nom', '')
            prenom_raw = l.get('prenom', '')
            # Si le nom contient nom+prénom (ex: "MECHMOUM YASSINE"), séparer
            if not prenom_raw and ' ' in nom_raw:
                parts = nom_raw.split(' ', 1)
                nom_raw = parts[0]
                prenom_raw = parts[1]
            result.append({
                'nom': nom_raw,
                'prenom': prenom_raw,
                'loyer': l.get('loyer', 400),
                'charges': l.get('charges', 50),
                'date_debut': l.get('date_entree', l.get('date_debut', '')),
                'date_fin': l.get('date_fin', ''),
                'bien': l.get('bien', 'EVRY'),
                'devise': l.get('devise', 'EUR'),
                'bail': BAIL_FILES.get(nom_raw.split()[0].upper(), l.get('bail', '')),
                'contrats_historique': l.get('contrats_historique', []),
                'portal_messages': l.get('portal_messages', []),
                'depot_garantie': l.get('depot_garantie', l.get('loyer', 400)),
                'portal_pin': l.get('portal_pin', ''),
                'signature_active': l.get('signature_active', True),
                'contrat_signe': l.get('contrat_signe', ''),
            })
        print(f"  Chargé {len(result)} locataires depuis backup")
        return result
    except Exception as e:
        print(f"  Erreur lecture backup: {e}")
        return None

def fmt_date(d):
    try: return datetime.strptime(d,'%Y-%m-%d').strftime('%d/%m/%Y')
    except: return d

def quittances_html(loc):
    rows=''
    now=datetime.now()
    # Collecter toutes les périodes: anciens contrats + contrat actuel
    periods=[]
    for h in loc.get('contrats_historique',[]):
        try:
            h_start=datetime.strptime(h['date_debut'],'%Y-%m-%d').replace(day=1)
            h_end=datetime.strptime(h['date_fin'],'%Y-%m-%d')
            periods.append({'start':h_start,'end':h_end,'loyer':h.get('loyer',loc['loyer']),'charges':h.get('charges',loc['charges'])})
        except: pass
    # Contrat actuel
    try:
        c_start=datetime.strptime(loc['date_debut'],'%Y-%m-%d').replace(day=1)
        periods.append({'start':c_start,'end':now,'loyer':loc['loyer'],'charges':loc['charges']})
    except: pass
    # Générer les lignes mois par mois pour chaque période
    seen=set()
    for p in periods:
        cur=p['start']
        end=min(p['end'],now)
        loyer,charges=p['loyer'],p['charges']
        total=loyer+charges
        while cur<=end:
            key=f'{cur.year}-{cur.month:02d}'
            if key not in seen:
                seen.add(key)
                ml=MOIS[cur.month-1]+' '+str(cur.year)
                deb=f'01/{cur.month:02d}/{cur.year}'
                fin=f'{28 if cur.month==2 else 30}/{cur.month:02d}/{cur.year}'
                ds=loc.get('devise','EUR')
                rows+=f'''<tr style="border-bottom:1px solid #2a3655"><td style="padding:8px;font-weight:600">{ml}</td><td style="text-align:right;padding:8px">{loyer} {ds}</td><td style="text-align:right;padding:8px">{charges} {ds}</td><td style="text-align:right;padding:8px;font-weight:700;color:#fbbf24">{total} {ds}</td><td style="text-align:center;padding:8px"><button onclick="_qpdf('{ml}','{deb}','{fin}')" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:4px 10px;font-size:.72rem;cursor:pointer">PDF</button></td></tr>'''
            cur=cur.replace(year=cur.year+1,month=1) if cur.month==12 else cur.replace(month=cur.month+1)
    return rows

def docs_html(loc, bail_url, dd_fmt, df_fmt):
    """Génère la section Documents avec contrat actuel + historique."""
    isMAD = loc.get('devise') == 'MAD'
    ds = 'MAD' if isMAD else '\u20ac'
    total = loc['loyer'] + loc['charges']
    h = f'<div style="display:flex;flex-direction:column;gap:8px">'
    # Contrat actuel
    h += f'<div style="padding:10px;background:#1a2236;border-radius:8px;border-left:3px solid #10b981">'
    h += f'<div style="display:flex;align-items:center;gap:10px">'
    h += f'<span style="font-size:1.2rem">\U0001f4cb</span>'
    h += f'<div style="flex:1"><div style="font-weight:600;font-size:.82rem">Contrat de Bail actuel</div><div style="font-size:.7rem;color:#64748b">Du {dd_fmt} au {df_fmt} \u2014 {total} {ds}/mois</div></div>'
    if isMAD:
        # MAD: ouvrir le PDF original signé
        if bail_url != '#':
            h += f'<a href="{bail_url}" target="_blank" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;cursor:pointer;text-decoration:none;font-weight:600">\U0001f4e5 Ouvrir PDF original</a>'
        else:
            h += f'<span style="font-size:.75rem;color:#64748b;padding:6px 14px">PDF non disponible</span>'
    else:
        # EUR: générer via jsPDF
        h += f'<button onclick="_contratPDF()" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;cursor:pointer;font-weight:600">\U0001f4e5 T\u00e9l\u00e9charger PDF</button>'
    h += f'<span id="sign-badge" style="padding:3px 8px;border-radius:4px;background:rgba(16,185,129,.13);color:#10b981;font-size:.68rem;font-weight:700">En cours</span></div>'
    if not isMAD:
        # Boutons Signer / Commenter — uniquement pour France (Maroc = signature devant légalisation)
        h += f'<div id="sign-actions" style="margin-top:10px;padding-top:10px;border-top:1px solid #2a3655;display:flex;gap:8px;flex-wrap:wrap;align-items:center">'
        h += f'<button onclick="_signerContrat()" id="btn-signer" style="background:#10b981;color:#fff;border:none;border-radius:6px;padding:8px 18px;font-size:.8rem;cursor:pointer;font-weight:700">\u2714 Signer le contrat</button>'
        h += f'<button onclick="document.getElementById(\'comment-zone\').style.display=\'block\'" style="background:#f59e0b;color:#fff;border:none;border-radius:6px;padding:8px 18px;font-size:.8rem;cursor:pointer;font-weight:600">\U0001f4ac Demander une modification</button>'
        h += f'</div>'
        h += f'<div id="comment-zone" style="display:none;margin-top:10px">'
        h += f'<textarea id="comment-text" rows="3" placeholder="Decrivez les modifications souhaitees..." style="width:100%;background:#0b0f19;color:#e2e8f0;border:1px solid #2a3655;border-radius:8px;padding:10px;font-size:.82rem;resize:vertical"></textarea>'
        h += f'<div style="display:flex;gap:8px;margin-top:8px">'
        h += f'<button onclick="_envoyerCommentaire()" style="background:#f59e0b;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.78rem;cursor:pointer;font-weight:600">\U0001f4e8 Envoyer au proprietaire</button>'
        h += f'<button onclick="document.getElementById(\'comment-zone\').style.display=\'none\'" style="background:#334155;color:#e2e8f0;border:none;border-radius:6px;padding:6px 14px;font-size:.78rem;cursor:pointer">Annuler</button>'
        h += f'</div></div>'
    else:
        h += f'<div style="margin-top:8px;font-size:.75rem;color:#64748b">\U0001f4dd Signature du contrat devant la l\u00e9galisation marocaine</div>'
    h += f'</div>'
    # Anciens contrats — lien vers le bail PDF original
    hist = loc.get('contrats_historique', [])
    for i, c in enumerate(reversed(hist)):
        c_deb = fmt_date(c.get('date_debut', '?'))
        c_fin = fmt_date(c.get('date_fin', '?'))
        c_total = c.get('loyer', 0) + c.get('charges', 0)
        c_arch = c.get('date_archivage', '')
        h += f'<div style="display:flex;align-items:center;gap:10px;padding:10px;background:#1a2236;border-radius:8px;border-left:3px solid #64748b"><span style="font-size:1.2rem">\U0001f4c4</span><div style="flex:1"><div style="font-weight:600;font-size:.82rem;color:#94a3b8">Ancien contrat #{len(hist)-i}</div><div style="font-size:.7rem;color:#64748b">Du {c_deb} au {c_fin} \u2014 {c_total} \u20ac/mois</div></div><a href="{bail_url}" target="_blank" style="background:#64748b;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;cursor:pointer;text-decoration:none;font-weight:600">\U0001f4e5 Ouvrir PDF</a><span style="font-size:.68rem;color:#64748b;padding:4px 8px;background:#0b0f19;border-radius:4px">Archiv\u00e9 {c_arch}</span></div>'
    h += '</div>'
    return h

def messages_html(loc):
    """Génère la section Messages."""
    msgs = loc.get('portal_messages', [])
    if not msgs:
        return '<div style="color:#64748b;font-size:.82rem">Aucun message.</div>'
    h = ''
    for m in msgs:
        h += f'<div style="padding:10px;background:#1a2236;border-radius:8px;margin-bottom:8px;border-left:3px solid #8b5cf6"><div style="font-size:.82rem">{m.get("text","")}</div><div style="font-size:.68rem;color:#64748b;margin-top:4px">{m.get("date","")}</div></div>'
    return h

def gen_portal(loc):
    nom,prenom=loc['nom'],loc['prenom']
    slug=(nom+'-'+prenom).lower().replace(' ','-')
    # Use existing PIN: from app data > from previous manifest > generate new
    old_manifest=[]
    try: old_manifest=json.loads((DIR/'manifest.json').read_text())
    except: pass
    old_entry=next((m for m in old_manifest if m.get('nom','').lower()==nom.lower()),{})
    pin=loc.get('portal_pin','') or loc.get('pin','') or old_entry.get('pin','') or str(1000+random.randint(0,8999))
    loc['pin']=pin  # Store back so manifest has it
    pin_hash=hashlib.sha256(pin.encode()).hexdigest()
    bien=loc.get('bien','EVRY')
    devise=loc.get('devise','EUR')
    isMAD=devise=='MAD'
    dev_sym='MAD' if isMAD else 'EUR'
    loyer,charges=loc['loyer'],loc['charges']
    depot=loc.get('depot_garantie') or loc.get('depot') or loyer
    total=loyer+charges
    dd_fmt=fmt_date(loc['date_debut'])
    df_fmt=fmt_date(loc['date_fin'])
    bail_file=loc.get('bail','')
    bail_src=GED/bail_file if bail_file else None
    if bail_src and bail_src.is_file():
        shutil.copy2(bail_src,CONTRATS/f'{slug}-bail.pdf')
        bail_url=f'../contrats/{slug}-bail.pdf'
    else: bail_url='#'
    q=quittances_html(loc)
    html=f'''<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Portail Locataire</title>
<script src="https://cdn.tailwindcss.com"></script><script src="https://unpkg.com/jspdf@2.5.2/dist/jspdf.umd.min.js"></script><script src="https://cdn.jsdelivr.net/npm/@emailjs/browser@4/dist/email.min.js"></script>
<style>body{{font-family:system-ui;background:#0b0f19;color:#e2e8f0;margin:0;min-height:100vh}}.po{{position:fixed;inset:0;z-index:9999;background:#0b0f19;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:24px}}.pd{{width:14px;height:14px;border-radius:50%;background:#243050;border:2px solid #2a3655;transition:.2s}}.pd.f{{background:#3b82f6}}.pb{{width:64px;height:52px;border-radius:10px;background:#1a2236;border:1px solid #2a3655;color:#e2e8f0;font-size:1.2rem;font-weight:600;cursor:pointer}}.pb:hover{{background:#243050}}</style></head><body>
<div id="pl" class="po"><div style="text-align:center"><div style="font-size:3rem">\U0001f3e0</div><h1 style="font-size:1.4rem;color:#fbbf24">Portail Locataire</h1><p style="color:#64748b;font-size:.85rem">Entrez votre code PIN</p></div>
<div style="display:flex;gap:12px"><div class="pd" id="d0"></div><div class="pd" id="d1"></div><div class="pd" id="d2"></div><div class="pd" id="d3"></div></div>
<div id="pe" style="color:#ef4444;font-size:.82rem;min-height:20px"></div>
<div style="display:grid;grid-template-columns:repeat(3,64px);gap:8px"><button class="pb" onclick="pk('1')">1</button><button class="pb" onclick="pk('2')">2</button><button class="pb" onclick="pk('3')">3</button><button class="pb" onclick="pk('4')">4</button><button class="pb" onclick="pk('5')">5</button><button class="pb" onclick="pk('6')">6</button><button class="pb" onclick="pk('7')">7</button><button class="pb" onclick="pk('8')">8</button><button class="pb" onclick="pk('9')">9</button><button class="pb" onclick="pk('clr')" style="font-size:.8rem">CLR</button><button class="pb" onclick="pk('0')">0</button><button class="pb" onclick="pk('del')" style="color:#ef4444">\u232b</button></div></div>
<div id="pc" style="display:none">
<div style="background:#111827;border-bottom:1px solid #2a3655;padding:16px 24px;display:flex;align-items:center;gap:12px"><div style="width:42px;height:42px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#8b5cf6);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1.1rem">{nom[0]}</div><div><div style="font-weight:800;font-size:1rem">{nom} {prenom}</div><div style="font-size:.72rem;color:#64748b">Locataire - {bien}</div></div><div style="margin-left:auto;text-align:right"><div style="font-size:.68rem;color:#64748b">Loyer mensuel</div><div style="font-size:1.2rem;font-weight:800;color:#fbbf24">{loyer} {dev_sym}</div></div></div>
<div style="max-width:900px;margin:24px auto;padding:0 16px">
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:24px">
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Bien</div><div style="font-size:1rem;font-weight:700;margin-top:4px">{bien}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Debut contrat</div><div style="font-size:1rem;font-weight:700;margin-top:4px;color:#10b981">{dd_fmt}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Fin contrat</div><div style="font-size:1rem;font-weight:700;margin-top:4px;color:#f59e0b">{df_fmt}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Charges</div><div style="font-size:1rem;font-weight:700;margin-top:4px">{charges} {dev_sym}/mois</div></div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f4c4 Documents</h3></div><div style="padding:14px 18px">{docs_html(loc, bail_url, dd_fmt, df_fmt)}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f9fe Quittances de Loyer</h3></div><div style="padding:14px 18px"><table style="width:100%;border-collapse:collapse;font-size:.82rem"><thead><tr style="border-bottom:2px solid #2a3655"><th style="text-align:left;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Periode</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Loyer</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Charges</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Total</th><th style="text-align:center;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">PDF</th></tr></thead><tbody>{q}</tbody></table></div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden;border-left:3px solid #8b5cf6"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f4ac Messages du Proprietaire</h3></div><div style="padding:14px 18px">{messages_html(loc)}</div></div>
<div style="text-align:center;padding:20px;font-size:.7rem;color:#64748b">EL OUARDI PATRIMOINE - Portail Locataire Securise</div></div></div>
<script>
var _p='',_h='{pin_hash}';var _SIG_ACTIVE={'true' if loc.get('signature_active',True) else 'false'};
async function _sha(t){{var e=new TextEncoder().encode(t);var h=await crypto.subtle.digest('SHA-256',e);return Array.from(new Uint8Array(h)).map(b=>b.toString(16).padStart(2,'0')).join('')}}
function pk(k){{if(k==='clr'){{_p='';ud();document.getElementById('pe').textContent='';return}}if(k==='del'){{_p=_p.slice(0,-1);ud();return}}if(_p.length>=4)return;_p+=k;ud();if(_p.length===4)_sha(_p).then(function(h){{if(h===_h){{document.getElementById('pl').style.display='none';document.getElementById('pc').style.display='block';_checkSignedOnLoad();}}else{{document.getElementById('pe').textContent='Code PIN incorrect';_p='';setTimeout(ud,300)}}}})}}
function ud(){{for(var i=0;i<4;i++){{var d=document.getElementById('d'+i);if(d)d.classList.toggle('f',i<_p.length)}}}}
var _EJS_KEY='73LOazWxg3Xb82Xjk';var _EJS_SVC='service_lwj64xp';var _EJS_TPL='template_0xxr7zr';
try{{emailjs.init({{publicKey:_EJS_KEY}});}}catch(e){{}}
function _sendEmail(subject,body){{try{{emailjs.send(_EJS_SVC,_EJS_TPL,{{subject:subject,message:body,to_email:'ing.elouardi@gmail.com'}});}}catch(e){{console.warn('Email error:',e);}}}}
function _showSignedState(ds,ts){{var b=document.getElementById('sign-badge');b.textContent='\u2714 Signe le '+ds;b.style.background='rgba(16,185,129,.2)';b.style.color='#10b981';var a=document.getElementById('sign-actions');a.innerHTML='<div style="padding:8px 12px;background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.2);border-radius:8px;font-size:.82rem;color:#10b981">\u2714 Contrat signe electroniquement le '+ds+' a '+ts+' par {nom} {prenom}</div>';}}
function _disableSignBtn(msg){{var btn=document.getElementById('btn-signer');if(btn){{btn.disabled=true;btn.style.opacity='.4';btn.style.cursor='not-allowed';btn.title=msg;}}}}
function _checkSignedOnLoad(){{var sg=localStorage.getItem('contrat_signe_{nom}');if(sg){{var sd=new Date(sg);_showSignedState(sd.toLocaleDateString('fr-FR'),sd.toLocaleTimeString('fr-FR',{{hour:'2-digit',minute:'2-digit'}}));}}else if(!_SIG_ACTIVE){{_disableSignBtn('La signature n\\'est pas encore activee par le proprietaire.');var b=document.getElementById('sign-badge');b.textContent='\U0001f512 Signature desactivee';b.style.background='rgba(100,116,139,.15)';b.style.color='#64748b';}}}}
function _signerContrat(){{if(localStorage.getItem('contrat_signe_{nom}')){{alert('Vous avez deja signe ce contrat.');return;}}if(!_SIG_ACTIVE){{alert('La signature n\\'est pas encore activee par le proprietaire. Veuillez patienter.');return;}}if(!confirm('En cliquant OK, vous signez electroniquement ce contrat de bail.\\n\\nLocataire: {nom} {prenom}\\nPeriode: {dd_fmt} au {df_fmt}\\nLoyer: {total} {dev_sym}/mois\\n\\nCette action est definitive.'))return;var now=new Date();var ds=now.toLocaleDateString('fr-FR');var ts=now.toLocaleTimeString('fr-FR',{{hour:'2-digit',minute:'2-digit'}});localStorage.setItem('contrat_signe_{nom}',now.toISOString());_showSignedState(ds,ts);_sendEmail('\u2714 Contrat signe - {nom} {prenom}','Le locataire {nom} {prenom} a signe electroniquement son contrat de bail.\\n\\nBien: {bien}\\nPeriode: {dd_fmt} au {df_fmt}\\nLoyer: {total} EUR/mois\\nDate signature: '+ds+' a '+ts+'\\n\\nLe PDF signe a ete telecharge par le locataire.');_contratPDF();}}
function _envoyerCommentaire(){{var t=document.getElementById('comment-text').value.trim();if(!t){{alert('Veuillez saisir votre commentaire.');return;}}var data={{locataire:'{nom} {prenom}',bien:'{bien}',date:new Date().toISOString(),commentaire:t}};var old=JSON.parse(localStorage.getItem('contrat_commentaires')||'[]');old.push(data);localStorage.setItem('contrat_commentaires',JSON.stringify(old));document.getElementById('comment-zone').style.display='none';var a=document.getElementById('sign-actions');a.innerHTML+='<div style="margin-top:8px;padding:8px 12px;background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.2);border-radius:8px;font-size:.82rem;color:#f59e0b">\U0001f4e8 Commentaire envoye le '+new Date().toLocaleDateString('fr-FR')+' : '+t.substring(0,100)+'</div>';_sendEmail('\U0001f4ac Commentaire contrat - {nom} {prenom}','Le locataire {nom} {prenom} a envoye un commentaire sur son contrat de bail.\\n\\nBien: {bien}\\nPeriode: {dd_fmt} au {df_fmt}\\n\\nCommentaire:\\n'+t);}}
function _contratPDF(){{try{{var d=new jspdf.jsPDF();var pw=d.internal.pageSize.getWidth();var y=22;d.setFontSize(17);d.setFont('helvetica','bold');d.text('Bail de location meublee - Chambre en colocation',pw/2,y,{{align:'center'}});y+=14;d.setDrawColor(180);d.line(14,y,pw-14,y);y+=10;d.setFontSize(10);d.setFont('helvetica','normal');d.text('Entre les soussignes :',14,y);y+=6;d.setFont('helvetica','bold');d.text('Le bailleur (proprietaire)',14,y);y+=5;d.setFont('helvetica','normal');d.setFontSize(9.5);d.text('Nom / Prenom : Monsieur Yassine EL OUARDI',14,y);y+=5;d.text('Adresse : 3 Allee du Pourquoi Pas, 91000 Evry',14,y);y+=5;d.text('Telephone / Email : 06.21.35.64.07 - ing.elouardi@gmail.com',14,y);y+=7;d.setFont('helvetica','bold');d.setFontSize(10);d.text('Et le locataire (colocataire)',14,y);y+=5;d.setFont('helvetica','normal');d.setFontSize(9.5);d.text('Nom / Prenom : {nom} {prenom}',14,y);y+=8;var arts=[['1. Designation du logement','Type : Chambre meublee\\nAdresse : 3 Allee du Pourquoi Pas, 91000 Evry\\nSurface habitable : 12 m2\\nEquipements communs : cuisine, salle de bain, WC'],['2. Duree du bail','Du {dd_fmt} au {df_fmt}, renouvelable par tacite reconduction.'],['3. Loyer et charges','Loyer mensuel hors charges : {loyer} EUR\\nCharges forfaitaires : {charges} EUR (eau, electricite, chauffage, internet, entretien).\\nTotal mensuel : {total} EUR charges comprises.\\nLe loyer est payable mensuellement et d\\'avance, au plus tard le 5 du mois.'],['4. Depot de garantie','Le locataire verse a la signature du bail un depot de garantie de {depot} EUR.'],['5. Inventaire du mobilier','Le logement contient au minimum :\\n- Literie avec couette/couverture\\n- Plaques de cuisson\\n- Four ou micro-ondes\\n- Refrigerateur avec congelation\\n- Vaisselle et ustensiles\\n- Table + sieges\\n- Etageres\\n- Luminaires'],['6. Obligations du locataire','- Payer loyers/charges\\n- User paisiblement du logement\\n- Assurer le logement (attestation obligatoire)\\n- Restituer en bon etat'],['7. Obligations du bailleur','- Remettre logement decent\\n- Assurer jouissance paisible\\n- Fournir quittances\\n- Realiser reparations non locatives'],['8. Annexes','- Etat des lieux d\\'entree\\n- Inventaire du mobilier\\n- Diagnostics techniques (DPE, risques, plomb)\\n- Reglement copropriete (si applicable)'],['9. Clause resolutoire','Le bail sera resilie en cas de non-paiement du loyer/charges ou defaut de depot de garantie, apres commandement reste infructueux.']];arts.forEach(function(a){{if(y>255){{d.addPage();y=20;}}d.setFont('helvetica','bold');d.setFontSize(10);d.text(a[0],14,y);y+=6;d.setFont('helvetica','normal');d.setFontSize(9);var ls=d.splitTextToSize(a[1].replace(/\\\\n/g,'\\n'),pw-28);d.text(ls,14,y);y+=ls.length*4.5+7;}});if(y>170){{d.addPage();y=20;}}d.setFont('helvetica','bold');d.setFontSize(14);d.text('ETAT DES LIEUX D\\'ENTREE',14,y);y+=10;var tw=pw-28;var cols=[{{l:'Piece',w:Math.round(tw*.17)}},{{l:'Etat murs',w:Math.round(tw*.15)}},{{l:'Etat sols',w:Math.round(tw*.15)}},{{l:'Etat plafonds',w:Math.round(tw*.16)}},{{l:'Equipements',w:Math.round(tw*.17)}},{{l:'Observations',w:Math.round(tw*.20)}}];var rows=['Chambre','Cuisine','Salle de bain','WC','Parties communes'];d.setDrawColor(150);d.setLineWidth(.3);d.setFillColor(80,80,80);var cx=14;cols.forEach(function(c){{d.rect(cx,y,c.w,9,'FD');cx+=c.w;}});d.setTextColor(255,255,255);d.setFontSize(8);d.setFont('helvetica','bold');cx=14;cols.forEach(function(c){{d.text(c.l,cx+c.w/2,y+6,{{align:'center'}});cx+=c.w;}});y+=9;d.setDrawColor(180);rows.forEach(function(p,ri){{d.setFillColor(ri%2===0?245:255,ri%2===0?245:255,ri%2===0?245:255);cx=14;cols.forEach(function(c){{d.rect(cx,y,c.w,9,'FD');cx+=c.w;}});d.setTextColor(0,0,0);d.setFont('helvetica','normal');d.setFontSize(8.5);cx=14;cols.forEach(function(c,ci){{d.text(ci===0?p:'Bien',cx+c.w/2,y+6,{{align:'center'}});cx+=c.w;}});y+=9;}});y+=10;if(y>240){{d.addPage();y=20;}}d.setDrawColor(180);d.line(14,y,pw-14,y);y+=10;d.setTextColor(0);d.setFontSize(10);d.setFont('helvetica','normal');d.text('Fait a Evry, le '+new Date().toLocaleDateString('fr-FR'),14,y);y+=10;d.text('Signature du bailleur :',14,y);d.text('Signature du locataire :',pw/2+10,y);y+=8;d.setFont('courier','bolditalic');d.setFontSize(15);d.setTextColor(0,0,100);d.text('Yassine EL OUARDI',14,y);var sg=localStorage.getItem('contrat_signe_{nom}');if(sg){{d.setTextColor(0,100,0);d.text('{nom} {prenom}',pw/2+10,y);}}else{{d.setTextColor(0);d.setFont('helvetica','italic');d.setFontSize(9);d.text('..............................',pw/2+10,y);}}y+=6;d.setDrawColor(0,0,100);d.line(14,y,70,y);if(sg){{d.setDrawColor(0,100,0);d.line(pw/2+10,y,pw/2+70,y);}}y+=4;d.setFont('helvetica','normal');d.setFontSize(7);d.setTextColor(100);d.text('Signe electroniquement le '+new Date().toLocaleDateString('fr-FR'),14,y);if(sg){{var sd=new Date(sg);d.text('Signe par {nom} {prenom} le '+sd.toLocaleDateString('fr-FR')+' a '+sd.toLocaleTimeString('fr-FR',{{hour:'2-digit',minute:'2-digit'}}),pw/2+10,y);}}y+=14;if(y>210){{d.addPage();y=20;}}d.setTextColor(0);d.setFontSize(13);d.setFont('helvetica','bold');d.text('Liste des documents a fournir',14,y);y+=10;d.setDrawColor(150);d.setFontSize(9);d.setFillColor(240,240,240);d.rect(14,y-4,pw-28,8,'F');d.setFont('helvetica','bold');d.text('Documents bailleur',16,y);d.text('Documents locataire',pw/2+7,y);y+=8;d.line(14,y,pw-14,y);y+=5;d.setFont('helvetica','normal');d.setFontSize(8.5);var db=['- Bail signe','- Quittances mensuelles','- Reglement copropriete'];var dl=['- Piece d\\'identite valide','- Justificatif domicile','- 3 fiches de paie','- Dernier avis imposition','- Attestation assurance','- Garant (Visale)'];for(var ri=0;ri<Math.max(db.length,dl.length);ri++){{if(db[ri])d.text(db[ri],16,y);if(dl[ri])d.text(dl[ri],pw/2+7,y);y+=5;}}y+=4;d.setFontSize(7);d.setTextColor(130);d.text('Contrat conforme a la loi n. 89-462 du 6 juillet 1989.',14,y);d.save('Contrat_Bail_{nom}_{prenom}_'+new Date().toISOString().slice(0,10)+'.pdf');}}catch(e){{alert('Erreur generation PDF: '+e.message);}}}}
function _qpdf(mois,deb,fin){{try{{var d=new jspdf.jsPDF();var y=20;d.setFontSize(18);d.setFont('helvetica','bold');d.text('QUITTANCE DE LOYER',105,y,{{align:'center'}});y+=8;d.setFontSize(9);d.setFont('helvetica','normal');d.setTextColor(100);d.text('Loi du 6 juillet 1989 - Article 21',105,y,{{align:'center'}});y+=12;d.setTextColor(0);d.setFontSize(11);d.setFont('helvetica','bold');d.text('BAILLEUR',14,y);y+=6;d.setFont('helvetica','normal');d.setFontSize(10);d.text('EL OUARDI Yassine',14,y);y+=5;d.text('3 Allee du Pourquoi Pas, 91000 Evry',14,y);y+=10;d.setFont('helvetica','bold');d.setFontSize(11);d.text('LOCATAIRE',14,y);y+=6;d.setFont('helvetica','normal');d.setFontSize(10);d.text('{nom} {prenom}',14,y);y+=10;d.setFont('helvetica','bold');d.setFontSize(11);d.text('LOGEMENT',14,y);y+=6;d.setFont('helvetica','normal');d.setFontSize(10);d.text('3 Allee du Pourquoi Pas, 91000 Evry',14,y);y+=5;d.text('Periode: du '+deb+' au '+fin,14,y);y+=12;d.text('Je soussigne EL OUARDI Yassine declare avoir recu de {nom} {prenom} la somme de:',14,y);y+=10;d.setDrawColor(0);d.setLineWidth(1);d.rect(35,y-2,140,22);d.setFontSize(24);d.setFont('helvetica','bold');d.text('{total} EUR',105,y+12,{{align:'center'}});y+=28;d.setFontSize(9);d.setFont('helvetica','normal');d.text('Loyer: {loyer} EUR | Charges: {charges} EUR | Total: {total} EUR',105,y,{{align:'center'}});y+=12;d.setFont('helvetica','bold');d.text('DETAIL',14,y);y+=6;d.setFont('helvetica','normal');d.text('Loyer: {loyer} EUR',14,y);y+=5;d.text('Charges: {charges} EUR',14,y);y+=5;d.setFont('helvetica','bold');d.text('Total: {total} EUR',14,y);y+=12;d.line(14,y,196,y);y+=8;d.setFont('helvetica','normal');d.text('Le bailleur',14,y);d.text('Le locataire',120,y);y+=6;d.setFont('helvetica','bold');d.text('EL OUARDI Yassine',14,y);d.text('{nom} {prenom}',120,y);y+=10;d.setFont('helvetica','normal');d.setFontSize(8);d.text('Fait en deux exemplaires a Evry, le '+new Date().toLocaleDateString('fr-FR'),14,y);y+=8;d.setFontSize(7);d.setTextColor(130);d.text('Loi n. 89-462 du 6 juillet 1989 (article 21)',14,y);d.save('Quittance_'+mois.replace(/ /g,'_')+'_{nom}_{prenom}.pdf')}}catch(e){{var w=window.open('','_blank');w.document.write('<html><head><title>Quittance '+mois+'</title><style>body{{font-family:system-ui;max-width:700px;margin:40px auto;padding:20px;line-height:1.8}}h1{{color:#1e40af;border-bottom:2px solid #1e40af;padding-bottom:8px}}@media print{{button{{display:none}}}}</style></head><body><h1>QUITTANCE DE LOYER</h1><p>Loi du 6 juillet 1989 - Article 21</p><hr><p><b>BAILLEUR:</b> EL OUARDI Yassine<br>3 Allee du Pourquoi Pas, 91000 Evry</p><p><b>LOCATAIRE:</b> {nom} {prenom}</p><p><b>PERIODE:</b> du '+deb+' au '+fin+'</p><div style="border:2px solid #000;padding:20px;text-align:center;margin:20px 0"><h2>{total} EUR</h2><p>Loyer: {loyer} EUR | Charges: {charges} EUR</p></div><p>Fait en deux exemplaires a Evry, le '+new Date().toLocaleDateString('fr-FR')+'</p><p style="margin-top:30px"><b>Le bailleur:</b> EL OUARDI Yassine &nbsp;&nbsp;&nbsp; <b>Le locataire:</b> {nom} {prenom}</p><hr><p style="font-size:0.8em;color:#666">Loi n. 89-462 du 6 juillet 1989 (article 21)</p><button onclick="window.print()" style="padding:10px 24px;background:#1e40af;color:#fff;border:none;border-radius:8px;cursor:pointer;margin-top:20px">Imprimer / Sauvegarder PDF</button></body></html>');w.document.close()}}}}
</script></body></html>'''
    (PUBLIC/f'{slug}.html').write_text(html,encoding='utf-8')
    return {'nom':nom,'prenom':prenom,'pin':pin,'slug':slug,
        'portal_url':f'https://ingelouardi-cloud.github.io/patrimoine/public/{slug}.html',
        'contrat_url':f'https://ingelouardi-cloud.github.io/patrimoine/contrats/{slug}-bail.pdf'}

def main():
    # Priority: 1) --from-app input file  2) backup de l'app  3) données hardcodées
    locs = None
    if '--from-app' in sys.argv:
        inp=DIR/'_input_locataires.json'
        if inp.exists():
            raw=json.loads(inp.read_text())
            app_locs=raw.get('locataires',raw) if isinstance(raw,dict) else raw
            locs=[]
            for a in app_locs:
                base=next((l for l in LOCATAIRES_FALLBACK if l['nom'].lower()==(a.get('nom','').lower())),{})
                merged={**base,**{k:v for k,v in a.items() if v or isinstance(v,list)},'loyer':a.get('loyer',400),'charges':a.get('charges',50)}
                if 'date_debut' not in merged and 'date_entree' in merged:
                    merged['date_debut']=merged['date_entree']
                if 'date_debut' not in merged: merged['date_debut']=''
                if 'date_fin' not in merged: merged['date_fin']=''
                locs.append(merged)
            inp.unlink()
    # Enrichir avec le backup (historique, messages, locataires manquants)
    backup_locs = load_from_backup()
    if backup_locs:
        if locs:
            for bl in backup_locs:
                bl_nom=bl['nom'].lower().split()[0]
                match = next((l for l in locs if l.get('nom','').lower().split()[0] == bl_nom), None)
                if match:
                    if not match.get('contrats_historique'): match['contrats_historique'] = bl.get('contrats_historique', [])
                    if not match.get('portal_messages'): match['portal_messages'] = bl.get('portal_messages', [])
                    if not match.get('bien') or match.get('bien')=='EVERY': match['bien'] = bl.get('bien', 'EVRY')
                else:
                    # Locataire dans backup mais pas dans payload → ajouter
                    locs.append(bl)
                    print(f"  + Ajouté depuis backup: {bl['nom']} {bl.get('prenom','')}")
        else:
            locs = backup_locs
    if not locs:
        locs = LOCATAIRES_FALLBACK

    manifest=[]
    for loc in locs:
        r=gen_portal(loc)
        manifest.append(r)
        print(f"  OK {r['nom']} {r['prenom']} PIN:{r['pin']}")
    (DIR/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    # Copy manifest to vanilla app
    dst=Path(os.path.expanduser('~/Downloads/patrimoine-app/portail-locataires/manifest.json'))
    if dst.parent.exists(): shutil.copy2(DIR/'manifest.json',dst)
    # Git
    os.system(f'cd {DIR} && git add -A && git commit -m "MAJ portails" 2>/dev/null')
    os.system(f'cd {DIR} && git push origin main 2>/dev/null')
    print(f"  {len(manifest)} portails generes")

if __name__=='__main__': main()
