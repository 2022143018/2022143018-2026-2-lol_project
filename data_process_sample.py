import json

def get_default_match_data(match, timeline, challengers):
    data = {}

    # 게임의 기본정보
    # data는 우리가 원하는 정보를 추출하는데 필요한 틀이다.
    data["matchId"] = match["metadata"]["matchId"]
    data["gameDurationSec"] = match["info"]["gameDuration"]
    data["numFrames"] = len(timeline["info"]["frames"])
    tmp_teamId = match["info"]["participants"][0]["teamId"]
    tmp_win    = match["info"]["participants"][0]["win"]
    data["blueWin"] = tmp_win if tmp_teamId == 100 else (not tmp_win)

    # 데이터 틀 초기화
    lanes = ["TOP", "MIDDLE", "JUNGLE", "BOTTOM"]
    for lane in lanes:
        data[lane] = {"blue":{"feature": {}}, "red":{"feature":{}}}
    data["BOTTOM"]["blue"]["participantId"] = {}
    data["BOTTOM"]["blue"]["challengerPuuid"] = {}
    data["BOTTOM"]["red"]["participantId"] = {}
    data["BOTTOM"]["red"]["challengerPuuid"] = {}

    # lane별로 feature를 제외한 기본정보를 입력해준다
    # 기본정보는 participantId, challengerPuuid, teamId(Blue / Red)
    # lane을 구분하기 위해서 match["info"]["participants"]를 참조해보면
    # lane, indivisualPosition, teamPosition, role 등이 있는데
    # 서로 구분되는 역할을 명시한 키 값은 teamPosition 이다.
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
    # Feature의 설정은 여러가지로 할 수 있다.
    # 누적, 격차, 시점의 세가지 방식
    # 누적(cumulative) : 10분의 지표 (1~10분까지의 누적된 값)
    # 격차(gap, difference) : 상대방과의 차이 (블루-레드 혹은 레드-블루), 누적과 시점으로 선택도 가능
    # 시점(delta) : 증감을 계산 (10분에서 11분 사이의 챔피언에게 가한 데미지)
    # 제안 : 세 가지를 섞어서 사용하지 말고, 가급적 하나로 통일해서 쓴다.

    # 1. 누적 예시
    # 분단위로 timeline에서 minionsKilled의 누적 지표를 TOP 라인에 한해서 추출
    # "TOP" : {"blue" : { "feature": {"minionKillCum":[minionKillCumBlue], ... },
    #          "red"  : { "feature": {"minionKillCum":[minionKillCumRed], ... }}
    minionKillCumBlue, minionKillCumRed = [], []

    # 2. 격차 예시 (누적)
    # 분단위로 timeline에서 xp의 누적 지표를 블루와 레드 관점에서 격차를 계산
    # 블루 : 블루 - 레드, 레드 : 레드 - 블루
    xpDiffCumBlue, xpDiffCumRed = [], []

    # 3. 시점 예시 (1분 단위)
    # t시점에서 지난 1분간 챔피언에게 가한 데미지를 계산 : t - (t-1) 로 계산하고 t > 0 일때
    # 0분시점에서는 아무것도 없으므로 0을 넣는다. (t-1 시점의 데미지인 prior를 0으로 초기화)
    dmgDealToChampsDeltaBlue, dmgDealToChampsDeltaRed = [], []
    prior = {"blueDeal": 0, "redDeal": 0}

    # 4. 이벤트 추출
    # TOP라인의 누적 솔로킬을 계산해본다. 솔로킬은 어시스트가 없어야 한다.
    # frame["events"] 에서 type CHAMPION_KILL 인 것 중에
    # killerId == bluePid 이면서 victimId == redPid인 것으로 계산
    soloKillCumBlue, soloKillCumRed = [], []
    soloKillBlue, soloKillRed = 0, 0

    bluePid = data["TOP"]["blue"]["participantId"]
    redPid  = data["TOP"]["red"]["participantId"]

    for frame in timeline["info"]["frames"]:
        pf = frame["participantFrames"]
        events = frame["events"]

        # 1. 누적 예시 추출
        # 블루와 레드의 minionskilled(누적) 정보를 minionKillCum(Blue, Red)으로 저장
        minionKillCumBlue.append(pf[str(bluePid)]["minionsKilled"])
        minionKillCumRed.append(pf[str(redPid)]["minionsKilled"])

        # 2. 격차 예시 추출
        blue_xp = pf[str(bluePid)]["xp"]; red_xp = pf[str(redPid)]["xp"]
        xpDiffCumBlue.append(blue_xp - red_xp)
        xpDiffCumRed.append(red_xp - blue_xp)

        # 3. 시점 예시 추출
        blueDealCum = pf[str(bluePid)]["damageStats"]["totalDamageDoneToChampions"]
        redDealCum  = pf[str(redPid) ]["damageStats"]["totalDamageDoneToChampions"]
        dDealBlue = blueDealCum - prior["blueDeal"]
        dDealRed  = redDealCum  - prior["redDeal"]
        dmgDealToChampsDeltaBlue.append(dDealBlue)
        dmgDealToChampsDeltaRed.append(dDealRed)
        prior["blueDeal"] = blueDealCum
        prior["redDeal"]  = redDealCum

        # 4. 이벤트 예시 추출
        for event in events:
            if event["type"] == "CHAMPION_KILL" and "assistingParticipantIds" not in event:
                if event["killerId"] == bluePid and event["victimId"] == redPid:
                    soloKillBlue += 1
                elif event["killerId"] == redPid and event["victimId"] == bluePid:
                    soloKillRed += 1
        soloKillCumBlue.append(soloKillBlue)
        soloKillCumRed.append(soloKillRed)

    TOP_blue = {
        "minionKillCum" : minionKillCumBlue,
        "xpDiffCum" : xpDiffCumBlue,
        "dmgDealToChampsDelta" : dmgDealToChampsDeltaBlue,
        "soloKillCum": soloKillCumBlue
    }
    TOP_red = {
        "minionKillCum" : minionKillCumRed,
        "xpDiffCum" : xpDiffCumRed,
        "dmgDealToChampsDelta": dmgDealToChampsDeltaRed,
        "soloKillCum": soloKillCumRed
    }
    data["TOP"]["blue"]["feature"].update(TOP_blue)
    data["TOP"]["red"]["feature"].update(TOP_red)
    return TOP_blue, TOP_red


def main():
    with open("match_0.json", "r", encoding="utf-8") as f:
        match = json.load(f)
    with open("timeline_0.json", "r", encoding="utf-8") as f:
        timeline = json.load(f)
    with open("puuid_challengers.txt", "r", encoding="utf-8") as f:
        challengers = f.read().splitlines()

    #for m, tl in zip(match, timeline):
    m = match[0]
    tl = timeline[0]
    data = get_default_match_data(m, tl, challengers)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    TOP_blue, TOP_red = get_top_feature(m, tl, data)
    print("\n\n TOP Feature 추출 완료")
    print(json.dumps(data, indent=2, ensure_ascii=False))



if __name__ == "__main__":
    main()