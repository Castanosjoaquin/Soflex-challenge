"""Evaluación of the copiloto over the dataset and its variantes ruidosas (SPEC §8).

`python -m app.eval.noise` writes the variantes; `python -m app.eval` replays them and writes the
table. Neither runs under pytest: only the generator and the metrics have unit tests.
"""
