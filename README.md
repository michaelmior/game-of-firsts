# Game of Firsts

This repo is inspired by [The Initials Game](https://www.initialsgame.com/).
It uses Ollama to generate puzzles where given two letters and several clues, you must guess a two-word phrase.
An example is below.

[example.webm](https://github.com/user-attachments/assets/0d79be8b-4bf4-4202-82cf-b39308cc9e90)

# Installation

Dependencies are managed with [pipenv](https://pipenv.pypa.io/en/latest/) and can be installed with `pipenv install`.
The project relies on [OpenTTS](https://github.com/synesthesiam/opentts) for text-to-speech.
Refer to OpenTTS documentation for configuration instructions, but currently this is as simple as running via Docker as below.

    docker run -it -p 5500:5500 synesthesiam/opentts:en

# Running

To generate a puzzle, run the following command:

    pipenv run python puzzle.py

By default, audio of the puzzle will be written to `output.wav`.
You can change the output file with the `--output` flag.
You can also immediately play the audio with the `--play` flag.
Run with `--help` to see available options.
