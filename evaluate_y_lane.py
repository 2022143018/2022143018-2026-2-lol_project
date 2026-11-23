"""
라인별 타겟 검증: 각 라인의 격차(골드 / 경험치 / 정규화 합)만 보고 승패를 얼마나 잘 맞히는지 확인

- 시점별 검증: tci_features.csv (tci_modeling.py 가 만든 피처 파일)의 블루팀 기준 라인 격차 사용
- 경기 종료 검증: match_0.json 샘플 30경기의 라인별 goldEarned / champExperience 사용
결과는 tci_target_by_lane.md 에 저장한다.

실행: python evaluate_y_lane.py
"""
import os
import json

import pandas as pd

LANES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM"]
POS = {"TOP": ["TOP"], "JUNGLE": ["JUNGLE"], "MIDDLE": ["MIDDLE"], "BOTTOM": ["BOTTOM", "UTILITY"]}
MINUTES = [5, 10, 15, 20, 25]
CACHE = "tci_features.csv"
MATCH_SAMPLE = "match_0.json"
OUT_MD = "tci_target_by_lane.md"

out = ["## 라인별 타겟 검증\n"]

# ------------------------------------------------------------------
# 1. 시점별: 라인 격차의 부호(+ 면 블루팀 승리로 예측)로 승패 예측 정확도
# ------------------------------------------------------------------
if os.path.exists(CACHE):
    df = pd.read_csv(CACHE, usecols=["matchId", "lane", "side", "minute", "win", "goldDiff", "xpDiff"])
    # tci_modeling.py 의 add_target 과 같은 방식으로 정규화
    scale = df.groupby("lane")[["goldDiff", "xpDiff"]].std()
    df["y"] = (df["goldDiff"] / df["lane"].map(scale["goldDiff"]) +
               df["xpDiff"] / df["lane"].map(scale["xpDiff"])) / 2
    blue = df[(df["side"] == "blue") & (df["minute"].isin(MINUTES))]
    n_match = blue["matchId"].nunique()

    out.append(f"### 시점별 라인 격차로 본 승패 예측 정확도 ({n_match:,}경기)\n")
    out.append("| 라인 | 타겟 후보 | " + " | ".join(f"{t}분" for t in MINUTES) + " |")
    out.append("|---|---|" + "---|" * len(MINUTES))
    for lane in LANES:
        d = blue[blue["lane"] == lane]
        for i, (name, col) in enumerate([("골드 차이", "goldDiff"), ("경험치 차이", "xpDiff"),
                                         ("골드 + 경험치 차이 (정규화)", "y")]):
            accs = []
            for t in MINUTES:
                sub = d[d["minute"] == t]
                accs.append(f"{((sub[col] > 0) == sub['win']).mean() * 100:.1f}%")
            out.append(f"| {lane if i == 0 else ''} | {name} | " + " | ".join(accs) + " |")
    out.append("")
else:
    print(f"{CACHE} 가 없어 시점별 검증을 건너뜁니다. 먼저 tci_modeling.py 를 실행하세요.")

# ------------------------------------------------------------------
# 2. 경기 종료 시점: 샘플 경기의 라인별 최종 골드 / 경험치 우위와 승패 일치율
# ------------------------------------------------------------------
with open(MATCH_SAMPLE, encoding="utf-8") as f:
    matches = json.load(f)

rows = []
for m in matches:
    parts = m["info"]["participants"]
    blue_win = next(p["win"] for p in parts if p["teamId"] == 100)
    for lane in LANES:
        val = {100: {"gold": 0, "xp": 0}, 200: {"gold": 0, "xp": 0}}
        for p in parts:
            if p["teamPosition"] in POS[lane]:
                val[p["teamId"]]["gold"] += p["goldEarned"]
                val[p["teamId"]]["xp"] += p["champExperience"]
        rows.append({"lane": lane, "win": blue_win,
                     "gold": val[100]["gold"] - val[200]["gold"],
                     "xp": val[100]["xp"] - val[200]["xp"]})
end = pd.DataFrame(rows)

out.append(f"### 경기 종료 시점 라인별 우위와 승패 일치율 (샘플 {len(matches)}경기, `{MATCH_SAMPLE}`)\n")
out.append("| 라인 | 최종 골드(`goldEarned`) 우위 | 최종 경험치(`champExperience`) 우위 |")
out.append("|---|---|---|")
for lane in LANES:
    d = end[end["lane"] == lane]
    g = ((d["gold"] > 0) == d["win"]).mean() * 100
    x = ((d["xp"] > 0) == d["win"]).mean() * 100
    out.append(f"| {lane} | {g:.1f}% | {x:.1f}% |")
out.append("")

text = "\n".join(out)
with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write(text)
print(text)
print(f"\n저장 완료: {OUT_MD}")
