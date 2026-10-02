"""후보 레코드 v1의 위치 필드(span, line, context)를 만드는 공용 함수.

데이터(creddata_to_v1.py 등)와 hook이 둘 다 이 파일을 import해서 쓴다.
위치 계산을 한 곳에서만 하므로 span과 line이 서로 어긋날 수 없다.

위치 규칙 (2026-10-01 확정)
1. 기준 문자열(chunk)은 가공 전 원문 str 하나로 고정한다.
   - hook: extract_text()가 돌려준 str 그대로
   - 데이터: 원본 파일을 open(..., encoding="utf-8", errors="replace", newline="")로 읽은 str 그대로
     (newline=""를 빼면 Python이 \r\n, \r을 \n으로 바꿔버려서 원문이 달라진다)
2. 원문은 가공하지 않는다. 정규화(NFC/NFD), strip, 탭 변환, 줄바꿈 변환 금지.
   필요하면 위치를 다 계산한 뒤 복사본에서만 한다.
3. 위치 단위는 Python str 인덱스(Unicode 코드포인트), start 포함·end 미포함.
4. 줄은 "\n"으로만 나눈다 (str.splitlines() 금지). \r은 line.text 끝에 그대로 남는다.

문맥 규칙 (2026-10-01 확정)
5. 문맥 창 = 원문에서 값 앞 N자 + 값 + 값 뒤 N자 (N = chars_each_side, 기본 1000).
   줄 개수가 아니라 글자 수로 자른다. 창 안의 내용을 '\n'으로 나눠
   후보 줄은 line.text, 그 앞은 context.before, 그 뒤는 context.after에 넣는다.
   - 잘리는 곳은 항상 창의 양 끝(값에서 먼 쪽)뿐이다.
   - 창 끝이 줄 중간에 걸리면 그 줄은 일부만 들어가고 before_truncated / after_truncated = true.
   - 후보 줄 자체가 창보다 길면(압축된 JS 등) line.text도 창 범위만 남고,
     앞에서 잘라낸 길이를 meta.line_crop_offset에 적는다.
   - 값 위치를 모르는 경우(granularity=line)는 후보 줄 전체를 값처럼 취급하되,
     줄이 2N자보다 길면 앞 2N자만 남기고 after는 비운다.
"""

DEFAULT_CHARS_EACH_SIDE = 1000


class Chunk:
    """원문 + 줄 목록 + 각 줄 시작 위치. 같은 chunk에서 후보를 여러 개 뽑을 때 재사용한다."""

    def __init__(self, text: str):
        self.text = text
        self.lines = split_lines(text)
        self.offs = line_offsets(self.lines)

    def line_range(self, first, last):
        """first~last 줄(1부터)이 chunk에서 차지하는 [start, end)."""
        return self.offs[first - 1], self.offs[last - 1] + len(self.lines[last - 1])


def split_lines(chunk: str) -> list:
    """규칙 4: '\n'으로만 나눈다."""
    return chunk.split("\n")


def line_offsets(lines: list) -> list:
    """각 줄이 chunk에서 시작하는 위치."""
    offs, acc = [], 0
    for ln in lines:
        offs.append(acc)
        acc += len(ln) + 1
    return offs


def _as_chunk(chunk):
    return chunk if isinstance(chunk, Chunk) else Chunk(chunk)


def build_location(chunk, first, last, vs=None, ve=None, *, chars_each_side=DEFAULT_CHARS_EACH_SIDE):
    """줄 번호(1부터)와 줄 안 위치로 위치 필드를 만든다.

    chunk: 원문 str 또는 Chunk
    vs, ve: first~last 줄을 '\n'으로 이은 텍스트 안에서 값 위치. 모르면 None (granularity=line).
    반환: {"value", "span", "line", "context", "line_crop_offset"}
    line_crop_offset은 스키마 필드가 아니므로 레코드의 meta에 넣는다.
    """
    ch = _as_chunk(chunk)
    text, n = ch.text, chars_each_side
    if not (1 <= first <= last <= len(ch.lines)):
        raise ValueError(f"줄 번호 범위 오류: first={first}, last={last}, 줄 수={len(ch.lines)}")
    ls, le = ch.line_range(first, last)          # 후보 줄들의 원문 범위
    has_value = vs is not None and ve is not None
    if has_value:
        if not (0 <= vs < ve <= le - ls):
            raise ValueError(f"값 위치 범위 오류: vs={vs}, ve={ve}, 줄 길이={le - ls}")
        a, b = ls + vs, ls + ve                  # 값의 원문 범위
        ws, we = max(0, a - n), min(len(text), b + n)
    else:
        a, b = ls, min(le, ls + 2 * n)           # 값 위치를 모르면 줄 자체를 중심으로
        ws = max(0, a - n)
        we = min(len(text), le + n) if b == le else b   # 줄이 너무 길어 잘렸으면 뒤 문맥 없음

    # 후보 줄: 창과 겹치는 부분만
    lt_s, lt_e = max(ws, ls), min(we, le)
    line = {"first": first, "last": last, "text": text[lt_s:lt_e],
            "value_start": a - lt_s if has_value else None,
            "value_end": b - lt_s if has_value else None}

    # 앞 문맥: 창 시작 ~ 후보 줄 직전 '\n' 앞까지
    # (창 끝이 마침 '\n' 위에 걸리면 빈 조각이 생기므로 한 칸 안쪽으로 당긴다)
    before, before_trunc = [], False
    bs = ws + 1 if ws < ls - 1 and text[ws] == "\n" else ws
    if bs < ls - 1:
        before = split_lines(text[bs:ls - 1])
        before_trunc = bs > 0 and text[bs - 1] != "\n"
    # 뒤 문맥: 후보 줄 직후 '\n' 다음 ~ 창 끝까지
    after, after_trunc = [], False
    ae = we - 1 if we > le + 1 and text[we - 1] == "\n" else we
    if ae > le + 1:
        after = split_lines(text[le + 1:ae])
        after_trunc = ae < len(text) and text[ae] != "\n"

    return {
        "value": text[a:b] if has_value else None,
        "span": {"start": a, "end": b} if has_value else None,
        "line": line,
        "context": {"before": before, "after": after, "chars_each_side": n,
                    "before_truncated": before_trunc, "after_truncated": after_trunc},
        "line_crop_offset": lt_s - ls,
    }


def locate(chunk, start: int, end: int, **kw):
    """chunk 기준 [start, end) 위치로 위치 필드를 만든다. hook은 이걸 쓰면 된다."""
    ch = _as_chunk(chunk)
    if not (0 <= start < end <= len(ch.text)):
        raise ValueError(f"span 범위 오류: start={start}, end={end}, chunk 길이={len(ch.text)}")
    first = ch.text.count("\n", 0, start) + 1
    last = ch.text.count("\n", 0, end) + 1
    base = ch.offs[first - 1]
    loc = build_location(ch, first, last, start - base, end - base, **kw)
    assert ch.text[start:end] == loc["value"]
    return loc


def window_text(rec: dict) -> str:
    """레코드의 before + line.text + after를 원문 모양 그대로 다시 이어 붙인다 (모델 입력 조립용)."""
    ctx, ln = rec["context"], rec["line"]
    parts = []
    if ctx["before"]:
        parts.append("\n".join(ctx["before"]) + "\n")
    parts.append(ln["text"])
    if ctx["after"]:
        parts.append("\n" + "\n".join(ctx["after"]))
    return "".join(parts)


def check_span(chunk, rec: dict) -> list:
    """chunk가 있을 때 레코드의 위치·문맥이 원문과 맞는지 확인. 문제 목록을 돌려준다."""
    ch = _as_chunk(chunk)
    text = ch.text
    problems = []
    sp, ln = rec.get("span"), rec.get("line") or {}
    if sp is not None:
        if not (0 <= sp["start"] < sp["end"] <= len(text)):
            problems.append("span이 chunk 범위를 벗어남")
        elif rec.get("value") is not None and text[sp["start"]:sp["end"]] != rec["value"]:
            problems.append("chunk[span] != value")
    first, last = ln.get("first"), ln.get("last")
    if first is None or last is None:
        return problems
    if not (1 <= first <= last <= len(ch.lines)):
        problems.append("line.first/last가 chunk 줄 수를 벗어남")
        return problems
    ls, _ = ch.line_range(first, last)
    crop = (rec.get("meta") or {}).get("line_crop_offset", 0) or 0
    lt_s = ls + crop
    if text[lt_s:lt_s + len(ln["text"])] != ln["text"]:
        problems.append("line.text가 chunk의 해당 줄과 다름")
    if sp is not None and ln.get("value_start") is not None and lt_s + ln["value_start"] != sp["start"]:
        problems.append("span.start != 줄 시작 + line_crop_offset + line.value_start")
    ctx = rec.get("context")
    if ctx and "before" in ctx:
        win = window_text(rec)
        w_s = lt_s - (len("\n".join(ctx["before"])) + 1 if ctx["before"] else 0)
        if w_s < 0 or text[w_s:w_s + len(win)] != win:
            problems.append("context가 원문의 연속 구간과 다름")
    return problems
