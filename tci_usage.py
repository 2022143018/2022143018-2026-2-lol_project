"""
TCI 모델 활용 예시 스크립트 (tci_modeling.py 실행 후 사용)
1) 라인별 최종 모델의 교차검증(out-of-fold) 예측값으로 TCI를 계산
   - 학습에 쓰지 않은 경기에 대한 예측값만 사용하므로 과대평가가 없음
2) 예시 경기 1개의 분 단위 TCI 곡선 그래프 (tci_example_<matchId>.png)
3) 챌린저 소환사별 라인 평균 TCI와 승률 비교 (tci_player_scatter.png, tci_usage_results.md)
"""
import json
import os
import sys
import time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.model_selection import GroupKFold

from tci_modeling import (CACHE, LANES, LANE_FEATURES, POS2LANE, SUB_TRAIN,
                          add_target, find_pairs, make_models)

FINAL_MODEL = {"TOP": "MLP", "JUNGLE": "MLP", "MIDDLE": "MLP", "BOTTOM": "GB"}  # 3.2절 결과
EXAMPLE_MATCH = "KR_7461530602"   # 그림 1과 같은 경기 (없으면 첫 경기)
TCI_MINUTE = 15                   # 소환사 비교 기준 시점 (라인전 종료 무렵)
MIN_GAMES = 20                    # 소환사 비교에 필요한 최소 경기 수
OUT_MD = "tci_usage_results.md"


def oof_predict(df):
    """라인별 최종 모델로 5-fold out-of-fold 예측 → df['tci']"""
    df["tci"] = np.nan
    rng = np.random.default_rng(42)
    for lane in LANES:
        mask = (df.lane == lane).to_numpy()
        d = df[mask]
        X = d[LANE_FEATURES[lane] + ["minute"]].to_numpy(float)
        y = d["y"].to_numpy()
        pred = np.zeros(len(d))
        name = FINAL_MODEL[lane]
        for fold, (tr, te) in enumerate(GroupKFold(n_splits=5).split(X, y, d["matchId"]), 1):
            idx = tr if name in ("LR", "GB") or len(tr) <= SUB_TRAIN else rng.choice(tr, SUB_TRAIN, replace=False)
            t0 = time.time()
            model = make_models()[name].fit(X[idx], y[idx])
            pred[te] = model.predict(X[te])
            print(f"  {lane}({name}) fold {fold}/5 완료 ({time.time()-t0:.0f}초)")
        df.loc[mask, "tci"] = pred
    return df


def plot_example(df, match_id):
    d = df[df.matchId == match_id]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    for ax, lane in zip(axes.flat, LANES):
        for side, color in [("blue", "#2f6fdf"), ("red", "#d9443a")]:
            s = d[(d.lane == lane) & (d.side == side)].sort_values("minute")
            ax.plot(s.minute, s.tci, color=color, lw=2, label=f"{side} TCI (predicted)")
            ax.plot(s.minute, s.y, color=color, lw=1, ls="--", alpha=0.6, label=f"{side} y (actual)")
        ax.axhline(0, color="gray", lw=0.8)
        ax.set_title(f"{lane} ({FINAL_MODEL[lane]})")
        ax.grid(alpha=0.3)
    axes[0, 0].legend(fontsize=8, loc="upper left")
    for ax in axes[1]:
        ax.set_xlabel("Game time (min)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Normalized gold+XP gap")
    win = "Blue" if d[d.side == "blue"].win.iloc[0] else "Red"
    fig.suptitle(f"Timeline Contribution Index - {match_id} (winner: {win})", fontsize=13)
    fig.tight_layout()
    path = f"tci_example_{match_id}.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def player_map(match_ids, challengers):
    """(matchId, lane, side) → 챌린저 puuid 목록"""
    rows = []
    for _, mp, _ in find_pairs():
        with open(mp, encoding="utf-8") as f:
            matches = json.load(f)
        for m in matches:
            mid = m["metadata"]["matchId"]
            if mid not in match_ids:
                continue
            for p in m["info"]["participants"]:
                lane = POS2LANE.get(p["teamPosition"])
                if lane and p["puuid"] in challengers:
                    rows.append((mid, lane, "blue" if p["teamId"] == 100 else "red", p["puuid"]))
    return pd.DataFrame(rows, columns=["matchId", "lane", "side", "puuid"]).drop_duplicates()


def main():
    if not os.path.exists(CACHE):
        sys.exit("tci_features.csv가 없습니다. tci_modeling.py를 먼저 실행하세요.")
    df, _ = add_target(pd.read_csv(CACHE))
    print(f"매치 수: {df.matchId.nunique()}")
    df = oof_predict(df)
    out = ["## TCI 활용 결과\n"]

    # 1) 예시 경기
    mid = EXAMPLE_MATCH if EXAMPLE_MATCH in set(df.matchId) else df.matchId.iloc[0]
    path = plot_example(df, mid)
    print(f"예시 그래프 저장: {path}")
    out.append(f"### 예시 경기: {mid} (`{path}`)\n")
    out.append("| 라인 | 블루 TCI 10분 | 블루 TCI 15분 | 블루 TCI 20분 | 블루 TCI 최종 |")
    out.append("|---|---|---|---|---|")
    d = df[(df.matchId == mid) & (df.side == "blue")]
    for lane in LANES:
        s = d[d.lane == lane].set_index("minute").tci
        v = [f"{s.get(t, np.nan):+.2f}" for t in (10, 15, 20)] + [f"{s.iloc[-1]:+.2f}"]
        out.append(f"| {lane} | " + " | ".join(v) + " |")
    out.append(f"\n블루팀 승리 여부: {bool(d.win.iloc[0])}\n")

    # 2) 소환사별 평균 TCI
    with open("puuid_challengers.txt", encoding="utf-8") as f:
        challengers = set(f.read().split())
    at = df[df.minute == TCI_MINUTE][["matchId", "lane", "side", "tci", "win"]]
    pm = player_map(set(at.matchId), challengers)
    pl = pm.merge(at, on=["matchId", "lane", "side"])
    agg = pl.groupby(["lane", "puuid"]).agg(games=("tci", "size"), tci=("tci", "mean"),
                                           winrate=("win", "mean")).reset_index()
    min_games = MIN_GAMES if (agg.games >= MIN_GAMES).any() else 1
    agg = agg[agg.games >= min_games]
    # 진 경기에서의 TCI (승패와 무관한 개인 경기력 확인용)
    lose = pl[~pl.win].groupby(["lane", "puuid"]).tci.mean().rename("tci_lose")
    agg = agg.join(lose, on=["lane", "puuid"])

    out.append(f"### 챌린저 소환사별 {TCI_MINUTE}분 시점 평균 TCI ({min_games}경기 이상)\n")
    out.append("| 라인 | 소환사 수 | 평균 TCI–승률 상관계수 |")
    out.append("|---|---|---|")
    fig, axes = plt.subplots(1, 4, figsize=(16, 4), sharey=True)
    for ax, lane in zip(axes, LANES):
        a = agg[agg.lane == lane]
        r = a.tci.corr(a.winrate) if len(a) > 2 else np.nan
        out.append(f"| {lane} | {len(a)} | {r:.3f} |")
        ax.scatter(a.tci, a.winrate * 100, s=12, alpha=0.6)
        ax.set_title(f"{lane} (r={r:.2f}, n={len(a)})")
        ax.set_xlabel(f"Mean TCI @ {TCI_MINUTE} min")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Win rate (%)")
    fig.tight_layout()
    fig.savefig("tci_player_scatter.png", dpi=200)
    plt.close(fig)
    out.append("\n(그래프: `tci_player_scatter.png`)\n")

    for lane in LANES:
        a = agg[agg.lane == lane].sort_values("tci", ascending=False).head(5)
        out.append(f"#### {lane} 평균 TCI 상위 5명\n")
        out.append("| 순위 | 소환사(puuid 앞 8자리) | 경기 수 | 평균 TCI | 진 경기 평균 TCI | 승률 |")
        out.append("|---|---|---|---|---|---|")
        for i, r in enumerate(a.itertuples(), 1):
            out.append(f"| {i} | {r.puuid[:8]} | {r.games} | {r.tci:+.3f} | {'-' if pd.isna(r.tci_lose) else format(r.tci_lose, '+.3f')} | {r.winrate*100:.1f}% |")
        out.append("")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"\n결과 저장 완료: {OUT_MD}")


if __name__ == "__main__":
    main()
