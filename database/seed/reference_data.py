from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    Achievement,
    AchievementCriteriaType,
    AchievementTier,
    Franchise,
    Genre,
    UserAchievement,
    Universe,
)

logger = logging.getLogger(__name__)

# --- Universes --------------------------------------------------------------
UNIVERSES: list[dict] = [
    {
        "name": "Marvel Cinematic Universe",
        "slug": "mcu",
        "abbreviation": "MCU",
        "description": "The flagship shared universe of films and series produced by Marvel Studios.",
        "color_hex": "#E62429",
        "sort_order": 1,
    },
    {
        "name": "Sony's Spider-Man Universe",
        "slug": "sony-spider-man-universe",
        "abbreviation": "SSU",
        "description": "Sony Pictures' universe built around Spider-Man villains and allies.",
        "color_hex": "#8B0000",
        "sort_order": 2,
    },
    {
        "name": "X-Men Universe (Fox)",
        "slug": "fox-x-men-universe",
        "abbreviation": "FOX-X",
        "description": "20th Century Fox's X-Men film series, produced prior to the Disney acquisition.",
        "color_hex": "#1B3A6B",
        "sort_order": 3,
    },
    {
        "name": "Marvel Television (Pre-MCU)",
        "slug": "marvel-television-classic",
        "abbreviation": "MTV",
        "description": "Earlier Marvel TV productions made outside current MCU continuity.",
        "color_hex": "#4A4A4A",
        "sort_order": 4,
    },
    {
        "name": "Marvel Television (ABC/Netflix)",
        "slug": "marvel-television-abc-netflix",
        "abbreviation": "MTV-ABC",
        "description": (
            "The 2013-2020 slate of Marvel Television/ABC Studios series "
            "(Agents of S.H.I.E.L.D., Agent Carter, the Netflix Defenders "
            "shows, and their Hulu/Freeform siblings), set within or "
            "adjacent to MCU continuity but produced outside Marvel "
            "Studios and never assigned an MCU phase."
        ),
        "color_hex": "#B8860B",
        "sort_order": 5,
    },
]

# --- Franchises (keyed by parent universe slug) ------------------------------
FRANCHISES: list[dict] = [
    {"universe": "mcu", "name": "Avengers", "slug": "avengers"},
    {"universe": "mcu", "name": "Iron Man", "slug": "iron-man"},
    {"universe": "mcu", "name": "Captain America", "slug": "captain-america"},
    {"universe": "mcu", "name": "Thor", "slug": "thor"},
    {"universe": "mcu", "name": "Guardians of the Galaxy", "slug": "guardians-of-the-galaxy"},
    {"universe": "mcu", "name": "Spider-Man", "slug": "mcu-spider-man"},
    {"universe": "mcu", "name": "Doctor Strange", "slug": "doctor-strange"},
    {"universe": "mcu", "name": "Black Panther", "slug": "black-panther"},
    {"universe": "mcu", "name": "Ant-Man", "slug": "ant-man"},
    {"universe": "mcu", "name": "Captain Marvel", "slug": "captain-marvel"},
    {"universe": "mcu", "name": "Disney+ Series", "slug": "mcu-disney-plus-series"},
    {"universe": "sony-spider-man-universe", "name": "Venom", "slug": "venom"},
    {"universe": "sony-spider-man-universe", "name": "Morbius", "slug": "morbius"},
    {"universe": "fox-x-men-universe", "name": "X-Men", "slug": "fox-x-men"},
    {"universe": "fox-x-men-universe", "name": "Deadpool", "slug": "fox-deadpool"},
    {"universe": "fox-x-men-universe", "name": "Wolverine", "slug": "fox-wolverine"},
    {"universe": "marvel-television-abc-netflix", "name": "ABC/Netflix Series", "slug": "abc-netflix-series"},
]

# --- Genres -------------------------------------------------------------------
GENRES: list[str] = [
    "Action",
    "Adventure",
    "Science Fiction",
    "Fantasy",
    "Comedy",
    "Drama",
    "Thriller",
    "Animation",
    "Documentary",
    "Family",
    "Crime",
    "Mystery",
    "War",
]

# --- Achievements ---------------------------------------------------------
# 51 total: 10 each of Bronze/Silver/Gold/Platinum/Diamond, plus one
# top-of-the-heap "Marvelous" achievement for unlocking every other one.
#
# Every WATCH_COUNT/REWATCH_COUNT/RATING_COUNT threshold stays within what's
# actually reachable against the shipped catalog (148 projects, 123 of them
# RELEASED) -- rewatches are uncapped (the same project can be rewatched
# indefinitely) so those ladders run higher than the watch/rating ones,
# which top out just under the catalog size as a genuine "watch/rate
# nearly everything" stretch goal.
#
# FRANCHISE_COMPLETE/UNIVERSE_COMPLETE entries are ordered into tiers by
# real difficulty -- how many projects actually have to be watched to
# complete them, checked against the shipped database -- not just picked
# arbitrarily: Doctor Strange and Captain Marvel (2 projects each) are
# Bronze, all the way up to the whole MCU (119 projects) as the single
# Diamond-tier completion. Sony's Spider-Man Universe, the Fox X-Men
# Universe, and their per-franchise breakdowns (Venom, Morbius, X-Men,
# Deadpool, Wolverine) are deliberately *not* used here: none of them have
# any synced projects yet, so a completion achievement against any of them
# would be permanently stuck at 0% -- the same "never seed something that
# can't evaluate" rule GENRE_COUNT is held to.
#
# ALL_ACHIEVEMENTS_COMPLETE has no criteria_reference (see
# services.achievement_service._all_achievements_percent) -- it just reads
# the unlock state of every other achievement directly.
ACHIEVEMENTS: list[dict] = [
    # --- Bronze (10) ---------------------------------------------------------
    {
        "key": "first_watch",
        "name": "First Steps",
        "description": "Watch your very first Marvel project.",
        "icon": "footprints",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 1,
    },
    {
        "key": "watch_5",
        "name": "Marathon Starter",
        "description": "Watch 5 Marvel projects.",
        "icon": "clapper",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 5,
    },
    {
        "key": "watch_10",
        "name": "Binge Mode Engaged",
        "description": "Watch 10 Marvel projects.",
        "icon": "tv",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 10,
    },
    {
        "key": "watch_15",
        "name": "Deep Cuts Curious",
        "description": "Watch 15 Marvel projects.",
        "icon": "popcorn",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 15,
    },
    {
        "key": "rewatch_1",
        "name": "One More Time",
        "description": "Log your first rewatch.",
        "icon": "replay",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.REWATCH_COUNT,
        "criteria_value": 1,
    },
    {
        "key": "rewatch_3",
        "name": "Comfort Rewatch",
        "description": "Log 3 rewatches across your library.",
        "icon": "couch",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.REWATCH_COUNT,
        "criteria_value": 3,
    },
    {
        "key": "rate_5",
        "name": "First Impressions",
        "description": "Rate 5 different projects.",
        "icon": "notepad",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 5,
    },
    {
        "key": "rate_10",
        "name": "Building a Critique",
        "description": "Rate 10 different projects.",
        "icon": "clipboard",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 10,
    },
    {
        "key": "doctor_strange_complete",
        "name": "Master of the Mystic Arts",
        "description": "Watch every project in the Doctor Strange franchise.",
        "icon": "portal",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "doctor-strange",
    },
    {
        "key": "captain_marvel_complete",
        "name": "Higher, Further, Faster",
        "description": "Watch every project in the Captain Marvel franchise.",
        "icon": "blitz",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "captain-marvel",
    },
    {
        "key": "watch_3",
        "name": "Getting Started",
        "description": "Watch 3 Marvel projects.",
        "icon": "popcorn",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 3,
    },
    {
        "key": "rate_3",
        "name": "Speaking Up",
        "description": "Rate 3 different projects.",
        "icon": "notepad",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 3,
    },
    {
        "key": "ghost_rider_complete",
        "name": "Spirit of Vengeance",
        "description": "Watch every project in the Ghost Rider franchise.",
        "icon": "flame",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "ghost-rider",
    },
    {
        "key": "blade_complete",
        "name": "Daywalker",
        "description": "Watch every project in the Blade franchise.",
        "icon": "dagger",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "blade",
    },
    {
        "key": "venom_complete",
        "name": "We Are Venom",
        "description": "Watch every project in the Venom franchise.",
        "icon": "venom",
        "tier": AchievementTier.BRONZE,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "venom",
    },
    # --- Silver (10) ---------------------------------------------------------
    {
        "key": "watch_20",
        "name": "Settling In",
        "description": "Watch 20 Marvel projects.",
        "icon": "clapper",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 20,
    },
    {
        "key": "watch_25",
        "name": "Getting Serious",
        "description": "Watch 25 Marvel projects.",
        "icon": "popcorn",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 25,
    },
    {
        "key": "rewatch_5",
        "name": "Second Helpings",
        "description": "Log 5 rewatches across your library.",
        "icon": "replay",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.REWATCH_COUNT,
        "criteria_value": 5,
    },
    {
        "key": "rewatch_10",
        "name": "Worth Watching Twice",
        "description": "Log 10 rewatches across your library.",
        "icon": "refresh",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.REWATCH_COUNT,
        "criteria_value": 10,
    },
    {
        "key": "rate_15",
        "name": "Sharing Opinions",
        "description": "Rate 15 different projects.",
        "icon": "notepad",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 15,
    },
    {
        "key": "rate_20",
        "name": "Developing a Palate",
        "description": "Rate 20 different projects.",
        "icon": "clipboard",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 20,
    },
    {
        "key": "iron_man_complete",
        "name": "I Am Iron Man",
        "description": "Watch every project in the Iron Man franchise.",
        "icon": "reactor",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "iron-man",
    },
    {
        "key": "black_panther_complete",
        "name": "Wakanda Forever",
        "description": "Watch every project in the Black Panther franchise.",
        "icon": "gem",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "black-panther",
    },
    {
        "key": "ant_man_complete",
        "name": "Quantum Realm Explorer",
        "description": "Watch every project in the Ant-Man franchise.",
        "icon": "ant",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "ant-man",
    },
    {
        "key": "captain_america_complete",
        "name": "First Avenger Fan",
        "description": "Watch every project in the Captain America franchise.",
        "icon": "shield",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "captain-america",
    },
    {
        "key": "watch_30",
        "name": "In Deep Now",
        "description": "Watch 30 Marvel projects.",
        "icon": "clapper",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 30,
    },
    {
        "key": "deadpool_complete",
        "name": "Merc with a Mouth",
        "description": "Watch every project in the Deadpool franchise.",
        "icon": "chimichanga",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "fox-deadpool",
    },
    {
        "key": "punisher_complete",
        "name": "One Man War",
        "description": "Watch every project in the Punisher franchise.",
        "icon": "skull",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "punisher-franchise",
    },
    {
        "key": "morbius_complete",
        "name": "Living Vampire",
        "description": "Watch every project in the Morbius franchise.",
        "icon": "bat",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "morbius",
    },
    {
        "key": "daredevil_complete",
        "name": "The Man Without Fear",
        "description": "Watch every project in the Daredevil franchise.",
        "icon": "scales",
        "tier": AchievementTier.SILVER,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "daredevil-franchise",
    },
    # --- Gold (10) -------------------------------------------------------------
    {
        "key": "watch_35",
        "name": "More Than a Fan",
        "description": "Watch 35 Marvel projects.",
        "icon": "flame",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 35,
    },
    {
        "key": "watch_50",
        "name": "Halfway to Endgame",
        "description": "Watch 50 Marvel projects.",
        "icon": "flame",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 50,
    },
    {
        "key": "rewatch_20",
        "name": "Rewatch Regular",
        "description": "Log 20 rewatches across your library.",
        "icon": "couch",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.REWATCH_COUNT,
        "criteria_value": 20,
    },
    {
        "key": "rewatch_35",
        "name": "On Repeat",
        "description": "Log 35 rewatches across your library.",
        "icon": "replay",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.REWATCH_COUNT,
        "criteria_value": 35,
    },
    {
        "key": "rate_25",
        "name": "Critic's Corner",
        "description": "Rate 25 different projects.",
        "icon": "star-half",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 25,
    },
    {
        "key": "rate_35",
        "name": "Well-Reviewed",
        "description": "Rate 35 different projects.",
        "icon": "clipboard",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 35,
    },
    {
        "key": "thor_complete",
        "name": "Worthy",
        "description": "Watch every project in the Thor franchise.",
        "icon": "hammer",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "thor",
    },
    {
        "key": "guardians_complete",
        "name": "Awesome Mix Completionist",
        "description": "Watch every project in the Guardians of the Galaxy franchise.",
        "icon": "rocket",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "guardians-of-the-galaxy",
    },
    {
        "key": "spiderman_complete",
        "name": "Friendly Neighborhood Completionist",
        "description": "Watch every project in the (MCU) Spider-Man franchise.",
        "icon": "web",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "mcu-spider-man",
    },
    {
        "key": "marvel_tv_classic_complete",
        "name": "Saturday Morning Marvel",
        "description": "Watch every project in Marvel Television (Pre-MCU).",
        "icon": "cassette",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.UNIVERSE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "marvel-television-classic",
    },
    {
        "key": "rate_45",
        "name": "Thorough Reviewer",
        "description": "Rate 45 different projects.",
        "icon": "clipboard",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 45,
    },
    {
        "key": "fantastic_four_legacy_complete",
        "name": "First Family",
        "description": "Watch every project in the Fantastic Four (Legacy) franchise.",
        "icon": "four",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "fantastic-four-legacy",
    },
    {
        "key": "hulk_complete",
        "name": "Puny God",
        "description": "Watch every project in the Hulk franchise.",
        "icon": "smash",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "hulk",
    },
    {
        "key": "lego_universe_complete",
        "name": "Brick by Brick",
        "description": "Watch every project in the Marvel Lego Universe franchise.",
        "icon": "brick",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "marvel-lego-universe",
    },
    {
        "key": "xmen_original_complete",
        "name": "Original Mutant",
        "description": "Watch every project in the X-Men franchise.",
        "icon": "dna",
        "tier": AchievementTier.GOLD,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "fox-x-men",
    },
    # --- Platinum (10) ---------------------------------------------------------
    {
        "key": "watch_75",
        "name": "Serious Business",
        "description": "Watch 75 Marvel projects.",
        "icon": "star",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 75,
    },
    {
        "key": "watch_100",
        "name": "True Believer",
        "description": "Watch 100 Marvel projects.",
        "icon": "star",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 100,
    },
    {
        "key": "rewatch_50",
        "name": "Comfort Viewing",
        "description": "Log 50 rewatches across your library.",
        "icon": "couch",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.REWATCH_COUNT,
        "criteria_value": 50,
    },
    {
        "key": "rewatch_75",
        "name": "Rewatch Habit",
        "description": "Log 75 rewatches across your library.",
        "icon": "refresh",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.REWATCH_COUNT,
        "criteria_value": 75,
    },
    {
        "key": "rate_50",
        "name": "Seasoned Critic",
        "description": "Rate 50 different projects.",
        "icon": "clipboard",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 50,
    },
    {
        "key": "rate_65",
        "name": "Extensive Archive",
        "description": "Rate 65 different projects.",
        "icon": "archive",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 65,
    },
    {
        "key": "avengers_complete",
        "name": "Assemble Completionist",
        "description": "Watch every project in the Avengers franchise.",
        "icon": "shield",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "avengers",
    },
    {
        "key": "marvel_tv_abc_netflix_complete",
        "name": "Hell's Kitchen Completionist",
        "description": "Watch every project in Marvel Television (ABC/Netflix).",
        "icon": "mask",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.UNIVERSE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "marvel-television-abc-netflix",
    },
    {
        "key": "disney_plus_complete",
        "name": "Streaming Completionist",
        "description": "Watch every project in the Disney+ Series franchise.",
        "icon": "stream",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "mcu-disney-plus-series",
    },
    {
        "key": "rate_75",
        "name": "Prolific Reviewer",
        "description": "Rate 75 different projects.",
        "icon": "notepad",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 75,
    },
    {
        "key": "watch_90",
        "name": "Almost Everything",
        "description": "Watch 90 Marvel projects.",
        "icon": "flame",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 90,
    },
    {
        "key": "post_dofp_complete",
        "name": "Reset Timeline",
        "description": "Watch every project in the Post-Days of Future Past Timeline franchise.",
        "icon": "hourglass",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "post-dofp-timeline",
    },
    {
        "key": "independent_xmen_complete",
        "name": "Going Solo",
        "description": "Watch every project in the Independent X-Men Canon franchise.",
        "icon": "clapper",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "independent-x-men-canon",
    },
    {
        "key": "spiderverse_animated_complete",
        "name": "Anyone Can Wear the Mask",
        "description": "Watch every project in the SpiderVerse Animated franchise.",
        "icon": "spider",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.FRANCHISE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "spiderverse-animated",
    },
    {
        "key": "earth_616_complete",
        "name": "Comics Canon",
        "description": "Watch every project in the Marvel Comics Universe (Earth-616).",
        "icon": "comic",
        "tier": AchievementTier.PLATINUM,
        "criteria_type": AchievementCriteriaType.UNIVERSE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "marvel-comics-universe-earth-616",
    },
    # --- Diamond (10) ----------------------------------------------------------
    {
        "key": "watch_120",
        "name": "Nearly There",
        "description": "Watch 120 Marvel projects.",
        "icon": "flame",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 120,
    },
    {
        "key": "watch_135",
        "name": "Completionist in Training",
        "description": "Watch 135 Marvel projects.",
        "icon": "star",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 135,
    },
    {
        "key": "watch_145",
        "name": "Nothing Left Unwatched",
        "description": "Watch 145 Marvel projects.",
        "icon": "globe",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 145,
    },
    {
        "key": "rewatch_100",
        "name": "Rewatch Royalty",
        "description": "Log 100 rewatches across your library.",
        "icon": "crown",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.REWATCH_COUNT,
        "criteria_value": 100,
    },
    {
        "key": "rewatch_150",
        "name": "Rewatch Obsession",
        "description": "Log 150 rewatches across your library.",
        "icon": "couch",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.REWATCH_COUNT,
        "criteria_value": 150,
    },
    {
        "key": "rewatch_200",
        "name": "Infinite Loop",
        "description": "Log 200 rewatches across your library.",
        "icon": "refresh",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.REWATCH_COUNT,
        "criteria_value": 200,
    },
    {
        "key": "rate_100",
        "name": "The Critic's Archive",
        "description": "Rate 100 different projects.",
        "icon": "archive",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 100,
    },
    {
        "key": "rate_125",
        "name": "Definitive Opinions",
        "description": "Rate 125 different projects.",
        "icon": "clipboard",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 125,
    },
    {
        "key": "rate_140",
        "name": "Rated Everything",
        "description": "Rate 140 different projects.",
        "icon": "notepad",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 140,
    },
    {
        "key": "mcu_complete",
        "name": "Universe Unlocked",
        "description": "Watch every project in the Marvel Cinematic Universe.",
        "icon": "globe",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.UNIVERSE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "mcu",
    },
    {
        "key": "watch_175",
        "name": "Encyclopedic Knowledge",
        "description": "Watch 175 Marvel projects.",
        "icon": "star",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.WATCH_COUNT,
        "criteria_value": 175,
    },
    {
        "key": "rate_160",
        "name": "Every Opinion Counts",
        "description": "Rate 160 different projects.",
        "icon": "archive",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.RATING_COUNT,
        "criteria_value": 160,
    },
    {
        "key": "spiderverse_universe_complete",
        "name": "Multiversal Menace",
        "description": "Watch every project in the SpiderVerse (Multiverse Canon).",
        "icon": "multiverse",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.UNIVERSE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "sony-spider-man-universe",
    },
    {
        "key": "marvel_multiverse_complete",
        "name": "Legacy Canon",
        "description": "Watch every project in the Marvel Multiverse (Legacy/Parallel Canon).",
        "icon": "portal",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.UNIVERSE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "marvel-multiverse-legacy",
    },
    {
        "key": "fox_xmen_universe_complete",
        "name": "School for Gifted Youngsters",
        "description": "Watch every project in the X-Men Universe (Fox).",
        "icon": "dna",
        "tier": AchievementTier.DIAMOND,
        "criteria_type": AchievementCriteriaType.UNIVERSE_COMPLETE,
        "criteria_value": 1,
        "criteria_reference": "fox-x-men-universe",
    },
    # --- Marvelous (1) -----------------------------------------------------------
    {
        "key": "marvelous_complete",
        "name": "Marvelous",
        "description": "Unlock every other achievement.",
        "icon": "gauntlet",
        "tier": AchievementTier.MARVELOUS,
        "criteria_type": AchievementCriteriaType.ALL_ACHIEVEMENTS_COMPLETE,
        "criteria_value": 1,
    },
    # --- Hidden (10) -- see services/achievement_service.py's
    # _HIDDEN_ACHIEVEMENT_CHECKS for what actually unlocks each of these.
    # Deliberately vague/absent descriptions in some cases so nothing
    # here spoils its own solution -- the whole point of a hidden
    # achievement is that you find out how you got it *after*.
    {
        "key": "hidden_perfect_order",
        "name": "Perfect Order",
        "description": "Watch every Phase One film for the first time in the exact order they were originally released.",
        "icon": "hourglass",
        "tier": AchievementTier.VIBRANIUM,
        "criteria_type": AchievementCriteriaType.HIDDEN_SPECIAL,
        "criteria_value": 1,
        "is_hidden": True,
    },
    {
        "key": "hidden_deja_vu",
        "name": "Déjà Vu",
        "description": "Rewatch the same project 10 or more times.",
        "icon": "refresh",
        "tier": AchievementTier.VIBRANIUM,
        "criteria_type": AchievementCriteriaType.HIDDEN_SPECIAL,
        "criteria_value": 1,
        "is_hidden": True,
    },
    {
        "key": "hidden_right_on_time",
        "name": "Right on Time",
        "description": "Watch something on the exact anniversary of its original release date.",
        "icon": "star",
        "tier": AchievementTier.VIBRANIUM,
        "criteria_type": AchievementCriteriaType.HIDDEN_SPECIAL,
        "criteria_value": 1,
        "is_hidden": True,
    },
    {
        "key": "hidden_triple_feature",
        "name": "Triple Feature",
        "description": "Watch 3 different projects in a single day.",
        "icon": "popcorn",
        "tier": AchievementTier.VIBRANIUM,
        "criteria_type": AchievementCriteriaType.HIDDEN_SPECIAL,
        "criteria_value": 1,
        "is_hidden": True,
    },
    {
        "key": "hidden_quiet_completionist",
        "name": "Quiet Completionist",
        "description": "Watch 50 or more projects without ever leaving a single rating.",
        "icon": "mask",
        "tier": AchievementTier.VIBRANIUM,
        "criteria_type": AchievementCriteriaType.HIDDEN_SPECIAL,
        "criteria_value": 1,
        "is_hidden": True,
    },
    {
        "key": "hidden_social_circle",
        "name": "Social Circle",
        "description": "Log \"watched with\" someone on 10 or more separate watches.",
        "icon": "couch",
        "tier": AchievementTier.VIBRANIUM,
        "criteria_type": AchievementCriteriaType.HIDDEN_SPECIAL,
        "criteria_value": 1,
        "is_hidden": True,
    },
    {
        "key": "hidden_marathon_runner",
        "name": "Marathon Runner",
        "description": "Watch every project in a 4+ project franchise, all within the same 7-day span.",
        "icon": "blitz",
        "tier": AchievementTier.VIBRANIUM,
        "criteria_type": AchievementCriteriaType.HIDDEN_SPECIAL,
        "criteria_value": 1,
        "is_hidden": True,
    },
    {
        "key": "hidden_answer_to_everything",
        "name": "The Answer to Everything",
        "description": "Build a Collection containing exactly 42 projects.",
        "icon": "clipboard",
        "tier": AchievementTier.VIBRANIUM,
        "criteria_type": AchievementCriteriaType.HIDDEN_SPECIAL,
        "criteria_value": 1,
        "is_hidden": True,
    },
    {
        "key": "hidden_renaissance_fan",
        "name": "Renaissance Fan",
        "description": "Watch at least one project from every universe in your library.",
        "icon": "globe",
        "tier": AchievementTier.VIBRANIUM,
        "criteria_type": AchievementCriteriaType.HIDDEN_SPECIAL,
        "criteria_value": 1,
        "is_hidden": True,
    },
    {
        "key": "hidden_full_circle",
        "name": "Full Circle",
        "description": "Watch both the oldest and the newest release in your entire library.",
        "icon": "portal",
        "tier": AchievementTier.VIBRANIUM,
        "criteria_type": AchievementCriteriaType.HIDDEN_SPECIAL,
        "criteria_value": 1,
        "is_hidden": True,
    },
]



def seed_universes(session: Session) -> dict[str, Universe]:
    existing = {u.slug: u for u in session.scalars(select(Universe)).all()}
    for payload in UNIVERSES:
        if payload["slug"] in existing:
            continue
        universe = Universe(**payload)
        session.add(universe)
        existing[universe.slug] = universe
    session.flush()
    return existing


def seed_franchises(session: Session, universes: dict[str, Universe]) -> None:
    existing_slugs = {f.slug for f in session.scalars(select(Franchise)).all()}
    for payload in FRANCHISES:
        if payload["slug"] in existing_slugs:
            continue
        universe = universes.get(payload["universe"])
        if universe is None:
            logger.warning("Skipping franchise %s: unknown universe %s", payload["slug"], payload["universe"])
            continue
        session.add(Franchise(universe_id=universe.id, name=payload["name"], slug=payload["slug"]))
    session.flush()


def seed_genres(session: Session) -> None:
    existing = {g.name for g in session.scalars(select(Genre)).all()}
    for name in GENRES:
        if name in existing:
            continue
        slug = name.lower().replace(" ", "-")
        session.add(Genre(name=name, slug=slug))
    session.flush()


def seed_achievements(session: Session) -> None:
    existing_keys = {a.key for a in session.scalars(select(Achievement)).all()}
    for payload in ACHIEVEMENTS:
        if payload["key"] in existing_keys:
            continue
        achievement = Achievement(**payload)
        session.add(achievement)
        session.flush()
        session.add(UserAchievement(achievement_id=achievement.id))
    session.flush()


def seed_all(session: Session) -> None:
    """Idempotently populate canonical reference data on a fresh database.
    Safe to call on every startup: existing rows are left untouched."""
    universes = seed_universes(session)
    seed_franchises(session, universes)
    seed_genres(session)
    seed_achievements(session)
    logger.info("Reference data seed check complete")
