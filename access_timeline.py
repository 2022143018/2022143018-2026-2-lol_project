import json

def main():
    with open("match_0.json", "r", encoding="utf-8") as f:
        match = json.load(f)
    with open("timeline_0.json", "r", encoding="utf-8") as f:
        timeline = json.load(f)


    m = match[0]
    tl = timeline[0]

    print(f"매치 아이디 정보: 매치-{m['metadata']['matchId']}, 타임라인-{tl['metadata']['matchId']}")

    p = m['info']['participants'][0]
    pid = p['participantId']
    print(f"챔피언: {p['championName']}")
    print(f"아이디: {pid}")
    print(f"포지션: {p['teamPosition']}, 팀: {p['teamId']}")

    to_extract = 'totalGold'
    for j, frame in enumerate(tl['info']['frames']):
        score = frame['participantFrames'][str(pid)][to_extract]
        print(f"{j}분의 {to_extract}: {score}")


if __name__ == '__main__':
    main()