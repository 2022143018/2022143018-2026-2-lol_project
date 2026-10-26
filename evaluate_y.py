# 이 소스코드는 P_TOP(x, t; theta) 기여도 산출 수식에서
# y = f(x, t; theta) 관점의 지도학습으로 볼 때
# 적절한 답안지(라벨)의 y를 선택하는 과정을 간단하게 실습한다

# 블루/레드팀의 게임 종료시점에서의 골드 합산 수치로 승패를 얼마나 잘 예측하는지 확인한다.

import json

def main():
    with open("match_0.json", "r", encoding="utf-8") as f:
        match = json.load(f)

    # to_extract = 'goldEarned'
    to_extract = 'champExperience'

    num_acc = 0
    for m in match:
        # tbs = total blue score; trs = total red score
        tbs, trs = 0, 0
        if m['info']['participants'][0]['win']:
            bluewin = True if m['info']['participants'][0]['teamId'] == 100 else False
        else:
            bluewin = False if m['info']['participants'][0]['teamId'] == 100 else True
        for p in m['info']['participants']:
            if p['teamId'] == 100:
                tbs += p[to_extract]
            else:
                trs += p[to_extract]
        # 10명의 합산이 끝난 뒤 매치당 한 번만 비교한다
        print(f"블루팀 총 {to_extract}:{tbs}, 레드팀 총 {to_extract}:{trs}"
              f"\n{to_extract} 우위: {tbs > trs}, 블루팀 승리 여부: {bluewin}")
        num_acc += (tbs > trs) == bluewin

    print(f"{to_extract} 변수에 대한 예측정확도: {num_acc/len(match):.2f}")

            # print(f"팀 : {'블루'if p['teamId'] == 100 else '레드'}")
            # print(f"포지션: {p['teamPosition']}")
            # print(f"플레이어별 골드: {p['goldEarned']}")


if __name__ == "__main__":
    main()
