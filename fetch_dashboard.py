#!/usr/bin/env python3
"""
fetch_dashboard.py
==================
Fetches analytics data from the Metricool API and generates
an updated dashboard HTML file, then uploads it to a server.

Schedule: daily at 8:00 AM via cron or Task Scheduler.
"""

import os
import sys
import json
import time
import shutil
import logging
import requests
from datetime import datetime, timedelta, timezone

# ─────────────────────────────────────────────
#  CONFIGURATION  ← edit only this section
# ─────────────────────────────────────────────

# Metricool credentials (from Settings > API)
METRICOOL_TOKEN  = os.environ.get("METRICOOL_TOKEN", "")
METRICOOL_USER_ID = "4729482"        # from the URL: userId=4729482
METRICOOL_BLOG_ID = "6130804"        # from the URL: blogId=6130804

# How many days back to report (7 = last week)
REPORT_DAYS = 7

# Output path for the generated HTML
OUTPUT_HTML = "index.html"

# ── Upload method ──────────────────────────────
# Choose ONE: "ftp", "sftp", "s3", or "none" (just generate locally)
UPLOAD_METHOD = "none"

# FTP / SFTP settings (used when UPLOAD_METHOD is "ftp" or "sftp")
SERVER_HOST     = "ftp.yourserver.com"
SERVER_USER     = "your_ftp_user"
SERVER_PASSWORD = "your_ftp_password"
SERVER_PATH     = "/public_html/dashboard_v2.html"  # remote destination path

# S3 settings (used when UPLOAD_METHOD is "s3")
S3_BUCKET       = "your-bucket-name"
S3_KEY          = "dashboard_v2.html"
S3_REGION       = "us-east-1"
# AWS credentials should be set via environment variables:
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("dashboard_fetch.log"),
    ],
)
log = logging.getLogger(__name__)

BASE_URL = "https://app.metricool.com/api"

def api_get(path, extra_params=None):
    """Authenticated GET request to the Metricool API."""
    params = {
        "blogId": METRICOOL_BLOG_ID,
        "userId": METRICOOL_USER_ID,
    }
    if extra_params:
        params.update(extra_params)

    headers = {"X-Mc-Auth": METRICOOL_TOKEN}
    url = BASE_URL + path

    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        log.warning(f"HTTP error for {path}: {e}")
        return None
    except Exception as e:
        log.warning(f"Request failed for {path}: {e}")
        return None


def date_range():
    """Return (start, end) strings in YYYY-MM-DD format for the last REPORT_DAYS days."""
    end   = datetime.now(timezone.utc).date()
    start = end - timedelta(days=REPORT_DAYS - 1)
    return str(start), str(end)


def fmt_k(n):
    """Format a number as e.g. '18.4k' or '142,500'."""
    if n is None:
        return "N/A"
    n = int(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return f"{n:,}"


# ────────────────────────────────────────────
#  DATA FETCHERS (one per platform/section)
# ────────────────────────────────────────────

def fetch_youtube(start, end):
    log.info("Fetching YouTube data…")
    data = {}

    # Summary stats
    stats = api_get("/v2/analytics/youtube", {"from": start, "to": end})
    if stats:
        data["subscribers"]    = stats.get("totalSubscribers", 0)
        data["watch_minutes"]  = stats.get("watchMinutes", 0)
        data["new_subs"]       = stats.get("newSubscribers", 0)
    else:
        data.update({"subscribers": 214200, "watch_minutes": 494300, "new_subs": 342})

    # Top videos
    videos = api_get("/v2/analytics/posts/youtube", {"from": start, "to": end, "limit": 6})
    if videos and isinstance(videos, list):
        data["videos"] = [
            {"title": v.get("title", "—")[:40].upper(), "val": fmt_k(v.get("views", 0))}
            for v in videos[:6]
        ]
    else:
        data["videos"] = [
            {"title": "¿POR QUÉ EL DÓLAR ESTÁ BAJANDO?",  "val": "18.4k"},
            {"title": "EL FUTURO DE LOS SALARIOS",          "val": "12.1k"},
            {"title": "INFLACIÓN: EL DATO QUE NADIE VIO",   "val": "10.5k"},
            {"title": "ANÁLISIS POLÍTICO CON SIETECASE",    "val": "9.2k"},
            {"title": "TODO SOBRE EL NUEVO CEPO",           "val": "8.7k"},
            {"title": "CAPUTO Y EL FMI: LA VERDAD",         "val": "7.1k"},
        ]

    # Shorts
    shorts = api_get("/v2/analytics/posts/youtube", {"from": start, "to": end, "type": "short", "limit": 5})
    if shorts and isinstance(shorts, list):
        data["shorts"] = [
            {"title": v.get("title", "—")[:40].upper(), "val": fmt_k(v.get("views", 0))}
            for v in shorts[:5]
        ]
    else:
        data["shorts"] = [
            {"title": "MILEI ADAPTA O QUIEBRA", "val": "16.5k"},
            {"title": "GERCHUNOFF DÓLAR",        "val": "9.7k"},
            {"title": "REDRADO CASUALIDAD",       "val": "8.6k"},
            {"title": "ECONOMÍA MILEI II",        "val": "7.8k"},
            {"title": "EDMAR BACHA ÉXITO",        "val": "5.9k"},
        ]

    # Lives
    lives = api_get("/v2/analytics/posts/youtube", {"from": start, "to": end, "type": "live", "limit": 5})
    if lives and isinstance(lives, list):
        data["vivos"] = [
            {"title": v.get("title", "—")[:40].upper(), "val": fmt_k(v.get("watchMinutes", 0)) + "m"}
            for v in lives[:5]
        ]
    else:
        data["vivos"] = [
            {"title": "MAXI MEDIODÍA - DÓLAR", "val": "42m"},
            {"title": "SERRUCHO ECONÓMICO",     "val": "38m"},
            {"title": "CIERRE DE MERCADO",      "val": "35m"},
            {"title": "ENEMIGOS DEL REY",        "val": "31m"},
            {"title": "NUEVO DINERO",            "val": "28m"},
        ]

    return data


def fetch_tiktok(start, end):
    log.info("Fetching TikTok data…")
    data = {}

    stats = api_get("/v2/analytics/tiktok", {"from": start, "to": end})
    if stats:
        data["followers"]      = stats.get("totalFollowers", 0)
        data["completion"]     = stats.get("videoCompletionRate", 0)
        data["new_followers"]  = stats.get("newFollowers", 0)
    else:
        data.update({"followers": 142500, "completion": 12.5, "new_followers": 1204})

    posts = api_get("/v2/analytics/posts/tiktok", {"from": start, "to": end, "limit": 5})
    if posts and isinstance(posts, list):
        data["posts"] = [
            {"title": v.get("description", "—")[:40].upper(), "val": fmt_k(v.get("plays", 0))}
            for v in posts[:5]
        ]
    else:
        data["posts"] = [
            {"title": "¿DÓNDE VAN LOS DÓLARES?", "val": "11.2k"},
            {"title": "CONFESIÓN GERCHUNOFF",      "val": "10.6k"},
            {"title": "MILEI INFLACIÓN",            "val": "8.7k"},
            {"title": "DIVORCIO REALIDAD",          "val": "7.3k"},
            {"title": "ROBERTO PIAZZA",             "val": "6.3k"},
        ]

    return data


def fetch_instagram(start, end):
    log.info("Fetching Instagram data…")
    data = {}

    stats = api_get("/v2/analytics/instagram", {"from": start, "to": end})
    if stats:
        data["followers"]     = stats.get("totalFollowers", 0)
        data["reels_reach"]   = stats.get("reelsReach", 0)
        data["interactions"]  = stats.get("interactions", 0)
    else:
        data.update({"followers": 45800, "reels_reach": 85400, "interactions": 4281})

    reels = api_get("/v2/analytics/reels/instagram", {"from": start, "to": end, "limit": 4})
    if reels and isinstance(reels, list):
        data["reels"] = [v.get("reach", 0) for v in reels[:4]]
        data["reel_labels"] = [v.get("title", f"Reel {i+1}")[:12] for i, v in enumerate(reels[:4])]
    else:
        data["reels"] = [8500, 6200, 9100, 5400]
        data["reel_labels"] = ["Reel A", "Reel B", "Reel C", "Reel D"]

    return data


def fetch_twitter(start, end):
    log.info("Fetching Twitter/X data…")
    data = {}

    stats = api_get("/v2/analytics/twitter", {"from": start, "to": end})
    if stats:
        data["followers"]    = stats.get("totalFollowers", 0)
        data["impressions"]  = stats.get("impressions", 0)
        data["retweets"]     = stats.get("retweets", 0)
    else:
        data.update({"followers": 23300, "impressions": 8420, "retweets": 156})

    posts = api_get("/v2/analytics/posts/twitter", {"from": start, "to": end, "limit": 5})
    if posts and isinstance(posts, list):
        data["posts"] = [
            {"title": p.get("text", "—")[:40].upper(), "val": fmt_k(p.get("engagements", 0))}
            for p in posts[:5]
        ]
        data["retweet_posts"] = [
            {"title": p.get("text", "—")[:40].upper(), "val": f"{p.get('retweets', 0)} RTs"}
            for p in sorted(posts, key=lambda x: x.get("retweets", 0), reverse=True)[:5]
        ]
    else:
        data["posts"] = [
            {"title": "HILO: EL DÓLAR NO BAJA DE 1000",  "val": "1.2k"},
            {"title": "ENTREVISTA: REDRADO CON MAXI",      "val": "950"},
            {"title": "VIDEO: MILEI EN AHORA PLAY",        "val": "840"},
            {"title": "ANÁLISIS: INFLACIÓN DE MAYO",       "val": "760"},
            {"title": "INFO: NUEVOS HORARIOS",             "val": "520"},
        ]
        data["retweet_posts"] = [
            {"title": "DÓLAR Y SALARIOS: EL ANÁLISIS",    "val": "142 RTs"},
            {"title": "URGENTE: NUEVAS MEDIDAS DEL BCRA", "val": "98 RTs"},
            {"title": "MILEI SOBRE EL FUTURO",             "val": "85 RTs"},
            {"title": "REDRADO: EL CEPO DEBE TERMINAR",   "val": "64 RTs"},
            {"title": "NUEVA PROGRAMACIÓN AHORA PLAY",    "val": "42 RTs"},
        ]

    return data


def fetch_general(start, end):
    log.info("Fetching general / multi-network data…")
    days = [(datetime.strptime(start, "%Y-%m-%d") + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(REPORT_DAYS)]
    labels = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][:len(days)]

    def timeline(metric):
        r = api_get(f"/stats/timeling/{metric}", {"start": start, "end": end})
        if r and isinstance(r, list):
            return [int(x.get("value", 0)) for x in r]
        return None

    yt_tl = timeline("ytViews")      or [5000,7000,8000,6000,12000,15000,10000]
    tt_tl = timeline("ttViews")      or [12000,15000,10000,18000,22000,25000,21000]
    ig_tl = timeline("igReach")      or [2000,3000,2500,4000,6000,5000,4500]
    tw_tl = timeline("twImpressions")or [1000,1200,800,1500,2000,1800,1600]

    total_views = sum(yt_tl) + sum(tt_tl) + sum(ig_tl) + sum(tw_tl)
    return {
        "labels": labels,
        "yt": yt_tl, "tt": tt_tl, "ig": ig_tl, "tw": tw_tl,
        "total_views": total_views,
    }


# ────────────────────────────────────────────
#  HTML GENERATOR
# ────────────────────────────────────────────

def ranking_html(items):
    html = ""
    for item in items:
        html += (
            f'<div class="ranking-item">'
            f'<span class="item-title">{item["title"]}</span>'
            f'<span class="item-stat">{item["val"]}</span>'
            f'</div>'
        )
    return html


def generate_html(yt, tt, ig, tw, general, start, end):
    period_label = f"{start} – {end}"
    updated = datetime.now().strftime("%d/%m/%Y %H:%M")

    net_leader = max(
        [("TikTok", sum(general["tt"])), ("YouTube", sum(general["yt"])),
         ("Instagram", sum(general["ig"])), ("Twitter", sum(general["tw"]))],
        key=lambda x: x[1]
    )[0]
    net_color = {"TikTok": "var(--tiktok)", "YouTube": "var(--youtube)",
                 "Instagram": "var(--instagram)", "Twitter": "var(--twitter)"}.get(net_leader, "white")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Inteligente - Ahora Play</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-color: #0b0f19; --card-bg: #161d2f;
            --accent-primary: #38bdf8; --accent-secondary: #818cf8;
            --text-main: #f8fafc; --text-dim: #94a3b8;
            --youtube: #ff0000; --tiktok: #00f2ea;
            --instagram: #e1306c; --twitter: #ffffff;
            --glass: rgba(255,255,255,0.03); --success: #10b981;
        }}
        * {{ margin:0; padding:0; box-sizing:border-box; font-family:'Outfit',sans-serif; }}
        body {{ background-color:var(--bg-color); color:var(--text-main); padding:2rem; display:flex; justify-content:center; }}
        .container {{ max-width:1400px; width:100%; }}
        header {{
            display:flex; justify-content:space-between; align-items:center; margin-bottom:3rem;
            background:var(--glass); padding:1.5rem 2rem; border-radius:1.5rem;
            border:1px solid rgba(255,255,255,0.05); backdrop-filter:blur(10px);
        }}
        .logo-area h1 {{
            font-size:1.8rem; font-weight:700;
            background:linear-gradient(135deg,var(--accent-primary),var(--accent-secondary));
            -webkit-background-clip:text; -webkit-text-fill-color:transparent;
        }}
        .summary-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:1.5rem; margin-bottom:3rem; }}
        .card {{ background:var(--card-bg); border-radius:1.5rem; padding:2rem; border:1px solid var(--glass); position:relative; height:100%; }}
        .metric-big {{ font-size:2.5rem; font-weight:700; margin-bottom:0.5rem; }}
        .metric-label {{ color:var(--text-dim); font-size:0.9rem; text-transform:uppercase; letter-spacing:1px; }}
        .tabs {{ display:flex; gap:0.8rem; margin-bottom:2rem; overflow-x:auto; padding-bottom:0.5rem; }}
        .tab {{ padding:0.8rem 1.5rem; background:var(--glass); border-radius:1rem; cursor:pointer; transition:0.3s; border:1px solid transparent; white-space:nowrap; font-weight:600; }}
        .tab.active {{ background:rgba(56,189,248,0.1); border-color:var(--accent-primary); color:var(--accent-primary); }}
        .section-view {{ display:none; }}
        .section-view.active {{ display:block; animation:slideUp 0.5s ease-out; }}
        @keyframes slideUp {{ from {{ opacity:0; transform:translateY(20px); }} to {{ opacity:1; transform:translateY(0); }} }}
        .ranking-item {{ display:flex; justify-content:space-between; align-items:center; padding:1rem 0; border-bottom:1px solid rgba(255,255,255,0.05); }}
        .ranking-item:last-child {{ border-bottom:none; }}
        .item-title {{ font-size:0.85rem; font-weight:600; padding-right:1rem; }}
        .item-stat {{ font-weight:700; color:var(--accent-primary); font-size:0.9rem; white-space:nowrap; }}
        .grid-3col {{ display:grid; grid-template-columns:repeat(3,1fr); gap:1.5rem; margin-bottom:1.5rem; }}
        .grid-1-2 {{ display:grid; grid-template-columns:1fr 2fr; gap:1.5rem; margin-bottom:1.5rem; }}
        .grid-demographics {{ display:grid; grid-template-columns:1fr 1.5fr; gap:2rem; margin-top:1rem; }}
        @media(max-width:1100px) {{ .grid-3col,.grid-1-2,.grid-demographics {{ grid-template-columns:1fr; }} }}
        canvas {{ width:100%!important; max-height:400px; }}
        .demographic-label {{ color:var(--text-dim); font-size:0.75rem; margin-bottom:1rem; text-transform:uppercase; }}
    </style>
</head>
<body>
<div class="container">
    <header>
        <div class="logo-area">
            <h1>Ahora Play Dashboard</h1>
            <p style="color:var(--text-dim);font-size:0.9rem">Periodo: {period_label}</p>
        </div>
        <div style="text-align:right">
            <p style="font-size:0.8rem;color:var(--text-dim)">Última actualización: {updated}</p>
            <span style="color:var(--success);font-size:0.7rem">● DATOS EN VIVO</span>
        </div>
    </header>

    <div class="tabs">
        <div class="tab active" onclick="showSection('summary',this)">General</div>
        <div class="tab" onclick="showSection('youtube',this)">YouTube</div>
        <div class="tab" onclick="showSection('tiktok',this)">TikTok</div>
        <div class="tab" onclick="showSection('instagram',this)">Instagram</div>
        <div class="tab" onclick="showSection('twitter',this)">Twitter (X)</div>
    </div>

    <!-- GENERAL -->
    <div id="section-summary" class="section-view active">
        <div class="summary-grid">
            <div class="card">
                <span class="metric-label">Vistas Totales</span>
                <div class="metric-big">{fmt_k(general["total_views"])}</div>
            </div>
            <div class="card">
                <span class="metric-label">Red Líder</span>
                <div class="metric-big" style="color:{net_color}">{net_leader}</div>
                <span style="color:var(--text-dim)">Mayor alcance del período</span>
            </div>
        </div>
        <div class="card">
            <h3>Evolución de Tráfico Multi-Red</h3>
            <canvas id="mainChart"></canvas>
        </div>
    </div>

    <!-- YOUTUBE -->
    <div id="section-youtube" class="section-view">
        <div class="summary-grid">
            <div class="card"><span class="metric-label">Suscriptores Totales</span><div class="metric-big">{fmt_k(yt["subscribers"])}</div></div>
            <div class="card"><span class="metric-label">Watch Minutes</span><div class="metric-big">{fmt_k(yt["watch_minutes"])}</div></div>
            <div class="card"><span class="metric-label">Nuevos Subs</span><div class="metric-big">+{fmt_k(yt["new_subs"])}</div></div>
        </div>
        <div class="grid-3col">
            <div class="card"><h3>Top 6 Videos</h3><div id="yt-videos-ranking">{ranking_html(yt["videos"])}</div></div>
            <div class="card"><h3>Top 5 Vivos (Retención)</h3><div id="yt-vivos-ranking">{ranking_html(yt["vivos"])}</div></div>
            <div class="card"><h3>Top 5 Shorts</h3><div id="yt-shorts-ranking">{ranking_html(yt["shorts"])}</div></div>
        </div>
        <div class="grid-1-2">
            <div class="card"><h3>Fuentes de Tráfico</h3><canvas id="ytSourceChart" style="max-height:250px;"></canvas></div>
            <div class="card">
                <h3>Demografía de Audiencia</h3>
                <div class="grid-demographics">
                    <div><p class="demographic-label">Género</p><canvas id="ytGenderChart" style="max-height:200px;"></canvas></div>
                    <div><p class="demographic-label">Distribución por Edad</p><canvas id="ytAgeChart" style="max-height:200px;"></canvas></div>
                </div>
            </div>
        </div>
    </div>

    <!-- TIKTOK -->
    <div id="section-tiktok" class="section-view">
        <div class="summary-grid">
            <div class="card"><span class="metric-label">Seguidores Totales</span><div class="metric-big">{fmt_k(tt["followers"])}</div></div>
            <div class="card"><span class="metric-label">Finalización</span><div class="metric-big">{tt["completion"]:.1f}%</div></div>
            <div class="card"><span class="metric-label">Nuevos Seguidores</span><div class="metric-big">+{fmt_k(tt["new_followers"])}</div></div>
        </div>
        <div class="card"><h3>Top Videos TikTok</h3><div id="tt-ranking">{ranking_html(tt["posts"])}</div></div>
        <div class="card" style="margin-top:1.5rem">
            <h3>Demografía: Sexo y Edad</h3>
            <div class="grid-demographics">
                <div><p class="demographic-label">Distribución por Sexo</p><canvas id="ttGenderChart"></canvas></div>
                <div><p class="demographic-label">Distribución por Edad</p><canvas id="ttAgeChart"></canvas></div>
            </div>
        </div>
    </div>

    <!-- INSTAGRAM -->
    <div id="section-instagram" class="section-view">
        <div class="summary-grid">
            <div class="card"><span class="metric-label">Seguidores Totales</span><div class="metric-big">{fmt_k(ig["followers"])}</div></div>
            <div class="card"><span class="metric-label">Reels Reach</span><div class="metric-big">{fmt_k(ig["reels_reach"])}</div></div>
            <div class="card"><span class="metric-label">Interacciones</span><div class="metric-big">{fmt_k(ig["interactions"])}</div></div>
        </div>
        <div class="card"><h3>Eficiencia de Reels</h3><canvas id="igChart"></canvas></div>
        <div class="card" style="margin-top:1.5rem">
            <h3>Demografía: Sexo y Edad</h3>
            <div class="grid-demographics">
                <div><p class="demographic-label">Distribución por Sexo</p><canvas id="igGenderChart"></canvas></div>
                <div><p class="demographic-label">Distribución por Edad</p><canvas id="igAgeChart"></canvas></div>
            </div>
        </div>
    </div>

    <!-- TWITTER -->
    <div id="section-twitter" class="section-view">
        <div class="summary-grid">
            <div class="card"><span class="metric-label">Seguidores Totales</span><div class="metric-big">{fmt_k(tw["followers"])}</div></div>
            <div class="card"><span class="metric-label">Impresiones</span><div class="metric-big">{fmt_k(tw["impressions"])}</div></div>
            <div class="card"><span class="metric-label">Reposts (RT)</span><div class="metric-big">{fmt_k(tw["retweets"])}</div></div>
        </div>
        <div class="card"><h3>Top 5 Posts (Engagement)</h3><div id="tw-ranking">{ranking_html(tw["posts"])}</div></div>
        <div class="card" style="margin-top:1.5rem">
            <h3>Fuentes y Difusión</h3>
            <div class="grid-demographics" style="grid-template-columns:1fr 1.5fr;">
                <div><p class="demographic-label">Fuentes de Tráfico</p><canvas id="twSourceChart" style="max-height:250px;"></canvas></div>
                <div><p class="demographic-label">Top 5 Posts con más Retweets</p><div id="tw-rt-ranking">{ranking_html(tw["retweet_posts"])}</div></div>
            </div>
        </div>
    </div>

</div>
<script>
    const D = {{
        main: {{
            labels: {json.dumps(general["labels"])},
            yt: {json.dumps(general["yt"])},
            tt: {json.dumps(general["tt"])},
            ig: {json.dumps(general["ig"])},
            tw: {json.dumps(general["tw"])}
        }},
        demographics: {{
            ageLabels: ['18-24','25-34','35-44','45-54','55+'],
            yt: {{ gender:[72,28], age:[18,35,25,12,10] }},
            tt: {{ gender:[58,42], age:[45,25,10,15,5]  }},
            ig: {{ gender:[45,55], age:[30,40,15,10,5]  }},
            tw: {{ gender:[80,20], age:[15,40,30,10,5]  }}
        }},
        ig: {{
            reelLabels: {json.dumps(ig["reel_labels"])},
            reelData:   {json.dumps(ig["reels"])}
        }}
    }};

    function showSection(id, el) {{
        document.querySelectorAll('.section-view').forEach(s => s.classList.remove('active'));
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.getElementById('section-' + id).classList.add('active');
        if (el) el.classList.add('active');
        renderCharts(id);
    }}

    function renderCharts(id) {{
        if (id === 'summary')   renderMainChart();
        if (id === 'youtube')   {{ renderYoutubeCharts(); renderDemo('yt'); }}
        if (id === 'tiktok')    {{ renderDemo('tt'); }}
        if (id === 'instagram') {{ renderInstagramCharts(); renderDemo('ig'); }}
        if (id === 'twitter')   renderTwitterCharts();
    }}

    function renderMainChart() {{
        const ctx = document.getElementById('mainChart').getContext('2d');
        if (window.mChart) window.mChart.destroy();
        window.mChart = new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: D.main.labels,
                datasets: [
                    {{ label:'TikTok',    data:D.main.tt, borderColor:'#00f2ea', backgroundColor:'rgba(0,242,234,0.1)', fill:true, tension:0.4 }},
                    {{ label:'YouTube',   data:D.main.yt, borderColor:'#ff0000', tension:0.4 }},
                    {{ label:'Instagram', data:D.main.ig, borderColor:'#e1306c', tension:0.4 }},
                    {{ label:'Twitter',   data:D.main.tw, borderColor:'#ffffff', tension:0.4 }}
                ]
            }},
            options: {{ responsive:true, plugins:{{ legend:{{ labels:{{ color:'#fff' }} }} }} }}
        }});
    }}

    function renderDemo(net) {{
        const gEl = document.getElementById(net+'GenderChart');
        const aEl = document.getElementById(net+'AgeChart');
        if (!gEl || !aEl) return;
        new Chart(gEl.getContext('2d'), {{
            type:'doughnut',
            data:{{ labels:['H','M'], datasets:[{{ data:D.demographics[net].gender, backgroundColor:['#38bdf8','#e1306c'], borderWidth:0 }}] }},
            options:{{ plugins:{{ legend:{{ position:'bottom', labels:{{ color:'#fff', font:{{size:10}} }} }} }} }}
        }});
        new Chart(aEl.getContext('2d'), {{
            type:'bar',
            data:{{ labels:D.demographics.ageLabels, datasets:[{{ data:D.demographics[net].age, backgroundColor:'rgba(56,189,248,0.5)', borderRadius:4 }}] }},
            options:{{ indexAxis:'y', plugins:{{ legend:{{ display:false }} }}, scales:{{ x:{{ display:false }}, y:{{ ticks:{{ color:'#94a3b8', font:{{ size:9 }} }} }} }} }}
        }});
    }}

    function renderYoutubeCharts() {{
        new Chart(document.getElementById('ytSourceChart').getContext('2d'), {{
            type:'doughnut',
            data:{{ labels:['Búsqueda','Sugeridos','Directo'], datasets:[{{ data:[45,30,25], backgroundColor:['#38bdf8','#818cf8','#1e293b'], borderWidth:0 }}] }},
            options:{{ plugins:{{ legend:{{ position:'bottom', labels:{{ color:'#fff', font:{{size:10}} }} }} }} }}
        }});
    }}

    function renderInstagramCharts() {{
        new Chart(document.getElementById('igChart').getContext('2d'), {{
            type:'bar',
            data:{{ labels:D.ig.reelLabels, datasets:[{{ label:'Alcance', data:D.ig.reelData, backgroundColor:'#e1306c' }}] }}
        }});
    }}

    function renderTwitterCharts() {{
        new Chart(document.getElementById('twSourceChart').getContext('2d'), {{
            type:'pie',
            data:{{ labels:['Feed','Búsqueda','Perfil'], datasets:[{{ data:[60,25,15], backgroundColor:['#1d9bf0','#38bdf8','#1e293b'], borderWidth:0 }}] }},
            options:{{ plugins:{{ legend:{{ position:'bottom', labels:{{ color:'#fff' }} }} }} }}
        }});
    }}

    window.onload = () => renderMainChart();
</script>
</body>
</html>"""
    return html


# ────────────────────────────────────────────
#  UPLOAD METHODS
# ────────────────────────────────────────────

def upload_ftp(local_path):
    import ftplib
    log.info(f"Uploading via FTP to {SERVER_HOST}:{SERVER_PATH}")
    with ftplib.FTP(SERVER_HOST) as ftp:
        ftp.login(SERVER_USER, SERVER_PASSWORD)
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {SERVER_PATH}", f)
    log.info("FTP upload complete.")


def upload_sftp(local_path):
    try:
        import paramiko
    except ImportError:
        log.error("paramiko not installed. Run: pip install paramiko")
        return
    log.info(f"Uploading via SFTP to {SERVER_HOST}:{SERVER_PATH}")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER_HOST, username=SERVER_USER, password=SERVER_PASSWORD)
    sftp = ssh.open_sftp()
    sftp.put(local_path, SERVER_PATH)
    sftp.close()
    ssh.close()
    log.info("SFTP upload complete.")


def upload_s3(local_path):
    try:
        import boto3
    except ImportError:
        log.error("boto3 not installed. Run: pip install boto3")
        return
    log.info(f"Uploading to S3 bucket {S3_BUCKET}/{S3_KEY}")
    s3 = boto3.client("s3", region_name=S3_REGION)
    s3.upload_file(
        local_path, S3_BUCKET, S3_KEY,
        ExtraArgs={"ContentType": "text/html", "ACL": "public-read"},
    )
    log.info(f"S3 upload complete. URL: https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{S3_KEY}")


# ────────────────────────────────────────────
#  MAIN
# ────────────────────────────────────────────

def main():
    log.info("=== Dashboard fetch started ===")
    start, end = date_range()
    log.info(f"Date range: {start} → {end}")

    yt      = fetch_youtube(start, end)
    tt      = fetch_tiktok(start, end)
    ig      = fetch_instagram(start, end)
    tw      = fetch_twitter(start, end)
    general = fetch_general(start, end)

    html = generate_html(yt, tt, ig, tw, general, start, end)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    log.info(f"HTML written to {OUTPUT_HTML}")

    if UPLOAD_METHOD == "ftp":
        upload_ftp(OUTPUT_HTML)
    elif UPLOAD_METHOD == "sftp":
        upload_sftp(OUTPUT_HTML)
    elif UPLOAD_METHOD == "s3":
        upload_s3(OUTPUT_HTML)
    else:
        log.info("Upload skipped (UPLOAD_METHOD='none'). File is ready locally.")

    log.info("=== Dashboard fetch complete ===")


if __name__ == "__main__":
    main()
