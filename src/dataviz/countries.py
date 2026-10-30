# dataviz/countries.py
#
# 27.10.2026: דגלים אוטומטיים לישויות שהן מדינות (images.flags). שם המדינה - בעברית או באנגלית, וכמה כינויים נפוצים -
# לקוד ISO של שתי אותיות, שהוא גם שם קובץ הדגל (<קוד>.png) בתיקיית הדגלים. הדגלים עצמם לא בריפו: הם יורדים רק
# בלחיצה בעורך (dataviz/web/flags.py), כמו המפות המוכנות. ההתאמה מתעלמת מרווחים, מקפים, גרשיים ואותיות גדולות.

import re
from typing import Dict, Iterable, Optional

# (קוד, שם באנגלית, שם בעברית, כינויים...)
COUNTRIES = (
    ("af", "Afghanistan", "אפגניסטן"), ("al", "Albania", "אלבניה"), ("dz", "Algeria", "אלג'יריה"),
    ("ad", "Andorra", "אנדורה"), ("ao", "Angola", "אנגולה"), ("ag", "Antigua and Barbuda", "אנטיגואה וברבודה"),
    ("ar", "Argentina", "ארגנטינה"), ("am", "Armenia", "ארמניה"), ("au", "Australia", "אוסטרליה"),
    ("at", "Austria", "אוסטריה"), ("az", "Azerbaijan", "אזרבייג'ן"), ("bs", "Bahamas", "איי בהאמה", "בהאמה"),
    ("bh", "Bahrain", "בחריין"), ("bd", "Bangladesh", "בנגלדש"), ("bb", "Barbados", "ברבדוס"),
    ("by", "Belarus", "בלארוס", "בלרוס"), ("be", "Belgium", "בלגיה"), ("bz", "Belize", "בליז"),
    ("bj", "Benin", "בנין"), ("bt", "Bhutan", "בהוטן"), ("bo", "Bolivia", "בוליביה"),
    ("ba", "Bosnia and Herzegovina", "בוסניה והרצגובינה", "בוסניה"), ("bw", "Botswana", "בוטסואנה"),
    ("br", "Brazil", "ברזיל"), ("bn", "Brunei", "ברוניי"), ("bg", "Bulgaria", "בולגריה"),
    ("bf", "Burkina Faso", "בורקינה פאסו"), ("bi", "Burundi", "בורונדי"), ("kh", "Cambodia", "קמבודיה"),
    ("cm", "Cameroon", "קמרון"), ("ca", "Canada", "קנדה"), ("cv", "Cape Verde", "כף ורדה"),
    ("cf", "Central African Republic", "הרפובליקה המרכז-אפריקאית"), ("td", "Chad", "צ'אד"),
    ("cl", "Chile", "צ'ילה"), ("cn", "China", "סין"), ("co", "Colombia", "קולומביה"),
    ("km", "Comoros", "קומורו"), ("cg", "Congo", "קונגו", "Republic of the Congo"),
    ("cd", "DR Congo", "הרפובליקה הדמוקרטית של קונגו", "Democratic Republic of the Congo", "קונגו קינשאסה"),
    ("cr", "Costa Rica", "קוסטה ריקה"), ("ci", "Ivory Coast", "חוף השנהב", "Côte d'Ivoire", "Cote d'Ivoire"),
    ("hr", "Croatia", "קרואטיה"), ("cu", "Cuba", "קובה"), ("cy", "Cyprus", "קפריסין"),
    ("cz", "Czechia", "צ'כיה", "Czech Republic"), ("dk", "Denmark", "דנמרק"), ("dj", "Djibouti", "ג'יבוטי"),
    ("dm", "Dominica", "דומיניקה"), ("do", "Dominican Republic", "הרפובליקה הדומיניקנית"),
    ("ec", "Ecuador", "אקוודור"), ("eg", "Egypt", "מצרים"), ("sv", "El Salvador", "אל סלבדור"),
    ("gq", "Equatorial Guinea", "גינאה המשוונית"), ("er", "Eritrea", "אריתריאה"), ("ee", "Estonia", "אסטוניה"),
    ("sz", "Eswatini", "אסוואטיני", "Swaziland", "סווזילנד"), ("et", "Ethiopia", "אתיופיה"), ("fj", "Fiji", "פיג'י"),
    ("fi", "Finland", "פינלנד"), ("fr", "France", "צרפת"), ("ga", "Gabon", "גבון"), ("gm", "Gambia", "גמביה"),
    ("ge", "Georgia", "גאורגיה", "גרוזיה"), ("de", "Germany", "גרמניה"), ("gh", "Ghana", "גאנה"),
    ("gr", "Greece", "יוון"), ("gd", "Grenada", "גרנדה"), ("gt", "Guatemala", "גואטמלה"), ("gn", "Guinea", "גינאה"),
    ("gw", "Guinea-Bissau", "גינאה ביסאו"), ("gy", "Guyana", "גיאנה"), ("ht", "Haiti", "האיטי"),
    ("hn", "Honduras", "הונדורס"), ("hu", "Hungary", "הונגריה"), ("is", "Iceland", "איסלנד"),
    ("in", "India", "הודו"), ("id", "Indonesia", "אינדונזיה"), ("ir", "Iran", "איראן", "אירן"), ("iq", "Iraq", "עיראק"),
    ("ie", "Ireland", "אירלנד"), ("il", "Israel", "ישראל"), ("it", "Italy", "איטליה"), ("jm", "Jamaica", "ג'מייקה"),
    ("jp", "Japan", "יפן"), ("jo", "Jordan", "ירדן"), ("kz", "Kazakhstan", "קזחסטן"), ("ke", "Kenya", "קניה"),
    ("ki", "Kiribati", "קיריבטי"), ("kp", "North Korea", "צפון קוריאה"), ("kr", "South Korea", "דרום קוריאה", "Korea"),
    ("xk", "Kosovo", "קוסובו"), ("kw", "Kuwait", "כווית"), ("kg", "Kyrgyzstan", "קירגיזסטן"), ("la", "Laos", "לאוס"),
    ("lv", "Latvia", "לטביה"), ("lb", "Lebanon", "לבנון"), ("ls", "Lesotho", "לסוטו"), ("lr", "Liberia", "ליבריה"),
    ("ly", "Libya", "לוב"), ("li", "Liechtenstein", "ליכטנשטיין"), ("lt", "Lithuania", "ליטא"),
    ("lu", "Luxembourg", "לוקסמבורג"), ("mg", "Madagascar", "מדגסקר"), ("mw", "Malawi", "מלאווי"),
    ("my", "Malaysia", "מלזיה"), ("mv", "Maldives", "האיים המלדיביים", "מלדיביים"), ("ml", "Mali", "מאלי"),
    ("mt", "Malta", "מלטה"), ("mh", "Marshall Islands", "איי מרשל"), ("mr", "Mauritania", "מאוריטניה"),
    ("mu", "Mauritius", "מאוריציוס"), ("mx", "Mexico", "מקסיקו"), ("fm", "Micronesia", "מיקרונזיה"),
    ("md", "Moldova", "מולדובה"), ("mc", "Monaco", "מונקו"), ("mn", "Mongolia", "מונגוליה"),
    ("me", "Montenegro", "מונטנגרו"), ("ma", "Morocco", "מרוקו"), ("mz", "Mozambique", "מוזמביק"),
    ("mm", "Myanmar", "מיאנמר", "Burma", "בורמה"), ("na", "Namibia", "נמיביה"), ("nr", "Nauru", "נאורו"),
    ("np", "Nepal", "נפאל"), ("nl", "Netherlands", "הולנד", "Holland"), ("nz", "New Zealand", "ניו זילנד"),
    ("ni", "Nicaragua", "ניקרגואה"), ("ne", "Niger", "ניז'ר"), ("ng", "Nigeria", "ניגריה"),
    ("mk", "North Macedonia", "צפון מקדוניה", "Macedonia", "מקדוניה"), ("no", "Norway", "נורווגיה"),
    ("om", "Oman", "עומאן"), ("pk", "Pakistan", "פקיסטן"), ("pw", "Palau", "פלאו"),
    ("ps", "Palestine", "פלסטין", "הרשות הפלסטינית"), ("pa", "Panama", "פנמה"),
    ("pg", "Papua New Guinea", "פפואה גינאה החדשה"), ("py", "Paraguay", "פרגוואי"), ("pe", "Peru", "פרו"),
    ("ph", "Philippines", "הפיליפינים", "פיליפינים"), ("pl", "Poland", "פולין"), ("pt", "Portugal", "פורטוגל"),
    ("qa", "Qatar", "קטאר"), ("ro", "Romania", "רומניה"), ("ru", "Russia", "רוסיה", "Russian Federation"),
    ("rw", "Rwanda", "רואנדה"), ("kn", "Saint Kitts and Nevis", "סנט קיטס ונוויס"), ("lc", "Saint Lucia", "סנט לוסיה"),
    ("vc", "Saint Vincent and the Grenadines", "סנט וינסנט והגרנדינים"), ("ws", "Samoa", "סמואה"),
    ("sm", "San Marino", "סן מרינו"), ("st", "Sao Tome and Principe", "סאו טומה ופרינסיפה"),
    ("sa", "Saudi Arabia", "ערב הסעודית", "סעודיה"), ("sn", "Senegal", "סנגל"), ("rs", "Serbia", "סרביה"),
    ("sc", "Seychelles", "סיישל"), ("sl", "Sierra Leone", "סיירה לאונה"), ("sg", "Singapore", "סינגפור"),
    ("sk", "Slovakia", "סלובקיה"), ("si", "Slovenia", "סלובניה"), ("sb", "Solomon Islands", "איי שלמה"),
    ("so", "Somalia", "סומליה"), ("za", "South Africa", "דרום אפריקה"), ("ss", "South Sudan", "דרום סודאן"),
    ("es", "Spain", "ספרד"), ("lk", "Sri Lanka", "סרי לנקה"), ("sd", "Sudan", "סודאן"), ("sr", "Suriname", "סורינאם"),
    ("se", "Sweden", "שוודיה"), ("ch", "Switzerland", "שווייץ", "שוויץ"), ("sy", "Syria", "סוריה"),
    ("tw", "Taiwan", "טייוואן"), ("tj", "Tajikistan", "טג'יקיסטן"), ("tz", "Tanzania", "טנזניה"),
    ("th", "Thailand", "תאילנד"), ("tl", "Timor-Leste", "מזרח טימור", "East Timor"), ("tg", "Togo", "טוגו"),
    ("to", "Tonga", "טונגה"), ("tt", "Trinidad and Tobago", "טרינידד וטובגו"), ("tn", "Tunisia", "תוניסיה"),
    ("tr", "Turkey", "טורקיה", "Türkiye"), ("tm", "Turkmenistan", "טורקמניסטן"), ("tv", "Tuvalu", "טובאלו"),
    ("ug", "Uganda", "אוגנדה"), ("ua", "Ukraine", "אוקראינה"), ("ae", "United Arab Emirates", "איחוד האמירויות", "UAE", "האמירויות"),
    ("gb", "United Kingdom", "בריטניה", "UK", "Great Britain", "הממלכה המאוחדת", "אנגליה", "England"),
    ("us", "United States", "ארצות הברית", "USA", "US", "United States of America", "ארה\"ב", "ארהב"),
    ("uy", "Uruguay", "אורוגוואי"), ("uz", "Uzbekistan", "אוזבקיסטן"), ("vu", "Vanuatu", "ונואטו"),
    ("va", "Vatican City", "הוותיקן", "Vatican"), ("ve", "Venezuela", "ונצואלה"), ("vn", "Vietnam", "וייטנאם", "Viet Nam"),
    ("ye", "Yemen", "תימן"), ("zm", "Zambia", "זמביה"), ("zw", "Zimbabwe", "זימבבואה"),
    ("hk", "Hong Kong", "הונג קונג"), ("pr", "Puerto Rico", "פוארטו ריקו"), ("eu", "European Union", "האיחוד האירופי", "EU"),
)

_FLAG_EMOJI = re.compile("[\U0001F1E6-\U0001F1FF]{2}")


def _key(name: str) -> str:
    """שם להשוואה: בלי אימוג'י דגל, רווחים, מקפים, נקודות וגרשיים, באותיות קטנות."""
    name = _FLAG_EMOJI.sub("", str(name))
    return re.sub(r"[\s\-_.'\"’`׳״]+", "", name).casefold()


def _build() -> Dict[str, str]:
    table: Dict[str, str] = {}
    for code, *names in COUNTRIES:
        for name in (code, *names):
            table.setdefault(_key(name), code)
    return table


_BY_NAME = _build()


def country_code(entity: object) -> Optional[str]:
    """קוד ISO (שתי אותיות קטנות) של ישות שהיא מדינה, או None. גם דגל כאימוג'י ("🇺🇸") או שם עם דגל ("USA 🇺🇸")."""
    text = str(entity)
    emoji = _FLAG_EMOJI.search(text)
    if emoji:
        code = "".join(chr(ord(c) - 0x1F1E6 + ord("a")) for c in emoji.group(0))
        if code in {c for c, *_ in COUNTRIES}:
            return code
    return _BY_NAME.get(_key(text))


def codes_for(entities: Iterable[object]) -> Dict[str, str]:
    """ישות (כטקסט) -> קוד, רק לישויות שזוהו כמדינות."""
    found = {}
    for entity in entities:
        code = country_code(entity)
        if code:
            found[str(entity)] = code
    return found
