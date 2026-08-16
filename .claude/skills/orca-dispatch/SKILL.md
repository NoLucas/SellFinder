---
name: orca-dispatch
description: 총괄자(orchestrator) 세션 전용 — Orca 의 다른 터미널 탭에서 돌고 있는 에이전트 세션(A/B/C/D/검증)에 지시 텍스트를 직접 입력하고 응답을 읽어온다. "각 창에 명령 넣어줘", "에이전트들 착수시켜", "각 세션 상태 확인해줘" 같은 요청에 쓴다. 에이전트 세션(A~D)은 이 스킬을 쓰지 마라 — 서로에게 지시하면 계약 소유자가 흐름에서 빠진다.
---

# Orca 세션에 직접 지시 넣기

## 이 스킬을 쓸 수 있는 사람

**총괄자 세션과 jin 뿐이다.**

네가 A(data-platform) · B(intelligence) · C(backend) · D(console) · 검증 중 하나라면 **여기서 멈춰라.**
다른 에이전트에게 직접 지시하는 것은 `orchestrator/CHARTER.md` §7 위반이다.
할 말이 있으면 자기 폴더 문서에 남기고 총괄자가 배분하게 한다.

---

## 1. 대상 창 찾기 — 탭 제목은 `visualLayouts` 에만 있다

`orca terminal list` 의 `title` 필드는 **그 세션의 첫 프롬프트**("진행 상황 파악" 등)라서
전부 비슷하게 보이고 누가 A 인지 알 수 없다. 사람이 보는 탭 제목("A 데이터 파이프라인")은
`--include-visual-layouts` 를 줘야 나온다.

```bash
PYTHONIOENCODING=utf-8 orca terminal list --include-visual-layouts --json 2>&1 | PYTHONIOENCODING=utf-8 python -c "
import json,sys,re
d=json.loads(sys.stdin.read())
s=json.dumps(d['result']['visualLayouts'], ensure_ascii=False)
pairs=re.findall(r'\"tabId\":\s*\"([0-9a-f-]+)\",\s*\"title\":\s*\"([^\"]+)\",\s*\"activeLeafId\".*?\"handle\":\s*\"(term_[0-9a-f-]+)\"', s)
for tab,title,handle in pairs:
    print(f'{title:20s} -> {handle}')
"
```

**`PYTHONIOENCODING=utf-8` 을 빼지 마라.** Windows 콘솔은 cp949 라서 한글 탭 제목이 깨지고,
`p['C 백엔드/API']` 같은 조회가 `KeyError` 로 죽는다. 조회가 죽으면 변수가 비고,
그 다음이 아래 §2 의 사고다.

출력 예:

```
총괄자                -> term_3a5d36da-...
A 데이터 파이프라인  -> term_fca80a48-...
B 예측 모델           -> term_3b80f14d-...
검증                 -> term_e494ba3a-...
C 백엔드/API          -> term_02a3c015-...
D 프론트엔드          -> term_e65ee256-...
```

**핸들을 기억해 두지 마라.** 세션이 다시 뜨면 바뀐다. 매번 위 명령으로 다시 뽑아라.

## 2. 보내기 — 핸들이 비면 **엉뚱한 창으로 간다**

`--terminal` 값이 비면 orca 는 오류를 내지 않고 **"현재 워크트리의 활성 터미널"** 로 보낸다.
즉 조회가 실패한 줄도 모르고 남의 창에 지시가 들어간다. 실제로 한 번 그렇게 나갔다
(운 좋게 의도한 창이었을 뿐이다). **변수에 담아 보낼 때는 반드시 비었는지 먼저 막아라.**

```bash
export PYTHONIOENCODING=utf-8
H=$(orca terminal list --include-visual-layouts --json 2>/dev/null | python -c "
import json,sys,re
s=json.dumps(json.loads(sys.stdin.read())['result']['visualLayouts'], ensure_ascii=False)
p=dict((t,h) for _,t,h in re.findall(r'\"tabId\":\s*\"([0-9a-f-]+)\",\s*\"title\":\s*\"([^\"]+)\",\s*\"activeLeafId\".*?\"handle\":\s*\"(term_[0-9a-f-]+)\"', s))
print(p.get('C 백엔드/API',''))")
[ -z "$H" ] && { echo '핸들 조회 실패 — 발송하지 않는다'; exit 1; }

orca terminal send --terminal "$H" --text '<지시문>' --enter --json
```

**응답의 `handle` 이 네가 의도한 핸들과 같은지 대조해라.** `accepted: true` 는
"어딘가에 들어갔다"는 뜻이지 "맞는 창에 들어갔다"는 뜻이 아니다.

핸들을 직접 아는 경우엔 변수 없이 그냥 박아 넣는 편이 안전하다.

- **반드시 한 줄로 써라.** 줄바꿈이 들어가면 TUI 가 중간에 제출해 버릴 수 있다.
  문장은 마침표로 끊고, 목록이 필요하면 `첫째, 둘째,` 로 풀어 쓴다.
- 작은따옴표로 전체를 감싸므로 **지시문 안에 작은따옴표를 쓰지 마라.**
- 긴 지시는 저장소 문서(`orchestrator/DISPATCH.md` §N)에 먼저 커밋하고,
  메시지는 "그 문서의 어느 절을 읽고 무엇부터 하라"로 짧게 보내는 편이 안전하고 재현성도 높다.
- `--enter` 를 빼면 입력만 되고 제출되지 않는다. `--interrupt` 로 실행 중인 작업을 끊을 수 있다.

## 3. 발송 후 확인 — 화면에 찍힌 것만 믿는다

확인할 것은 둘이다. **(a) 맞는 창에 들어갔는가** — 읽어온 tail 에 `❯ [지시문 첫머리]` 가 보이는가.
**(b) 인코딩이 살아 있는가** — 한글·`§`·`—` 가 깨지는 환경이 있다.
**한 창에 먼저 보내고 읽어서 확인한 뒤** 나머지에 보내라.

```bash
PYTHONIOENCODING=utf-8 orca terminal read --terminal <handle> --limit 40 --json 2>/dev/null | PYTHONIOENCODING=utf-8 python -c "
import json,sys
t=json.loads(sys.stdin.read())['result']['terminal']
tail=[l.strip() for l in t['tail'] if l.strip()]
hit=[l for l in tail if '<지시문에서 고른 고유 문구>' in l]
print('status:', t['status'], '| 수신 확인 줄:', len(hit))
for l in hit[:3]: print('  ', l[:92])
for l in tail[-4:]: print('  ', l[:92])
"
```

응답 구조는 `result.terminal.{status, tail[], nextCursor, latestCursor}` 다.
`--cursor <nextCursor>` 로 그 이후 새 출력만 받을 수 있다.

## 4. 상태 훑기

여러 창을 한 번에 볼 때:

```bash
for h in term_aaa:A term_bbb:B term_ccc:C; do
  echo "===== ${h##*:}"
  orca terminal read --terminal "${h%%:*}" --limit 40 --json 2>/dev/null | python -c "
import json,sys
t=json.loads(sys.stdin.read())['result']['terminal']
tail=[l.strip() for l in t['tail'] if l.strip() and not l.strip().startswith('-')]
for l in tail[-5:]: print('  ', l[:95])
"
done
```

`Processing…` / `Thinking…` 이 보이면 작업 중, `❯` 만 있고 조용하면 대기 중이다.

---

## 지시문에 반드시 넣을 것 (이 프로젝트에서 사고가 났던 지점들)

1. **이미 끝난 일을 먼저 못 박는다.** 세션은 자기가 낡았다는 걸 스스로 모른다.
   "X 는 이미 커밋됐다(해시). 다시 하지 마라" 를 첫 문장으로. 안 그러면 여러 창이 같은 문서를 다시 쓴다.
2. **폴더 경계**: "네 폴더 밖은 전부 읽기 전용" 을 매번 반복한다.
3. **`git add -A` 금지, `git add <자기폴더>` 만.** 여러 세션이 한 저장소에서 동시에 커밋하므로
   `-A` 는 남의 작업을 자기 커밋에 끌어들인다. `index.lock` 이 나면 20초 후 한 번 재시도하게 한다.
4. **완료 판정은 명령과 그 출력으로 요구한다.** "다 했습니다" 를 받지 않으려면
   실행할 명령을 지시문에 박고 출력을 붙여 보고하게 한다.
5. **오해 방지 문장을 넣는다.** 예: "네 모델은 정상이다. 고치지 마라" —
   findings 를 받은 세션이 멀쩡한 코드를 되돌리는 사고가 실제로 있었다.

## 알려진 잡음

- 발송 직후 `UserPromptSubmit hook timed out after 10s` 가 뜰 수 있다. 무해하고 지시는 정상 전달된다.
