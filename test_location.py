"""location.py 테스트. 실행: python test_location.py  (pytest로 돌려도 됨)

각 케이스는 '원문에서 값을 찾아 locate → 원문 기준으로 다시 확인'을 한다.
"""
import unicodedata
from location import locate, build_location, check_span, split_lines, window_text

CASES = {
    "ascii": ("DB_HOST=db-prod-2\nDB_USER=deploy\nDB_PASSWORD=Tq7!mZ2p#Lw9\nLOG_LEVEL=info", "Tq7!mZ2p#Lw9"),
    "korean": ("DB 비번은 qwer1234! 이야. 접속 에러 좀 고쳐줘", "qwer1234!"),
    "korean_value": ("설명\n비밀번호: 한글비번123\n끝", "한글비번123"),
    "emoji_before": ("배포 완료 😀👍🏽\nTOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789\n", "ghp_abcdefghijklmnopqrstuvwxyz0123456789"),
    "nfd_korean": (unicodedata.normalize("NFD", "파일 이름: 비밀.txt\nkey=") + "sk-test-1234567890abcdef\n", "sk-test-1234567890abcdef"),
    "crlf": ("A=1\r\nSECRET=s3cr3t-value\r\nB=2\r\n", "s3cr3t-value"),
    "u2028_line_sep": ("var a='x y';\nAPI_KEY=AKIAIOSFODNN7EXAMPLE\n", "AKIAIOSFODNN7EXAMPLE"),
    "vertical_tab_formfeed": ("a\x0bb\x0cc\nPASSWORD=hunter2hunter2\n", "hunter2hunter2"),
    "first_line_no_newline": ("token=abc123def456", "abc123def456"),
    "multiline_private_key": ("x=1\n-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----\ny=2",
                              "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----"),
    "many_short_lines": ("\n".join(f"K{i}=v{i}" for i in range(400)) + "\nSECRET=zz9988\n" +
                         "\n".join(f"J{i}=w{i}" for i in range(400)), "zz9988"),
    "long_prev_line": ('{"a":"' + "x" * 3000 + '","auth":{"type":"password",\n"value":"Tq7!mZ2p#Lw9"}}\nnext', "Tq7!mZ2p#Lw9"),
}


def loc_of(chunk, value, **kw):
    start = chunk.index(value)
    return locate(chunk, start, start + len(value), **kw)


def as_rec(loc):
    return {"value": loc["value"], "span": loc["span"], "line": loc["line"], "context": loc["context"],
            "meta": {"line_crop_offset": loc["line_crop_offset"]}}


def run_case(name, chunk, value, n=1000):
    loc = loc_of(chunk, value, chars_each_side=n)
    ln, ctx = loc["line"], loc["context"]
    assert loc["value"] == value, name
    assert ln["text"][ln["value_start"]:ln["value_end"]] == value, name
    assert check_span(chunk, as_rec(loc)) == [], (name, check_span(chunk, as_rec(loc)))
    # 문맥 창 크기: 값 앞뒤로 n자를 넘지 않는다
    win = window_text(as_rec(loc))
    before_len = len("\n".join(ctx["before"])) + 1 if ctx["before"] else 0
    assert before_len + ln["value_start"] <= n, name
    assert len(win) - (before_len + ln["value_end"]) <= n, name


def test_all_cases():
    for name, (chunk, value) in CASES.items():
        run_case(name, chunk, value)
        run_case(name + "_small_window", chunk, value, n=20)


def test_window_is_chars_not_lines():
    """짧은 줄이 많으면 여러 줄이 들어가고, 창 끝 줄은 잘렸다고 표시된다."""
    chunk, value = CASES["many_short_lines"]
    ctx = loc_of(chunk, value, chars_each_side=50)["context"]
    assert len(ctx["before"]) > 3 and len(ctx["after"]) > 3
    total_before = len("\n".join(ctx["before"])) + 1
    assert total_before <= 50 + len("SECRET=")


def test_long_prev_line_keeps_near_side():
    """윗줄이 아주 길면, 값과 가까운 윗줄 '끝부분'이 남아야 한다 (옛 방식 x[:500]의 문제)."""
    chunk, value = CASES["long_prev_line"]
    ctx = loc_of(chunk, value, chars_each_side=100)["context"]
    assert ctx["before"][-1].endswith('"auth":{"type":"password",')
    assert ctx["before_truncated"] is True


def test_minified_one_line():
    chunk = "x" * 5000 + "SECRET_abcdefghijklmnop" + "y" * 5000
    value = "SECRET_abcdefghijklmnop"
    loc = loc_of(chunk, value)
    ln = loc["line"]
    assert len(ln["text"]) == 1000 + len(value) + 1000 and loc["line_crop_offset"] == 4000
    assert loc["context"]["before"] == [] and loc["context"]["after"] == []
    assert check_span(chunk, as_rec(loc)) == []


def test_window_edge_on_newline_has_no_empty_piece():
    chunk = "aaaa\nbbbb\nSECRET=xyz123\ncccc\ndddd"
    for n in range(1, 25):
        ctx = loc_of(chunk, "xyz123", chars_each_side=n)["context"]
        assert "" not in ctx["before"] and "" not in ctx["after"], (n, ctx)


def test_line_granularity_without_value():
    chunk = "a=1\nsome_line_without_known_value\nb=2"
    loc = build_location(chunk, 2, 2, chars_each_side=20)
    assert loc["value"] is None and loc["span"] is None
    assert loc["line"]["text"] == "some_line_without_known_value"
    assert loc["context"]["before"] == ["a=1"] and loc["context"]["after"] == ["b=2"]
    long = "p\n" + "z" * 100 + "\nq"
    loc = build_location(long, 2, 2, chars_each_side=10)
    assert loc["line"]["text"] == "z" * 20 and loc["context"]["after"] == []


def test_splitlines_would_break():
    """splitlines()를 쓰면 줄 번호가 달라진다 (규칙 4의 이유)."""
    chunk, value = CASES["u2028_line_sep"]
    loc = loc_of(chunk, value)
    assert loc["line"]["first"] == 2
    assert chunk.splitlines()[1] != loc["line"]["text"]


def test_crlf_keeps_cr():
    chunk, value = CASES["crlf"]
    loc = loc_of(chunk, value)
    assert loc["line"]["text"] == "SECRET=s3cr3t-value\r"
    assert loc["context"]["before"] == ["A=1\r"]


def test_nfd_not_normalized():
    """NFD 원문 그대로면 위치가 맞고, NFC로 바꾸면 틀어진다 (규칙 2의 이유)."""
    chunk, value = CASES["nfd_korean"]
    loc = loc_of(chunk, value)
    nfc = unicodedata.normalize("NFC", chunk)
    assert len(nfc) != len(chunk)
    assert nfc[loc["span"]["start"]:loc["span"]["end"]] != value


def test_check_span_catches_mismatch():
    chunk, value = CASES["ascii"]
    loc = loc_of(chunk, value)
    bad = as_rec(loc)
    bad["span"] = {"start": loc["span"]["start"] + 1, "end": loc["span"]["end"] + 1}
    assert "chunk[span] != value" in check_span(chunk, bad)
    bad = as_rec(loc)
    bad["context"] = dict(loc["context"], before=["DB_HOST=WRONG"])
    assert "context가 원문의 연속 구간과 다름" in check_span(chunk, bad)


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
    print(f"OK: {len(tests)} tests, {len(CASES)} cases x 2 window sizes")
