"""Dashboard "Marvel Fact of the Day" -- a curated list of trivia spanning
the MCU, Fox's X-Men films, Sony's Spider-Man/Venom films, and the wider
history of Marvel on screen.

IMPORTANT LIMITATION: this environment has no web browsing/search
access, so none of these facts have been independently verified
against Marvel Wiki, IMDb, or any other outside source -- they're
written from general background knowledge, restricted to claims common
and well-established enough to be reasonably confident about, with
anything more specific, obscure, or interpretive deliberately left out
rather than risk stating it as fact. Even so, "reasonably confident"
is not the same as "verified." Before shipping this to real users, it's
worth having someone (or a Claude session with actual web search
enabled) fact-check this list against a real source and correct
anything that's wrong.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

FACTS: tuple[str, ...] = (
    "Iron Man, the film that kicked off the MCU in 2008, wasn't a "
    "shoo-in at the time -- Robert Downey Jr. was considered a risky "
    "casting choice by some at the studio, and Marvel had to personally "
    "vouch for him to get insurance companies on board.",
    "The now-famous Marvel Studios post-credits scene tradition started "
    "with Iron Man's very first film, when Samuel L. Jackson appeared as "
    "Nick Fury to mention the \"Avenger Initiative\" -- a scene shot in "
    "secret with a skeleton crew.",
    "Chris Evans turned down the role of Captain America at first, "
    "reportedly worried about the long-term commitment a Marvel contract "
    "would require, before eventually accepting.",
    "The Hulk has been played by three different actors across the "
    "franchise's live-action history: Eric Bana, Edward Norton, and Mark "
    "Ruffalo, with Ruffalo the only one to stick around for the wider "
    "shared universe.",
    "Groot's dialogue in the Guardians of the Galaxy films is almost "
    "entirely the same three words -- \"I am Groot\" -- but Vin Diesel "
    "reportedly recorded many different line readings and deliveries to "
    "give each version a distinct emotional meaning.",
    "Avengers: Endgame briefly became the highest-grossing film of all "
    "time worldwide, a title it held before being overtaken again later.",
    "Tom Holland is famously bad at keeping Spider-Man plot secrets -- "
    "several productions have reportedly fed him fake pages or false "
    "details specifically to throw off leaks.",
    "The Russo Brothers, who directed several of the biggest Avengers "
    "films, got their start directing episodes of sitcoms, including "
    "Community and Arrested Development, before moving to blockbuster "
    "filmmaking.",
    "Wesley Snipes' Blade movies, starting in 1998, predate the MCU by a "
    "full decade and are often credited with helping prove that a "
    "Marvel character could carry a successful franchise on the big "
    "screen.",
    "Deadpool's fourth-wall-breaking style made the character notoriously "
    "difficult to adapt -- Ryan Reynolds spent years advocating for a "
    "faithful R-rated version before the first film finally got made.",
    "Hugh Jackman played Wolverine across nearly two decades of films, "
    "from 2000's X-Men to 2024's Deadpool & Wolverine, making it one of "
    "the longest runs any actor has had in a single superhero role.",
    "Thanos, the MCU's central villain across its first three phases, "
    "appeared only in a brief post-credits scene for years before ever "
    "getting real screen time.",
    "Black Panther was the first Marvel Studios film to receive a Best "
    "Picture nomination at the Academy Awards.",
    "Stan Lee made a cameo appearance in nearly every Marvel Studios film "
    "released during his lifetime, a tradition that started small and "
    "became something audiences actively watched for.",
    "The Infinity Gauntlet storyline that Avengers: Infinity War and "
    "Endgame are loosely based on originally ran as a comic book "
    "miniseries in the early 1990s.",
    "Andrew Garfield returned to play Peter Parker again in Spider-Man: "
    "No Way Home years after his own Amazing Spider-Man series had "
    "ended, reuniting with Tobey Maguire's version of the character for "
    "the first time on screen.",
    "Robert Downey Jr. improvised a significant amount of Tony Stark's "
    "dialogue across the franchise, and several of his most quoted lines "
    "were reportedly not in the original scripts.",
    "The Fantastic Four have been adapted into a live-action film more "
    "times than almost any other Marvel property, including a low-budget "
    "1994 version that was never officially released in theaters.",
    "Wanda Maximoff and Pietro Maximoff (Scarlet Witch and Quicksilver) "
    "were originally tied to the X-Men in the comics as Magneto's "
    "children, a connection the early MCU films couldn't use due to "
    "film rights being split between studios at the time.",
    "Venom's design in the comics started as a simple alien costume for "
    "Spider-Man before writers gave it its own separate, symbiotic "
    "identity entirely.",
    "James Gunn was briefly let go from directing Guardians of the "
    "Galaxy Vol. 3 before being reinstated, following pressure from the "
    "film's own cast in his support.",
    "Loki was originally intended to appear in only one Marvel film, "
    "but Tom Hiddleston's performance as the character proved popular "
    "enough that the role expanded across nearly every phase of the "
    "franchise since.",
    "Ms. Marvel's Kamala Khan, introduced in the comics in 2014, was "
    "one of the first Muslim characters to headline her own ongoing "
    "Marvel series.",
    "X-Men: Days of Future Past was based on a much-loved two-issue "
    "comic book story from 1981 that has been reprinted and referenced "
    "many times since.",
    "Michael B. Jordan played the Human Torch in 2015's Fantastic Four "
    "years before taking on the very different role of Killmonger in "
    "Black Panther.",
)


@dataclass(frozen=True)
class FactOfTheDay:
    text: str
    day_index: int


def get_fact_of_the_day(on_date: date | None = None) -> FactOfTheDay:
    """Picks one fact deterministically from `on_date` (today, by
    default) -- the same fact shows all day and only changes at
    midnight, rather than a different one every time the Dashboard
    happens to refresh. Cycles back through the list once it's been
    exhausted (day 31 shows the same fact as day 1 again, etc.), rather
    than repeating today's fact for the rest of the list's lifetime."""
    target_date = on_date or date.today()
    index = target_date.toordinal() % len(FACTS)
    return FactOfTheDay(text=FACTS[index], day_index=index)
