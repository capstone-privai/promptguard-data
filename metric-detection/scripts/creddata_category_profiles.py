"""Empirical train-only CredData skeletons (standard library only).

Build: python3 -B metric-detection/scripts/creddata_category_profiles.py build
Each distinct (session, value) pair has one vote. Public dictionary matches,
counting/repeated digits, repeated hex blocks and leading zeros retain structure;
other characters use uniform alphabets. Only punctuation and whitespace remain
literal. Unicode letters use public script/case alphabets, never source letters.
The embedded public lexicon makes both fitting and sampling reproducible.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
import string
import unicodedata

from value_gen import WORDS, WEAK

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SESSIONS = ROOT / "runs/creddata-source-fullfile/data_test/sessions_from_CredData.jsonl"
DEFAULT_LABELS = ROOT / "runs/creddata-source-fullfile/labels_from_CredData.jsonl"
DEFAULT_TRAIN = ROOT / "metric-detection/source_splits/creddata-v1/train.txt"
DEFAULT_CATEGORIES = ROOT / "runs/creddata-source-fullfile/gold_category_train.jsonl"
DEFAULT_OUTPUT = ROOT / "runs/creddata-source-fullfile/category_profiles_v2.json"
BUILD_COMMAND = "python3 -B metric-detection/scripts/creddata_category_profiles.py build"
LOWER, UPPER, DIGITS = string.ascii_lowercase, string.ascii_uppercase, string.digits
ALNUM = LOWER + UPPER + DIGITS
PLAIN_ALPHABET = ALNUM + "-_"
CLASS_NAMES = ("lower", "upper", "digit", "symbol", "space", "line", "unicode")
SHAPES = (
    "digits", "hex_lower", "hex_upper", "hex_mixed", "lower_alpha",
    "upper_alpha", "mixed_alpha", "lower_alnum", "upper_alnum", "mixed_alnum",
    "base64_like", "base64url_like", "with_symbols", "whitespace", "multiline", "unicode",
)
# Fixed-format categories must never contribute to any free-form atom pool.
FREE_ATOMS = frozenset((
    "Password", "Key", "Secret", "Token", "Auth", "API", "Credential",
    "URL Credentials", "CMD Password", "CMD Secret", "CMD Token",
    "CMD ConvertTo-SecureString", "CURL Options", "CURL User Password",
    "SQL Password", "Salt", "Other", "Bearer Authorization",
))
ALPHABETS = {"digits": DIGITS, "hex_lower": DIGITS + "abcdef",
             "hex_upper": DIGITS + "ABCDEF", "hex_mixed": DIGITS + "abcdefABCDEF", "base64": ALNUM + "+/",
             "base64url": ALNUM + "-_"}
VOWELS = "aeiou"
# First 3,000 entries of the public frequency-ranked Google English list:
# https://github.com/first20hours/google-10000-english/blob/master/google-10000-english.txt
# Full upstream snapshot SHA256: 9c965d384526facc59260e94f8ccff1582633fa385004abe1455ed457062acbc
# This lexicon is independent of CredData. Repo WORDS/WEAK add public defaults.
COMMON_WORDS = tuple("""
the of and to a in for is on that by this with i you
it not or be are from at as your all have new more an was
we will home can us about if page my has search free but our one
other do no information time they site he up may what which their news out
use any there see only so his when contact here business who web also now
help get pm view online c e first am been would how were me s
services some these click its like service x than find price date back top people
had list name just over state year day into email two health n world re
next used go b work last most products music buy data make them should product
system post her city t add policy number such please available copyright support message after
best software then jan good video well d where info rights public books high school
through m each links she review years order very privacy book items company r read
group sex need many user said de does set under general research university january mail
full map reviews program life know games way days management p part could great united
hotel real f item international center ebay must store travel comments made development report off
member details line terms before hotels did send right type because local those using results
office education national car design take posted internet address community within states area want phone
dvd shipping reserved subject between forum family l long based w code show o even
black check special prices website index being women much sign file link open today technology
south case project same pages uk version section own found sports house related security both
g county american photo game members power while care network down computer systems three total
place end following download h him without per access think north resources current posts big
media law control water history pictures size art personal since including guide shop directory board
location change white text small rating rate government children during usa return students v shopping
account times sites level digital profile previous form events love old john main call hours
image department title description non k y insurance another why shall property class cd still
money quality every listing content country private little visit save tools low reply customer december
compare movies include college value article york man card jobs provide j food source author
different press u learn sale around print course job canada process teen room stock training
too credit point join science men categories advanced west sales look english left team estate
box conditions select windows photos gay thread week category note live large gallery table register
however june october november market library really action start series model features air industry plan
human provided tv yes required second hot accessories cost movie forums march la september better
say questions july yahoo going medical test friend come dec server pc study application cart
staff articles san feedback again play looking issues april never users complete street topic comment
financial things working against standard tax person below mobile less got blog party payment equipment
login student let programs offers legal above recent park stores side act problem red give
memory performance social q august quote language story sell options experience rates create key body
young america important field few east paper single ii age activities club example girls additional
password z latest something road gift question changes night ca hard texas oct pay four
poker status browse issue range building seller court february always result audio light write war
nov offer blue groups al easy given files event release analysis request fax china making
picture needs possible might professional yet month major star areas future space committee hand sun
cards problems london washington meeting rss become interest id child keep enter california porn share
similar garden schools million added reference companies listed baby learning energy run delivery net popular
term film stories put computers journal reports co try welcome central images president notice god
original head radio until cell color self council away includes track australia discussion archive once
others entertainment agreement format least society months log safety friends sure faq trade edition cars
messages marketing tell further updated association able having provides david fun already green studies close
common drive specific several gold feb living sep collection called short arts lot ask display
limited powered solutions means director daily beach past natural whether due et electronics five upon
period planning database says official weather mar land average done technical window france pro region
island record direct microsoft conference environment records st district calendar costs style url front statement
update parts aug ever downloads early miles sound resource present applications either ago document word
works material bill apr written talk federal hosting rules final adult tickets thing centre requirements
via cheap nude kids finance true minutes else mark third rock gifts europe reading topics
bad individual tips plus auto cover usually edit together videos percent fast function fact unit
getting global tech meet far economic en player projects lyrics often subscribe submit germany amount
watch included feel though bank risk thanks everything deals various words linux jul production commercial
james weight town heart advertising received choose treatment newsletter archives points knowledge magazine error camera
jun girl currently construction toys registered clear golf receive domain methods chapter makes protection policies
loan wide beauty manager india position taken sort listings models michael known half cases step
engineering florida simple quick none wireless license paul friday lake whole annual published later basic
sony shows corporate google church method purchase customers active response practice hardware figure materials fire
holiday chat enough designed along among death writing speed html countries loss face brand discount
higher effects created remember standards oil bit yellow political increase advertise kingdom base near environmental
thought stuff french storage oh japan doing loans shoes entry stay nature orders availability africa
summary turn mean growth notes agency king monday european activity copy although drug pics western
income force cash employment overall bay river commission ad package contents seen players engine port
album regional stop supplies started administration bar institute views plans double dog build screen exchange
types soon sponsored lines electronic continue across benefits needed season apply someone held ny anything
printer condition effective believe organization effect asked eur mind sunday selection casino pdf lost tour
menu volume cross anyone mortgage hope silver corporation wish inside solution mature role rather weeks
addition came supply nothing certain usr executive running lower necessary union jewelry according dc clothing
mon com particular fine names robert homepage hour gas skills six bush islands advice career
military rental decision leave british teens pre huge sat woman facilities zip bid kind sellers
middle move cable opportunities taking values division coming tuesday object lesbian appropriate machine logo length
actually nice score statistics client ok returns capital follow sample investment sent shown saturday christmas
england culture band flash ms lead george choice went starting registration fri thursday courses consumer
hi airport foreign artist outside furniture levels channel letter mode phones ideas wednesday structure fund
summer allow degree contract button releases wed homes super male matter custom virginia almost took
located multiple asian distribution editor inn industrial cause potential song cnet ltd los hp focus
late fall featured idea rooms female responsible inc communications win associated thomas primary cancer numbers
reason tool browser spring foundation answer voice eg friendly schedule documents communication purpose feature bed
comes police everyone independent ip approach cameras brown physical operating hill maps medicine deal hold
ratings chicago forms glass happy tue smith wanted developed thank safe unique survey prior telephone
sport ready feed animal sources mexico population pa regular secure navigation operations therefore ass simply
evidence station christian round paypal favorite understand option master valley recently probably thu rentals sea
built publications blood cut worldwide improve connection publisher hall larger anti networks earth parents nokia
impact transfer introduction kitchen strong tel carolina wedding properties hospital ground overview ship accommodation owners
disease tx excellent paid italy perfect hair opportunity kit classic basis command cities william express
anal award distance tree peter assessment ensure thus wall ie involved el extra especially interface
pussy partners budget rated guides success maximum ma operation existing quite selected boy amazon patients
restaurants beautiful warning wine locations horse vote forward flowers stars significant lists technologies owner retail
animals useful directly manufacturer ways est son providing rule mac housing takes iii gmt bring
catalog searches max trying mother authority considered told xml traffic programme joined input strategy feet
agent valid bin modern senior ireland sexy teaching door grand testing trial charge units instead
canadian cool normal wrote enterprise ships entire educational md leading metal positive fl fitness chinese
opinion mb asia football abstract uses output funds mr greater likely develop employees artists alternative
processing responsibility resolution java guest seems publication pass relations trust van contains session multi photography
republic fees components vacation century academic assistance completed skin graphics indian prev ads mary il
expected ring grade dating pacific mountain organizations pop filter mailing vehicle longer consider int northern
behind panel floor german buying match proposed default require iraq boys outdoor deep morning otherwise
allows rest protein plant reported hit transportation mm pool mini politics partner disclaimer authors boards
faculty parties fish membership mission eye string sense modified pack released stage internal goods recommended
born unless richard detailed japanese race approved background target except character usb maintenance ability maybe
functions ed moving brands places php pretty trademarks phentermine spain southern yourself etc winter rape
battery youth pressure submitted boston incest debt keywords medium television interested core break purposes throughout
sets dance wood msn itself defined papers playing awards fee studio reader virtual device established
answers rent las remote dark programming external apple le regarding instructions min offered theory enjoy
remove aid surface minimum visual host variety teachers isbn martin manual block subjects agents increased
repair fair civil steel understanding songs fixed wrong beginning hands associates finally az updates desktop
classes paris ohio gets sector capacity requires jersey un fat fully father electric saw instruments
quotes officer driver businesses dead respect unknown specified restaurant mike trip pst worth mi procedures
poor teacher xxx eyes relationship workers farm fucking georgia peace traditional campus tom showing creative
coast benefit progress funding devices lord grant sub agree fiction hear sometimes watches careers beyond
goes families led museum themselves fan transport interesting blogs wife evaluation accepted former implementation ten
hits zone complex th cat galleries references die presented jack flat flow agencies literature respective
parent spanish michigan columbia setting dr scale stand economy highest helpful monthly critical frame musical
definition secretary angeles networking path australian employee chief gives kb bottom magazines packages detail francisco
laws changed pet heard begin individuals colorado royal clean switch russian largest african guy titles
relevant guidelines justice connect bible dev cup basket applied weekly vol installation described demand pp
suite vegas na square chris attention advance skip diet army auction gear lee os difference
allowed correct charles nation selling lots piece sheet firm seven older illinois regulations elements species
jump cells module resort facility random pricing dvds certificate minister motion looks fashion directions visitors
documentation monitor trading forest calls whose coverage couple giving chance vision ball ending clients actions
listen discuss accept automotive naked goal successful sold wind communities clinical situation sciences markets lowest
highly publishing appear emergency developing lives currency leather determine milf temperature palm announcements patient actual
historical stone bob commerce ringtones perhaps persons difficult scientific satellite fit tests village accounts amateur
ex met pain xbox particularly factors coffee www settings cum buyer cultural steve easily oral
ford poster edge functional root au fi closed holidays ice pink zealand balance monitoring graduate
replies shot nc architecture initial label thinking scott llc sec recommend canon hardcore league waste
minute bus provider optional dictionary cold accounting manufacturing sections chair fishing effort phase fields bag
fantasy po letters motor va professor context install shirt apparel generally continued foot mass crime
count breast techniques ibm rd johnson sc quickly dollars websites religion claim driving permission surgery
patch heat wild measures generation kansas miss chemical doctor task reduce brought himself nor component
enable exercise bug santa mid guarantee leader diamond israel se processes soft servers alone meetings
seconds jones arizona keyword interests flight congress fuel username walk fuck produced italian paperback classifieds
wait supported pocket saint rose freedom argument competition creating jim drugs joint premium providers fresh
characters attorney upgrade di factor growing thousands km stream apartments pick hearing eastern auctions therapy
entries dates generated signed upper administrative serious prime samsung limit began louis steps errors shops
bondage del efforts informed ga ac thoughts creek ft worked quantity urban practices sorted reporting
essential myself tours platform load affiliate labor immediately admin nursing defense machines designated tags heavy
covered recovery joe guys integrated configuration cock merchant comprehensive expert universal protect drop solid cds
presentation languages became orange compliance vehicles prevent theme rich im campaign marine improvement vs guitar
finding pennsylvania examples ipod saying spirit ar claims porno challenge motorola acceptance strategies mo seem
affairs touch intended towards sa goals hire election suggest branch charges serve affiliates reasons magic
mount smart talking gave ones latin multimedia xp tits avoid certified manage corner rank computing
oregon element birth virus abuse interactive requests separate quarter procedure leadership tables define racing religious
facts breakfast kong column plants faith chain developer identify avenue missing died approximately domestic sitemap
recommendations moved houston reach comparison mental viewed moment extended sequence inch attack sorry centers opening
damage lab reserve recipes cvs gamma plastic produce snow placed truth counter failure follows eu
weekend dollar camp ontario automatically des minnesota films bridge native fill williams movement printing baseball
owned approval draft chart played contacts cc jesus readers clubs lcd wa jackson equal adventure
matching offering shirts profit leaders posters institutions assistant variable ave dj advertisement expect parking headlines
yesterday compared determined wholesale workshop russia gone codes kinds extension seattle statements golden completely teams
fort cm wi lighting senate forces funny brother gene turned portable tried electrical applicable disc
returned pattern ct hentai boat named theatre laser earlier manufacturers sponsor classical icon warranty dedicated
indiana direction harry basketball objects ends delete evening assembly nuclear taxes mouse signal criminal issued
brain sexual wisconsin powerful dream obtained false da cast flower felt personnel passed supplied identified
falls pic soul aids opinions promote stated stats hawaii professionals appears carry flag decided nj
covers hr em advantage hello designs maintain tourism priority newsletters adults clips savings iv graphic
atom payments rw estimated binding brief ended winning eight anonymous iron straight script served wants
miscellaneous prepared void dining alert integration atlanta dakota tag interview mix framework disk installed queen
vhs credits clearly fix handle sweet desk criteria pubmed dave massachusetts diego hong vice associate
ne truck behavior enlarge ray frequently revenue measure changing votes du duty looked discussions bear
gain festival laboratory ocean flights experts signs lack depth iowa whatever logged laptop vintage train
exactly dry explore maryland spa concept nearly eligible checkout reality forgot handling origin knew gaming
feeds billion destination scotland faster intelligence dallas bought con ups nations route followed specifications broken
tripadvisor frank alaska zoom blow battle residential anime speak decisions industries protocol query clip partnership
editorial nt expression es equity provisions speech wire principles suggestions rural shared sounds replacement tape
strategic judge spam economics acid bytes cent forced compatible fight apartment height null zero speaker
filed gb netherlands obtain bc consulting recreation offices designer remain managed pr failed marriage roll
korea banks fr participants secret bath aa kelly leads negative austin favorites toronto theater springs
missouri andrew var perform healthy translation estimates font assets injury mt joseph ministry drivers lawyer
figures married protected proposal sharing philadelphia portal waiting birthday beta fail gratis banking officials brian
toward won slightly assist conduct contained lingerie shemale legislation calling parameters jazz serving bags profiles
miami comics matters houses doc postal relationships tennessee wear controls breaking combined ultimate wales representative
frequency introduced minor finish departments residents noted displayed mom reduced physics rare spent performed extreme
samples davis daniel bars reviewed row oz forecast removed helps singles administrator cycle amounts contain
accuracy dual rise usd sleep mg bird pharmacy brazil creation static scene hunter addresses lady
crystal famous writer chairman violence fans oklahoma speakers drink academy dynamic gender eat permanent agriculture
dell cleaning constitutes portfolio practical delivered collectibles infrastructure exclusive seat concerns colour vendor originally intel
utilities philosophy regulation officers reduction aim bids referred supports nutrition recording regions junior toll les
cape ann rings meaning tip secondary wonderful mine ladies henry ticket announced guess agreed prevention
whom ski soccer math import posting presence instant mentioned automatic healthcare viewing maintained ch increasing
majority connected christ dan dogs sd directors aspects austria ahead moon participation scheme utility preview
fly manner matrix containing combination devel amendment despite strength guaranteed turkey libraries proper distributed degrees
singapore enterprises delta fear seeking inches phoenix rs convention shares principal daughter standing voyeur comfort
colors wars cisco ordering kept alpha appeal cruise bonus certification previously hey bookmark buildings specials
beat disney household batteries adobe smoking bbc becomes drives arms alabama tea improved trees avg
achieve positions dress subscription dealer contemporary sky utah nearby rom carried happen exposure panasonic hide
permalink signature gambling refer miller provision outdoors clothes caused luxury babes frames viagra certainly indeed
newspaper toy circuit layer printed slow removal easier src liability trademark hip printers faqs nine
adding kentucky mostly eric spot taylor trackback prints spend factory interior revised grow americans optical
promotion relative amazing clock dot hiv identity suites conversion feeling hidden reasonable victoria serial relief
revision broadband influence ratio pda importance rain onto dsl planet webmaster copies recipe zum permit
seeing proof dna diff tennis bass prescription bedroom empty instance hole pets ride licensed orlando
specifically tim bureau maine sql represent conservation pair ideal specs recorded don pieces finished parks
dinner lawyers sydney stress cream ss runs trends yeah discover sexo ap patterns boxes louisiana
""".split())
PUBLIC_WORDS = frozenset(COMMON_WORDS) | frozenset(WORDS) | frozenset(("beef", "cafe", "deed", "feed")) | frozenset(
    w.lower() for w in WEAK if w.isascii() and w.isalpha())
# Modest public frequency weights; no source word or word frequency is fitted.
WORD_WEIGHTS = {w: 1 + (3 if i < 100 else 1 if i < 1000 else 0)
                for i, w in reversed(list(enumerate(COMMON_WORDS)))}
WORDS_BY_LENGTH = {
    n: tuple((w, WORD_WEIGHTS.get(w, 1)) for w in sorted(PUBLIC_WORDS) if len(w) == n)
    for n in sorted(set(map(len, PUBLIC_WORDS)))
}
MAX_ATTEMPTS = 128
# Use public extended script alphabets to avoid copying the common source
# glyphs even incidentally. These ranges are fixed, never fitted to gold data.
SCRIPT_RANGES = {
    "LATIN": (0xA720, 0xA800), "GREEK": (0x1F00, 0x2000),
    "CYRILLIC": (0xA640, 0xA6A0), "CJK": (0x3400, 0x4DC0),
    "KATAKANA": (0x31F0, 0x3200), "HIRAGANA": (0x3041, 0x3097),
    "HANGUL": (0xAC00, 0xD7A4), "ARABIC": (0x600, 0x700),
    "HEBREW": (0x590, 0x600), "DEVANAGARI": (0x900, 0x980),
}


def canonical_category(category: str) -> str:
    return ":".join(sorted(set(category.split(":"))))


def is_free(category: str) -> bool:
    return bool(category) and set(category.split(":")) <= FREE_ATOMS


def _class(char: str) -> str:
    if char in LOWER:
        return "lower"
    if char in UPPER:
        return "upper"
    if char in DIGITS:
        return "digit"
    if not char.isascii():
        return "unicode"
    if char in "\r\n":
        return "line"
    return "space" if char.isspace() else "symbol"


def character_classes(value: str) -> set[str]:
    return {_class(c) for c in value}


def shape_of(value: str) -> str:
    """Disjoint audit shapes; base64-like alone does not prove an encoding."""
    if not value:
        raise ValueError("Empty gold spans have no composition profile")
    chars = set(value)
    if not value.isascii():
        return "unicode"
    if "\n" in chars or "\r" in chars:
        return "multiline"
    if any(c.isspace() for c in chars):
        return "whitespace"
    if chars <= set(DIGITS):
        return "digits"
    # Short a-f-only words are letters, even when they also parse as hex.
    if chars <= set(LOWER + UPPER) and len(value) < 16:
        return "lower_alpha" if value.islower() else "upper_alpha" if value.isupper() else "mixed_alpha"
    for shape, alphabet in (
        ("hex_lower", DIGITS + "abcdef"), ("hex_upper", DIGITS + "ABCDEF"),
        ("hex_mixed", DIGITS + "abcdefABCDEF"),
        ("lower_alpha", LOWER), ("upper_alpha", UPPER), ("mixed_alpha", LOWER + UPPER),
        ("lower_alnum", LOWER + DIGITS), ("upper_alnum", UPPER + DIGITS),
        ("mixed_alnum", ALNUM), ("base64_like", ALNUM + "+/="),
        ("base64url_like", ALNUM + "-_="),
    ):
        if chars <= set(alphabet):
            return shape
    return "with_symbols"


def runs_of(value: str) -> list[tuple[str, int]]:
    runs = []
    for char in value:
        name = _class(char)
        if runs and runs[-1][0] == name:
            runs[-1] = (name, runs[-1][1] + 1)
        else:
            runs.append((name, 1))
    return runs


def dictionary_run(run: str) -> bool:
    return run.isascii() and run.isalpha() and run.lower() in PUBLIC_WORDS


def digit_sequence(run: str) -> int:
    if len(run) < 3 or not set(run) <= set(DIGITS):
        return 0
    for step in (1, -1):
        if all((int(b) - int(a)) % 10 == step % 10 for a, b in zip(run, run[1:])):
            return step
    return 0


def repeated_block(run: str) -> int:
    for size in range(1, min(4, len(run) // 2) + 1):
        if len(run) % size == 0 and run == run[:size] * (len(run) // size):
            return size
    return 0


def structure_of(value: str, hex_value: bool = False) -> dict:
    repeat = repeated_block(value)
    if repeat:
        return {"repeat": repeat}
    step = digit_sequence(value)
    if step:
        return {"sequence": step}
    zeros = len(value) - len(value.lstrip("0"))
    return {"leading_zeros": zeros} if hex_value and zeros >= 2 else {}


def unicode_marker(char: str) -> dict:
    name = unicodedata.name(char, "")
    script = next((s for s in SCRIPT_RANGES if s in name), None)
    category = unicodedata.category(char)
    marker = dict(kind="unicode", case=category)
    if script:
        marker["script"] = script
    else:
        marker["block"] = ord(char) // 256
    return marker


@lru_cache(maxsize=None)
def unicode_alphabet(script: str = "", block: int = 0, case: str = "Lo") -> str:
    start, end = SCRIPT_RANGES.get(script, (block * 256, (block + 1) * 256))
    alphabet = "".join(chr(i) for i in range(start, end)
                       if unicodedata.category(chr(i)) == case)
    if not alphabet:
        raise ValueError("No public alphabet for Unicode class")
    return alphabet


@dataclass
class TrainingValues:
    """Private source data: never serialize values or include them in errors."""
    full: dict[str, Counter]
    atoms: dict[str, Counter]
    categories: list[str]
    train_sessions: int
    all_gold_values: set[str]
    span_counts: Counter
    pairs: dict[str, set[tuple[str, str]]] | None = None


def load_training_values(sessions=DEFAULT_SESSIONS, labels=DEFAULT_LABELS,
                         train=DEFAULT_TRAIN, categories=DEFAULT_CATEGORIES) -> TrainingValues:
    train_ids = set(Path(train).read_text(encoding="utf-8").splitlines()) - {""}
    category_rows, gold_rows = defaultdict(list), defaultdict(list)
    span_counts = Counter()
    with Path(categories).open(encoding="utf-8") as src:
        for line in src:
            row = json.loads(line)
            if "dropped" in row or row["session_id"] not in train_ids:
                continue
            if not row.get("category"):
                raise ValueError("Categorized gold row is missing its category")
            category_rows[row["session_id"]].append(row)
            span_counts[row["category"]] += 1
    # All splits are read ONLY for the output collision audit, never fitting.
    with Path(labels).open(encoding="utf-8") as src:
        for line in src:
            row = json.loads(line)
            if row.get("gold") is True:
                gold_rows[row["session_id"]].append(row)
    full_pairs, atom_pairs = defaultdict(set), defaultdict(set)
    all_gold_values, seen = set(), set()
    with Path(sessions).open(encoding="utf-8") as src:
        for line in src:
            row = json.loads(line)
            session = row["session_id"]
            if session not in category_rows and session not in gold_rows:
                continue
            if session in seen:
                raise ValueError("Duplicate source session")
            seen.add(session)
            items = {item["item_id"]: item["text"] for item in row["items"]}
            def value_of(label):
                text = items[label.get("item_id", 0)]
                start, end = label["start"], label["end"]
                if not 0 <= start < end <= len(text):
                    raise ValueError("Invalid gold span offsets")
                return text[start:end]
            all_gold_values.update(value_of(label) for label in gold_rows[session])
            for label in category_rows[session]:
                value = value_of(label)
                all_gold_values.add(value)
                category = canonical_category(label["category"])
                full_pairs[category].add((session, value))
                if is_free(category):
                    for atom in category.split(":"):
                        atom_pairs[atom].add((session, value))
    if (set(category_rows) | set(gold_rows)) - seen:
        raise ValueError("Gold labels reference missing sessions")
    return TrainingValues(
        {c: Counter(v for _, v in pairs) for c, pairs in full_pairs.items()},
        {c: Counter(v for _, v in pairs) for c, pairs in atom_pairs.items()},
        sorted(span_counts), len(train_ids), all_gold_values, span_counts, dict(full_pairs),
    )



def skeleton_of(value: str) -> dict:
    shape = shape_of(value)
    if shape in ("digits", "hex_lower", "hex_upper", "hex_mixed"):
        alphabet = shape
        # Mixed hex retains case positions instead of inventing a case ratio.
        if shape != "hex_mixed" or structure_of(value, True):
            return dict(kind="uniform", alphabet=alphabet, length=len(value), padding=0,
                        **structure_of(value, shape.startswith("hex")))
    padding = len(value) - len(value.rstrip("="))
    body = value[:-padding] if padding else value
    variant = next((name for name in ("base64", "base64url")
                    if body and set(body) <= set(ALPHABETS[name])), None)
    encoded = (variant and (1 <= padding <= 2 or
               (padding == 0 and len(body) >= 16 and
                {"lower", "upper", "digit", "symbol"} <= character_classes(body))))
    if encoded:
        length = len(value) + (-len(value) % 4 if padding else 0)
        return dict(kind="uniform", alphabet=variant, length=length, padding=padding)
    tokens, pos = [], 0
    while pos < len(value):
        char = value[pos]
        if char == "%" and re.match(r"[0-9a-fA-F]{2}", value[pos + 1:pos + 3]):
            tokens.append(dict(kind="escape", case="".join(
                "0" if c in DIGITS else "A" if c in UPPER else "a" for c in value[pos+1:pos+3])))
            pos += 3
            continue
        if char in LOWER + UPPER:
            end = pos + 1
            while end < len(value) and value[end] in LOWER + UPPER:
                end += 1
            run = value[pos:end]
            tokens.append(dict(kind="letters", case="".join("A" if c in UPPER else "a" for c in run),
                               dictionary=dictionary_run(run)))
        elif char in DIGITS:
            end = pos + 1
            while end < len(value) and value[end] in DIGITS:
                end += 1
            tokens.append(dict(kind="digits", length=end-pos, **structure_of(value[pos:end])))
        elif not char.isascii() and unicodedata.category(char)[0] in "LNM":
            tokens.append(unicode_marker(char))
            end = pos + 1
        else:
            # Literal tokens contain only separators, whitespace or symbols.
            if tokens and tokens[-1]["kind"] == "literal":
                tokens[-1]["text"] += char
            else:
                tokens.append(dict(kind="literal", text=char))
            end = pos + 1
        pos = end
    return dict(kind="classes", tokens=tokens)


def usable_value(value: str) -> bool:
    return any(c.isalnum() for c in value)


def make_profile(values: Counter, source: str, category: str) -> dict:
    if not values:
        raise ValueError("A profile needs at least one training value")
    skeletons = Counter()
    repaired = dropped = 0
    for value, weight in sorted(values.items()):
        if not usable_value(value):
            dropped += weight
            continue
        skeleton = skeleton_of(value)
        repaired += weight * (skeleton.get("length", len(value)) != len(value))
        skeletons[json.dumps(skeleton, sort_keys=True, ensure_ascii=False)] += weight
    if not skeletons:
        raise ValueError("A profile needs a letter or digit position")
    cells, cumulative = [], []
    total = 0
    for encoded, weight in sorted(skeletons.items()):
        cells.append(dict(json.loads(encoded), weight=weight))
        total += weight
        cumulative.append(total)
    return dict(source=source, category=category, distinct_values=len(values),
                session_values=total, padding_repairs=repaired, dropped_symbol_values=dropped,
                skeletons=cells, cumulative_weights=cumulative)


def length_counts(values: Counter) -> Counter:
    counts = Counter()
    for value, weight in values.items():
        counts[len(value)] += weight
    return counts


def cdf_gap(left: Counter, right: Counter) -> float:
    total_a, total_b = sum(left.values()), sum(right.values())
    ca = cb = 0
    gap = 0.
    for knot in sorted(set(left) | set(right)):
        ca += left.get(knot, 0) / total_a
        cb += right.get(knot, 0) / total_b
        gap = max(gap, abs(ca - cb))
    return gap


def profile_distance(left: Counter, right: Counter) -> float:
    """Public fallback rule: shape TV + length KS + mean class-presence gap."""
    def features(values):
        shapes, classes = Counter(), Counter()
        total = sum(values.values())
        for value, weight in sorted(values.items()):
            shapes[shape_of(value)] += weight
            for name in character_classes(value):
                classes[name] += weight
        return (Counter({k: v / total for k, v in shapes.items()}),
                Counter({k: v / total for k, v in classes.items()}))
    a, ac = features(left)
    b, bc = features(right)
    return (sum(abs(a[s] - b[s]) for s in sorted(set(a) | set(b))) / 2
            + cdf_gap(length_counts(left), length_counts(right))
            + sum(abs(ac[c] - bc[c]) for c in CLASS_NAMES) / len(CLASS_NAMES))


def build_document(data: TrainingValues | None = None) -> dict:
    data = data if data is not None else load_training_values()
    singletons = {c: v for c, v in data.full.items()
                  if is_free(c) and ":" not in c and len(v) >= 2}
    if not singletons:
        raise ValueError("Need a free-form singleton category with at least two distinct values")
    profiles, fallbacks = {}, {}
    for category, values in sorted(data.full.items()):
        if not is_free(category):
            continue
        source = values
        if len(values) == 1:
            distances = {c: profile_distance(values, v) for c, v in sorted(singletons.items())}
            closest = min(distances, key=lambda c: (distances[c], c))
            source = pooled_values(data, category, closest)
            fallbacks[category] = dict(singleton=closest, distance=distances[closest],
                                       candidates=distances, own_distinct_values=1,
                                       singleton_distinct_values=len(singletons[closest]))
        profiles["category:" + category] = make_profile(source,
            "pooled_singleton" if len(values) == 1 else "full_category", category)
    resolutions = {c: "category:" + canonical_category(c) for c in sorted(data.categories) if is_free(c)}
    # Unseen free-form combinations use their most evidenced single atom.
    # Missing singleton atoms (e.g. Salt) are mapped by their train atom pool,
    # never by an unsupported hand-written family or specificity order.
    atom_resolutions = {}
    for atom, values in sorted(data.atoms.items()):
        own = "category:" + atom
        if own in profiles:
            atom_resolutions[atom] = own
        else:
            closest = min(singletons, key=lambda c: (profile_distance(values, singletons[c]), c))
            atom_resolutions[atom] = "category:" + closest
    return dict(version=2, weight_unit="distinct_session_value_pairs",
                sampling="empirical_skeletons", train_sessions=data.train_sessions,
                profiles=profiles, resolutions=resolutions, atom_resolutions=atom_resolutions,
                fallbacks=fallbacks)


def serialize_document(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


@lru_cache(maxsize=1)
def _document() -> dict:
    try:
        return json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"Missing CredData skeleton profile: {DEFAULT_OUTPUT}. "
                                f"Build it with: {BUILD_COMMAND}") from None


def _resolve(category: str, document: dict) -> str:
    canonical = canonical_category(category)
    if not is_free(canonical):
        raise KeyError(category)
    own = "category:" + canonical
    if own in document["profiles"]:
        return own
    candidates = {document["atom_resolutions"][a] for a in canonical.split(":")
                  if a in document["atom_resolutions"]}
    if not candidates:
        raise KeyError(category)
    return min(candidates, key=lambda key: (-document["profiles"][key]["session_values"], key))


def profile_for(category: str) -> str:
    return _resolve(category, _document())


def _index(draw, size: int) -> int:
    if not hasattr(draw, "raw"):
        return draw.int(size)
    width = max(1, (size.bit_length() + 7) // 8)
    bound = 256 ** width
    limit = bound - bound % size
    while True:
        number = int.from_bytes(draw.raw(width), "big")
        if number < limit:
            return number % size


def _chars(draw, length: int, alphabet: str) -> str:
    # Draw.chars uses byte modulo and biases alphabets that do not divide 256.
    # Rejection sampling gives genuinely uniform characters on its byte stream.
    if not hasattr(draw, "raw"):
        return "".join(draw.choice(alphabet) for _ in range(length))
    if len(alphabet) > 256:
        return "".join(alphabet[_index(draw, len(alphabet))] for _ in range(length))
    limit = 256 - 256 % len(alphabet)
    chars = []
    while len(chars) < length:
        for byte in draw.raw(length - len(chars)):
            if byte < limit:
                chars.append(alphabet[byte % len(alphabet)])
    return "".join(chars)


def _word(draw, length: int) -> str:
    candidates = WORDS_BY_LENGTH.get(length, ())
    if not candidates:
        return _chars(draw, length, LOWER)
    target = _index(draw, sum(weight for _, weight in candidates))
    for word, weight in candidates:
        if target < weight:
            return word
        target -= weight
    raise AssertionError("Unreachable dictionary choice")


def _structured(draw, length: int, alphabet: str, spec: dict) -> str:
    repeat = spec.get("repeat", 0)
    require_letter = spec.get("alphabet", "").startswith("hex_")
    if repeat:
        while True:
            block = _chars(draw, repeat, alphabet)
            # Avoid turning a repeated 4-character block into one repeated char.
            if not repeated_block(block) and (not require_letter or any(c in LOWER+UPPER for c in block)):
                return block * (length // repeat)
    if spec.get("sequence"):
        start = _index(draw, 10)
        return "".join(str((start + i * spec["sequence"]) % 10) for i in range(length))
    zeros = spec.get("leading_zeros", 0)
    while True:
        tail = _chars(draw, length - zeros, alphabet)
        if not require_letter or any(c in LOWER+UPPER for c in tail):
            return "0" * zeros + tail


def generate_from_skeleton(skeleton: dict, draw) -> str:
    if skeleton["kind"] == "uniform":
        padding = skeleton["padding"]
        return _structured(draw, skeleton["length"] - padding,
                           ALPHABETS[skeleton["alphabet"]], skeleton) + "=" * padding
    out = []
    for token in skeleton["tokens"]:
        kind = token["kind"]
        if kind == "letters":
            pattern = token["case"]
            run = _word(draw, len(pattern)) if token["dictionary"] else _chars(draw, len(pattern), LOWER)
            out.append("".join(c.upper() if case == "A" else c for c, case in zip(run, pattern)))
        elif kind == "digits":
            out.append(_structured(draw, token["length"], DIGITS, token))
        elif kind == "unicode":
            out.append(_chars(draw, 1, unicode_alphabet(**{k:v for k,v in token.items() if k != "kind"})))
        elif kind == "escape":
            out.append("%" + "".join(_chars(draw, 1, DIGITS if c == "0" else
                                           "ABCDEF" if c == "A" else "abcdef") for c in token["case"]))
        else:
            out.append(token["text"])
    return "".join(out)


def _plain(value: str, draw) -> str:
    out = []
    for i, char in enumerate(value):
        if char in PLAIN_ALPHABET and not (i == 0 and char == "-"):
            out.append(char)
            continue
        # Prefer the closest left neighbour, then the right; use its case or
        # digit class. Padding and dropped punctuation cannot create separators.
        neighbour = next((value[j] for d in range(1, len(value)+1)
                          for j in (i-d, i+d) if 0 <= j < len(value) and value[j] in ALNUM), "")
        alphabet = LOWER if neighbour in LOWER and neighbour else UPPER if neighbour in UPPER and neighbour else DIGITS if neighbour else ALNUM
        out.append(_chars(draw, 1, alphabet))
    return "".join(out)


def generate_from_profile(profile: dict, draw, plain: bool = False, avoid: str = "") -> str:
    for _ in range(MAX_ATTEMPTS):
        index = bisect_right(profile["cumulative_weights"], _index(draw, profile["session_values"]))
        value = generate_from_skeleton(profile["skeletons"][index], draw)
        if plain:
            value = _plain(value, draw)
        if not any(c in value for c in avoid):
            return value
    raise ValueError(f"Cannot generate a value satisfying avoid after {MAX_ATTEMPTS} attempts")


def generate(category: str, draw, plain: bool = False, avoid: str = "") -> str:
    document = _document()
    return generate_from_profile(document["profiles"][_resolve(category, document)], draw, plain, avoid)


def values_for_profile(data: TrainingValues, key: str) -> Counter:
    category = key.split(":", 1)[1]
    values = data.full[category]
    if len(values) >= 2:
        return values
    eligible = {c: v for c, v in data.full.items()
                if is_free(c) and ":" not in c and len(v) >= 2}
    closest = min(eligible, key=lambda c: (profile_distance(values, eligible[c]), c))
    return pooled_values(data, category, closest)


def pooled_values(data: TrainingValues, category: str, singleton: str) -> Counter:
    if data.pairs is not None:
        return Counter(value for _, value in data.pairs[category] | data.pairs[singleton])
    return data.full[category] + data.full[singleton]


def summary(document: dict, data: TrainingValues) -> str:
    lines = ["Own empirical skeletons are used for every category with >=2 distinct values.",
             "For one-value categories, the nearest singleton is pooled using shape TV + length KS + mean class-presence gap.",
             "", "| Category | Own distinct | Pairs | Pool | Distance | Pool distinct | Padding repairs |",
             "|---|---:|---:|---|---:|---:|---:|"]
    for category, values in sorted(data.full.items()):
        if not is_free(category):
            continue
        model = document["profiles"]["category:" + category]
        fallback = document["fallbacks"].get(category, {})
        lines.append(f"| {category} | {len(values)} | {sum(values.values())} | "
                     f"{fallback.get('singleton', 'own')} | {fallback.get('distance', 0):.4f} | "
                     f"{fallback.get('singleton_distinct_values', 0)} | {model['padding_repairs']} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "summary"))
    for name, default in (("sessions", DEFAULT_SESSIONS), ("labels", DEFAULT_LABELS),
                          ("train", DEFAULT_TRAIN), ("categories", DEFAULT_CATEGORIES), ("output", DEFAULT_OUTPUT)):
        parser.add_argument("--" + name, type=Path, default=default)
    args = parser.parse_args(argv)
    data = load_training_values(args.sessions, args.labels, args.train, args.categories)
    document = build_document(data)
    if args.command == "build":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialize_document(document), encoding="utf-8")
        print(f"Built {len(document['profiles'])} empirical category profiles at {args.output}; "
              f"{sum(m['padding_repairs'] for m in document['profiles'].values())} padded-length repairs.")
    else:
        print(summary(document, data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
