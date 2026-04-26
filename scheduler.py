#!/usr/bin/env python3
"""
Scheduler configurable — lit scheduler.json et exécute les tâches programmées.
Usage:
  python3 scheduler.py                    # Vérifie et exécute les tâches dues
  python3 scheduler.py --list             # Liste les tâches programmées
  python3 scheduler.py --add "2026-05-01 18:30"  # Programme une génération
  python3 scheduler.py --cron             # Installe le cron automatique
  python3 scheduler.py --run-now          # Exécute maintenant
"""

import json, os, sys, subprocess
from datetime import datetime, timedelta
from pathlib import Path

DIR = Path(__file__).parent
CONFIG = DIR / 'scheduler.json'

def load_config():
    if CONFIG.exists():
        return json.loads(CONFIG.read_text())
    return {"enabled": True, "tasks": []}

def save_config(cfg):
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))

def list_tasks():
    cfg = load_config()
    print(f"\n{'═' * 50}")
    print(f"  📅 TÂCHES PROGRAMMÉES ({len(cfg['tasks'])})")
    print(f"{'═' * 50}\n")
    for t in cfg['tasks']:
        status = '✅ Activée' if t.get('enabled', True) else '❌ Désactivée'
        last = t.get('last_run', 'Jamais')
        print(f"  📌 {t['name']}")
        print(f"     Prochaine: {t.get('schedule', '—')}")
        print(f"     Répétition: {t.get('repeat', 'none')} (jour {t.get('repeat_day', '—')} à {t.get('repeat_time', '—')})")
        print(f"     Dernière exécution: {last}")
        print(f"     Statut: {status}")
        print()

def add_task(schedule_str):
    cfg = load_config()
    # Parse "2026-05-01 18:30"
    try:
        dt = datetime.strptime(schedule_str, '%Y-%m-%d %H:%M')
    except:
        print(f"❌ Format invalide. Utilisez: YYYY-MM-DD HH:MM")
        return

    task = {
        "id": f"gen_{dt.strftime('%Y%m%d_%H%M')}",
        "name": f"Génération portails — {dt.strftime('%d/%m/%Y à %H:%M')}",
        "command": "python3 generate.py",
        "schedule": schedule_str,
        "repeat": "none",
        "enabled": True,
        "last_run": None
    }
    cfg['tasks'].append(task)
    save_config(cfg)
    print(f"✅ Tâche ajoutée: {task['name']}")
    print(f"   Exécution prévue: {schedule_str}")

def set_repeat(repeat_type, day=1, time="18:30"):
    """Configure la répétition: monthly, weekly, daily, none"""
    cfg = load_config()
    if not cfg['tasks']:
        print("❌ Aucune tâche. Ajoutez d'abord avec --add")
        return
    task = cfg['tasks'][0]
    task['repeat'] = repeat_type
    task['repeat_day'] = day
    task['repeat_time'] = time
    # Calcul prochaine exécution
    now = datetime.now()
    if repeat_type == 'monthly':
        next_dt = now.replace(day=day, hour=int(time.split(':')[0]), minute=int(time.split(':')[1]), second=0)
        if next_dt <= now:
            if now.month == 12:
                next_dt = next_dt.replace(year=now.year + 1, month=1)
            else:
                next_dt = next_dt.replace(month=now.month + 1)
        task['schedule'] = next_dt.strftime('%Y-%m-%d %H:%M')
    elif repeat_type == 'weekly':
        next_dt = now + timedelta(days=(day - now.weekday()) % 7)
        next_dt = next_dt.replace(hour=int(time.split(':')[0]), minute=int(time.split(':')[1]), second=0)
        if next_dt <= now:
            next_dt += timedelta(days=7)
        task['schedule'] = next_dt.strftime('%Y-%m-%d %H:%M')
    elif repeat_type == 'daily':
        next_dt = now.replace(hour=int(time.split(':')[0]), minute=int(time.split(':')[1]), second=0)
        if next_dt <= now:
            next_dt += timedelta(days=1)
        task['schedule'] = next_dt.strftime('%Y-%m-%d %H:%M')
    save_config(cfg)
    print(f"✅ Répétition: {repeat_type} (jour {day} à {time})")
    print(f"   Prochaine exécution: {task['schedule']}")

def check_and_run():
    """Vérifie si une tâche est due et l'exécute."""
    cfg = load_config()
    if not cfg.get('enabled', True):
        return

    now = datetime.now()
    for task in cfg['tasks']:
        if not task.get('enabled', True):
            continue
        schedule = task.get('schedule')
        if not schedule:
            continue
        try:
            dt = datetime.strptime(schedule, '%Y-%m-%d %H:%M')
        except:
            continue

        # Check if due (within 2 min window)
        if abs((now - dt).total_seconds()) < 120:
            print(f"⏰ Exécution: {task['name']}")
            result = subprocess.run(
                task['command'], shell=True, cwd=str(DIR),
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"✅ Terminé avec succès")
            else:
                print(f"❌ Erreur: {result.stderr[:200]}")

            task['last_run'] = now.isoformat()

            # Schedule next if repeat
            repeat = task.get('repeat', 'none')
            if repeat == 'monthly':
                next_month = dt.month + 1 if dt.month < 12 else 1
                next_year = dt.year if dt.month < 12 else dt.year + 1
                task['schedule'] = dt.replace(year=next_year, month=next_month).strftime('%Y-%m-%d %H:%M')
            elif repeat == 'weekly':
                task['schedule'] = (dt + timedelta(days=7)).strftime('%Y-%m-%d %H:%M')
            elif repeat == 'daily':
                task['schedule'] = (dt + timedelta(days=1)).strftime('%Y-%m-%d %H:%M')
            elif repeat == 'none':
                task['enabled'] = False

            save_config(cfg)

def install_cron():
    """Installe un cron qui vérifie toutes les minutes."""
    script_path = str(DIR / 'scheduler.py')
    cron_line = f'* * * * * cd {DIR} && /usr/bin/python3 {script_path} >> {DIR}/scheduler.log 2>&1'

    # Get existing crontab
    result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ''

    if 'scheduler.py' in existing:
        print("⚠️ Cron déjà installé")
        return

    new_crontab = existing.rstrip() + '\n' + cron_line + '\n'
    proc = subprocess.run(['crontab', '-'], input=new_crontab, capture_output=True, text=True)
    if proc.returncode == 0:
        print(f"✅ Cron installé — vérifie toutes les minutes")
        print(f"   Log: {DIR}/scheduler.log")
    else:
        print(f"❌ Erreur cron: {proc.stderr}")

def remove_cron():
    result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
    if result.returncode != 0:
        return
    lines = [l for l in result.stdout.split('\n') if 'scheduler.py' not in l]
    subprocess.run(['crontab', '-'], input='\n'.join(lines) + '\n', capture_output=True, text=True)
    print("✅ Cron supprimé")

def run_now():
    print("🚀 Exécution immédiate...")
    result = subprocess.run('python3 generate.py', shell=True, cwd=str(DIR), capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr[:500])

def main():
    args = sys.argv[1:]

    if not args:
        check_and_run()
    elif args[0] == '--list':
        list_tasks()
    elif args[0] == '--add' and len(args) >= 2:
        add_task(' '.join(args[1:]))
    elif args[0] == '--repeat' and len(args) >= 2:
        repeat_type = args[1]
        day = int(args[2]) if len(args) > 2 else 1
        time = args[3] if len(args) > 3 else '18:30'
        set_repeat(repeat_type, day, time)
    elif args[0] == '--cron':
        install_cron()
    elif args[0] == '--remove-cron':
        remove_cron()
    elif args[0] == '--run-now':
        run_now()
    elif args[0] == '--enable':
        cfg = load_config()
        cfg['enabled'] = True
        save_config(cfg)
        print("✅ Scheduler activé")
    elif args[0] == '--disable':
        cfg = load_config()
        cfg['enabled'] = False
        save_config(cfg)
        print("❌ Scheduler désactivé")
    else:
        print(__doc__)

if __name__ == '__main__':
    main()
