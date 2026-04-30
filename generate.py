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

LOCATAIRES = [
    {'nom':'DRAA','prenom':'Abdelilah','loyer':400,'charges':50,
     'date_debut':'2025-09-30','date_fin':'2026-06-30',
     'bail':'20260422_164010_Bail-DRAA-ABDELILAH.pdf'},
    {'nom':'MESBAH','prenom':'Abderahmane','loyer':400,'charges':50,
     'date_debut':'2026-04-01','date_fin':'2027-04-01',
     'bail':'20260422_163919_MESBAHI-bail_colocation_chambre_v3 1.pdf'},
    {'nom':'EZZAHID','prenom':'Samir','loyer':400,'charges':50,
     'date_debut':'2026-02-01','date_fin':'2027-02-01',
     'bail':'20260422_163919_SAMI-Contrat bail de location chambre Bras de Fer.pdf'},
]

def fmt_date(d):
    try: return datetime.strptime(d,'%Y-%m-%d').strftime('%d/%m/%Y')
    except: return d

def quittances_html(loc):
    rows=''
    try:
        start=datetime.strptime(loc['date_debut'],'%Y-%m-%d').replace(day=1)
        now=datetime.now()
        cur=start
        while cur<=now:
            ml=MOIS[cur.month-1]+' '+str(cur.year)
            deb=f'01/{cur.month:02d}/{cur.year}'
            fin=f'{28 if cur.month==2 else 30}/{cur.month:02d}/{cur.year}'
            rows+=f'''<tr style="border-bottom:1px solid #2a3655"><td style="padding:8px;font-weight:600">{ml}</td><td style="text-align:right;padding:8px">{loc['loyer']} EUR</td><td style="text-align:right;padding:8px">{loc['charges']} EUR</td><td style="text-align:right;padding:8px;font-weight:700;color:#fbbf24">{loc['loyer']+loc['charges']} EUR</td><td style="text-align:center;padding:8px"><button onclick="_qpdf('{ml}','{deb}','{fin}')" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:4px 10px;font-size:.72rem;cursor:pointer">PDF</button></td></tr>'''
            cur=cur.replace(year=cur.year+1,month=1) if cur.month==12 else cur.replace(month=cur.month+1)
    except: pass
    return rows

def gen_portal(loc):
    nom,prenom=loc['nom'],loc['prenom']
    slug=(nom+'-'+prenom).lower().replace(' ','-')
    # Use existing PIN from app or generate new one
    pin=loc.get('portal_pin','') or loc.get('pin','') or str(1000+random.randint(0,8999))
    loc['pin']=pin  # Store back so manifest has it
    pin_hash=hashlib.sha256(pin.encode()).hexdigest()
    loyer,charges=loc['loyer'],loc['charges']
    total=loyer+charges
    dd_fmt=fmt_date(loc['date_debut'])
    df_fmt=fmt_date(loc['date_fin'])
    bail_file=loc.get('bail','')
    bail_src=GED/bail_file
    if bail_src.exists():
        shutil.copy2(bail_src,CONTRATS/f'{slug}-bail.pdf')
        bail_url=f'../contrats/{slug}-bail.pdf'
    else: bail_url='#'
    q=quittances_html(loc)
    html=f'''<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Portail Locataire</title>
<script src="https://cdn.tailwindcss.com"></script><script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.2/jspdf.umd.min.js"></script>
<style>body{{font-family:system-ui;background:#0b0f19;color:#e2e8f0;margin:0;min-height:100vh}}.po{{position:fixed;inset:0;z-index:9999;background:#0b0f19;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:24px}}.pd{{width:14px;height:14px;border-radius:50%;background:#243050;border:2px solid #2a3655;transition:.2s}}.pd.f{{background:#3b82f6}}.pb{{width:64px;height:52px;border-radius:10px;background:#1a2236;border:1px solid #2a3655;color:#e2e8f0;font-size:1.2rem;font-weight:600;cursor:pointer}}.pb:hover{{background:#243050}}</style></head><body>
<div id="pl" class="po"><div style="text-align:center"><div style="font-size:3rem">\U0001f3e0</div><h1 style="font-size:1.4rem;color:#fbbf24">Portail Locataire</h1><p style="color:#64748b;font-size:.85rem">Entrez votre code PIN</p></div>
<div style="display:flex;gap:12px"><div class="pd" id="d0"></div><div class="pd" id="d1"></div><div class="pd" id="d2"></div><div class="pd" id="d3"></div></div>
<div id="pe" style="color:#ef4444;font-size:.82rem;min-height:20px"></div>
<div style="display:grid;grid-template-columns:repeat(3,64px);gap:8px"><button class="pb" onclick="pk('1')">1</button><button class="pb" onclick="pk('2')">2</button><button class="pb" onclick="pk('3')">3</button><button class="pb" onclick="pk('4')">4</button><button class="pb" onclick="pk('5')">5</button><button class="pb" onclick="pk('6')">6</button><button class="pb" onclick="pk('7')">7</button><button class="pb" onclick="pk('8')">8</button><button class="pb" onclick="pk('9')">9</button><button class="pb" onclick="pk('clr')" style="font-size:.8rem">CLR</button><button class="pb" onclick="pk('0')">0</button><button class="pb" onclick="pk('del')" style="color:#ef4444">\u232b</button></div></div>
<div id="pc" style="display:none">
<div style="background:#111827;border-bottom:1px solid #2a3655;padding:16px 24px;display:flex;align-items:center;gap:12px"><div style="width:42px;height:42px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#8b5cf6);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1.1rem">{nom[0]}</div><div><div style="font-weight:800;font-size:1rem">{nom} {prenom}</div><div style="font-size:.72rem;color:#64748b">Locataire - EVERY</div></div><div style="margin-left:auto;text-align:right"><div style="font-size:.68rem;color:#64748b">Loyer mensuel</div><div style="font-size:1.2rem;font-weight:800;color:#fbbf24">{loyer} EUR</div></div></div>
<div style="max-width:900px;margin:24px auto;padding:0 16px">
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:24px">
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Bien</div><div style="font-size:1rem;font-weight:700;margin-top:4px">EVERY</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Debut contrat</div><div style="font-size:1rem;font-weight:700;margin-top:4px;color:#10b981">{dd_fmt}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Fin contrat</div><div style="font-size:1rem;font-weight:700;margin-top:4px;color:#f59e0b">{df_fmt}</div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:10px;padding:14px"><div style="font-size:.68rem;color:#64748b;text-transform:uppercase">Charges</div><div style="font-size:1rem;font-weight:700;margin-top:4px">{charges} EUR/mois</div></div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f4c4 Documents</h3></div><div style="padding:14px 18px"><div style="display:flex;align-items:center;gap:10px;padding:10px;background:#1a2236;border-radius:8px"><span style="font-size:1.2rem">\U0001f4cb</span><div style="flex:1"><div style="font-weight:600;font-size:.82rem">Contrat de Bail (PDF original)</div><div style="font-size:.7rem;color:#64748b">Du {dd_fmt} au {df_fmt}</div></div><a href="{bail_url}" target="_blank" style="background:#3b82f6;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:.75rem;cursor:pointer;text-decoration:none;font-weight:600">\U0001f4e5 Ouvrir PDF</a></div></div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f9fe Quittances de Loyer</h3></div><div style="padding:14px 18px"><table style="width:100%;border-collapse:collapse;font-size:.82rem"><thead><tr style="border-bottom:2px solid #2a3655"><th style="text-align:left;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Periode</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Loyer</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Charges</th><th style="text-align:right;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">Total</th><th style="text-align:center;padding:8px;font-size:.68rem;color:#64748b;text-transform:uppercase">PDF</th></tr></thead><tbody>{q}</tbody></table></div></div>
<div style="background:#111827;border:1px solid #2a3655;border-radius:12px;margin-bottom:20px;overflow:hidden;border-left:3px solid #8b5cf6"><div style="padding:14px 18px;border-bottom:1px solid #2a3655"><h3 style="font-size:.9rem;font-weight:700;margin:0">\U0001f4ac Messages du Proprietaire</h3></div><div style="padding:14px 18px"><div style="color:#64748b;font-size:.82rem">Aucun message.</div></div></div>
<div style="text-align:center;padding:20px;font-size:.7rem;color:#64748b">EL OUARDI PATRIMOINE - Portail Locataire Securise</div></div></div>
<script>
var _p='',_h='{pin_hash}';
async function _sha(t){{var e=new TextEncoder().encode(t);var h=await crypto.subtle.digest('SHA-256',e);return Array.from(new Uint8Array(h)).map(b=>b.toString(16).padStart(2,'0')).join('')}}
function pk(k){{if(k==='clr'){{_p='';ud();document.getElementById('pe').textContent='';return}}if(k==='del'){{_p=_p.slice(0,-1);ud();return}}if(_p.length>=4)return;_p+=k;ud();if(_p.length===4)_sha(_p).then(function(h){{if(h===_h){{document.getElementById('pl').style.display='none';document.getElementById('pc').style.display='block'}}else{{document.getElementById('pe').textContent='Code PIN incorrect';_p='';setTimeout(ud,300)}}}})}}
function ud(){{for(var i=0;i<4;i++){{var d=document.getElementById('d'+i);if(d)d.classList.toggle('f',i<_p.length)}}}}
function _qpdf(mois,deb,fin){{var d=new jspdf.jsPDF();var y=20;d.setFontSize(18);d.setFont('helvetica','bold');d.text('QUITTANCE DE LOYER',105,y,{{align:'center'}});y+=8;d.setFontSize(9);d.setFont('helvetica','normal');d.setTextColor(100);d.text('Loi du 6 juillet 1989 - Article 21',105,y,{{align:'center'}});y+=12;d.setTextColor(0);d.setFontSize(11);d.setFont('helvetica','bold');d.text('BAILLEUR',14,y);y+=6;d.setFont('helvetica','normal');d.setFontSize(10);d.text('EL OUARDI Yassine',14,y);y+=5;d.text('3 Allee du Pourquoi Pas, 91000 Evry',14,y);y+=10;d.setFont('helvetica','bold');d.setFontSize(11);d.text('LOCATAIRE',14,y);y+=6;d.setFont('helvetica','normal');d.setFontSize(10);d.text('{nom} {prenom}',14,y);y+=10;d.setFont('helvetica','bold');d.setFontSize(11);d.text('LOGEMENT',14,y);y+=6;d.setFont('helvetica','normal');d.setFontSize(10);d.text('3 Allee du Pourquoi Pas, 91000 Evry',14,y);y+=5;d.text('Periode: du '+deb+' au '+fin,14,y);y+=12;d.text('Je soussigne EL OUARDI Yassine declare avoir recu de {nom} {prenom} la somme de:',14,y);y+=10;d.setDrawColor(0);d.setLineWidth(1);d.rect(35,y-2,140,22);d.setFontSize(24);d.setFont('helvetica','bold');d.text('{total} EUR',105,y+12,{{align:'center'}});y+=28;d.setFontSize(9);d.setFont('helvetica','normal');d.text('Loyer: {loyer} EUR | Charges: {charges} EUR | Total: {total} EUR',105,y,{{align:'center'}});y+=12;d.setFont('helvetica','bold');d.text('DETAIL',14,y);y+=6;d.setFont('helvetica','normal');d.text('Loyer: {loyer} EUR',14,y);y+=5;d.text('Charges: {charges} EUR',14,y);y+=5;d.setFont('helvetica','bold');d.text('Total: {total} EUR',14,y);y+=12;d.line(14,y,196,y);y+=8;d.setFont('helvetica','normal');d.text('Le bailleur',14,y);d.text('Le locataire',120,y);y+=6;d.setFont('helvetica','bold');d.text('EL OUARDI Yassine',14,y);d.text('{nom} {prenom}',120,y);y+=10;d.setFont('helvetica','normal');d.setFontSize(8);d.text('Fait en deux exemplaires a Evry, le '+new Date().toLocaleDateString('fr-FR'),14,y);y+=8;d.setFontSize(7);d.setTextColor(130);d.text('Loi n. 89-462 du 6 juillet 1989 (article 21)',14,y);d.save('Quittance_'+mois.replace(/ /g,'_')+'_{nom}_{prenom}.pdf')}}
</script></body></html>'''
    (PUBLIC/f'{slug}.html').write_text(html,encoding='utf-8')
    return {'nom':nom,'prenom':prenom,'pin':pin,'slug':slug,
        'portal_url':f'https://ingelouardi-cloud.github.io/patrimoine/public/{slug}.html',
        'contrat_url':f'https://ingelouardi-cloud.github.io/patrimoine/contrats/{slug}-bail.pdf'}

def main():
    # Read from app if --from-app
    if '--from-app' in sys.argv:
        inp=DIR/'_input_locataires.json'
        if inp.exists():
            raw=json.loads(inp.read_text())
            app_locs=raw.get('locataires',raw) if isinstance(raw,dict) else raw
            locs=[]
            for a in app_locs:
                # Find matching LOCATAIRE for bail
                base=next((l for l in LOCATAIRES if l['nom'].lower()==(a.get('nom','').lower())),{})
                locs.append({**base,**{k:v for k,v in a.items() if v},'loyer':a.get('loyer',400),'charges':a.get('charges',50)})
            inp.unlink()
        else: locs=LOCATAIRES
    else: locs=LOCATAIRES

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
