import os, json, logging
from datetime import datetime, timedelta
from pathlib import Path
from telegram import Update
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, filters, ContextTypes,
)
import anthropic

TG = os.environ["TELEGRAM_TOKEN"]
AK = os.environ["ANTHROPIC_API_KEY"]
CID = int(os.environ["MY_CHAT_ID"])
DATA = Path("data.json")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

DEFAULT = {
    "profile": {
        "name": "Hraf",
        "ville": "Casablanca",
        "stage": "Marketing @ CIMAT",
        "projet": "QISSA - marque streetwear"
    },
    "objectifs": [], "rdv": [], "notes": [],
    "history": []
}

def load():
    if DATA.exists():
        with open(DATA, "r") as f:
            d = json.load(f)
            if "history" not in d:
                d["history"] = []
            return d
    save(DEFAULT)
    return DEFAULT.copy()

def save(d):
    with open(DATA, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

client = anthropic.Anthropic(api_key=AK)

SYS = """Tu es l'assistant perso de Hraf sur Telegram.
Tu le tutoies, tu parles informel en francais.

CONTEXTE: {ctx}
RDV: {rdv}
OBJECTIFS: {obj}
NOTES: {notes}
DATE ACTUELLE: {now}

Role:
- Concis et naturel, comme un collegue
- Si Hraf mentionne un RDV/objectif/note, tu le detectes
- Tu aides sur le marketing (CIMAT), branding (QISSA), orga perso
- Emojis avec moderation
- Tu te souviens de toute la conversation

Commandes: /rdv /objectif /note /planning /objectifs

Si Hraf dit naturellement un RDV ou objectif, ajoute en fin de reponse:
---ACTION: RDV|date|heure|description
---ACTION: OBJECTIF|description
---ACTION: NOTE|texte
Seulement si pertinent."""

def sysprompt(d):
    ctx = ", ".join(f"{k}: {v}" for k,v in d["profile"].items())
    rdv = "\n".join(f"- {r['date']} {r['heure']} {r['description']}" for r in d["rdv"]) or "Aucun"
    obj = "\n".join(f"- {'[OK]' if o.get('done') else '[  ]'} {o['description']}" for o in d["objectifs"]) or "Aucun"
    notes = "\n".join(f"- {n['text']}" for n in d.get("notes",[])[-5:]) or "Aucune"
    now = datetime.now().strftime("%A %d/%m/%Y %H:%M")
    return SYS.format(ctx=ctx, rdv=rdv, obj=obj, notes=notes, now=now)

async def ai(msg, d):
    try:
        history = d.get("history", [])[-20:]
        history.append({"role": "user", "content": msg})
        r = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=sysprompt(d),
            messages=history
        )
        reply = r.content[0].text
        d["history"] = d.get("history", [])[-20:]
        d["history"].append({"role": "user", "content": msg})
        d["history"].append({"role": "assistant", "content": reply})
        save(d)
        return reply
    except Exception as e:
        log.error(f"API error: {e}")
        return "Souci technique, reessaie"

async def start(u: Update, c):
    await u.message.reply_text(
        "Hey! Ton assistant est la.\n\n"
        "/rdv [date] [heure] [desc]\n"
        "/objectif [desc]\n"
        "/note [texte]\n"
        "/planning\n/objectifs\n\n"
        "Ou parle-moi naturellement"
    )

async def add_rdv(u: Update, c):
    d = load()
    args = " ".join(c.args) if c.args else ""
    if not args:
        await u.message.reply_text("/rdv 15/04/2026 14:00 Description")
        return
    p = args.split(" ", 2)
    if len(p) < 3:
        await u.message.reply_text("/rdv [date] [heure] [description]")
        return
    d["rdv"].append({"date":p[0],"heure":p[1],"description":p[2],"rappel":False})
    save(d)
    await u.message.reply_text(f"RDV note: {p[2]}\n{p[0]} a {p[1]}")

async def add_obj(u: Update, c):
    d = load()
    desc = " ".join(c.args) if c.args else ""
    if not desc:
        await u.message.reply_text("/objectif [description]")
        return
    d["objectifs"].append({"description":desc,"done":False,"date":datetime.now().strftime("%d/%m/%Y")})
    save(d)
    await u.message.reply_text(f"Objectif ajoute: {desc}")

async def add_note(u: Update, c):
    d = load()
    txt = " ".join(c.args) if c.args else ""
    if not txt:
        await u.message.reply_text("/note [texte]")
        return
    d["notes"].append({"text":txt,"date":datetime.now().strftime("%d/%m/%Y %H:%M")})
    save(d)
    await u.message.reply_text("Note!")

async def planning(u: Update, c):
    d = load()
    r = await ai(f"Donne mon planning. Date: {datetime.now().strftime('%A %d/%m/%Y %H:%M')}", d)
    await u.message.reply_text(r)

async def objectifs(u: Update, c):
    d = load()
    if not d["objectifs"]:
        await u.message.reply_text("Aucun objectif. /objectif pour en ajouter")
        return
    lines = ["Objectifs:\n"]
    for i,o in enumerate(d["objectifs"],1):
        s = "OK" if o.get("done") else "..."
        lines.append(f"{i}. [{s}] {o['description']}")
    await u.message.reply_text("\n".join(lines))

async def del_rdv(u: Update, c):
    d = load()
    try:
        idx = int(c.args[0])-1
        rm = d["rdv"].pop(idx)
        save(d)
        await u.message.reply_text(f"Supprime: {rm['description']}")
    except: await u.message.reply_text("Numero invalide")

async def del_obj(u: Update, c):
    d = load()
    try:
        idx = int(c.args[0])-1
        rm = d["objectifs"].pop(idx)
        save(d)
        await u.message.reply_text(f"Supprime: {rm['description']}")
    except: await u.message.reply_text("Numero invalide")

async def handle(u: Update, c):
    if u.effective_chat.id != CID:
        await u.message.reply_text("Bot prive")
        return
    d = load()
    msg = u.message.text
    resp = await ai(msg, d)
    lines, clean = resp.split("\n"), []
    for l in lines:
        if l.strip().startswith("---ACTION:"):
            a = l.strip().replace("---ACTION:","").strip().split("|")
            if a[0]=="RDV" and len(a)>=4:
                d["rdv"].append({"date":a[1].strip(),"heure":a[2].strip(),"description":a[3].strip(),"rappel":False})
                save(d)
            elif a[0]=="OBJECTIF" and len(a)>=2:
                d["objectifs"].append({"description":a[1].strip(),"done":False,"date":datetime.now().strftime("%d/%m/%Y")})
                save(d)
            elif a[0]=="NOTE" and len(a)>=2:
                d["notes"].append({"text":a[1].strip(),"date":datetime.now().strftime("%d/%m/%Y %H:%M")})
                save(d)
        else: clean.append(l)
    await u.message.reply_text("\n".join(clean).strip())

async def morning(c):
    d = load()
    r = await ai(f"Briefing matinal! Date: {datetime.now().strftime('%A %d/%m/%Y')}. Liste les RDV du jour et objectifs.", d)
    await c.bot.send_message(chat_id=CID, text=f"Salut Hraf!\n\n{r}")

async def check(c):
    d = load()
    now = datetime.now()
    up = False
    for r in d["rdv"]:
        if r.get("rappel"): continue
        try:
            dt = datetime.strptime(f"{r['date']} {r['heure']}", "%d/%m/%Y %H:%M")
            diff = dt - now
            if timedelta(0) < diff <= timedelta(minutes=30):
                await c.bot.send_message(chat_id=CID, text=f"Rappel! Dans {int(diff.total_seconds()//60)} min: {r['description']}")
                r["rappel"] = True
                up = True
        except: continue
    if up: save(d)

async def evening(c):
    d = load()
    r = await ai(f"Recap du soir. Date: {datetime.now().strftime('%A %d/%m/%Y')}. Rappelle les objectifs en cours.", d)
    await c.bot.send_message(chat_id=CID, text=f"Recap\n\n{r}")

def main():
    app = Application.builder().token(TG).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rdv", add_rdv))
    app.add_handler(CommandHandler("objectif", add_obj))
    app.add_handler(CommandHandler("note", add_note))
    app.add_handler(CommandHandler("planning", planning))
    app.add_handler(CommandHandler("objectifs", objectifs))
    app.add_handler(CommandHandler("supprimer_rdv", del_rdv))
    app.add_handler(CommandHandler("supprimer_objectif", del_obj))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    jq = app.job_queue
    jq.run_daily(morning, time=datetime.strptime("07:00","%H:%M").time())
    jq.run_repeating(check, interval=900, first=10)
    jq.run_daily(evening, time=datetime.strptime("19:00","%H:%M").time())
    log.info("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
