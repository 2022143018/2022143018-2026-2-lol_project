import json
import matplotlib.pyplot as plt


def get_default_match_data(match, timeline, challengers):
    data = {}

    # 게임의 기본정보
    data["matchId"] = match["metadata"]["matchId"]
    data["gameDurationSec"] = match["info"]["gameDuration"]
    data["numFrames"] = len(timeline["info"]["frames"])
    tmp_teamId = match["info"]["participants"][0]["teamId"]
    tmp_win = match["info"]["participants"][0]["win"]
    data["blueWin"] = tmp_win if tmp_teamId == 100 else (not tmp_win)

    # 데이터 틀 초기화
    lanes = ["TOP", "MIDDLE", "JUNGLE", "BOTTOM"]
    for lane in lanes:
        data[lane] = {"blue": {"feature": {}}, "red": {"feature": {}}}
    data["BOTTOM"]["blue"]["participantId"] = {}
    data["BOTTOM"]["blue"]["challengerPuuid"] = {}
    data["BOTTOM"]["red"]["participantId"] = {}
    data["BOTTOM"]["red"]["challengerPuuid"] = {}

    for p in match["info"]["participants"]:
        team = p["teamId"]
        side = "blue" if team == 100 else "red"
        pos = p["teamPosition"]
        pid = p["participantId"]
        puid = p["puuid"]
        is_chall = puid in challengers
        chall = puid if is_chall else None

        if pos == "TOP":
            data["TOP"][side]["teamId"] = team
            data["TOP"][side]["participantId"] = pid
            data["TOP"][side]["challengerPuuid"] = chall
        elif pos == "MIDDLE":
            data["MIDDLE"][side]["teamId"] = team
            data["MIDDLE"][side]["participantId"] = pid
            data["MIDDLE"][side]["challengerPuuid"] = chall
        elif pos == "JUNGLE":
            data["JUNGLE"][side]["teamId"] = team
            data["JUNGLE"][side]["participantId"] = pid
            data["JUNGLE"][side]["challengerPuuid"] = chall
        elif pos == "BOTTOM":
            data["BOTTOM"][side]["teamId"] = team
            data["BOTTOM"][side]["participantId"]["ADC"] = pid
            data["BOTTOM"][side]["challengerPuuid"]["ADC"] = chall
        elif pos == "UTILITY":
            data["BOTTOM"][side]["teamId"] = team
            data["BOTTOM"][side]["participantId"]["SPT"] = pid
            data["BOTTOM"][side]["challengerPuuid"]["SPT"] = chall
        else:
            print(f"Something error: {pos}")
            pass

    return data


def get_top_feature(match, timeline, data):
    minionKillCumBlue, minionKillCumRed = [], []
    xpDiffCumBlue, xpDiffCumRed = [], []
    dmgDealToChampsDeltaBlue, dmgDealToChampsDeltaRed = [], []
    prior = {"blueDeal": 0, "redDeal": 0}

    soloKillCumBlue, soloKillCumRed = [], []
    soloKillBlue, soloKillRed = 0, 0

    bluePid = data["TOP"]["blue"]["participantId"]
    redPid = data["TOP"]["red"]["participantId"]

    for frame in timeline["info"]["frames"]:
        pf = frame["participantFrames"]
        events = frame["events"]

        # 1. 누적 CS
        minionKillCumBlue.append(pf[str(bluePid)]["minionsKilled"])
        minionKillCumRed.append(pf[str(redPid)]["minionsKilled"])

        # 2. XP 격차
        blue_xp = pf[str(bluePid)]["xp"]
        red_xp = pf[str(redPid)]["xp"]
        xpDiffCumBlue.append(blue_xp - red_xp)
        xpDiffCumRed.append(red_xp - blue_xp)

        # 3. 딜량 (Delta)
        blueDealCum = pf[str(bluePid)]["damageStats"][
            "totalDamageDoneToChampions"
        ]
        redDealCum = pf[str(redPid)]["damageStats"][
            "totalDamageDoneToChampions"
        ]
        dDealBlue = blueDealCum - prior["blueDeal"]
        dDealRed = redDealCum - prior["redDeal"]
        dmgDealToChampsDeltaBlue.append(dDealBlue)
        dmgDealToChampsDeltaRed.append(dDealRed)
        prior["blueDeal"] = blueDealCum
        prior["redDeal"] = redDealCum

        # 4. 솔로킬 누적
        for event in events:
            if (
                event["type"] == "CHAMPION_KILL"
                and "assistingParticipantIds" not in event
            ):
                if event["killerId"] == bluePid and event["victimId"] == redPid:
                    soloKillBlue += 1
                elif (
                    event["killerId"] == redPid and event["victimId"] == bluePid
                ):
                    soloKillRed += 1
        soloKillCumBlue.append(soloKillBlue)
        soloKillCumRed.append(soloKillRed)

    TOP_blue = {
        "minionKillCum": minionKillCumBlue,
        "xpDiffCum": xpDiffCumBlue,
        "dmgDealToChampsDelta": dmgDealToChampsDeltaBlue,
        "soloKillCum": soloKillCumBlue,
    }
    TOP_red = {
        "minionKillCum": minionKillCumRed,
        "xpDiffCum": xpDiffCumRed,
        "dmgDealToChampsDelta": dmgDealToChampsDeltaRed,
        "soloKillCum": soloKillCumRed,
    }
    data["TOP"]["blue"]["feature"].update(TOP_blue)
    data["TOP"]["red"]["feature"].update(TOP_red)
    return TOP_blue, TOP_red


# ==========================================
# 새로 추가된 그래프 시각화 함수
# ==========================================
def plot_top_features(data):
    """
    추출된 TOP 라인 지표(XP 차이, CS 비교)를 그래프로 그립니다.
    """
    xp_diff = data["TOP"]["blue"]["feature"]["xpDiffCum"]
    blue_cs = data["TOP"]["blue"]["feature"]["minionKillCum"]
    red_cs = data["TOP"]["red"]["feature"]["minionKillCum"]

    minutes = list(range(len(xp_diff)))

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    # 1번째 서브플롯: XP 차이 (양수: 블루 우세 / 음수: 레드 우세)
    axes[0].plot(
        minutes,
        xp_diff,
        color="#3498db",
        linewidth=2,
        label="XP Diff (Blue - Red)",
    )
    axes[0].axhline(
        0, color="black", linestyle="--", alpha=0.6, label="Even (0 Diff)"
    )
    axes[0].set_title(
        f"TOP Lane Feature Analysis - Match: {data['matchId']}",
        fontsize=13,
        pad=10,
    )
    axes[0].set_ylabel("XP Difference", fontsize=11)
    axes[0].legend(loc="upper left")
    axes[0].grid(True, alpha=0.3)

    # 2번째 서브플롯: 블루 vs 레드 누적 CS 비교
    axes[1].plot(
        minutes,
        blue_cs,
        color="blue",
        linewidth=2,
        label="Blue TOP CS (Minions)",
    )
    axes[1].plot(
        minutes, red_cs, color="red", linewidth=2, label="Red TOP CS (Minions)"
    )
    axes[1].set_xlabel("Game Time (Minutes)", fontsize=11)
    axes[1].set_ylabel("Minions Killed", fontsize=11)
    axes[1].legend(loc="upper left")
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()

    # 이미지 저장 및 화면 출력
    filename = f"top_analysis_{data['matchId']}.png"
    plt.savefig(filename, dpi=300)
    print(f"\n-> 그래프 이미지가 저장되었습니다: {filename}")
    plt.show()


def main():
    with open("match_0.json", "r", encoding="utf-8") as f:
        match = json.load(f)
    with open("timeline_0.json", "r", encoding="utf-8") as f:
        timeline = json.load(f)
    with open("puuid_challengers.txt", "r", encoding="utf-8") as f:
        challengers = f.read().splitlines()

    m = match[0]
    tl = timeline[0]

    # 1. 기본 데이터 틀 가져오기
    data = get_default_match_data(m, tl, challengers)

    # 2. TOP 라인 Feature 추출
    TOP_blue, TOP_red = get_top_feature(m, tl, data)

    print("\n\n TOP Feature 추출 완료")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    # 3. 그래프 출력 함수 호출 (추가된 부분)
    plot_top_features(data)


if __name__ == "__main__":
    main()