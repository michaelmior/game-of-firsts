import argparse
from pathlib import Path
from urllib.parse import urlencode, quote_plus
from urllib.request import urlopen, urlretrieve
import collections
import json
import random
import string
import sys

from playsound import playsound
import ollama


POPULARITY_THRESHOLD = 10_000
UPPER_POPULARITY_THRESHOLD = 1_000
LETTER_RETRIES = 10
MODELFILE = """
FROM llama3.1
SYSTEM You are a puzzle designer who is going to help create a word puzzle. Any pieces of the puzzle you generate should be short and simple and easily understandable to the average English-speaking adult anywhere in the world.
"""
VOICE = "coqui-tts:en_ljspeech"
SSML_TEMPLATE = """<speak>
  The letters are {letters[0]}, and {letters[1]}.
  <break time="0.5s" />
  The first clue is {clues[0]}.
  <break time="5s" />
  The second clue is {clues[1]}.
  <break time="5s" />
  The third clue is {clues[2]}.
  <break time="5s" />
  The fourth clue is {clues[3]}.
  <break time="5s" />
  The last clue is {clues[4]}.
  <break time="10s" />
  The answer is {phrase}.
</speak>"""
LETTER_PRONUNCIATIONS = {
    "A": "Ae",
    "B": "Bee",
    "C": "Cee",
    "D": "Dee",
    "E": "Eeh",
    "F": "Eff",
    "G": "Gee",
    "H": "Ayche",
    "I": "Eye",
    "J": "Jay",
    "K": "Kay",
    "L": "Ell",
    "M": "Em",
    "N": "En",
    "O": "Oh",
    "P": "Pee",
    "Q": "Cue",
    "R": "Are",
    "S": "Ess",
    "T": "Tee",
    "U": "You",
    "V": "Vee",
    "W": "Double You",
    "X": "Ex",
    "Y": "Why",
    "Z": "Zee",
}
STOP_WORDS = ["A", "AND"]


def pick_phrase(letter1, letter2, past_phrases=set()):
    # Avoid similar phrases
    if len(past_phrases) > 1:
        phrase_str = (
            "Do not pick phrases similar to "
            + " or ".join('"' + p + '"' for p in past_phrases)
            + "."
        )
    else:
        phrase_str = ""

    messages = [
        {
            "role": "user",
            "content": f"I will give you two letters and then you will think of a very simple two word phrase that starts with those two letters. For example, if I give you the letters C and F, you might pick Correctional Facility. For the letters P and T, you might select Party Trick. {phrase_str} Respond with only the two word phrase and nothing else. The letters are {letter1} and {letter2}.",
        },
    ]

    # Note: Decaying the temperature below prevents the model
    #       from ignoring the phrases it was told to avoid

    response = ollama.chat(
        model="wordpuzzle",
        messages=messages,
        options={"temperature": 1 + 1 / (2 ** len(past_phrases))},
    )
    phrase = response["message"]["content"]
    return phrase


def pick_phrase_with_retry(letter1, letter2, past_phrases=set(), limit_retries=True):
    phrase = pick_phrase(letter1, letter2)
    letter_attempts = 0
    is_valid = is_valid_phrase(phrase, past_phrases, letters)
    while (letter_attempts < LETTER_RETRIES or not limit_retries) and not is_valid:
        sys.stderr.write(f"Invalid phrase {phrase}, trying again\n")
        phrase = pick_phrase(letters[0], letters[1], past_phrases)
        letter_attempts += 1
        is_valid = is_valid_phrase(phrase, past_phrases, letters)

    return (phrase, is_valid)


def get_clues(phrase):
    messages = [
        {
            "role": "user",
            "content": f'I am going to give you a two word phrase and I would like you to devise five very short clues (three or four words maximum) that will help someone guess the phrase. The first clue should be very vague and subsequent clues should get increasingly specific. Do not use any of the words from the phrase anywhere in any of the clues or elsewhere in your response. Output should be a simple numbered list in Markdown format. The two word phrase is "{phrase}".',
        },
    ]
    response = ollama.chat(model="wordpuzzle", messages=messages)
    clues = response["message"]["content"].split("\n")
    return clues[-5:]


def is_popular(phrase):
    # Check the popularity of the phrase via Google n-grams
    query_str = urlencode({"query": phrase}, quote_via=quote_plus)
    with urlopen("https://api.ngrams.dev/eng/search?" + query_str) as response:
        data = json.load(response)
        total = sum([item["absTotalMatchCount"] for item in data["ngrams"]])

        # Get the uppercase version of the phrase
        phrase = phrase.upper()

        # Separately check that the uppercase version of
        # the phrase meets a second popularity threshold.
        # It's unclear why this works, but it seems effective.
        upper_count = 0
        for item in data["ngrams"]:
            ngram = " ".join(t["text"] for t in item["tokens"])
            if ngram == phrase:
                upper_count = item["absTotalMatchCount"]
                break

        return (
            total >= POPULARITY_THRESHOLD and upper_count >= UPPER_POPULARITY_THRESHOLD
        )


def is_valid_phrase(phrase, past_phrases, letters):
    # The phrase must be popular and contain exactly two words
    words = phrase.upper().split(" ")
    return (
        phrase not in past_phrases
        and len(words) == 2
        and words[0][0] == letters[0]
        and words[1][0] == letters[1]
        and is_popular(phrase)
        and not any(word in STOP_WORDS for word in words)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--letters", nargs=2, metavar="LETTER", default=None)
    parser.add_argument("--output", default="output.wav")
    parser.add_argument("--play", action="store_true", default=False)
    parser.add_argument("--num-puzzles", type=int, default=1)
    parser.add_argument(
        "--words", nargs="?", default="/usr/share/dict/words", const=None
    )
    parser.add_argument("--opentts-host", default="localhost")
    parser.add_argument("--opentts-port", type=int, default=5500)
    args = parser.parse_args()

    # Get a frequency table for first letters of words
    if not args.letters:
        counter = collections.defaultdict(int)
        if args.words is not None:
            for line in open(args.words):
                line = line.upper()
                if line[0] in string.ascii_uppercase:
                    counter[line[0]] += 1
        else:
            for letter in string.ascii_uppercase:
                counter[letter] += 1

    # Build a model with a new system prompt
    ollama.create(model="wordpuzzle", modelfile=MODELFILE)

    # Keep track of history
    output_puzzles = 0
    past_phrases = set()

    # Continue picking letters and phrases until we get a valid one
    while output_puzzles < args.num_puzzles:
        # Select two letters based on the frequency table
        if args.letters is not None:
            letters = args.letters
        else:
            weights = list(counter.values())
            letters = random.choices(string.ascii_uppercase, weights=weights, k=1)
            weights[string.ascii_uppercase.index(letters[0])] /= 2
            letters += random.choices(string.ascii_uppercase, weights=weights, k=1)
            sys.stderr.write(f"Letters: {letters}\n")

        # Fix the letters if we need more than one puzzle
        if args.num_puzzles > 1:
            args.letters = letters

        # Keep trying to pick a good phrase
        phrase, is_valid = pick_phrase_with_retry(
            letters[0], letters[1], past_phrases, limit_retries=args.letters is not None
        )

        # If we found an invalid phrase, stop
        if not is_valid:
            break

        past_phrases.add(phrase)

        if args.num_puzzles > 1:
            path = Path(args.output)
            output = f"{args.output}{output_puzzles + 1}.wav"
            output = f"{path.stem}{output_puzzles + 1}{path.suffix}"
        else:
            output = args.output

        clues = get_clues(phrase)
        clue_str = "\n".join(clues)
        sys.stderr.write(f"Clues: \n{clue_str}\n")
        pronunciation = [LETTER_PRONUNCIATIONS[letter] for letter in letters]
        text = SSML_TEMPLATE.format(letters=pronunciation, clues=clues, phrase=phrase)
        query_str = urlencode(
            {"text": text, "ssml": "true", "cache": "false", "voice": VOICE},
            quote_via=quote_plus,
        )

        sys.stderr.write("Generating audio...\n")
        urlretrieve(
            f"http://{args.opentts_host}:{args.opentts_port}/api/tts?" + query_str,
            output,
        )
        if args.play:
            sys.stderr.write("Playing...\n")
            playsound(output)

        output_puzzles += 1
