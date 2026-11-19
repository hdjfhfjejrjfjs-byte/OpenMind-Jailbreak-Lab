"""Only benign, meaning-preserving representation transforms are registered."""
import base64, codecs, json, unicodedata
from .core import Kind, transform

@transform("format.quote", cost=.1, tags=("format", "benign"))
def quote(text, rng, **p):
    return 'Benign test input follows as data:\n"""\n' + text + '\n"""'

@transform("format.json", cost=.1, tags=("format", "parser"))
def json_envelope(text, rng, **p):
    return json.dumps({"input": text, "content_type": "plain_text"}, ensure_ascii=False)

@transform("format.line_wrap", cost=.1, tags=("format",))
def line_wrap(text, rng, width=48, **p):
    width = int(width)
    if not 1 <= width <= 512:
        raise ValueError("width must be between 1 and 512")
    return "\n".join(text[i:i + width] for i in range(0, len(text), width))

@transform("unicode.nfc", cost=.05, tags=("unicode", "normalization"))
def nfc(text, rng, **p):
    return unicodedata.normalize("NFC", text)

@transform("unicode.nfd", cost=.05, tags=("unicode", "normalization"))
def nfd(text, rng, **p):
    return unicodedata.normalize("NFD", text)

@transform("unicode.nfkc", cost=.05, tags=("unicode", "normalization"))
def nfkc(text, rng, **p):
    return unicodedata.normalize("NFKC", text)

@transform("encoding.base64", output_kind=Kind.BASE64, cost=.2, tags=("representation", "benign-only"))
def b64(text, rng, **p):
    return base64.b64encode(text.encode()).decode("ascii")

@transform("encoding.hex", output_kind=Kind.HEX, cost=.2, tags=("representation", "benign-only"))
def hex_encode(text, rng, **p):
    return text.encode().hex()

@transform("encoding.rot13", output_kind=Kind.ROT13, cost=.1, tags=("representation", "benign-only"))
def rot13(text, rng, **p):
    return codecs.encode(text, "rot_13")
