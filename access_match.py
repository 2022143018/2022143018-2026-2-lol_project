import json
import datetime

def main():
    with open("match_0.json", "r", encoding="utf-8") as f:
        match = json.load(f)

    print("매치의 개수 : ",len(match))
    print("match 변수의 타입 : ", type(match))
    print("하나의 match의 타입 : ", type(match[0]))

    single_match = match[0]
    #print(single_match.keys())
    #print(single_match["info"].keys())

    #import datetime
    time = single_match["info"]["gameCreation"]
    print(time)
    time = time // 1000
    date = datetime.datetime.fromtimestamp(time, datetime.UTC)
    print(date)

    metadata = single_match["metadata"]
    info = single_match["info"]

    print("\n=== LOL match 데이터 정보===")
    print(f"Match Id: {metadata['matchId']}")
    print(f"게임 생성 시간: {date.strftime('%Y년 %m월 %d일 %H시 %M분')}")
    print(f"게임 플레이 시간: {info['gameDuration']//60}분 {info['gameDuration']%60}초")
    paticipants = info["participants"]
    p = paticipants[0]
    #print(p.keys())
    # 블루(100)와 레드팀(200)의 승패 출력
    if p["win"]:
        winteam = "블루" if p["teamId"] == 100 else "레드"
    else:
        winteam = "레드"if p["teamId"] == 200 else "블루"
    print(f"승리 팁: {winteam}")

    # for 루프 한줄만 추가하여 모든 플레이어 정보를 출력해봅시다.
    # 11시 43분까지
    for p in paticipants:
        print("\n== 플레이어 정보 ==")
        print(f"포지션: {p['teamPosition']}")
        print(f"팀: {'블루' if p['teamId'] == 100 else '레드'}")
        print(f"챔피언: {p['championName']}")
        k = p['kills']; d = p['deaths']; a = p['assists']
        kda = (k+a) / (1 if d == 0 else d)
        print(f"K/D/A: {k}/{d}/{a}, KDA: {kda}")
        print(f"챔피언에게 가한 대미지: {p['totalDamageDealtToChampions']}")
        print(f"받은 총 데미지: {p['totalDamageTaken']}")
        print(f"총 골드 확득량: {p['goldEarned']}")
        print(f"총 경험치 획득량: {p['champExperience']}")
        print(f"총 미니언 처치수: {p['totalMinionsKilled']}")
        print(f"타임라인 연계 정보: {p['participantId']}")



if __name__ == "__main__":
    main()
