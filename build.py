"""Build index.html from the Sleeper export + template.html.

Usage: python3 build.py   (re-run after dropping in a fresh sleeper_league_*.json)
Only uses this season's export: no prior-league data is read.
"""
import collections, glob, json, os

SRC = sorted(glob.glob("sleeper_league_*.json"))[-1]
d = json.load(open(SRC))

picks = d["draft_details"][0]["picks"]
info = {p["player_id"]: dict(name=p["metadata"]["first_name"] + " " + p["metadata"]["last_name"],
                             pos=p["metadata"]["position"], nfl=p["metadata"]["team"],
                             pick=p["pick_no"], rnd=p["round"], by=p["roster_id"],
                             inj=p["metadata"].get("injury_status") or "")
        for p in picks}
users = {u["user_id"]: u for u in d["users"]}
# Completed weeks = games on the standings (the export can hold a partial in-progress week).
last_week = max(r["settings"]["wins"] + r["settings"]["losses"] + r["settings"]["ties"] for r in d["rosters"])
weeks = [str(w) for w in range(1, last_week + 1)]
reg_weeks = d["league"]["settings"]["playoff_week_start"] - 1


# Optional full player list (from Sleeper's /players/nfl) to name undrafted waiver pickups.
PLAYERS = json.load(open("sleeper_players_nfl.json")) if os.path.exists("sleeper_players_nfl.json") else {}


def name(pid):
    if pid in info:
        return info[pid]["name"]
    if pid.isalpha():
        return pid + " D/ST"
    if pid in PLAYERS and PLAYERS[pid].get("name"):
        return PLAYERS[pid]["name"]
    return None


def pos(pid):
    if pid.isalpha():
        return "DEF"
    if pid in info:
        return info[pid]["pos"]
    return PLAYERS.get(pid, {}).get("pos")


teams = {}
for r in d["rosters"]:
    u = users[r["owner_id"]]
    s = r["settings"]
    teams[r["roster_id"]] = dict(
        rid=r["roster_id"], name=u["metadata"].get("team_name"), owner=u["display_name"],
        w=s["wins"], l=s["losses"], pf=round(s["fpts"] + s["fpts_decimal"] / 100, 2),
        pa=round(s["fpts_against"] + s["fpts_against_decimal"] / 100, 2),
        maxpf=round(s["ppts"] + s["ppts_decimal"] / 100, 2), faab=s["waiver_budget_used"],
        nicks=sum(1 for k in r["metadata"] if k.startswith("p_nick_")),
        questionable=sum(1 for p in r["players"] if p in info and info[p]["inj"]),
        ir=[name(p) for p in (r["reserve"] or []) if name(p)],
        weekly=[], res=[], bench=0.0, allw=0, alll=0, adds=0, trades=0, failed=0, tradenet=0.0)

# matchups
games, perfs, blunders, blown = [], [], [], []
slots = [s for s in d["league"]["roster_positions"] if s != "BN"]
elig = {"QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "FLEX": {"RB", "WR", "TE"}, "K": {"K"}, "DEF": {"DEF"}}


def optimal(m):
    """Best legal lineup from players with known positions (a lower bound)."""
    pts = m["players_points"]
    used, tot = set(), 0.0
    fixed = [i for i, k in enumerate(m["starters"]) if pos(k) is None]
    for i in fixed:
        tot += pts.get(m["starters"][i], 0)
        used.add(m["starters"][i])
    for i in sorted([i for i in range(len(slots)) if i not in fixed], key=lambda i: slots[i] == "FLEX"):
        c = [k for k in pts if k not in used and pos(k) in elig[slots[i]]]
        if c:
            b = max(c, key=lambda k: pts[k])
            used.add(b)
            tot += pts[b]
    return tot


on_roster = collections.defaultdict(dict)
for w in weeks:
    wk = int(w)
    ms = collections.defaultdict(list)
    for m in d["matchups"][w]:
        ms[m["matchup_id"]].append(m)
    scores = [m["points"] for m in d["matchups"][w]]
    for m in d["matchups"][w]:
        t = teams[m["roster_id"]]
        t["weekly"].append(m["points"])
        t["allw"] += sum(1 for x in scores if x < m["points"])
        t["alll"] += sum(1 for x in scores if x > m["points"])
        for k, v in m["players_points"].items():
            on_roster[k][wk] = (m["roster_id"], v)
            if k in m["starters"]:
                continue
            t["bench"] += v
            if name(k):
                blunders.append(dict(player=name(k), pts=v, wk=wk, rid=m["roster_id"]))
        for pid, p in zip(m["starters"], m["starters_points"]):
            if name(pid):
                perfs.append(dict(player=name(pid), pts=p, wk=wk, rid=m["roster_id"]))
    for a, b in ms.values():
        win, lose = (a, b) if a["points"] > b["points"] else (b, a)
        teams[win["roster_id"]]["res"].append("W")
        teams[lose["roster_id"]]["res"].append("L")
        games.append(dict(wk=wk, w=win["roster_id"], l=lose["roster_id"], ws=win["points"], ls=lose["points"],
                          margin=round(win["points"] - lose["points"], 2)))
        o = optimal(lose)
        if o > win["points"]:
            blown.append(dict(wk=wk, rid=lose["roster_id"], opp=win["roster_id"], score=lose["points"],
                              opps=win["points"], best=round(o, 2)))

# transactions + trade ledger (points each acquired player scored for the new team)
trade_log = []
for leg, tx in d["transactions"].items():
    for t in tx:
        if t["status"] != "complete":
            teams[t["roster_ids"][0]]["failed"] += 1
            continue
        if t["type"] == "trade":
            for rid in t["roster_ids"]:
                teams[rid]["trades"] += 1
            for k, rid in (t["adds"] or {}).items():
                frm = t["drops"][k]
                got = sum(v for wk, (r, v) in on_roster[k].items() if r == rid and wk >= int(leg))
                teams[rid]["tradenet"] += got
                teams[frm]["tradenet"] -= got
                trade_log.append(dict(player=name(k) or "a waiver mystery man", to=rid, frm=frm, pts=round(got, 2), leg=int(leg)))
        else:
            teams[t["roster_ids"][0]]["adds"] += len(t["adds"] or {})

remaining = reg_weeks - last_week
for t in teams.values():
    t["bench"] = round(t["bench"], 2)
    t["tradenet"] = round(t["tradenet"], 1)
    t["eff"] = round(100 * t["pf"] / t["maxpf"], 1)
    t["xw"] = round(t["allw"] / (len(teams) - 1), 2)
    games_played = len(t["weekly"])
    t["proj"] = round(t["w"] + remaining * t["allw"] / ((len(teams) - 1) * games_played), 1)

pts_by = collections.Counter()
for k, wks in on_roster.items():
    for r, v in wks.values():
        pts_by[k] += v
draft = [dict(name=v["name"], pos=v["pos"], pick=v["pick"], rnd=v["rnd"], by=v["by"], pts=round(pts_by.get(k, 0), 2))
         for k, v in info.items()]

data = dict(
    league=dict(name=d["league"]["name"], season=d["league"]["season"], week=last_week, regWeeks=reg_weeks,
                playoffTeams=d["league"]["settings"]["playoff_teams"]),
    teams=teams, games=games, draft=draft, blown=blown, trades=trade_log,
    perfs=sorted(perfs, key=lambda p: -p["pts"])[:5],
    blunders=sorted(blunders, key=lambda p: -p["pts"])[:8],
)
# Fallback rankings baked into the page (the claude.ai version can override them from its database).
if os.path.exists("picks.json"):
    data["picks"] = json.load(open("picks.json"))

html = open("template.html").read().replace("__DATA__", json.dumps(data, separators=(",", ":"), ensure_ascii=False))

# claude.ai artifact: page content only (the artifact host adds the document skeleton).
open("index.html", "w").write(html)

# GitHub Pages: a complete standalone document in docs/.
split = html.index('<div class="topnav">')
head, body = html[:split], html[split:]
os.makedirs("docs", exist_ok=True)
open("docs/index.html", "w").write(
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
    f'<meta name="description" content="{d["league"]["name"]}: stats, luck, draft grades, nicknames and roasts.">\n'
    "<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}"
    "body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n"
    + head + "</head>\n<body>\n" + body + "\n</body>\n</html>\n")
print(f"Built index.html and docs/index.html from {SRC} through week {last_week}")
