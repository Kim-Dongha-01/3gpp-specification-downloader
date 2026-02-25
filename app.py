import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    page_title="3GPP Spec Downloader",
    page_icon="📡",
    layout="centered"
)

st.title("📡 3GPP Spec Downloader")
st.caption("ETSI에서 3GPP 문서를 자동으로 찾아 다운로드합니다.")

# ── session_state 초기화 ───────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = []

# ── 입력 영역 ──────────────────────────────────────────────
st.subheader("문서 번호 입력")
ts_input = st.text_area(
    "TS 번호 입력 (쉼표 또는 줄바꿈으로 구분)",
    placeholder="예:\n23.501\n38.401, 38.300\n38.331",
    height=120,
)

release_options = {
    "최신 버전 (자동 감지)": None,
    "Release 19": "19",
    "Release 18": "18",
    "Release 17": "17",
    "Release 16": "16",
    "Release 15": "15",
}
release_label = st.selectbox("릴리즈 버전 선택", list(release_options.keys()))
target_release = release_options[release_label]

run = st.button("⬇️ 문서 찾기 & 다운로드", type="primary", use_container_width=True)

# ── 유틸 함수 ──────────────────────────────────────────────
def ts_to_etsi(ts_number: str):
    parts = ts_number.strip().split(".")
    series = int(parts[0])
    num = int(parts[1])
    etsi_num = f"{series + 100}{num:03d}"
    series_base = (int(etsi_num) // 100) * 100
    series_range = f"{series_base}_{series_base + 99}"
    return etsi_num, series_range

def get_latest_version(etsi_num, series_range, target_release=None):
    dir_url = f"https://www.etsi.org/deliver/etsi_ts/{series_range}/{etsi_num}/"
    try:
        resp = requests.get(dir_url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        return None, str(e)

    soup = BeautifulSoup(resp.text, "html.parser")
    versions = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if re.search(r"\d+\.\d+\.\d+_\d+", href):
            versions.append(href.strip("/").split("/")[-1])

    if not versions:
        return None, f"버전 목록 없음 ({dir_url})"

    def version_key(v):
        return tuple(int(n) for n in re.findall(r"\d+", v))

    versions = sorted(set(versions), key=version_key, reverse=True)

    if target_release:
        filtered = [v for v in versions if v.startswith(target_release + ".")]
        if not filtered:
            return None, f"Rel-{target_release} 버전 없음"
        versions = filtered

    return versions[0], None

def build_pdf_url(etsi_num, series_range, ver_dir):
    ver_str = ver_dir.split("_")[0]
    ver_compact = ver_str.replace(".", "")
    ver_display = ".".join(str(int(p)) for p in ver_str.split("."))
    filename = f"ts_{etsi_num}v{ver_compact}p.pdf"
    url = f"https://www.etsi.org/deliver/etsi_ts/{series_range}/{etsi_num}/{ver_dir}/{filename}"
    return url, ver_str, ver_display

def fetch_one(ts, target_release):
    """버전 감지 + PDF 다운로드를 한 번에 처리"""
    try:
        etsi_num, series_range = ts_to_etsi(ts)
        ver_dir, err = get_latest_version(etsi_num, series_range, target_release)
        if err:
            return {"ts": ts, "error": err, "pdf": None, "friendly_name": None}

        pdf_url, ver_str, ver_display = build_pdf_url(etsi_num, series_range, ver_dir)
        friendly_name = f"TS {ts} V{ver_display}.pdf"

        resp = requests.get(pdf_url, timeout=60)
        resp.raise_for_status()

        return {"ts": ts, "error": None, "pdf": resp.content,
                "friendly_name": friendly_name, "ver_display": ver_display}
    except Exception as e:
        return {"ts": ts, "error": str(e), "pdf": None, "friendly_name": None}

# ── 문서 찾기 & 다운로드 ───────────────────────────────────
if run and ts_input.strip():
    raw = re.split(r"[,\n]+", ts_input)
    ts_list = [t.strip() for t in raw if re.match(r"^\d+\.\d+$", t.strip())]

    if not ts_list:
        st.error("올바른 TS 번호를 입력해주세요. (예: 23.501)")
    else:
        st.session_state.results = []
        with st.spinner(f"{len(ts_list)}개 문서 다운로드 중..."):
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(fetch_one, ts, target_release): ts for ts in ts_list}
                results = {}
                for future in as_completed(futures):
                    result = future.result()
                    results[result["ts"]] = result
            # 입력 순서 유지
            st.session_state.results = [results[ts] for ts in ts_list]

elif run:
    st.warning("TS 번호를 입력해주세요.")

# ── 결과 표시 ─────────────────────────────────────────────
if st.session_state.results:
    st.divider()
    st.subheader("결과")

    for item in st.session_state.results:
        ts = item["ts"]
        with st.container():
            if item["error"]:
                st.error(f"**TS {ts}**: {item['error']}")
            else:
                st.success(f"✓ **{item['friendly_name']}**")
                st.download_button(
                    label=f"💾 저장하기 — {item['friendly_name']}",
                    data=item["pdf"],
                    file_name=item["friendly_name"],
                    mime="application/pdf",
                    key=f"dl_{ts}_{item['ver_display']}",
                )
            st.divider()

# ── 사용법 ────────────────────────────────────────────────
with st.expander("💡 사용법"):
    st.markdown("""
- **문서 번호**: `23.501` 형식으로 입력
- **여러 문서**: 쉼표(`,`) 또는 줄바꿈으로 구분
- **릴리즈 선택**: 원하는 Release를 선택하면 해당 릴리즈의 최신 버전을 자동으로 찾습니다
- **문서 찾기 & 다운로드** 클릭 → 모든 문서를 병렬로 받아온 뒤 💾 저장하기 버튼 표시
- 저장 파일명은 `TS 24.501 V19.5.0.pdf` 형식으로 자동 지정됩니다
""")
