# 수정 코드 다운로드

[etl-fixes.zip 다운로드](etl-fixes.zip)

이 ZIP에는 `ec8e285`의 추출 보완 코드·문서·테스트 7개와 적용 안내,
파일별 SHA-256 목록이 들어 있습니다. 프로젝트 전체 코드가 필요한 경우
GitHub의 `work` 브랜치에서 **Code → Download ZIP**을 선택하세요.

## Windows에서 적용

1. `etl-fixes.zip` 파일 화면에서 **Download raw file** 버튼으로 저장합니다.
2. ZIP을 별도 폴더에 풀고 `etl`, `docs`, `tests` 안의 파일을 현재 프로젝트의
   같은 위치에 복사합니다. 자세한 안내는 ZIP의 `README-APPLY.txt`에 있습니다.
3. 프로젝트 최상위 폴더에서 기존 Python 가상환경과 DB 접속 환경변수를 사용해
   먼저 `--dry-run`으로 검증합니다.

```powershell
.\.venv\Scripts\python.exe -m etl.pipeline "data\raw\KP-M-Q-26-000 FROM START HERE.xlsx" --sheet "quote25-041" --dry-run
```

이 폴더는 코드 배포 파일을 Git에 포함하도록 설정했습니다. 원본 Excel과
업무 데이터 보고서는 기존 `data/raw`, `data/processed`에서 계속 관리합니다.
이 ZIP에는 원본 Excel·업무 데이터·DB·접속 비밀번호가 포함되지 않습니다.
