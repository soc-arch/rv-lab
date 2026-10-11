# RV Lab

C/assembly 프로그램을 RISC-V CPU에서 실행하고, 정답과 실제 RTL 동작을 확인하는
연구실 실습입니다. 각 Lab은 **따라 할 명령 → 예상 결과 → 확인 질문 → 제출물** 순서로
진행합니다. 실습 코어는 독립된 teaching RTL이며 학생은 먼저 소프트웨어와 관찰에
집중합니다.

**[HTML 실습 안내](https://soc-arch.github.io/rv-lab/)** ·
**[환경 준비](docs/setup.md)** · **[전체 실습 순서](docs/course/index.md)**

## 시작하기

Linux 터미널에서 실행합니다. 필요한 도구가 없는 경우 [환경 준비](docs/setup.md)를
먼저 읽으세요. 연구실 서버에서는 조교가 제공한 도구 환경을 선택합니다.
Voyager에서는 새 터미널마다 `source /tools/rv-lab/env.sh`를 실행하세요.

```sh
git clone https://github.com/soc-arch/rv-lab.git ~/rv-lab
cd ~/rv-lab
make doctor
make compare APP=01_arithmetic
```

`compare`는 **동일한 ELF**를 Spike와 Verilator RTL에서 실행하고 전체 결과를
비교합니다. `COMPARE PASS`를 확인한 뒤 Lab 01부터 진행하세요. 처음 RTL 실행은
시뮬레이터를 빌드하므로 시간이 더 걸립니다.

| Lab | 실습 내용 | 확인할 결과 |
| --- | --- | --- |
| [01 — Setup and baseline](docs/course/01-setup.md) | 환경 점검·첫 비교·기준 회귀 | 도구 버전과 passing baseline |
| [02 — Your first main](docs/course/02-first-main.md) | 나의 C 프로그램·정답 검사·출력 | 입력 변경 전후 정답과 PASS |
| [03 — Debugging](docs/course/03-debugging.md) | 의도한 실패를 관찰하고 수정 | 실제값·기대값·수정 근거 |
| [04 — Cycle viewer](docs/course/04-cycle-viewer.md) | 내 프로그램 등록·명령별 RTL 관찰 | load·branch·store의 동작 |
| [05 — Performance](docs/course/05-performance.md) | O0/O2·ROI·CSR 측정 | 같은 정답의 cycles·retirements·CPI |
| [06 — Memory timing](docs/course/06-memory.md) | 지연·backpressure 실험 | 전송 대기와 실행시간 차이 |
| [07 — Images](docs/course/07-images.md) | 이미지 처리·pixel 정답 검증 | 출력 이미지와 kernel 측정 |
| [08 — Reproducible project](docs/course/08-project.md) | 기준/개선 버전 비교·증거 모으기 | 다른 학생이 재현할 수 있는 보고서 |

HTML 실습 안내는 읽는 문서입니다. 실제 시뮬레이션과 결과 생성은 자신의 작업
공간에서 실행합니다. Lab 01 안내대로 실행하면 결과는
`http://127.0.0.1:8771/`에서 볼 수 있습니다. 원격 서버를 사용할 때는
[SSH 연결 안내](docs/setup.md#6-open-remote-results-through-ssh)를 따르세요.

추가 참고: [학생 작업 흐름](docs/student-workflow.md),
[성능 측정 기준](docs/performance-monitoring.md),
[검증·재현 방법](docs/reproducibility.md),
[공개 소스 snapshot](provenance/snapshot.json),
[실습 검증 기록](docs/validation.md).
