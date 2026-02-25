import streamlit as st
import requests
from bs4 import BeautifulSoup
import re

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
if "pdf_cache" not in st.session_state:
    st.session_state.pdf_cache = {}

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

run = st.button("🔍 문서 찾기", type="primary", use_container_width=True)

# ── 유틸 함수 ──────────────────────────────────────────────
def ts_to_etsi(ts_number: str):
    parts = ts_number.strip().split(".")
    series = int(parts[0])
    num = int(parts[1])
    etsi_num = f"{series + 100}{num:03d}"
    series_base = (int(etsi_num) // 100) * 100
    series_range = f"{series_base}_{series_base + 99}"
    return etsi_num, series_range

def get_versions(etsi_num, series_range, target_release=None):
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

    return versions, None

def build_pdf_url(etsi_num, series_range, ver_dir):
    ver_str = ver_dir.split("_")[0]
    ver_compact = ver_str.replace(".", "")
    filename = f"ts_{etsi_num}v{ver_compact}p.pdf"
    return f"https://www.etsi.org/deliver/etsi_ts/{series_range}/{etsi_num}/{ver_dir}/{filename}", ver_str

def fetch_pdf(pdf_url):
    try:
        resp = requests.get(pdf_url, timeout=60)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        st.error(f"PDF 다운로드 실패: {e}")
        return None

# ── 문서 찾기 ─────────────────────────────────────────────
if run and ts_input.strip():
    raw = re.split(r"[,\n]+", ts_input)
    ts_list = [t.strip() for t in raw if re.match(r"^\d+\.\d+$", t.strip())]

    if not ts_list:
        st.error("올바른 TS 번호를 입력해주세요. (예: 23.501)")
    else:
        st.session_state.results = []
        st.session_state.pdf_cache = {}
        for ts in ts_list:
            try:
                etsi_num, series_range = ts_to_etsi(ts)
                versions, err = get_versions(etsi_num, series_range, target_release)
                st.session_state.results.append({
                    "ts": ts, "etsi_num": etsi_num, "series_range": series_range,
                    "versions": versions,
                    "all_labels": [v.split("_")[0] for v in versions] if versions else [],
                    "error": err,
                })
            except Exception as e:
                st.session_state.results.append({
                    "ts": ts, "error": str(e),
                    "versions": None, "all_labels": [],
                    "etsi_num": None, "series_range": None,
                })
elif run:
    st.warning("TS 번호를 입력해주세요.")

# ── 결과 표시 ─────────────────────────────────────────────
if st.session_state.results:
    st.divider()
    st.subheader("결과")

    for item in st.session_state.results:
        ts = item["ts"]
        with st.container():
            st.markdown(f"**TS {ts}**")

            if item["error"]:
                st.error(item["error"])
                st.divider()
                continue

            versions     = item["versions"]
            all_labels   = item["all_labels"]
            etsi_num     = item["etsi_num"]
            series_range = item["series_range"]

            selected_label = st.selectbox(
                f"버전 선택 (TS {ts})", all_labels,
                key=f"ver_{ts}", label_visibility="collapsed"
            )
            selected_ver_dir = versions[all_labels.index(selected_label)]
            pdf_url, ver_str = build_pdf_url(etsi_num, series_range, selected_ver_dir)
            friendly_name = f"TS {ts} V{ver_str}.pdf"
            cache_key = f"{ts}_{ver_str}"

            st.success(f"✓ v{ver_str} 발견")

            # 캐시에 있으면 바로 저장 버튼, 없으면 준비 버튼
            if cache_key in st.session_state.pdf_cache:
                st.download_button(
                    label=f"💾 저장하기 — {friendly_name}",
                    data=st.session_state.pdf_cache[cache_key],
                    file_name=friendly_name,
                    mime="application/pdf",
                    key=f"dl_{cache_key}",
                )
            else:
                if st.button(f"⬇️ 다운로드 준비 — {friendly_name}", key=f"btn_{cache_key}"):
                    with st.spinner(f"{friendly_name} 불러오는 중..."):
                        pdf_bytes = fetch_pdf(pdf_url)
                    if pdf_bytes:
                        st.session_state.pdf_cache[cache_key] = pdf_bytes
                        st.rerun()

            st.divider()

# ── 사용법 ────────────────────────────────────────────────
with st.expander("💡 사용법"):
    st.markdown("""
- **문서 번호**: `23.501` 형식으로 입력
- **여러 문서**: 쉼표(`,`) 또는 줄바꿈으로 구분
- **릴리즈 선택**: 특정 Release가 필요하면 드롭다운에서 선택
- **⬇️ 다운로드 준비** 클릭 → PDF 로딩 후 **💾 저장하기** 버튼 자동 표시
- 저장 파일명은 `TS 24.501 V19.5.0.pdf` 형식으로 자동 지정됩니다
""")
