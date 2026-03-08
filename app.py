import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

# ── PAGE CONFIG ───────────────────────────────────────────────
st.set_page_config(
    page_title="Dashboard Lab RS 2026",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.block-container { padding: 1.2rem 2rem 2rem 2rem; max-width: 1400px; }
#MainMenu, footer, header { visibility: hidden; }
.kpi {
    background: white; border-radius: 14px; padding: 18px 20px;
    border: 1px solid #dde4ee;
    box-shadow: 0 1px 3px rgba(26,37,53,.06), 0 4px 12px rgba(26,37,53,.06);
    border-top: 3px solid var(--c, #0a9e87);
}
.kpi-lbl { font-size: 10px; font-weight: 600; text-transform: uppercase;
    letter-spacing:.1em; color:#7a8fa8; font-family:'DM Mono',monospace; }
.kpi-val { font-size: 24px; font-weight: 700; color: var(--c, #0a9e87);
    line-height:1.1; margin: 5px 0 3px; }
.kpi-sub { font-size: 11px; color: #7a8fa8; }
.unit-card {
    background:white; border-radius:12px; padding:16px;
    border:1px solid #dde4ee; text-align:center;
    box-shadow:0 1px 3px rgba(26,37,53,.06);
}
</style>
""", unsafe_allow_html=True)

# ── HELPERS ───────────────────────────────────────────────────
MONTH_ORDER = ['JAN','FEB','MAR','APR','MEI','JUN','JUL','AGT','SEP','OKT','NOV','DES']
MONTH_MAP_ID = {1:'JAN',2:'FEB',3:'MAR',4:'APR',5:'MEI',6:'JUN',
                7:'JUL',8:'AGT',9:'SEP',10:'OKT',11:'NOV',12:'DES'}
OMZET_MONTH_NAMES = {
    'JANUARI':'JAN','FEBRUARI':'FEB','MARET':'MAR','APRIL':'APR',
    'MEI':'MEI','JUNI':'JUN','JULI':'JUL','AGUSTUS':'AGT',
    'SEPTEMBER':'SEP','OKTOBER':'OKT','NOVEMBER':'NOV','DESEMBER':'DES'
}

def fmt_rp(v):
    if v >= 1_000_000_000: return f"Rp {v/1_000_000_000:.2f}M"
    if v >= 1_000_000:     return f"Rp {v/1_000_000:.1f}jt"
    return f"Rp {int(v):,}"

def badge_color(pct):
    if pct >= 150: return "#8b5cf6"
    if pct >= 100: return "#0a9e87"
    if pct >= 80:  return "#f59e0b"
    return "#f04e37"

def bar_colors(pcts):
    return ["rgba(10,158,135,.75)" if p >= 100 else "rgba(59,130,246,.6)" for p in pcts]

GRID = "rgba(26,37,53,.05)"
TT   = dict(bgcolor="#fff", font_color="#1a2535", bordercolor="#dde4ee", borderwidth=1)

# ── DATA LOADER ───────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data():
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly",
                    "https://www.googleapis.com/auth/drive.readonly"]
        )
        client = gspread.authorize(creds)
        ss = client.open_by_key(st.secrets["spreadsheet_id"])

        # ── OMZET SHEET ───────────────────────────────────────
        # Format: setiap bulan punya header baris (nama bulan),
        # lalu baris data tgl 1..N, lalu baris TOTAL
        # Kolom: tgl | petrokimia | perusahaan | bri | asuransi |
        #        prokMurni | prokBpjs | bpjsKes | bpjsTK | umum | total | target
        ws_o = ss.worksheet("OMZET 2026")
        raw_o = ws_o.get_all_values()
        omzet = {}
        cur = None
        for row in raw_o:
            v = str(row[0]).strip().upper()
            if v in OMZET_MONTH_NAMES:
                cur = OMZET_MONTH_NAMES[v]
                omzet[cur] = []
                continue
            if cur and v.replace('.','',1).isdigit():
                try:
                    tgl = int(float(v))
                    def n(x): return float(str(x).replace(',','').replace(' ','') or 0)
                    total  = n(row[10]) if len(row) > 10 else 0
                    target = n(row[11]) if len(row) > 11 else 0
                    omzet[cur].append({
                        'd': tgl,
                        'petrokimia': n(row[1]),  'perusahaan': n(row[2]),
                        'bri':        n(row[3]),  'asuransi':   n(row[4]),
                        'prokMurni':  n(row[5]),  'prokBpjs':   n(row[6]),
                        'bpjsKes':   n(row[7]),  'bpjsTK':     n(row[8]),
                        'umum':       n(row[9]),
                        'total': total, 'target': target,
                        'pct': round(total/target*100) if target > 0 else 0,
                    })
                except: pass

        # ── KUNJUNGAN SHEET ───────────────────────────────────
        # Format: header baris = tanggal bulan (2026-01-01 dst) + 2 baris sub-header
        # Kolom 0 = tgl
        # RJ  cols 1-9  : petro,perus,bri,asuransi,prokMurni,prokBpjs,bpjsKes,bpjsTK,tunai
        # RI  cols 10-18: petro,perus,bri,asuransi,prokMurni,prokBpjs,bpjsKes,bpjsTK,umum
        # IGD cols 19-27: petro,perus,bri,asuransi,prokMurni,prokBpjs,bpjsKes,bpjsTK,umum
        # MCU cols 28-31: petro,perus,asuransi,umum
        # 32=total, 33=target, 34=capaian
        ws_k = ss.worksheet("KUNJUNGAN 2026")
        raw_k = ws_k.get_all_values()
        kunjungan = {}
        cur_k = None
        skip = 0
        for row in raw_k:
            v = str(row[0]).strip()
            # Detect month header (date string or SEPT 2026)
            is_month_hdr = False
            month_label = None
            if '2026' in v:
                try:
                    import re
                    if re.match(r'\d{4}-\d{2}-\d{2}', v):
                        m = int(v[5:7])
                        month_label = MONTH_MAP_ID[m]
                        is_month_hdr = True
                    elif 'SEPT' in v.upper():
                        month_label = 'SEP'
                        is_month_hdr = True
                except: pass
            if is_month_hdr:
                cur_k = month_label
                kunjungan[cur_k] = []
                skip = 2  # skip 2 sub-header rows
                continue
            if skip > 0:
                skip -= 1
                continue
            if cur_k and v.replace('.','',1).isdigit() and v != '':
                try:
                    def ni(x): return int(float(str(x).replace(',','').replace(' ','') or 0))
                    tgl = ni(row[0])
                    rj_total  = sum(ni(row[i]) for i in range(1,10)  if i < len(row))
                    ri_total  = sum(ni(row[i]) for i in range(10,19) if i < len(row))
                    igd_total = sum(ni(row[i]) for i in range(19,28) if i < len(row))
                    mcu_total = sum(ni(row[i]) for i in range(28,32) if i < len(row))
                    total  = ni(row[32]) if len(row) > 32 else rj_total+ri_total+igd_total+mcu_total
                    target = ni(row[33]) if len(row) > 33 else 0
                    kunjungan[cur_k].append({
                        'd': tgl,
                        'rjTotal': rj_total, 'riTotal': ri_total,
                        'igdTotal': igd_total, 'mcuTotal': mcu_total,
                        'total': total, 'target': target,
                        'pct': round(total/target*100) if target > 0 else 0,
                    })
                except: pass

        # ── MCU SHEET ─────────────────────────────────────────
        # Format: row 0 = kosong, row 1 = header (Tanggal | JAN | FEB | ... | DES)
        # row 2..32 = tgl 1..31, row 33 = JUMLAH
        ws_m = ss.worksheet("OMZET MCU 2026")
        raw_m = ws_m.get_all_values()
        mcu = {}
        months_row = []
        for i, row in enumerate(raw_m):
            if row[0].strip() == 'Tanggal':
                months_row = row[1:]  # ['JAN','FEB',...]
                continue
            if months_row and row[0].strip().replace('.','',1).isdigit():
                tgl = int(float(row[0]))
                for j, mon in enumerate(months_row):
                    mon = mon.strip().upper()
                    if not mon: continue
                    if mon not in mcu: mcu[mon] = []
                    val_str = row[j+1].replace(',','').replace(' ','') if j+1 < len(row) else ''
                    val = float(val_str) if val_str and val_str not in ['-',''] else 0
                    mcu[mon].append({'d': tgl, 'omzet': val})

        return omzet, kunjungan, mcu, True

    except Exception as e:
        st.error(f"❌ Gagal konek ke Google Sheets: {e}")
        return {}, {}, {}, False


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    # Header
    st.markdown("""
    <div style="background:white;border-radius:14px;padding:16px 22px;
        border:1px solid #dde4ee;margin-bottom:18px;
        display:flex;align-items:center;gap:14px;">
      <div style="width:38px;height:38px;background:linear-gradient(135deg,#0a9e87,#06b6d4);
          border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:20px;">🔬</div>
      <div>
        <div style="font-size:16px;font-weight:700;color:#1a2535;">Dashboard Lab RS 2026</div>
        <div style="font-size:10px;color:#7a8fa8;font-family:'DM Mono',monospace;">REALTIME · GOOGLE SHEETS</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Memuat data..."):
        omzet, kunjungan, mcu, ok = load_data()
    if not ok:
        st.stop()

    # Available months dari semua sheet
    all_months = sorted(
        set(list(omzet.keys()) + list(kunjungan.keys()) + list(mcu.keys())),
        key=lambda m: MONTH_ORDER.index(m) if m in MONTH_ORDER else 99
    )
    if not all_months:
        st.warning("Belum ada data."); return

    # Controls
    c1, c2, c3 = st.columns([3, 2, 1])
    with c1:
        tab = st.radio("", ["💰 Omzet", "👥 Kunjungan", "🩺 MCU"],
                       horizontal=True, label_visibility="collapsed")
    with c2:
        month = st.selectbox("", all_months,
                             index=len(all_months)-1,
                             label_visibility="collapsed")
    with c3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear(); st.rerun()

    st.markdown("---")

    # ══════════════════════════════════════════════════════════
    # TAB OMZET
    # ══════════════════════════════════════════════════════════
    if "Omzet" in tab:
        rows = omzet.get(month, [])
        if not rows:
            st.info(f"Belum ada data omzet bulan {month}"); return
        df = pd.DataFrame(rows)

        tot    = df['total'].sum()
        tgt    = df['target'].sum()
        pct_t  = round(tot/tgt*100) if tgt > 0 else 0
        d_hit  = (df['pct'] >= 100).sum()
        best   = df.loc[df['total'].idxmax()]
        avg    = df['total'].mean()

        # KPI row
        kpi_data = [
            ("Total Omzet",       fmt_rp(tot),       f"{len(df)} hari tercatat",       "#0a9e87"),
            ("Target Bulan",      fmt_rp(tgt),        "Akumulasi target harian",        "#3b82f6"),
            ("Capaian",           f"{pct_t}%",        "Total vs Target",                badge_color(pct_t)),
            ("Hari Capai Target", f"{d_hit} hari",    f"dari {len(df)} hari",           "#f59e0b"),
            ("Omzet Terbanyak",   fmt_rp(best['total']), f"Tgl {int(best['d'])} {month}", "#e11d48"),
        ]
        cols = st.columns(5)
        for col, (lbl, val, sub, c) in zip(cols, kpi_data):
            with col:
                st.markdown(f'<div class="kpi" style="--c:{c}"><div class="kpi-lbl">{lbl}</div>'
                            f'<div class="kpi-val">{val}</div><div class="kpi-sub">{sub}</div></div>',
                            unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        # Payer breakdown row
        PAYERS = [
            ("petrokimia","Petrokimia","#8b5cf6"),("perusahaan","Perusahaan","#3b82f6"),
            ("bri","BRI","#06b6d4"),("asuransi","Asuransi","#f59e0b"),
            ("prokMurni","Prok Murni","#0a9e87"),("prokBpjs","Prok BPJS","#10b981"),
            ("bpjsKes","BPJS Kes","#f04e37"),("bpjsTK","BPJS TK","#e11d48"),
            ("umum","Umum","#64748b"),
        ]
        p_cols = st.columns(9)
        for pc, (key, lbl, c) in zip(p_cols, PAYERS):
            if key in df.columns:
                v = df[key].sum()
                pct_p = v/tot*100 if tot > 0 else 0
                with pc:
                    st.markdown(
                        f'<div class="unit-card"><div style="font-size:9px;font-weight:600;'
                        f'text-transform:uppercase;letter-spacing:.1em;color:#7a8fa8;'
                        f'font-family:DM Mono,monospace;margin-bottom:5px;">{lbl}</div>'
                        f'<div style="font-size:12px;font-weight:700;color:{c};">{fmt_rp(v)}</div>'
                        f'<div style="font-size:10px;color:#7a8fa8;">{pct_p:.1f}%</div></div>',
                        unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Charts row 1
        cl, cr = st.columns([2,1])
        with cl:
            st.markdown("**📊 Omzet Harian vs Target**")
            fig = go.Figure()
            fig.add_bar(x=df['d'].astype(str), y=df['total'],
                        marker_color=bar_colors(df['pct']),
                        name="Omzet Aktual", marker_line_width=0)
            fig.add_scatter(x=df['d'].astype(str), y=df['target'],
                            mode="lines+markers", name="Target",
                            line=dict(color="#f59e0b", dash="dash", width=2),
                            marker=dict(size=4))
            fig.update_layout(height=290, margin=dict(t=10,b=0,l=0,r=0),
                              plot_bgcolor="white", paper_bgcolor="white",
                              legend=dict(orientation="h",y=1.05),
                              xaxis=dict(showgrid=False, tickfont=dict(size=10)),
                              yaxis=dict(gridcolor=GRID, tickformat=".2s", tickprefix="Rp "))
            st.plotly_chart(fig, use_container_width=True)

        with cr:
            st.markdown("**🥧 Komposisi Payer**")
            vals_p = [df[k].sum() for k,_,_ in PAYERS if k in df.columns]
            lbls_p = [l for k,l,_ in PAYERS if k in df.columns]
            clrs_p = [c for k,_,c in PAYERS if k in df.columns]
            fig2 = go.Figure(go.Pie(labels=lbls_p, values=vals_p, hole=.58,
                                    marker_colors=clrs_p, textinfo="percent",
                                    hoverinfo="label+value+percent"))
            fig2.update_layout(height=290, margin=dict(t=10,b=0,l=0,r=0),
                               showlegend=True,
                               legend=dict(font=dict(size=9), orientation="v"))
            st.plotly_chart(fig2, use_container_width=True)

        # Chart: % capaian
        st.markdown("**📈 Capaian Harian (%)**")
        fig3 = go.Figure(go.Bar(
            x=df['d'].astype(str), y=df['pct'],
            marker_color=[badge_color(p) for p in df['pct']],
            text=[f"{p}%" for p in df['pct']], textposition="outside",
        ))
        fig3.add_hline(y=100, line_dash="dash", line_color="#f59e0b",
                       annotation_text="100%", annotation_position="top right")
        fig3.update_layout(height=230, margin=dict(t=25,b=0,l=0,r=0),
                           plot_bgcolor="white", paper_bgcolor="white",
                           xaxis=dict(showgrid=False, tickfont=dict(size=10)),
                           yaxis=dict(gridcolor=GRID, ticksuffix="%"))
        st.plotly_chart(fig3, use_container_width=True)

        # Tabel
        st.markdown("**📋 Detail Harian**")
        df_show = df[['d','petrokimia','perusahaan','bri','asuransi','prokMurni',
                       'prokBpjs','bpjsKes','bpjsTK','umum','total','target','pct']].copy()
        df_show['d'] = df_show['d'].astype(int)
        for c in df_show.columns:
            if c not in ['d','pct']:
                df_show[c] = df_show[c].apply(lambda x: f"Rp {int(x):,}")
        df_show['pct'] = df_show['pct'].apply(lambda x: f"{x}%")
        df_show.columns = ['Tgl','Petrokimia','Perusahaan','BRI','Asuransi','Prok Murni',
                           'Prok BPJS','BPJS Kes','BPJS TK','Umum','Total','Target','Capaian']
        st.dataframe(df_show, use_container_width=True, height=380, hide_index=True)

    # ══════════════════════════════════════════════════════════
    # TAB KUNJUNGAN
    # ══════════════════════════════════════════════════════════
    elif "Kunjungan" in tab:
        rows = kunjungan.get(month, [])
        if not rows:
            st.info(f"Belum ada data kunjungan bulan {month}"); return
        df = pd.DataFrame(rows)

        totK   = int(df['total'].sum())
        dHit   = int((df['pct'] >= 100).sum())
        best   = df.loc[df['total'].idxmax()]
        avgK   = round(totK / len(df))
        totRJ  = int(df['rjTotal'].sum())
        totRI  = int(df['riTotal'].sum())
        totIGD = int(df['igdTotal'].sum())
        totMCU = int(df['mcuTotal'].sum())

        # KPI
        kpi_data = [
            ("Total Kunjungan", f"{totK:,}",    f"{len(df)} hari tercatat", "#0a9e87"),
            ("Rata-rata/Hari",  str(avgK),       "Pasien harian",            "#3b82f6"),
            ("Hari Capai Target", f"{dHit} hari", f"dari {len(df)} hari",   "#f59e0b"),
            ("Kunjungan Terbanyak", f"{int(best['total']):,}", f"Tgl {int(best['d'])} {month}", "#e11d48"),
        ]
        cols = st.columns(4)
        for col, (lbl, val, sub, c) in zip(cols, kpi_data):
            with col:
                st.markdown(f'<div class="kpi" style="--c:{c}"><div class="kpi-lbl">{lbl}</div>'
                            f'<div class="kpi-val">{val}</div><div class="kpi-sub">{sub}</div></div>',
                            unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        # Unit summary
        units = [
            ("🚶", "Rawat Jalan", totRJ, "#3b82f6"),
            ("🛏️", "Rawat Inap", totRI, "#8b5cf6"),
            ("🚨", "IGD",        totIGD, "#e11d48"),
            ("🩺", "MCU",        totMCU, "#f59e0b"),
        ]
        ucols = st.columns(4)
        for uc, (ico, lbl, val, c) in zip(ucols, units):
            pct = val/totK*100 if totK > 0 else 0
            with uc:
                st.markdown(
                    f'<div class="unit-card"><div style="font-size:22px;margin-bottom:6px;">{ico}</div>'
                    f'<div style="font-size:9px;font-weight:600;text-transform:uppercase;'
                    f'letter-spacing:.1em;color:#7a8fa8;font-family:DM Mono,monospace;">{lbl}</div>'
                    f'<div style="font-size:22px;font-weight:700;color:{c};margin:4px 0;">{val:,}</div>'
                    f'<div style="font-size:10px;color:#7a8fa8;">{pct:.1f}% dari total</div></div>',
                    unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        # Charts
        cl, cr = st.columns([2,1])
        with cl:
            st.markdown("**📊 Kunjungan Harian vs Target**")
            fig4 = go.Figure()
            fig4.add_bar(x=df['d'].astype(str), y=df['total'],
                         marker_color=bar_colors(df['pct']),
                         name="Total Kunjungan", marker_line_width=0)
            tgt_vals = df['target'].replace(0, None)
            fig4.add_scatter(x=df['d'].astype(str), y=tgt_vals,
                             mode="lines+markers", name="Target",
                             line=dict(color="#f59e0b", dash="dash", width=2),
                             marker=dict(size=4), connectgaps=True)
            fig4.update_layout(height=290, margin=dict(t=10,b=0,l=0,r=0),
                               plot_bgcolor="white", paper_bgcolor="white",
                               legend=dict(orientation="h",y=1.05),
                               xaxis=dict(showgrid=False, tickfont=dict(size=10)),
                               yaxis=dict(gridcolor=GRID))
            st.plotly_chart(fig4, use_container_width=True)

        with cr:
            st.markdown("**🥧 Komposisi Unit**")
            fig5 = go.Figure(go.Pie(
                labels=["Rawat Jalan","Rawat Inap","IGD","MCU"],
                values=[totRJ, totRI, totIGD, totMCU], hole=.58,
                marker_colors=["#3b82f6","#8b5cf6","#e11d48","#f59e0b"],
                textinfo="percent", hoverinfo="label+value+percent"
            ))
            fig5.update_layout(height=290, margin=dict(t=10,b=0,l=0,r=0),
                               showlegend=True, legend=dict(font=dict(size=9)))
            st.plotly_chart(fig5, use_container_width=True)

        # Stacked bar
        st.markdown("**📊 Breakdown Harian per Unit**")
        fig6 = go.Figure()
        for key, lbl, c in [
            ("rjTotal","Rawat Jalan","rgba(59,130,246,.75)"),
            ("riTotal","Rawat Inap","rgba(139,92,246,.75)"),
            ("igdTotal","IGD","rgba(225,29,72,.7)"),
            ("mcuTotal","MCU","rgba(245,158,11,.75)"),
        ]:
            fig6.add_bar(x=df['d'].astype(str), y=df[key], name=lbl, marker_color=c)
        fig6.update_layout(barmode="stack", height=240,
                           margin=dict(t=10,b=0,l=0,r=0),
                           plot_bgcolor="white", paper_bgcolor="white",
                           legend=dict(orientation="h",y=1.05),
                           xaxis=dict(showgrid=False, tickfont=dict(size=10)),
                           yaxis=dict(gridcolor=GRID))
        st.plotly_chart(fig6, use_container_width=True)

        # Tabel
        st.markdown("**📋 Detail Harian**")
        df_show = df[['d','rjTotal','riTotal','igdTotal','mcuTotal','total','target','pct']].copy()
        for c in ['d','rjTotal','riTotal','igdTotal','mcuTotal','total','target']:
            df_show[c] = df_show[c].astype(int)
        df_show['pct'] = df_show['pct'].apply(lambda x: f"{x}%")
        df_show.columns = ['Tgl','Rawat Jalan','Rawat Inap','IGD','MCU','Total','Target','Capaian']
        st.dataframe(df_show, use_container_width=True, height=380, hide_index=True)

    # ══════════════════════════════════════════════════════════
    # TAB MCU
    # ══════════════════════════════════════════════════════════
    else:
        rows = mcu.get(month, [])
        if not rows:
            st.info(f"Belum ada data MCU bulan {month}"); return
        df = pd.DataFrame(rows)
        df = df[df['omzet'] > 0]  # skip hari tanpa omzet MCU

        tot_mcu = df['omzet'].sum()
        avg_mcu = df['omzet'].mean()
        best_m  = df.loc[df['omzet'].idxmax()]
        d_count = len(df)

        # Hitung year-to-date MCU
        ytd = sum(
            pd.DataFrame(mcu[m])['omzet'].sum()
            for m in MONTH_ORDER
            if m in mcu and MONTH_ORDER.index(m) <= MONTH_ORDER.index(month)
        )

        # KPI
        kpi_data = [
            ("Total Omzet MCU",  fmt_rp(tot_mcu),    f"{d_count} hari aktif",     "#8b5cf6"),
            ("Rata-rata/Hari",   fmt_rp(avg_mcu),     "Hari dengan transaksi",     "#3b82f6"),
            ("MCU Terbanyak",    fmt_rp(best_m['omzet']), f"Tgl {int(best_m['d'])} {month}", "#f59e0b"),
            ("YTD Omzet MCU",    fmt_rp(ytd),          f"Kumulatif s/d {month}",   "#0a9e87"),
        ]
        cols = st.columns(4)
        for col, (lbl, val, sub, c) in zip(cols, kpi_data):
            with col:
                st.markdown(f'<div class="kpi" style="--c:{c}"><div class="kpi-lbl">{lbl}</div>'
                            f'<div class="kpi-val">{val}</div><div class="kpi-sub">{sub}</div></div>',
                            unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        # Charts
        cl, cr = st.columns([2,1])
        with cl:
            st.markdown("**📊 Omzet MCU Harian**")
            fig_m = go.Figure()
            fig_m.add_bar(x=df['d'].astype(str), y=df['omzet'],
                          marker_color="rgba(139,92,246,.7)",
                          marker_line_width=0, name="Omzet MCU")
            fig_m.add_scatter(x=df['d'].astype(str), y=[avg_mcu]*len(df),
                              mode="lines", name=f"Rata-rata ({fmt_rp(avg_mcu)})",
                              line=dict(color="#f59e0b", dash="dash", width=2))
            fig_m.update_layout(height=290, margin=dict(t=10,b=0,l=0,r=0),
                                plot_bgcolor="white", paper_bgcolor="white",
                                legend=dict(orientation="h",y=1.05),
                                xaxis=dict(showgrid=False, tickfont=dict(size=10)),
                                yaxis=dict(gridcolor=GRID, tickformat=".2s", tickprefix="Rp "))
            st.plotly_chart(fig_m, use_container_width=True)

        with cr:
            st.markdown("**📊 Perbandingan Bulanan**")
            mon_labels = [m for m in MONTH_ORDER if m in mcu]
            mon_vals   = [pd.DataFrame(mcu[m])['omzet'].sum() for m in mon_labels]
            fig_mb = go.Figure(go.Bar(
                x=mon_labels, y=mon_vals,
                marker_color=["rgba(139,92,246,.85)" if m == month else "rgba(139,92,246,.35)"
                              for m in mon_labels],
                marker_line_width=0,
            ))
            fig_mb.update_layout(height=290, margin=dict(t=10,b=0,l=0,r=0),
                                 plot_bgcolor="white", paper_bgcolor="white",
                                 xaxis=dict(showgrid=False, tickfont=dict(size=10)),
                                 yaxis=dict(gridcolor=GRID, tickformat=".2s", tickprefix="Rp "))
            st.plotly_chart(fig_mb, use_container_width=True)

        # Trend line semua bulan
        st.markdown("**📈 Trend Omzet MCU per Hari — Semua Bulan**")
        fig_trend = go.Figure()
        colors_trend = ["#3b82f6","#0a9e87","#8b5cf6","#f59e0b","#e11d48","#06b6d4",
                        "#f97316","#84cc16","#ec4899","#14b8a6","#6366f1","#a16207"]
        for i, m in enumerate(MONTH_ORDER):
            if m not in mcu: continue
            dm = pd.DataFrame(mcu[m])
            dm = dm[dm['omzet'] > 0]
            lw = 2.5 if m == month else 1.2
            op = 1.0 if m == month else 0.45
            fig_trend.add_scatter(
                x=dm['d'], y=dm['omzet'],
                mode="lines+markers", name=m,
                line=dict(color=colors_trend[i % len(colors_trend)], width=lw),
                marker=dict(size=4 if m == month else 3),
                opacity=op,
            )
        fig_trend.update_layout(height=260, margin=dict(t=10,b=0,l=0,r=0),
                                plot_bgcolor="white", paper_bgcolor="white",
                                legend=dict(orientation="h", font=dict(size=10)),
                                xaxis=dict(showgrid=False, title="Tanggal"),
                                yaxis=dict(gridcolor=GRID, tickformat=".2s", tickprefix="Rp "))
        st.plotly_chart(fig_trend, use_container_width=True)

        # Tabel
        st.markdown("**📋 Detail MCU Harian**")
        df_show = df.copy()
        df_show['d'] = df_show['d'].astype(int)
        df_show['omzet'] = df_show['omzet'].apply(lambda x: f"Rp {int(x):,}")
        df_show.columns = ['Tanggal', 'Omzet MCU']
        st.dataframe(df_show, use_container_width=True, height=380, hide_index=True)


if __name__ == "__main__":
    main()
