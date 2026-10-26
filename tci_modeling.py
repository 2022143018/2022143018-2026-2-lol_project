"""
라인별 타임라인 기여도 지수(TCI) 모델링 스크립트
- 입력: match_N.json, timeline_N.json (Riot API Match-V5 / Timeline)
        기본 경로: ./match_data/match_data/ (없으면 현재 폴더의 match_0.json 사용)
- 타겟 y : 분 단위 라인 맞상대와의 누적 골드 격차와 누적 경험치 격차를
          각각 정규화(z-score)한 뒤 평균한 값
- 피처 x : 라인별 과정 지표의 누적 격차 (골드/경험치 자체는 제외)
- 모델  : 선형회귀, Random Forest, Gradient Boosting(Hist), 신경망(MLP) 비교, 매치 단위 GroupKFold 교차검증
"""
import json
import numpy as np
import pandas as pd
import glob
import os
import re
import sys
import time
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error

LANES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM"]
POS2LANE = {"TOP": "TOP", "JUNGLE": "JUNGLE", "MIDDLE": "MIDDLE",
            "BOTTOM": "BOTTOM", "UTILITY": "BOTTOM"}
MIN_DURATION = 20 * 60  # 20분 이상 경기만 사용


def lane_members(match):
    """{lane: {100: [pid,...], 200: [pid,...]}}"""
    out = {l: {100: [], 200: []} for l in LANES}
    for p in match["info"]["participants"]:
        lane = POS2LANE.get(p["teamPosition"])
        if lane:
            out[lane][p["teamId"]].append(p["participantId"])
    return out


def extract_rows(match, timeline):
    members = lane_members(match)
    p0 = match["info"]["participants"][0]
    blue_win = p0["win"] if p0["teamId"] == 100 else (not p0["win"])
    pid2team = {p["participantId"]: p["teamId"] for p in match["info"]["participants"]}

    # 이벤트 누적 카운터 (participantId 단위)
    cnt = {k: {pid: 0 for pid in range(1, 11)} for k in
           ["kill", "death", "assist", "solo", "plate", "tower", "ward", "wardKill", "dragon", "herald", "baron", "grub"]}
    rows = []
    for t, frame in enumerate(timeline["info"]["frames"]):
        for ev in frame["events"]:
            typ = ev["type"]
            if typ == "CHAMPION_KILL":
                k, v = ev.get("killerId", 0), ev.get("victimId", 0)
                assists = ev.get("assistingParticipantIds", [])
                if 1 <= k <= 10: cnt["kill"][k] += 1
                if 1 <= v <= 10: cnt["death"][v] += 1
                for a in assists: cnt["assist"][a] += 1
                if not assists and 1 <= k <= 10: cnt["solo"][k] += 1
            elif typ == "TURRET_PLATE_DESTROYED":
                k = ev.get("killerId", 0)
                if 1 <= k <= 10: cnt["plate"][k] += 1
            elif typ == "BUILDING_KILL":
                for pid in [ev.get("killerId", 0)] + ev.get("assistingParticipantIds", []):
                    if 1 <= pid <= 10: cnt["tower"][pid] += 1
            elif typ == "WARD_PLACED":
                c = ev.get("creatorId", 0)
                if 1 <= c <= 10: cnt["ward"][c] += 1
            elif typ == "WARD_KILL":
                k = ev.get("killerId", 0)
                if 1 <= k <= 10: cnt["wardKill"][k] += 1
            elif typ == "ELITE_MONSTER_KILL":
                k = ev.get("killerId", 0)
                key = {"DRAGON": "dragon", "RIFTHERALD": "herald",
                       "BARON_NASHOR": "baron", "HORDE": "grub"}.get(ev.get("monsterType"))
                if key and 1 <= k <= 10: cnt[key][k] += 1

        pf = frame["participantFrames"]
        for lane in LANES:
            for side, opp in [(100, 200), (200, 100)]:
                me, en = members[lane][side], members[lane][opp]
                if not me or not en:
                    continue

                def s(pids, f):
                    return sum(f(pid) for pid in pids)

                def diff(f):
                    return s(me, f) - s(en, f)

                gold = diff(lambda p: pf[str(p)]["totalGold"])
                xp = diff(lambda p: pf[str(p)]["xp"])
                row = {
                    "matchId": match["metadata"]["matchId"], "lane": lane,
                    "side": "blue" if side == 100 else "red", "minute": t,
                    "win": blue_win if side == 100 else (not blue_win),
                    "goldDiff": gold,
                    "xpDiff": xp,
                    # ---- 공통 피처 (누적 격차) ----
                    "csDiff": diff(lambda p: pf[str(p)]["minionsKilled"]),
                    "jgCsDiff": diff(lambda p: pf[str(p)]["jungleMinionsKilled"]),
                    "dmgToChampDiff": diff(lambda p: pf[str(p)]["damageStats"]["totalDamageDoneToChampions"]),
                    "dmgTakenDiff": diff(lambda p: pf[str(p)]["damageStats"]["totalDamageTaken"]),
                    "ccTimeDiff": diff(lambda p: pf[str(p)]["timeEnemySpentControlled"]),
                    "killDiff": diff(lambda p: cnt["kill"][p]),
                    "deathDiff": diff(lambda p: cnt["death"][p]),
                    "assistDiff": diff(lambda p: cnt["assist"][p]),
                    "soloKillDiff": diff(lambda p: cnt["solo"][p]),
                    "plateDiff": diff(lambda p: cnt["plate"][p]),
                    "towerDiff": diff(lambda p: cnt["tower"][p]),
                    "wardDiff": diff(lambda p: cnt["ward"][p]),
                    "wardKillDiff": diff(lambda p: cnt["wardKill"][p]),
                    "objectiveDiff": diff(lambda p: cnt["dragon"][p] + cnt["herald"][p] + cnt["baron"][p] + cnt["grub"][p]),
                }
                rows.append(row)
    return rows


LANE_FEATURES = {
    "TOP":    ["csDiff", "dmgToChampDiff", "dmgTakenDiff", "soloKillDiff", "killDiff", "deathDiff", "plateDiff", "towerDiff"],
    "JUNGLE": ["jgCsDiff", "killDiff", "deathDiff", "assistDiff", "objectiveDiff", "wardDiff", "wardKillDiff", "ccTimeDiff"],
    "MIDDLE": ["csDiff", "dmgToChampDiff", "soloKillDiff", "killDiff", "deathDiff", "assistDiff", "plateDiff", "ccTimeDiff"],
    "BOTTOM": ["csDiff", "dmgToChampDiff", "killDiff", "deathDiff", "assistDiff", "wardDiff", "wardKillDiff", "plateDiff", "objectiveDiff"],
}


DATA_DIR = os.path.join("match_data", "match_data")
CACHE = "tci_features.csv"          # 피처 추출 결과 캐시 (재실행 시 추출 생략)
RESULT_MD = "tci_results.md"        # README에 붙여 넣을 결과 표


def find_pairs():
    """match_N.json ↔ timeline_N.json 쌍을 번호 순으로 반환"""
    pairs = []
    for mp in glob.glob(os.path.join(DATA_DIR, "match_*.json")):
        n = int(re.findall(r"match_(\d+)\.json", os.path.basename(mp))[0])
        tp = os.path.join(DATA_DIR, f"timeline_{n}.json")
        if os.path.exists(tp):
            pairs.append((n, mp, tp))
    if os.path.exists("match_0.json") and os.path.exists("timeline_0.json") \
            and not any(n == 0 for n, _, _ in pairs):
        pairs.append((0, "match_0.json", "timeline_0.json"))
    return sorted(pairs)


def build_features():
    pairs = find_pairs()
    if not pairs:
        sys.exit("데이터 파일을 찾지 못했습니다. DATA_DIR 경로를 확인하세요.")
    print(f"파일 쌍 {len(pairs)}개 처리 시작")
    total, used, frames = 0, 0, []
    t0 = time.time()
    seen = set()
    for i, (n, mp, tp) in enumerate(pairs, 1):
        with open(mp, encoding="utf-8") as f:
            matches = json.load(f)
        with open(tp, encoding="utf-8") as f:
            tl_by_id = {t["metadata"]["matchId"]: t for t in json.load(f)}
        rows = []
        for m in matches:
            mid = m["metadata"]["matchId"]
            total += 1
            if mid in seen or m["info"]["gameDuration"] < MIN_DURATION:
                continue
            tl = tl_by_id.get(mid)
            if tl is None:
                continue
            try:
                rows += extract_rows(m, tl)
                seen.add(mid); used += 1
            except (KeyError, IndexError):
                continue          # 포지션 누락 등 비정상 경기 제외
        if rows:
            frames.append(pd.DataFrame(rows))
        del matches, tl_by_id
        if i % 50 == 0 or i == len(pairs):
            print(f"  [{i}/{len(pairs)}] 전체 {total}경기 / 사용 {used}경기 / {time.time()-t0:.0f}초")
    df = pd.concat(frames, ignore_index=True)
    df = df[df["minute"] > 0]
    df.to_csv(CACHE, index=False)
    print(f"피처 저장 완료: {CACHE} (총 {total}경기 중 20분 이상 {used}경기)")
    return df


SUB_TRAIN = 300_000   # RF·MLP는 학습 시간이 길어 fold별 학습 샘플을 30만 개로 제한 (평가는 전체)


def make_models():
    return {
        "LR":  LinearRegression(),
        "RF":  RandomForestRegressor(n_estimators=100, max_depth=12, min_samples_leaf=20,
                                     n_jobs=-1, random_state=42),
        "GB":  HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05,
                                             max_leaf_nodes=31, random_state=42),
        "MLP": make_pipeline(StandardScaler(),
                             MLPRegressor(hidden_layer_sizes=(64, 32), activation="relu",
                                          learning_rate_init=1e-3, batch_size=512, max_iter=50,
                                          early_stopping=True, n_iter_no_change=5, random_state=42)),
    }


def add_target(df):
    """골드 격차·경험치 격차를 라인별 표준편차로 정규화(z-score)한 뒤 평균
    (격차는 블루/레드 대칭이라 평균이 0이므로 표준편차로만 나눔)"""
    scale = df.groupby("lane")[["goldDiff", "xpDiff"]].std()
    g = df["goldDiff"] / df["lane"].map(scale["goldDiff"])
    x = df["xpDiff"] / df["lane"].map(scale["xpDiff"])
    df["y"] = (g + x) / 2
    return df, scale


def main():
    if os.path.exists(CACHE) and "--rebuild" not in sys.argv:
        df = pd.read_csv(CACHE, nrows=1)
        if "goldDiff" not in df.columns:
            print("이전 버전 캐시입니다. 피처를 다시 추출합니다.")
            df = build_features()
        else:
            print(f"캐시 사용: {CACHE} (다시 추출하려면 --rebuild)")
            df = pd.read_csv(CACHE)
    else:
        df = build_features()
    df, scale = add_target(df)
    n_match = df.matchId.nunique()
    print(f"매치 수: {n_match}, 샘플(라인×진영×분) 수: {len(df)}")
    out = [f"## TCI 결과 (매치 {n_match:,}경기)\n"]

    out.append("### 정규화 기준 (라인별 표준편차)\n")
    out.append("| 라인 | 골드 격차 σ | 경험치 격차 σ |")
    out.append("|---|---|---|")
    for lane in LANES:
        out.append(f"| {lane} | {scale.loc[lane,'goldDiff']:,.0f} | {scale.loc[lane,'xpDiff']:,.0f} |")
    out.append("")

    # 타겟 검증: 팀 단위 격차 부호로 승패 예측 정확도 (골드만 / 경험치만 / 정규화 합)
    team = df[df.side == "blue"].groupby(["matchId", "minute"]).agg(
        gold=("goldDiff", "sum"), xp=("xpDiff", "sum"), y=("y", "sum"),
        win=("win", "first")).reset_index()
    mins = [5, 10, 15, 20, 25]
    out.append("### 타겟 검증: 팀 격차 부호 기반 승패 예측 정확도\n")
    out.append("| 타겟 후보 | " + " | ".join(f"{t}분" for t in mins) + " |")
    out.append("|---|" + "---|" * len(mins))
    for name, col in [("골드 격차", "gold"), ("경험치 격차", "xp"), ("정규화 (골드+경험치) 격차", "y")]:
        accs = []
        for t in mins:
            sub = team[team.minute == t]
            accs.append(f"{((sub[col] > 0) == sub.win).mean()*100:.1f}%")
        out.append(f"| {name} | " + " | ".join(accs) + " |")
    out.append("")

    gkf = GroupKFold(n_splits=5)
    summary = []
    for lane in LANES:
        d = df[df.lane == lane].reset_index(drop=True)
        cols = LANE_FEATURES[lane] + ["minute"]
        X, y, g = d[cols].to_numpy(float), d["y"].to_numpy(), d["matchId"]
        preds = {k: np.zeros(len(d)) for k in make_models()}
        rng = np.random.default_rng(42)
        for fold, (tr, te) in enumerate(gkf.split(X, y, g), 1):
            for name, model in make_models().items():
                idx = tr if name in ("LR", "GB") or len(tr) <= SUB_TRAIN else rng.choice(tr, SUB_TRAIN, replace=False)
                t0 = time.time()
                model.fit(X[idx], y[idx])
                preds[name][te] = model.predict(X[te])
                print(f"  {lane} fold {fold}/5 {name} 완료 ({time.time()-t0:.0f}초)")
        out.append(f"### {lane} 모델 비교 (5-fold GroupKFold, 샘플 {len(d):,}개, y 표준편차 {y.std():.3f})\n")
        out.append("| 모델 | MSE | RMSE | MAE | R² |")
        out.append("|---|---|---|---|---|")
        best = None
        for name, p in preds.items():
            mse = mean_squared_error(y, p); r2 = r2_score(y, p)
            out.append(f"| {name} | {mse:.4f} | {mse**0.5:.4f} | {mean_absolute_error(y, p):.4f} | {r2:.4f} |")
            if best is None or mse < best[1]:
                best = (name, mse, r2)
        # 최종 모델(GB 기준) 순열 중요도
        gb_full = make_models()["GB"].fit(X, y)
        s_idx = rng.choice(len(d), min(len(d), 100_000), replace=False)
        pi = permutation_importance(gb_full, X[s_idx], y[s_idx], n_repeats=3, random_state=42, n_jobs=-1)
        imp = sorted(zip(cols, pi.importances_mean / pi.importances_mean.sum()), key=lambda z: -z[1])[:3]
        imp_s = ", ".join(f"{c}({v:.2f})" for c, v in imp)
        out.append(f"\n- 최저 MSE 모델: **{best[0]}** (R² {best[2]:.4f})")
        out.append(f"- GB 순열 중요도 상위 3개: {imp_s}\n")
        summary.append(f"| {lane} | {best[0]} | {best[1]:.4f} | {best[2]:.4f} | {imp_s} |")
        print("\n".join(out[-12:]))

    out.append("### 라인별 요약\n")
    out.append("| 라인 | 최종 모델 | MSE | R² | 주요 피처(GB 순열 중요도) |")
    out.append("|---|---|---|---|---|")
    out += summary
    with open(RESULT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("\n" + "\n".join(out))
    print(f"\n결과 저장 완료: {RESULT_MD}")


if __name__ == "__main__":
    main()
