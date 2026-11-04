from triage_agent.parse import load_log, parse_line
from triage_agent.redact import redact
from triage_agent.templates import build_digest, mine_templates


def test_threadtime_line_is_split_into_fields():
    line = parse_line(7, "09-11 14:49:29.553  2526  3005 D RILJ    : [UNSL]< UNSOL_RESPONSE [PHONE0]\n")
    assert (line.number, line.level, line.tag, line.message) == (7, "D", "RILJ", "[UNSL]< UNSOL_RESPONSE [PHONE0]")
    assert line.parsed


def test_tag_containing_colon_is_kept_whole():
    assert parse_line(1, "09-11 14:49:29.553  1  2 E a:b : hello").tag == "a:b"


def test_other_line_is_kept_with_its_number():
    line = parse_line(3, "--------- beginning of radio\n")
    assert not line.parsed and line.number == 3 and line.text == "--------- beginning of radio"


def test_line_numbers_match_the_file(sim_log):
    raw = sim_log.read_text(encoding="utf-8").splitlines()
    lines = load_log(sim_log)
    assert len(lines) == len(raw)
    assert lines[41].number == 42 and lines[41].message in raw[41]


def test_redact_masks_identifiers_and_keeps_ordinary_numbers():
    text = "imei=356938035643809 iccid=89882110000000000000 +420601234567 10.0.0.1 aa:bb:cc:dd:ee:ff a@b.cz sip:u@ims.net"
    masked = redact(text)
    for secret in ["356938035643809", "8988211", "601234567", "10.0.0.1", "aa:bb", "a@b.cz", "sip:u"]:
        assert secret not in masked
    assert redact("ssRsrp=-98 time=1736899200000") == "ssRsrp=-98 time=1736899200000"


def test_parsed_line_never_holds_raw_identifier():
    line = parse_line(1, "09-11 14:49:29.553  1  2 D Tag: imsi 230011234567890")
    assert "230011234567890" not in line.text + line.message


def _lines(*messages):
    return [parse_line(n, f"09-11 14:49:29.553  1  2 E Tag: {m}") for n, m in enumerate(messages, start=1)]


def test_lines_differing_only_by_numbers_share_a_template():
    templates = mine_templates(_lines("retry after 5000 ms", "retry after 1000 ms", "card removed from slot"))
    assert len(templates) == 2
    assert sorted(len(t.line_numbers) for t in templates) == [1, 2]


def test_every_real_line_belongs_to_one_template(shield_log):
    lines = load_log(shield_log)
    numbers = sorted(n for t in mine_templates(lines) for n in t.line_numbers)
    assert numbers == [l.number for l in lines if not l.text.startswith("---------") and l.text.strip()]


def test_digest_is_shorter_and_shows_real_line_numbers(shield_log):
    lines = load_log(shield_log)
    digest = build_digest(lines, mine_templates(lines))
    assert len(digest) < sum(len(l.text) for l in lines)
    assert "  L" in digest


def test_digest_puts_severe_templates_first():
    lines = [
        parse_line(1, "09-11 14:49:29.553  1  2 D Noise: common message"),
        parse_line(2, "09-11 14:49:29.553  1  2 F Crash: fatal thing"),
    ]
    digest = build_digest(lines, mine_templates(lines))
    assert digest.index("fatal thing") < digest.index("common message")
