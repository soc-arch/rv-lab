# CPU 이미지와 공개 자료 검토

현재 소개 이미지는 `HY-RV CPU CORE` 제목의 [영문 이미지](assets/hy-rv-cpu-overview-en-v1.png)입니다.
현재 canonical 소스 hash `35558e91c602324ddf5b2ab8de893bc0baead18cc9a82c3c336e16c6b3213dd8`와
기본 `ant_j0`를 바탕으로 생성했습니다. 원본 PNG·생성 프롬프트·provenance를 함께 보관합니다.

| 자료 | 내용과 적용 기준 |
| --- | --- |
| 사용자 첨부 `Inside the RV32IM Teaching Core` 이미지 | `teaching_fetch`, `teaching_backend`, 1-entry response buffer를 명시하므로 구 teaching 코어 설명입니다. 현재 P1/Q0 설명으로 사용할 수 없습니다. |
| 이 저장소의 새 `HY-RV CPU CORE` 이미지 | `rv_frontend`, `rv_insn_link` Q0, `rv_backend`, `rv_branch_predictor` 및 early JAL OFF를 표시한 최신 소개입니다. |
| 새 `viewer/microarchitecture.svg` | 현재 RTL에 대응하는 직접 편집 가능한 벡터 구조도입니다. 실제 cycle trace로 활성 신호를 강조합니다. |
| `docs/screenshots/` | 실제 실습 실행을 브라우저로 연 화면입니다. `reference-results.json`의 실행 identity와 함께 읽습니다. |
| `docs/historical/` | 교체 전 teaching CPU의 실제 결과·화면을 보존한 자료입니다. 최신 코어의 성능 기준으로 사용하지 않습니다. |

첨부한 예전 teaching 그림은 RV Lab의 구 구현을 설명하는 내용에는 부합하지만, HY-RV의
현재 P1/Q0 코어를 나타내지는 않습니다. 기존 공개 저장소에 포함된 `teaching_fetch.sv`와
1-entry response buffer 설명도 같은 구 버전을 가리켰습니다. 로컬 작업 사본에는 구 teaching core를 대상으로 한 이미지 생성 프롬프트와 source hash 목록이
있었으나, 이것만으로 첨부 PNG 파일의 생성 출처나 파일 동일성까지 증명할 수는 없습니다.
검토 당시 공개 홈페이지에는 대표 CPU PNG가 포함되어 있지 않았고, 공개 viewer SVG와
RTL·문서가 구 teaching core를 가리켰습니다. 그림의 내용 검토와 파일의 출처 확인을 구분합니다.

생성형 이미지는 구조를 소개하는 보조자료입니다. `D-memory` 표시는 코어 외부 D 포트이며,
그림 안의 이상적 same-edge 동작은 실측 trace가 아닙니다. 구현·검증의 기준은 RTL과
[현재 소스 provenance](../provenance/p1-static-core.json),
[실제 RTL→gate 기록](../provenance/p1-rtl-gate-equivalence.json),
[현재 실습 검증](current-validation.md)입니다.

이미지는 1672×941 원본 픽셀로 보존했습니다. 요청했던 3840×2160이 반환되지 않았으므로
이를 4K 원본으로 표현하지 않습니다. [프롬프트](assets/generation-prompt-en-v1.txt)와
[provenance](assets/provenance-en-v1.json)에서 출처와 제한을 확인할 수 있습니다.

[정확한 원본 파일 hash와 가져오기 기록](assets/import.json)을 보관했습니다. 원본 provenance의 상대 경로는 canonical 문서 위치를 기준으로 한 기록이며, 이 공개 저장소의 현재 연결은 [CPU 소개](core-overview.md)에서 안내합니다.
