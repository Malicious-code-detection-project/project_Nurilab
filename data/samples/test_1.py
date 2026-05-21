# ====
"""
1. 청소기 이동
- 로봇은 순서대로 움직인다 => input 된 순서대로
- 이동 거리가 가장 가까운 오염된 격자로 이동.
- 상하좌우로 인접한 격자를 한 칸씩 이동
- 우선순위 : 이동거리, 행, 열

2. 청소
- 청소기가 바라보고 있는 방향을 기준으로 본인이 위치한 격자, 왼쪽, 위쪽, 오른쪽 격자 청소
- 청소할 수 있는 4가지 격자에서 청소할 수 있는 먼지량이 가장 큰 방향에서 청소를 시작
- 격자마다 청소할 수 있는 최대 먼지량은 20
- 우선순위 : 오른쪽, 아래쪽, 왼쪽, 위쪽
- 청소기마다 순서대로 진행

3. 먼지 축적
- 먼지가 있는 모든 격자에 + 5

4. 먼지 확산
- 깨끗한 격자 : 주변 4방향 격자의 먼지량 합을 10으로 나눈 값만큼 먼지가 확산
- 상하좌우 다 더해서 10으로 나눈 값 이다?
- 소수점 아래 수는 버린다.

5. 출력
- 전체 공간의 총 먼지량을 출력
- 먼지가 있는 곳이 없으면 0 출력
"""
from collections import deque

# 전역 변수
N, K, L = map(int, input().split())
maps = [list(map(int, input().split())) for _ in range(N)]
robots = []

for _ in range(K) :
    a, b = map(int, input().split())
    robots.append([a-1, b-1])

DIRECTION = [[-1, 0], [1, 0], [0, -1], [0, 1]]
ROBOT_DIRECTION = [
    [[0, 0], [-1, 0], [0, 1], [1, 0]],     # 오른쪽
    [[0, 0], [1, 0], [0, -1], [0, 1]],     # 아래쪽
    [[0, 0], [-1, 0], [0, -1], [1, 0]],     # 왼쪽
    [[0, 0], [-1, 0], [0, -1], [0, 1]],     # 위쪽
]    

def robot_move(robots: list[list[int]], idx: int) :
    """
    robot : 전체 로봇 좌표
    idx : 현재 선택된 로봇 인덱스
    """
    robot_q = deque()
    visited = [[0] * N for _ in range(N)]   # 방문
    for robot in robots :
        visited[robot[0]][robot[1]] = 1     # 현재 로봇 있는 자리는 이동 불가
    
    res_list = []               # 여기에는 이동 가능한 좌표를 넣을거임.
    robot_q.append(robots[idx]) # 현재 로봇 좌표 

    while robot_q :
        # early stop
        if len(res_list) != 0 :
            break
        len_q = len(robot_q)    # flood fill 을 위한 length
        for _ in range(len_q) : # 현재 queue 만큼 반복
            ci, cj = robot_q.popleft()

            # stop 위치 잡기
            if maps[ci][cj] > 0 :       # 현재 위치에 먼지가 있으면
                res_list.append([ci, cj])   # 리스트에 넣는다.
            
            # 다음 이동 예정지 선택
            # 네 방향, 범위내, 미방문, 조건: 벽이 아닌 곳.
            for di, dj in DIRECTION :
                ni, nj = ci + di, cj + dj

                if 0 <= ni < N and 0 <= nj < N and maps[ni][nj] >= 0 and visited[ni][nj] == 0 :
                    robot_q.append([ni, nj])    
                    visited[ni][nj] = 1
        
    # 이동 위치가 존재하면 sort후 return
    if len(res_list) != 0 :
        res_list.sort()
        return res_list[0]
    # 아니면 현재 위치 그대로 유지
    else :
        return robots[idx]

if __name__ == '__main__' :
    for _ in range(L) :
        # 1. 로봇 이동
        for idx in range(len(robots)) :
            cur_robot = robot_move(robots, idx)
            robots[idx] = cur_robot
        
        # 2. 청소
        for idx in range(len(robots)) :
            clean_tbl = []      # 어느 방향으로 청소할까?
            for clean_idx in range(len(ROBOT_DIRECTION)) :
                curr_clean = 0  # 현재 범위에서 확인 가능한 먼지량
                for di, dj in ROBOT_DIRECTION[clean_idx] :  
                    ni, nj = robots[idx][0] + di, robots[idx][1] + dj
                    if 0 <= ni < N and 0 <= nj < N and maps[ni][nj] != -1:
                        curr_clean += min(20, maps[ni][nj])

                # 먼지량, (우하좌상) 인덱스로 들어가게됨.
                clean_tbl.append([curr_clean, clean_idx])

            # 우선순위 : 먼지량이 많을수록, 인덱스가 작을수록
            clean_tbl.sort(key=lambda x:(-x[0], x[1]))
            select_idx = clean_tbl[0][1]

            # 선택된 방향에서 정해진 격자만큼 최대 20 감소.
            for di, dj in ROBOT_DIRECTION[select_idx] :
                ni, nj = robots[idx][0] + di, robots[idx][1] + dj
                if 0 <= ni < N and 0 <= nj < N and maps[ni][nj] != -1 :
                    maps[ni][nj] = max(0, maps[ni][nj] - 20)

        # 3. 먼지 축적
        for i in range(N) :
            for j in range(N) :
                if maps[i][j] > 0 :
                    maps[i][j] += 5

        # 4. 먼지 확산
        temp = [[0] * N for _ in range(N)]
        for i in range(N) :
            for j in range(N) :
                if maps[i][j] == 0 :
                    dust_0 = 0          # 현재 위치의 먼지가 0이면 먼지 확산 후보군.
                    for di, dj in DIRECTION :
                        ni, nj = i + di, j + dj
                        if 0 <= ni < N and 0 <= nj < N and maps[ni][nj] > 0 :
                            dust_0 += maps[ni][nj]  # 현재 위치에서 4방향에 있는 먼지량을 다 더함.

                    temp[i][j] = (dust_0//10)   # 위에서 구한 먼지량을 10으로 나누고 소수점 버림.

        for i in range(N) :
            for j in range(N) :
                if temp[i][j] > 0 :
                    maps[i][j] += temp[i][j]    # 확산된 먼지를 maps에 추가함.

        # 5. 먼지 출력
        dust_cnt = 0
        for i in range(N) :
            for j in range(N) :
                if maps[i][j] > 0 :
                    dust_cnt += maps[i][j]

        print(dust_cnt)
        if dust_cnt == 0 :
            break
