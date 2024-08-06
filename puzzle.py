from urllib.parse import urlencode, quote_plus
from urllib.request import urlopen, urlretrieve
import collections
import json
import random
import string

from TTS.api import TTS
from playsound import playsound
import ollama


POPULARITY_THRESHOLD = 10_000
LETTER_RETRIES = 5
MODELFILE = """
FROM llama3.1
SYSTEM You are a puzzle designer who is going to help create a word puzzle. Any pieces of the puzzle you generate should be short and simple and easily understandable to the average English-speaking adult anywhere in the world.
"""
VOICE = "coqui-tts:en_ljspeech"
SSML_TEMPLATE = """<speak>
  The letters are {letters[0]} and {letters[1]}.
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
    "A": "A",
    "B": "Bee",
    "C": "Cee",
    "D": "Dee",
    "E": "E",
    "F": "Eff",
    "G": "Gee",
    "H": "Aitch",
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


def pick_phrase(letter1, letter2):
    messages = [
        {
            "role": "user",
            "content": f"I will give you two letters and then you will think of a very simple two word phrase that starts with those two letters. For example, if I give you the letters C and F, you might pick Correctional Facility. For the letters P and T, you might select Party Trick. Respond with only the two word phrase and nothing else. The letters are {letter1} and {letter2}.",
        },
    ]
    response = ollama.chat(
        model="wordpuzzle", messages=messages, options={"temperature": 2}
    )
    phrase = response["message"]["content"]
    return phrase


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


def get_popularity(phrase):
    # Check the popularity of the phrase via Google n-grams
    query_str = urlencode({"query": phrase}, quote_via=quote_plus)
    with urlopen("https://api.ngrams.dev/eng/search?" + query_str) as response:
        data = json.load(response)
        return sum([item["absTotalMatchCount"] for item in data["ngrams"]])


def is_valid_phrase(phrase, letters):
    # The phrase must be popular and contain exactly two words
    words = phrase.upper().split(" ")
    return (
        len(words) == 2
        and words[0][0] == letters[0]
        and words[1][0] == letters[1]
        and get_popularity(phrase) >= POPULARITY_THRESHOLD
    )


if __name__ == "__main__":
    # Get a frequency table for first letters of words
    counter = collections.defaultdict(int)
    for line in open("/usr/share/dict/words"):
        line = line.upper()
        if line[0] in string.ascii_uppercase:
            counter[line[0]] += 1

    # Build a model with a new system prompt
    ollama.create(model="wordpuzzle", modelfile=MODELFILE)

    # Continue picking letters and phrases until we get a valid one
    while True:
        # Select two letters based on the frequency table
        letters = random.choices(string.ascii_uppercase, weights=counter.values(), k=2)
        letter_attempts = 0

        # Keep trying to pick a good phrase
        phrase = pick_phrase(*letters)
        is_valid = is_valid_phrase(phrase, letters)
        while letter_attempts < LETTER_RETRIES and not is_valid:
            phrase = pick_phrase(letters[0], letters[1])
            letter_attempts += 1
            is_valid = is_valid_phrase(phrase, letters)

        # If we found a valid phrase, stop
        if is_valid:
            break

    clues = get_clues(phrase)
    pronunciation = [LETTER_PRONUNCIATIONS[letter] for letter in letters]
    text = SSML_TEMPLATE.format(letters=pronunciation, clues=clues, phrase=phrase)
    query_str = urlencode(
        {"text": text, "ssml": "true", "cache": "false", "voice": VOICE},
        quote_via=quote_plus,
    )
    urlretrieve("http://localhost:5500/api/tts?" + query_str, "output.wav")
    playsound("output.wav")
