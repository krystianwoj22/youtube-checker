# YouTube Checker — zasady sesji

## Język

**Zawsze odpowiadaj po polsku.** Krystian pracuje po polsku — dotyczy to całej
rozmowy oraz wyniku `/check` (bloki EVIDENCE / VERDICT / PACKAGING FIX itd. piszemy
po polsku). Wyjątki: nazwy pól evidence JSON, komendy, nazwy werdyktów
(FILM NOW / DON'T FILM...) i etykiety struktury outputu zostają po angielsku —
to identyfikatory, nie proza. Tytuły propozycji w PACKAGING FIX mogą być po
angielsku, jeśli film celuje w anglojęzyczną widownię — spytaj tylko wtedy,
gdy nie wynika to z kontekstu.

## Projekt w skrócie

Walidator pomysłów na wideo uruchamiany na żądanie (`/check`). Wejście: news,
link, screenshot albo wiersz backlogu. Wyjście: werdykt + score (przewidywana
wielokrotność mediany kanału) + dowody + najsilniejszy argument przeciw +
poprawka packagingu. Procedura operacyjna: `.claude/skills/check/SKILL.md`.

- Score liczy `scripts/score.py` — model raportuje liczbę, nie negocjuje jej.
- Dowody zbieramy i zapisujemy PRZED werdyktem, zawsze.
- Bez klucza API (zmienna `YOUTUBE_API_KEY` ze środowiska chmury albo `.env`)
  mediana i live supply nie działają — wtedy fallback: screenshot wyników
  wyszukiwania YouTube + web search, a braki oznaczamy jako `unknown`/`null`,
  nigdy nie zgadujemy.
- Każdy run kończy się wpisem do `data/predictions.csv` (`predlog.py add`).

## Testy

```bash
python -m unittest discover tests
```
