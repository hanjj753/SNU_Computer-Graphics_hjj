# report 

- Bspline control point 직접 움직일 수 있게 해서 track 그림
- HW2에서 trackball 조금 이상해서 수정
- u = u(s) 계산할 떄 biseciton algorithm 사용
- u, t, v 표시 되게
- frenet frame -> 첫번째는 12p, 그 다음부터 13p 내용
- 제가 제멋대로 type hint 적은 것도 있고 안 적은 것도 있어서 읽기 어려울 수 있을 것 같습니다

## 비율 계산
- 최대 h가 대충 2.얼마
- 일반적인 롤코 높이 30m, g= 9.8m/s^2, 최고 높이서 1.5m/s
- h=3으로 해서 0.1 곱하면 g = 0.98/s^2, 최고 높이서 0.15/s
- gh + 0.5v^2 = 2.95125

## 비교

- moving coordinate frame은 한 바퀴 돌고 오고 나면 오차가 심하게 발생 (당연히 처음 B랑 나중 B랑 같다는 수학적 보장이 없음)