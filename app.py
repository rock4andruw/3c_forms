import os
import io
import csv
import datetime
import streamlit as st

# ── Secrets（本地 .env 或 Streamlit Cloud secrets） ────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def _secret(key: str) -> str:
    return os.environ.get(key) or st.secrets.get(key, "")

# ── Supabase ───────────────────────────────────────────────────────────────
from supabase import create_client, Client

@st.cache_resource
def get_supabase() -> Client:
    return create_client(_secret("SUPABASE_URL"), _secret("SUPABASE_KEY"))

supabase = get_supabase()

# ── 常數 ───────────────────────────────────────────────────────────────────

CONDITIONS = ["傳統電商搜尋", "AI 智慧平台"]

DIMS = {
    "mental":      ("心智需求",  "完成任務需要多少腦力思考？（比對規格、在多頁面間查找資訊、判斷相容性）"),
    "physical":    ("身體需求",  "完成任務需要多少體力？（反覆點擊、捲動頁面）"),
    "temporal":    ("時間壓力",  "過程中您感受到多大的時間壓力或緊迫感？"),
    "performance": ("決策信心",  "完成後對選出的配件清單有多少把握？（確信相容、不會買錯）"),
    "effort":      ("努力程度",  "整體付出了多少心力與努力？"),
    "frustration": ("挫折程度",  "過程中感到多少挫折感、煩躁或壓力？"),
}

BACKGROUNDS = [
    "新手（無選購零件經驗）",
    "中階（有購買但不熟規格）",
    "專業（有 DIY 裝機經驗）",
]

# ── 計算 ───────────────────────────────────────────────────────────────────

def calc_overall(scores: dict) -> float:
    perf_adj = 10 - scores["performance"]   # 反向
    total = (scores["mental"] + scores["physical"] + scores["temporal"]
             + perf_adj + scores["effort"] + scores["frustration"])
    return round(total / 6 * 10, 1)

# ── 存結果 ─────────────────────────────────────────────────────────────────

def save_to_supabase(record: dict):
    supabase.table("experiment_results").insert(record).execute()

def fetch_all_results() -> list[dict]:
    res = supabase.table("experiment_results").select("*").order("created_at").execute()
    return res.data or []

def to_csv_bytes(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")  # utf-8-sig 讓 Excel 正確顯示中文

# ── Session 初始化 ─────────────────────────────────────────────────────────

def init():
    defaults = {
        "participant_id": "",
        "background": BACKGROUNDS[1],
        "done": set(),          # 已完成的 condition
        "page": "survey",       # survey | done | admin
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init()

# ── 頁面：問卷 ─────────────────────────────────────────────────────────────

def page_survey():
    st.title("3C 購物決策體驗評估")

    # 研究說明
    with st.expander("📋 研究說明（點此展開）", expanded=False):
        st.markdown("""
**研究目的**
本研究探討不同的電腦配件購物方式，對選購過程中認知負荷（心理感受）的差異。
您的回答僅用於學術研究，完全匿名，不會對外公開。

**您今天的任務**
分別以兩種方式，在新台幣 30,000 元預算內，選出一套能順暢執行《黑神話：悟空》的電腦配件清單（共 7 項零件）：
- **傳統電商搜尋**：使用原價屋等網站自行瀏覽、比對
- **AI 智慧平台**：透過自然語言對話讓 AI 引導選配

**填寫說明**
完成每次任務後，針對該次體驗填寫問卷。
每題使用 0–10 滑桿，0 = 非常低，10 = 非常高（決策信心題方向相反）。
        """)

    st.divider()

    # 受試者資料
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.participant_id = st.text_input(
            "受試者代號 *", value=st.session_state.participant_id,
            placeholder="A / B / C / D / E"
        )
    with col2:
        st.session_state.background = st.selectbox(
            "電腦背景 *", BACKGROUNDS,
            index=BACKGROUNDS.index(st.session_state.background)
        )

    if not st.session_state.participant_id:
        st.warning("請先輸入受試者代號")
        st.stop()

    st.divider()

    # 選擇填哪個 condition
    remaining = [c for c in CONDITIONS if c not in st.session_state.done]

    if not remaining:
        st.session_state.page = "done"
        st.rerun()

    condition = st.radio(
        "您剛才完成的是哪種方式？",
        remaining,
        horizontal=True,
    )

    st.caption(f"請根據剛才使用「**{condition}**」完成任務的真實感受評分。")
    st.divider()

    # 6 個滑桿
    scores = {}
    for key, (label, desc) in DIMS.items():
        st.markdown(f"**{label}**")
        st.caption(desc)

        if key == "performance":
            scores[key] = st.slider(
                label, 0, 10, 5,
                key=f"{condition}_{key}",
                label_visibility="collapsed",
                help="0 = 完全沒信心　10 = 非常有信心",
            )
            st.caption("*此題越高分代表越有信心（與其他題方向相反）*")
        else:
            scores[key] = st.slider(
                label, 0, 10, 5,
                key=f"{condition}_{key}",
                label_visibility="collapsed",
                help="0 = 非常低　10 = 非常高",
            )
        st.divider()

    overall = calc_overall(scores)
    st.metric("整體負荷預覽", f"{overall} 分　（0–100）")

    if st.button("✅ 送出", type="primary", use_container_width=True):
        record = {
            "created_at":     datetime.datetime.now().isoformat(),
            "participant_id": st.session_state.participant_id,
            "background":     st.session_state.background,
            "condition":      condition,
            "mental":         scores["mental"] * 10,
            "physical":       scores["physical"] * 10,
            "temporal":       scores["temporal"] * 10,
            "performance":    scores["performance"] * 10,
            "effort":         scores["effort"] * 10,
            "frustration":    scores["frustration"] * 10,
            "overall_raw":    overall,
        }
        save_to_supabase(record)
        st.session_state.done.add(condition)
        st.success(f"「{condition}」評估已儲存！")
        st.balloons()
        st.rerun()

# ── 頁面：完成 ─────────────────────────────────────────────────────────────

def page_done():
    st.title("🎉 兩份評估均已完成")
    st.success("感謝您的參與！請通知實驗主持人。")

    if st.button("重新開始（下一位受試者）", use_container_width=True):
        for k in ["participant_id", "done"]:
            st.session_state[k] = "" if k == "participant_id" else set()
        st.session_state.page = "survey"
        st.rerun()

# ── 頁面：管理（下載結果） ─────────────────────────────────────────────────

def page_admin():
    st.title("📊 實驗結果管理")

    rows = fetch_all_results()
    if not rows:
        st.info("尚無資料")
        return

    st.dataframe(rows, use_container_width=True)
    st.download_button(
        "⬇️ 下載 CSV",
        data=to_csv_bytes(rows),
        file_name=f"nasa_tlx_results_{datetime.date.today()}.csv",
        mime="text/csv",
        use_container_width=True,
    )

# ── 路由 ───────────────────────────────────────────────────────────────────

# 側欄導覽
with st.sidebar:
    st.header("導覽")
    if st.button("📝 填寫問卷", use_container_width=True):
        st.session_state.page = "survey"
        st.rerun()
    if st.button("📊 下載結果", use_container_width=True):
        st.session_state.page = "admin"
        st.rerun()

    done_count = len(st.session_state.done)
    st.caption(f"已完成：{done_count} / 2 份")
    for c in CONDITIONS:
        icon = "✅" if c in st.session_state.done else "⬜"
        st.caption(f"{icon} {c}")

# 顯示對應頁面
if st.session_state.page == "done":
    page_done()
elif st.session_state.page == "admin":
    page_admin()
else:
    page_survey()
