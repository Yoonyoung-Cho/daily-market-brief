"""자기완결형 HTML 리포트 생성 (designer 산출물).

방법론: .claude/skills/reporting/SKILL.md + reference/design_system.md

- 외부 CDN/폰트 의존 없이 한 파일로 완결(공유 용이).
- Plotly.js 는 한 번만 인라인.
- 주식 비전문가가 위→아래로 읽으며 이해하도록 교육 섹션 포함.
- 탭(구조적/산업/통계) + 클라이언트 필터(대형주·정렬·최소 |z|)로 Streamlit 처럼 탐색.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from src.config import Config
from src.viz.charts import (
    actual_price_chart,
    divergence_band_chart,
    normalized_price_chart,
    zscore_chart,
)

_REL_KR = {
    "pref_common": "보통주-우선주",
    "holdco_sub": "지주사-자회사",
    "group_chain": "그룹·밸류체인",
    "industry_peer": "동일 산업",
    "statistical": "통계 발굴",
}

_CAT_KR = {
    "structural": "🏛 구조적 (누가봐도)",
    "industry": "🔗 산업·밸류체인",
    "statistical": "🧪 통계 발굴 (잡주 포함)",
}


def _esc(text: Any) -> str:
    """HTML 이스케이프."""
    return html.escape(str(text))


def _metric_str(label: str, value: float | None) -> str:
    if value is None:
        return "—"
    if "할인율" in label or "디스카운트" in label:
        return f"{value * 100:.1f}%"
    return f"{value:.4f}"


def _fmt_marcap(value: float | None) -> str:
    """시가총액(원) -> '조원/억원' 읽기 쉬운 표기."""
    if value is None:
        return "—"
    if value >= 1e12:
        return f"{value / 1e12:.1f}조원"
    if value >= 1e8:
        return f"{value / 1e8:,.0f}억원"
    return f"{value:,.0f}원"


def _z_class(z: float | None) -> str:
    if z is None:
        return "z-neutral"
    a = abs(z)
    return "z-extreme" if a >= 2 else ("z-warn" if a >= 1 else "z-neutral")


def _fig_html(fig, idx: int) -> str:
    """Plotly Figure -> 인라인 div (plotly.js 는 별도 1회 로드)."""
    import plotly.io as pio

    fig.update_layout(margin=dict(l=50, r=40, t=50, b=40), height=320,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#cdd6e8"))
    return pio.to_html(fig, include_plotlyjs=False, full_html=False,
                       config={"displayModeBar": False}, div_id=f"chart-{idx}")


def _education_section() -> str:
    """비전문가용 교육 블록."""
    terms = [
        ("페어(쌍) 분석이란?",
         "두 종목이 평소 비슷하게 움직였다면, 어느 날 둘의 가격차가 유난히 벌어지는 "
         "순간을 포착하는 방법입니다. '나란히 걷던 두 사람이 갑자기 벌어지는' 순간을 찾는 셈입니다."),
        ("괴리율 / 스프레드",
         "두 종목 사이의 '가격 차이'를 수치화한 값입니다. 관계 유형에 따라 우선주 할인율, "
         "NAV 디스카운트, 또는 로그 가격 스프레드로 측정합니다."),
        ("z-score",
         "지금 괴리가 '최근 평소 대비 몇 표준편차나 벗어났는지'입니다. ±1 안이면 평범, "
         "±2 밖이면 드문 일입니다. (미래 정보를 안 쓰도록 과거 데이터로만 계산합니다.)"),
        ("역사적 백분위",
         "현재 괴리가 최근 2년 중 어느 위치인지(%)입니다. '상위 3%'면 그만큼 크게 벌어졌다는 뜻."),
        ("반감기(half-life)",
         "과거에 이 괴리가 평균으로 절반쯤 되돌아오는 데 걸린 거래일 수입니다. 짧을수록 "
         "'잘 돌아오던' 관계지만, 미래를 보장하진 않습니다."),
        ("공적분 / 우량주",
         "공적분은 두 종목이 장기적으로 묶여 움직이는지 보는 통계 검정입니다(추세장 가짜동조 제거). "
         "여기에 시가총액 큰 우량주를 우선해, 잡주 노이즈를 줄입니다."),
        ("스코어 / 탭",
         "스코어는 경제적 근거·공적분·상관·반감기·현재 괴리를 종합한 정렬 기준입니다. "
         "탭으로 '누가봐도 구조적 페어 / 산업 / 통계(잡주)'를 나눠 봅니다."),
    ]
    cards = "\n".join(
        f'<div class="term"><h4>{_esc(t)}</h4><p>{_esc(d)}</p></div>'
        for t, d in terms
    )
    pipeline = (
        '<ol class="pipeline">'
        '<li><b>수집</b> — 우량주 워치리스트의 일별 수정주가·시가총액을 모읍니다.</li>'
        '<li><b>시드 선정</b> — 누가봐도 묶이는 구조적 페어(보통주-우선주, 지주사-자회사)를 먼저 둡니다.</li>'
        '<li><b>스크리닝</b> — 상관·공적분으로 통계적으로 묶이는 쌍을 추립니다.</li>'
        '<li><b>괴리 분석</b> — 현재 괴리·z-score·반감기·백분위를 계산합니다.</li>'
        '<li><b>리포트</b> — 분석가 해석과 차트로 정리합니다(이 화면).</li>'
        '</ol>'
    )
    return f"""
    <section class="edu">
      <h2>📘 이게 뭔가요? <span class="sub">3분이면 이해하는 핵심 개념</span></h2>
      <div class="edu-grid">
        <div class="edu-pipeline"><h3>분석 5단계</h3>{pipeline}</div>
        <div class="edu-terms">{cards}</div>
      </div>
    </section>
    """


def _fund_badges(analysis: dict[str, Any], config: Config) -> str:
    """두 종목의 시총·PER·우량주 배지."""
    fa = analysis.get("fund_a", {}) or {}
    fb = analysis.get("fund_b", {}) or {}
    name_a = _esc(analysis.get("name_a", analysis["ticker_a"]))
    name_b = _esc(analysis.get("name_b", analysis["ticker_b"]))

    def per_txt(f):
        per = f.get("per")
        return f" · PER {per:.1f}" if isinstance(per, (int, float)) and per == per else ""

    parts = [
        f'<span class="badge cap">{name_a} 시총 {_esc(_fmt_marcap(fa.get("marcap")))}{per_txt(fa)}</span>',
        f'<span class="badge cap">{name_b} 시총 {_esc(_fmt_marcap(fb.get("marcap")))}{per_txt(fb)}</span>',
    ]
    if analysis.get("is_bluechip"):
        parts.append('<span class="badge bluechip">대형 우량주</span>')
    if analysis.get("pinned"):
        parts.insert(0, '<span class="badge pinned">📌 고정</span>')
    return "".join(parts)


def _card(analysis: dict[str, Any], config: Config, idx: int) -> str:
    """추천 카드 1개 (지표 + 펀더멘털 + 분석가 해석 + 차트 4종)."""
    label = analysis.get("label", "괴리 지표")
    name_a = _esc(analysis.get("name_a", analysis["ticker_a"]))
    name_b = _esc(analysis.get("name_b", analysis["ticker_b"]))
    rel = _REL_KR.get(analysis["relationship_type"], analysis["relationship_type"])
    src = "구조적 시드" if analysis.get("source") == "seed" else "통계 발굴"
    z = analysis.get("current_zscore")
    score = analysis.get("score", 0.0)
    nar = analysis.get("narrative", {})
    cat = analysis.get("category", "statistical")
    pinned = bool(analysis.get("pinned"))
    bluechip = 1 if analysis.get("is_bluechip") else 0

    s = analysis["series"]
    price_a = config.format_price(s["price_a"][-1]) if s["price_a"] else "—"
    price_b = config.format_price(s["price_b"][-1]) if s["price_b"] else "—"

    hl = analysis.get("half_life")
    hl_str = "약함(∞)" if hl is None else f"{hl:.0f}일"
    metrics = [
        ("현재 괴리", _metric_str(label, analysis.get("current_metric")), label),
        ("z-score", f"{z:+.2f}" if z is not None else "—", "평소 대비 이탈"),
        ("백분위", f"{analysis.get('percentile', float('nan')):.0f}%", "최근 2년 위치"),
        ("반감기", hl_str, "평균회귀 속도"),
    ]
    metric_html = "".join(
        f'<div class="metric"><span class="mlabel">{_esc(l)}</span>'
        f'<span class="mval">{_esc(v)}</span>'
        f'<span class="mhint">{_esc(h)}</span></div>'
        for l, v, h in metrics
    )

    rationale = analysis.get("rationale") or nar.get("why", "")
    charts = "".join([
        _fig_html(actual_price_chart(analysis), idx * 10 + 0),
        _fig_html(normalized_price_chart(analysis), idx * 10 + 1),
        _fig_html(divergence_band_chart(analysis, config.analysis.band_sigmas), idx * 10 + 2),
        _fig_html(zscore_chart(analysis), idx * 10 + 3),
    ])

    az = abs(z) if z is not None else 0.0
    pin_cls = " pinned-card" if pinned else ""
    return f"""
    <article class="card{pin_cls}" data-cat="{cat}" data-z="{az:.3f}"
             data-score="{score:.4f}" data-bluechip="{bluechip}"
             data-pinned="{1 if pinned else 0}" data-rel="{analysis['relationship_type']}">
      <header class="card-head">
        <div class="titles">
          <h3>{name_a} <span class="vs">↔</span> {name_b}</h3>
          <div class="badges">
            {f'<span class="badge theme">{_esc(analysis["theme"])}</span>' if analysis.get("theme") else ''}
            <span class="badge rel">{_esc(rel)}</span>
            <span class="badge src">{_esc(src)}</span>
            <span class="badge price">{name_a} {_esc(price_a)}</span>
            <span class="badge price">{name_b} {_esc(price_b)}</span>
          </div>
          <div class="badges fundrow">{_fund_badges(analysis, config)}</div>
        </div>
        <div class="score">
          <div class="score-num">{score:.2f}</div>
          <div class="score-bar"><span style="width:{min(score, 1.5) / 1.5 * 100:.0f}%"></span></div>
          <div class="score-cap">스코어</div>
        </div>
      </header>

      <p class="why"><b>왜 비교하나</b> · {_esc(rationale)}</p>

      <div class="metrics {_z_class(z)}">{metric_html}</div>

      <div class="signal">📍 <b>지금 읽는 법</b> · {_esc(nar.get('signal', ''))}</div>

      <div class="analyst">
        <div class="headline">🧑‍💼 {_esc(nar.get('headline', analysis.get('interpretation', '')))}</div>
        <div class="nar-grid">
          <p><b>지금 상황</b><br>{_esc(nar.get('what', ''))}</p>
          <p><b>왜 함께 보나</b><br>{_esc(nar.get('why', ''))}</p>
          <p><b>주의점</b><br>{_esc(nar.get('caveat', ''))}</p>
        </div>
      </div>

      <details class="charts">
        <summary>차트 보기 (실제가격 · 정규화 · 괴리밴드 · z-score)</summary>
        <div class="chart-grid">{charts}</div>
      </details>
    </article>
    """


def _controls(analyses: list[dict[str, Any]]) -> str:
    """탭 + 필터 UI (Streamlit 필터 대체)."""
    counts = {"all": 0, "structural": 0, "industry": 0, "statistical": 0}
    for a in analyses:
        if a.get("status") != "ok":
            continue
        counts["all"] += 1
        counts[a.get("category", "statistical")] += 1
    tabs = [("all", f"전체 ({counts['all']})")]
    for key in ("structural", "industry", "statistical"):
        tabs.append((key, f"{_CAT_KR[key]} ({counts[key]})"))
    tab_html = "".join(
        f'<button class="tab{" active" if k == "all" else ""}" data-tab="{k}">{_esc(label)}</button>'
        for k, label in tabs
    )
    return f"""
    <div class="controls">
      <div class="tabs">{tab_html}</div>
      <div class="filters">
        <label class="chk"><input type="checkbox" id="bluechipOnly"> 대형 우량주만</label>
        <label>정렬
          <select id="sortKey">
            <option value="z" selected>지금 벌어진 순 (|z|)</option>
            <option value="score">스코어순</option>
          </select>
        </label>
        <label>최소 |z|
          <input type="range" id="minZ" min="0" max="3" step="0.5" value="0">
          <span id="minZval">0.0</span>
        </label>
      </div>
    </div>
    """


def _js() -> str:
    """탭/정렬/필터 클라이언트 로직 (서버 불필요)."""
    return """
    (function(){
      var container = document.getElementById('cards');
      var cards = Array.prototype.slice.call(container.querySelectorAll('.card'));
      var tab = 'all';
      function num(c, k){ return parseFloat(c.getAttribute(k)) || 0; }
      function apply(){
        var bcOnly = document.getElementById('bluechipOnly').checked;
        var minZ = parseFloat(document.getElementById('minZ').value) || 0;
        var sortKey = document.getElementById('sortKey').value;
        // 정렬: 고정(pinned) 최우선, 그 다음 선택 키 내림차순
        var sorted = cards.slice().sort(function(a,b){
          var pa = num(a,'data-pinned'), pb = num(b,'data-pinned');
          if (pa !== pb) return pb - pa;
          return num(b,'data-'+sortKey) - num(a,'data-'+sortKey);
        });
        var visible = 0;
        sorted.forEach(function(c){
          var okTab = (tab === 'all') || (c.getAttribute('data-cat') === tab);
          var okBc = !bcOnly || num(c,'data-bluechip') === 1;
          var okZ = num(c,'data-z') >= minZ;
          var pinned = num(c,'data-pinned') === 1;
          // 고정 페어는 탭만 맞으면 항상 노출(필터 면제)
          var show = okTab && (pinned || (okBc && okZ));
          c.style.display = show ? '' : 'none';
          if (show) visible++;
          container.appendChild(c);
        });
        var emp = document.getElementById('empty');
        if (emp) emp.style.display = visible ? 'none' : '';
      }
      document.querySelectorAll('.tab').forEach(function(btn){
        btn.addEventListener('click', function(){
          document.querySelectorAll('.tab').forEach(function(b){b.classList.remove('active');});
          btn.classList.add('active'); tab = btn.getAttribute('data-tab'); apply();
        });
      });
      document.getElementById('bluechipOnly').addEventListener('change', apply);
      document.getElementById('sortKey').addEventListener('change', apply);
      var mz = document.getElementById('minZ');
      mz.addEventListener('input', function(){
        document.getElementById('minZval').textContent = parseFloat(mz.value).toFixed(1); apply();
      });
      apply();
    })();
    """


def _css() -> str:
    return """
    :root{--bg:#0f1420;--card:#1a2030;--ink:#e8edf6;--sub:#9aa7bd;
      --brand:#5b9dff;--warn:#ff6b6b;--ok:#4dd4ac;--gold:#ffcf5b;--line:#28324a;}
    *{box-sizing:border-box}
    body{margin:0;background:var(--bg);color:var(--ink);
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
      line-height:1.6}
    .wrap{max-width:1080px;margin:0 auto;padding:28px 20px 60px}
    h1{font-size:1.9rem;margin:0 0 4px}
    .meta{color:var(--sub);font-size:.9rem;margin-bottom:14px}
    .disclaimer{background:#2a1d22;border:1px solid #5a2b33;color:#ffd6d6;
      padding:10px 14px;border-radius:10px;font-size:.86rem;margin:14px 0}
    h2{font-size:1.3rem;margin:34px 0 12px}
    h2 .sub{font-size:.85rem;color:var(--sub);font-weight:400;margin-left:8px}
    .edu{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px}
    .edu-grid{display:grid;grid-template-columns:1fr 1.4fr;gap:22px}
    @media(max-width:780px){.edu-grid{grid-template-columns:1fr}}
    .pipeline{margin:0;padding-left:20px}.pipeline li{margin:6px 0;color:var(--sub)}.pipeline b{color:var(--ink)}
    .edu-terms{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    @media(max-width:560px){.edu-terms{grid-template-columns:1fr}}
    .term{background:#141a28;border:1px solid var(--line);border-radius:10px;padding:10px 12px}
    .term h4{margin:0 0 4px;font-size:.92rem;color:var(--brand)}.term p{margin:0;font-size:.82rem;color:var(--sub)}
    .controls{position:sticky;top:0;background:rgba(15,20,32,.95);backdrop-filter:blur(6px);
      padding:12px 0;margin:8px 0 4px;border-bottom:1px solid var(--line);z-index:5}
    .tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
    .tab{background:#1a2030;border:1px solid var(--line);color:var(--sub);
      padding:7px 12px;border-radius:20px;cursor:pointer;font-size:.85rem}
    .tab.active{background:#1b2c4a;color:#cfe0ff;border-color:#3a5d96}
    .filters{display:flex;gap:18px;flex-wrap:wrap;align-items:center;font-size:.85rem;color:var(--sub)}
    .filters select,.filters input[type=range]{accent-color:var(--brand)}
    .filters select{background:#141a28;color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:3px 6px}
    .chk{cursor:pointer}
    .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;margin:18px 0}
    .pinned-card{border-color:var(--gold);box-shadow:0 0 0 1px rgba(255,207,91,.35)}
    .card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}
    .card-head h3{margin:0;font-size:1.35rem}.vs{color:var(--brand)}
    .badges{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}
    .fundrow{margin-top:6px}
    .badge{font-size:.72rem;padding:3px 9px;border-radius:20px;background:#222b40;color:var(--sub);border:1px solid var(--line)}
    .badge.rel{background:#1b2c4a;color:#9cc2ff;border-color:#274a7a}
    .badge.src{background:#1f3a2f;color:#8ee0c0;border-color:#2c5a48}
    .badge.price{background:#2a2440;color:#cbb6ff;border-color:#473a6e}
    .badge.theme{background:#3a2342;color:#f0b6ff;border-color:#6e3a7e;font-weight:700}
    .badge.cap{background:#16202e;color:#a7b6cf}
    .research{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 20px;margin:14px 0}
    .research h3{margin:4px 0 10px;color:var(--brand)}
    .research ul{margin:0;padding-left:18px}.research li{margin:6px 0;font-size:.9rem;color:#d2dbec}
    .research a{color:#9cc2ff}
    .rnote{font-size:.78rem;color:var(--sub);margin:10px 0 0}
    .badge.bluechip{background:#243a22;color:#bfe6a0;border-color:#3c5e36}
    .badge.pinned{background:#3a2f12;color:var(--gold);border-color:#6e5a23}
    .score{text-align:center;min-width:110px}
    .score-num{font-size:1.8rem;font-weight:700;color:var(--brand)}
    .score-bar{height:6px;background:#222b40;border-radius:4px;overflow:hidden;margin:4px 0}
    .score-bar span{display:block;height:100%;background:linear-gradient(90deg,#4dd4ac,#5b9dff)}
    .score-cap{font-size:.72rem;color:var(--sub)}
    .why{background:#141a28;border-left:3px solid var(--brand);padding:10px 14px;border-radius:8px;font-size:.9rem;color:#d2dbec;margin:14px 0}
    .metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0}
    @media(max-width:560px){.metrics{grid-template-columns:repeat(2,1fr)}}
    .metric{background:#141a28;border:1px solid var(--line);border-radius:10px;padding:10px 12px;text-align:center}
    .mlabel{display:block;font-size:.74rem;color:var(--sub)}
    .mval{display:block;font-size:1.25rem;font-weight:700;margin:2px 0}
    .mhint{display:block;font-size:.68rem;color:#6f7d96}
    .metrics.z-extreme .mval{color:var(--warn)}.metrics.z-warn .mval{color:#ffb454}
    .analyst{background:#12182a;border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:14px 0}
    .headline{font-size:1.02rem;font-weight:600;margin-bottom:10px}
    .nar-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}
    @media(max-width:780px){.nar-grid{grid-template-columns:1fr}}
    .nar-grid p{margin:0;font-size:.84rem;color:#c4cee0}.nar-grid b{color:var(--ink)}
    .charts summary{cursor:pointer;color:var(--brand);font-size:.9rem;margin:6px 0}
    .chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}
    @media(max-width:780px){.chart-grid{grid-template-columns:1fr}}
    .signal{background:#10243a;border:1px solid #2a4a6e;
      border-radius:10px;padding:10px 14px;margin:14px 0;font-size:.92rem;color:#dbe7fb}
    .signal b{color:#fff}
    .pinned-section{background:#1c1a12;border:1px solid #6e5a23;border-radius:16px;
      padding:8px 18px 18px;margin:18px 0}
    .pinned-section h2{margin-top:18px}
    .pinned-section .card{margin-top:12px}
    .score-help{background:#141a28;border-left:3px solid var(--gold);border-radius:8px;
      padding:12px 14px;font-size:.86rem;color:#d2dbec;margin:6px 0 4px}
    .score-help u{color:var(--gold);text-decoration:none;font-weight:700}
    .empty{background:#141a28;border:1px dashed var(--line);border-radius:10px;
      padding:18px;color:var(--sub);font-size:.9rem;text-align:center}
    footer{margin-top:40px;color:var(--sub);font-size:.82rem;border-top:1px solid var(--line);padding-top:16px}
    """


def generate_report(
    analyses: list[dict[str, Any]],
    config: Config,
    *,
    watchlist: dict[str, Any] | None = None,
    generated_at: str = "",
    out_path: Path | None = None,
) -> Path:
    """분석 결과로 자기완결형 HTML 리포트를 생성한다(탭·필터 포함).

    Args:
        analyses: rank_pairs 로 정렬된 분석 결과 리스트.
        config: Config.
        watchlist: watchlist.json 내용(제목·출처 표기용).
        generated_at: 생성시각 문자열.
        out_path: 출력 경로. None 이면 data/report.html.

    Returns:
        생성된 HTML 파일 경로.
    """
    from plotly.offline import get_plotlyjs

    wl = watchlist or {}
    out = out_path or (config.cache_dir / "report.html")
    cur = config.currency

    title = wl.get("title", config.universe)
    source = wl.get("source", "데이터 출처 미상")
    wl_desc = wl.get("description", "")
    research = wl.get("research_sources", [])
    research_html = ""
    if research:
        items = "".join(
            f'<li><b>{_esc(r.get("firm",""))}</b> — {_esc(r.get("view",""))} '
            f'<a href="{_esc(r.get("url","#"))}" target="_blank">[리포트]</a></li>'
            for r in research
        )
        research_html = f"""
        <section class="research">
          <h3>🏦 섹터 선정 근거 (증권사 리서치)</h3>
          <ul>{items}</ul>
          <p class="rnote">증권사 리포트는 섹터 방향성 참고용이며, 개별 종목 매수·매도 권유가 아닙니다.</p>
        </section>"""

    ok = [a for a in analyses if a.get("status") == "ok"]
    pinned_html, rest_html, rest = [], [], []
    for i, a in enumerate(ok):
        card = _card(a, config, i)
        if a.get("pinned"):
            pinned_html.append(card)
        else:
            rest_html.append(card)
            rest.append(a)
    cards = "\n".join(rest_html) or '<p class="why">조건에 맞는 페어가 없습니다.</p>'

    pinned_section = ""
    if pinned_html:
        pinned_section = f"""
        <section class="pinned-section">
          <h2>📌 고정 페어 <span class="sub">탭·필터·정렬과 무관하게 항상 맨 위에 표시</span></h2>
          {''.join(pinned_html)}
        </section>"""

    plotly_js = get_plotlyjs()
    disclaimer = _esc(config.disclaimer)

    body = f"""
    <div class="wrap">
      <h1>📊 주가 괴리율 분석 — {_esc(title)}</h1>
      <div class="meta">
        시장 {_esc(config.market)} · 통화 {_esc(cur.code)}({_esc(cur.symbol)}) ·
        분석기간 {config.lookback_days}거래일 · 롤링윈도우 {config.rolling_window}일 ·
        생성 {_esc(generated_at)}<br>
        데이터 출처: {_esc(source)}
      </div>
      <div class="disclaimer">⚠️ {disclaimer}</div>
      <p class="why">{_esc(wl_desc)}</p>
      {research_html}
      {_education_section()}
      {pinned_section}
      <h2>🔎 추천 페어 <span class="sub">탭·필터로 골라 보세요</span></h2>
      <div class="score-help">
        <b>스코어란?</b> "이 페어를 먼저 들여다볼 가치"를 나타내는 <b>우선순위 점수</b>입니다
        (관계 신뢰도 = 경제적 근거·공적분·상관·반감기 + 현재 주목도 = |z|).
        <u>살 순서가 아닙니다.</u> 지금 실제로 벌어진 정도는 각 카드의
        <b>z-score</b>와 <b>📍 지금 읽는 법</b>을 보세요. (기본 정렬: 지금 벌어진 순)
      </div>
      {_controls(rest)}
      <div id="cards">{cards}</div>
      <p id="empty" class="empty" style="display:none">
        선택한 조건에 맞는 페어가 없습니다. 특히 <b>통계 발굴</b> 탭은 공적분 검정을
        통과한 쌍만 담기므로(가짜 동조 방지) 비어 있을 수 있습니다. 필터를 완화해 보세요.
      </p>
      <footer>
        데이터 출처: {_esc(source)}. 가격은 수정주가 기준. 시가총액·우량주 판정은 스냅샷 기준.<br>
        PER/PBR 은 KRX 자격증명(KRX_ID/KRX_PW) 설정 시 표시됩니다.<br>
        ⚠️ {disclaimer}
      </footer>
    </div>
    <script>{_js()}</script>
    """

    doc = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>주가 괴리율 분석 — {_esc(title)}</title>
<style>{_css()}</style>
<script>{plotly_js}</script>
</head><body>{body}</body></html>"""

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out
