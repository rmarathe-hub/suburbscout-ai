"""Phase 1.6 — Template-driven eval prompt generation from town pools."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable

from app.ranking import load_suburbs

CATEGORY_LABELS: dict[str, str] = {
    "lookup": "A. Lookup / single-town facts",
    "membership": "B. Membership / scope / aliases",
    "typo": "C. Typos / fuzzy town names",
    "compare": "D. Natural comparison questions",
    "budget": "E. Budget / affordability constraints",
    "commute": "F. Commute / distance constraints",
    "coastal": "G. Coastal / region filters",
    "semantic": "H. Semantic / vibe prompts",
    "inverted": "I. Inverted / tradeoff-heavy prompts",
}

INTENT_BY_CATEGORY: dict[str, str] = {
    "lookup": "lookup_single_town",
    "membership": "dataset_membership",
    "typo": "lookup_single_town",  # default; per-template override
    "compare": "compare_towns",
    "budget": "recommend_structured",
    "commute": "recommend_structured",
    "coastal": "recommend_structured",
    "semantic": "recommend_semantic",
    "inverted": "recommend_structured",
}

TOWN_TYPO_VARIANTS: dict[str, list[str]] = {
    "Shrewsbury": ["Shrewsbry", "Shrewsbery"],
    "Worcester": ["Worecester", "Worchester"],
    "Burlington": ["Burlignton", "Burlingtonn"],
    "Framingham": ["Framinghan", "Framinghm"],
    "Lexington": ["Lexinton", "Lexingtn"],
    "Marlborough": ["Marlborugh", "Marlboro"],
    "Manchester-by-the-Sea": ["Manchestr-by-the-Sea", "Manchester by the Sea"],
    "Swampscott": ["Swampscotte", "Swampscot"],
    "Wellesley": ["Wellesely", "Wellseley"],
    "Brookline": ["Brokkline", "Brooklin"],
    "Chelsea": ["Chelsa", "Chelseaa"],
    "Somerville": ["Somervile", "Somervill"],
    "Westford": ["Westfird", "Westfordd"],
    "Needham": ["Needam", "Needhamm"],
    "North Reading": ["North Readin", "North Reding"],
    "Natick": ["Natik", "Nattick"],
    "Acton": ["Actton", "Actn"],
    "Concord": ["Conccord", "Concrd"],
}

OUT_OF_SCOPE_TOWNS: tuple[str, ...] = (
    "Providence",
    "Nashua",
    "Springfield",
    "Amherst",
    "Brooklyn",
)

COMPARE_PAIRS: tuple[tuple[str, str], ...] = (
    ("Acton", "Concord"),
    ("Lynn", "Revere"),
    ("Westford", "Sharon"),
    ("Burlington", "Waltham"),
    ("Quincy", "Milton"),
    ("Newton", "Needham"),
    ("Rockport", "Gloucester"),
    ("Salem", "Beverly"),
    ("Framingham", "Natick"),
    ("Lexington", "Winchester"),
    ("Needham", "Dedham"),
    ("North Reading", "Reading"),
    ("Cambridge", "Somerville"),
    ("Brookline", "Newton"),
    ("Hingham", "Cohasset"),
)

LOOKUP_TEMPLATES: tuple[str, ...] = (
    "What does your suburb file say about {town}?",
    "Give me the data card for {town}.",
    "What are {town}'s commute and school numbers?",
    "Does {town} sit on the expensive side?",
    "Check {town}'s record for missing values.",
    "What are {town}'s main suburb stats?",
    "Is {town} flagged as high-crime or low-crime?",
    "What housing price do you have saved for {town}?",
    "Does {town} have a complete row?",
    "How far is {town} from the Boston destination point?",
    "Is {town}'s school data present?",
    "What crime/safety information do you have for {town}?",
    "Summarize the {town} entry.",
    "What commute time is listed for {town}?",
    "Show {town}'s housing, school, and safety info.",
    "Is {town} a partial-data town?",
    "What school number is listed for {town}?",
    "Does {town} have the coastal marker?",
    "What is {town}'s listed median price?",
    "Is {town} classified as not coastal?",
    "Pull up everything you know about {town}.",
    "What does the dataset report for {town}?",
    "Show me the stored profile for {town}.",
    "Does {town} look risky in your data?",
    "Is {town} tagged as coastal?",
    "What price do you have for {town}?",
    "What safety rating does {town} have?",
    "Pull facts for {town}.",
    "Open {town}'s suburb entry.",
    "What numbers do you have saved for {town}?",
    "Does {town} have a recorded school metric?",
    "Is {town} classified as complete data?",
    "Look up {town}.",
    "Based on your records, is {town} near the coast?",
    "Give me {town}'s safety and commute snapshot.",
    "What is {town}'s home value stored as?",
    "Does {town} have incomplete information?",
    "How long would a drive from {town} to Boston take?",
    "What county and region is {town} in?",
    "Is {town} marked full-data or partial-data?",
    "Tell me whether {town} has complete housing data.",
    "What do you know about {town}?",
    "Does {town} have good schools according to your data?",
    "Is {town} expensive in your dataset?",
    "What fields are unavailable for {town}?",
    "How many miles is {town} from Boston?",
    "How close is {town} to Boston?",
    "What is the school rating for {town}?",
    "Does {town} count as inland?",
    "Give me a full town summary for {town}.",
    "What is {town}'s drive time to Boston?",
    "Is {town} pricey in your data?",
    "What are the strongest and weakest stats for {town}?",
    "Does {town} have a stored home price?",
    "What commute data do you have for {town}?",
    "Is {town} labeled waterfront?",
    "What basic stats do you have for {town}?",
    "Does {town} have school and safety info saved?",
    "What is missing from {town}'s data profile?",
    "Is {town} actually coastal in your tags?",
    "Give me {town}'s price snapshot.",
    "What does your data say about {town}?",
    "Does {town} have a high or low crime score?",
    "Is {town} a coast town?",
    "Summarize {town} using your stored profile.",
    "What is {town}'s school percentile?",
    "Does {town} have complete housing data?",
    "Tell me about {town}'s affordability in your records.",
)

MEMBERSHIP_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("If I type {alias}, will the app understand it?", "dataset_membership"),
    ("Is {town} recognized by the system?", "dataset_membership"),
    ("Does {town} exist in your dataset?", "dataset_membership"),
    ("Are there records for {town}?", "dataset_membership"),
    ("Did {town} make the town list?", "dataset_membership"),
    ("Is {town} included?", "dataset_membership"),
    ("Are recommendations available for {town}?", "dataset_membership"),
    ("Can {town} be ranked by this tool?", "dataset_membership"),
    ("Is {town} loaded into the 200-town dataset?", "dataset_membership"),
    ("Is {town} searchable?", "dataset_membership"),
    ("Is {town} queryable in this app?", "dataset_membership"),
    ("Is {town} usable in this app?", "dataset_membership"),
    ("Is {town} available for recommendations?", "dataset_membership"),
    ("Can your system handle {town}?", "dataset_membership"),
    ("Is {town} in your database?", "dataset_membership"),
    ("Is {town} in scope?", "dataset_membership"),
    ("Is {town} covered by your suburb scope?", "dataset_membership"),
    ("Would {town} resolve to a valid result?", "dataset_membership"),
    ("Is {town} one of the towns you loaded?", "dataset_membership"),
    ("Can {town} be queried directly?", "dataset_membership"),
    ("Is {town} normalized to a canonical spelling?", "dataset_membership"),
    ("Would {town} be accepted as an alternate spelling?", "dataset_membership"),
    ("Is {town} part of the curated list?", "dataset_membership"),
    ("Do you keep {town} in the loaded towns?", "dataset_membership"),
    ("Is {town} actually loaded?", "dataset_membership"),
    ("Are {town} results available?", "dataset_membership"),
    ("Can {town} be used in recommendations?", "dataset_membership"),
    ("Did {town} make it into the loaded 200 towns?", "dataset_membership"),
    ("Do you store {town} under that exact name?", "dataset_membership"),
    ("Is {town} in the 200-town scope?", "dataset_membership"),
    ("Is {town} rankable here?", "dataset_membership"),
    ("Can the app answer questions about {town}?", "dataset_membership"),
    ("Is {town} treated as in the dataset?", "dataset_membership"),
    ("Is {town} mapped to a known town?", "dataset_membership"),
    ("Will {town} work as a search term?", "dataset_membership"),
    ("Does the system translate {alias} to {town}?", "dataset_membership"),
    ("Is {alias} the same as {town} in your data?", "dataset_membership"),
    ("Does the app know {alias} means {town}?", "dataset_membership"),
    ("Is {alias} a valid alias?", "dataset_membership"),
    ("Can I use {alias} as a town name?", "dataset_membership"),
    ("Would {town} be rejected if misspelled?", "dataset_membership"),
    ("Is {town} inside the project's town universe?", "dataset_membership"),
    ("Do you support recommendations for {town}?", "dataset_membership"),
    ("Is {town} part of your suburb scope?", "dataset_membership"),
    ("Would Providence be outside the supported geography?", "refuse_out_of_scope"),
    ("Is Nashua rejected because it is not Massachusetts?", "refuse_out_of_scope"),
    ("Do you exclude Springfield from this suburb project?", "refuse_out_of_scope"),
    ("Would Amherst be unavailable here?", "refuse_out_of_scope"),
    ("Are Cape communities part of your supported towns?", "refuse_out_of_scope"),
    ("Does this cover anything outside MA?", "refuse_out_of_scope"),
    ("Would {town} be outside your coverage?", "refuse_out_of_scope"),
    ("Is {town} excluded from the Boston-area list?", "refuse_out_of_scope"),
    ("How do you handle a place absent from the dataset?", "refuse_out_of_scope"),
    ("Is {town} outside the boston commuter scope?", "refuse_out_of_scope"),
    ("Can you search for {town}?", "dataset_membership"),
    ("Do you recognize {alias}?", "dataset_membership"),
    ("Is {town} in the dataset?", "dataset_membership"),
    ("Is {town} one of the 200 towns?", "dataset_membership"),
    ("Is {town} a town you track?", "dataset_membership"),
    ("Does your dataset include {town}?", "dataset_membership"),
    ("Is {town} loaded and usable?", "dataset_membership"),
    ("Are lookups possible for {town}?", "dataset_membership"),
)

TYPO_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("Search for {typo}.", "lookup_single_town"),
    ("What is {typo}'s commute?", "lookup_single_town"),
    ("Show {typo}'s home price.", "lookup_single_town"),
    ("Is {typo} coastal?", "lookup_single_town"),
    ("Pull up {typo}.", "lookup_single_town"),
    ("Does {typo} have strong schools?", "lookup_single_town"),
    ("Is {typo} loaded?", "dataset_membership"),
    ("Can you recognize {typo}?", "dataset_membership"),
    ("Is {typo} supported?", "dataset_membership"),
    ("Compare {typo} and {town2}.", "compare_towns"),
    ("{typo} and {town2}: compare price.", "compare_towns"),
    ("{typo} versus {town2} for safety.", "compare_towns"),
    ("What does your data say about {typo}?", "lookup_single_town"),
    ("Look up {typo}.", "lookup_single_town"),
    ("Is {typo} in your dataset?", "dataset_membership"),
    ("Would {typo} resolve correctly?", "dataset_membership"),
    ("Give me {typo}'s safety rating.", "lookup_single_town"),
    ("How far is {typo} from Boston?", "lookup_single_town"),
    ("Does {typo} look expensive?", "lookup_single_town"),
    ("Summarize {typo}.", "lookup_single_town"),
)

COMPARE_TEMPLATES: tuple[str, ...] = (
    "{a} compared to {b} — which has lower crime?",
    "{a} or {b}: where is safety worse?",
    "For a family with kids, {a} or {b}?",
    "Is {a} safer or less safe than {b}?",
    "{a} and {b} — which has the lower home price?",
    "Which town is more expensive: {a} or {b}?",
    "{a} compared with {b}: which is farther?",
    "Compare {a} and {b} on commute.",
    "{a} vs {b} for schools.",
    "Between {a} and {b}, which is cheaper?",
    "Which has better safety, {a} or {b}?",
    "{a} or {b} for affordability?",
    "Compare crime in {a} and {b}.",
    "Which is closer to Boston, {a} or {b}?",
    "{a} versus {b} — price and commute?",
    "For safety, {a} or {b}?",
    "Which town has lower crime: {a} or {b}?",
    "Compare {a} with {b} on housing price.",
    "{a} and {b}: which is more affordable?",
    "Which is safer for families, {a} or {b}?",
    "Compare {a} to {b} on school quality.",
    "{a} or {b} — better commute?",
    "Which has stronger schools, {a} or {b}?",
    "Between {a} and {b}, which is safer?",
    "Compare home prices: {a} vs {b}.",
    "{a} and {b} — which is farther from Boston?",
    "Which town is pricier, {a} or {b}?",
    "For a shorter commute, {a} or {b}?",
    "Compare {a} and {b} overall.",
    "{a} vs {b} on safety and price.",
    "Which is better value, {a} or {b}?",
    "Compare {a} and {b} for a young family.",
    "{a} or {b} for low crime?",
    "Which has the better school score, {a} or {b}?",
    "Compare {a} with {b} on affordability.",
    "{a} and {b} — safety comparison.",
    "Which town costs less, {a} or {b}?",
    "Compare commute times for {a} and {b}.",
    "{a} versus {b}: which is closer in?",
    "For schools and safety, {a} or {b}?",
    "Which is more coastal-feeling, {a} or {b}?",
    "Compare {a} and {b} on crime rates.",
    "{a} or {b} — which has lower price?",
    "Which town would you pick for safety: {a} or {b}?",
    "Compare {a} to {b} for families.",
    "{a} and {b}: price comparison.",
    "Which is less expensive, {a} or {b}?",
    "Compare {a} and {b} on drive time to Boston.",
    "{a} vs {b} — schools and commute.",
    "Which has worse crime, {a} or {b}?",
    "Between {a} and {b}, which is more affordable?",
    "Compare {a} and {b} for commute and price.",
    "{a} or {b} for a family commute?",
    "Which town is safer overall, {a} or {b}?",
    "Compare {a} with {b} on all main stats.",
    "{a} and {b} — which is better for kids?",
    "Which has a shorter drive to Boston, {a} or {b}?",
    "Compare {a} and {b} on safety score.",
    "{a} versus {b} for home price.",
    "Which town has better schools, {a} or {b}?",
    "Compare {a} and {b} side by side.",
    "{a} or {b}: affordability and safety?",
    "Which is the cheaper option, {a} or {b}?",
    "Compare {a} to {b} on crime and price.",
)

BUDGET_TEMPLATES: tuple[str, ...] = (
    "Show me towns under ${budget}k.",
    "What can I get with a ${budget}k budget?",
    "Find affordable towns below ${budget}k.",
    "I have a ${budget}k budget — what towns fit?",
    "Towns under ${budget},000 please.",
    "Recommend places under ${budget}k.",
    "My max is ${budget}k for a home.",
    "What towns are under ${budget}k?",
    "Give me options below ${budget}k.",
    "Working with ${budget}k — show towns.",
    "Budget ${budget}k, what is realistic?",
    "Under ${budget}k only.",
    "Don't show me anything over ${budget}k.",
    "Affordable towns under ${budget}k near Boston.",
    "What can I realistically get under ${budget}k?",
    "I can only spend ${budget}k.",
    "Show cheaper towns under ${budget}k.",
    "Find towns below ${budget}k with good schools.",
    "Under ${budget}k with a reasonable commute.",
    "Towns under ${budget}k in Middlesex County.",
    "What fits a ${budget}k cap?",
    "Max budget ${budget}k — recommend towns.",
    "Leave out towns above ${budget}k.",
    "Show me ${budget}k-and-under options.",
    "I need towns under ${budget}k.",
    "What towns match a ${budget}k budget?",
    "Recommend under ${budget}k with safety in mind.",
    "Below ${budget}k, family-friendly towns.",
    "Under ${budget}k on the North Shore.",
    "Affordable under ${budget}k with a short commute.",
    "Towns under ${budget}k, coastal if possible.",
    "What can I get if my max is ${budget}k?",
    "Show practical options under ${budget}k.",
    "Budget is ${budget}k — rank towns.",
    "Under ${budget}k, prioritize affordability.",
    "Find towns under ${budget}k in Essex County.",
    "Recommend towns below ${budget}000.",
    "I have ${budget}k — show best value towns.",
    "Under ${budget}k, ignore luxury towns.",
    "What towns are realistically under ${budget}k?",
    "Show lower-cost towns under ${budget}k.",
    "My budget is ${budget}k max.",
    "Towns under ${budget}k with decent schools.",
    "Under ${budget}k, South Shore options.",
    "Affordable towns capped at ${budget}k.",
    "Recommend under ${budget}k near Boston.",
    "Only show towns under ${budget}k.",
    "What fits under a ${budget}k limit?",
    "Under ${budget}k with low crime if possible.",
    "Show towns below ${budget}k in Norfolk County.",
    "Budget ${budget}k — what are my options?",
    "Find me towns under ${budget}k.",
    "Under ${budget}k, prioritize price.",
    "Recommend affordable towns under ${budget}k.",
    "Towns under ${budget}k with a commute under 45 minutes.",
    "What towns under ${budget}k are family-friendly?",
    "Show me under ${budget}k on the South Shore.",
    "Under ${budget}k, coastal towns only.",
    "I want towns under ${budget}k.",
    "Best value towns under ${budget}k.",
    "Under ${budget}k — show me options.",
    "What can I buy under ${budget}k in this dataset?",
    "Towns under ${budget}k, not too far from Boston.",
    "Recommend towns below ${budget}k with safety.",
    "Under ${budget}k, show affordable suburbs.",
    "My budget is only ${budget}k.",
    "Find towns under ${budget}k with good commute.",
)

COMMUTE_TEMPLATES: tuple[str, ...] = (
    "Show towns within {max} minutes of Boston.",
    "Towns under {max} minutes commute to Boston.",
    "Find places within {max} minutes of Boston.",
    "Commute capped at {max} minutes.",
    "I need a {max}-minute commute or less.",
    "Towns inside a {max}-minute Boston commute.",
    "No more than {max} minutes from Boston.",
    "Short commute — under {max} minutes.",
    "Show me towns within {max} mins of Boston.",
    "Max {max} minute commute to Boston.",
    "Towns between {min} and {max} minutes from Boston.",
    "Commute band {min} to {max} minutes.",
    "I want at least {min} minutes away from Boston.",
    "Towns {min} minutes or more from Boston.",
    "Long commute is fine — {min}+ minutes.",
    "Skip the close-in towns, show {min}+ minute commutes.",
    "Farther than {min} minutes from Boston.",
    "Give me towns beyond {min} minutes.",
    "I prefer being farther out — {min}+ minutes.",
    "Commute is not the priority — show affordable towns.",
    "Trade commute time for lower price.",
    "I can sacrifice commute for affordability.",
    "Affordability first, commute can be longer.",
    "Show towns with a long commute but lower price.",
    "Commute can be bad if the price is right.",
    "I do not mind a long drive to Boston.",
    "Prioritize cheap towns even with longer commutes.",
    "Fast commute matters more than schools.",
    "Both short commute and low cost under {max} minutes.",
    "Low price and quick commute under {max} minutes.",
    "Towns within {max} minutes with good safety.",
    "Under {max} minutes and affordable.",
    "Show coastal towns within {max} minutes.",
    "North Shore towns under {max} minutes.",
    "Which towns are within {max} minutes of Boston?",
    "Find towns with drive time under {max} minutes.",
    "Commute should be under {max} minutes.",
    "I need towns closer than {max} minutes.",
    "Show options within {max} minutes of South Station.",
    "Towns not too far — max {max} minutes.",
    "Half an hour or less to Boston.",
    "45+ minutes from Boston is okay.",
    "Show towns beyond 45 minutes.",
    "Commute between {min} and {max} minutes from Boston.",
    "I prefer a {min}-to-{max} minute commute window.",
    "Towns with {min} to {max} minute drives to Boston.",
    "Closer is better — under {max} minutes.",
    "Far-out towns with {min}+ minute commutes.",
    "Accept a longer commute for cheaper housing.",
    "Commute sacrifice is fine for affordability.",
    "Show practical towns with commute under {max} minutes.",
    "Drive time under {max} minutes to Boston.",
    "Towns within {max} minutes, budget under 800k.",
    "Short Boston commute under {max} minutes.",
    "I want to be within {max} minutes of Boston.",
    "Find suburbs under {max} minutes away.",
    "Commute max {max} minutes, prioritize safety.",
    "Show me towns at least {min} minutes out.",
    "Farther/closer tradeoff — at least {min} minutes.",
    "Not too close — at least {min} minutes from Boston.",
    "Give me towns with {min}+ minute commutes.",
    "Long commute acceptable — show affordable options.",
    "Commute not priority — rank by price.",
    "I can tolerate a long commute.",
    "Show towns where commute is over {min} minutes.",
    "Beyond {min} minutes but still in the dataset.",
)

COASTAL_TEMPLATES: tuple[str, ...] = (
    "Show me coastal towns only.",
    "Recommend seaside towns near Boston.",
    "Coastal suburbs with good schools.",
    "Find oceanfront-feeling towns.",
    "Coastal towns under 900k.",
    "North Shore coastal towns.",
    "South Shore coastal options.",
    "Waterfront towns in the dataset.",
    "Coastal but not Cape Cod.",
    "Beach town vibes near Boston.",
    "Coastal towns with a short commute.",
    "Show coastal family-friendly towns.",
    "Coastal, affordable if possible.",
    "Ocean-adjacent towns only.",
    "Coastal towns within 40 minutes.",
    "Recommend coastal places with safety.",
    "Coastal towns under 750k.",
    "Find coastal towns in Essex County.",
    "Coastal options with decent schools.",
    "Show water-adjacent suburbs.",
    "Coastal towns, exclude inland.",
    "Seaside towns with low crime.",
    "Coastal towns for families.",
    "Recommend coastal towns near Boston.",
    "Coastal only — no inland towns.",
    "Show me towns on the water.",
    "Coastal suburbs with affordability.",
    "Find coastal towns under 850k.",
    "Coastal with a reasonable commute.",
    "Beach towns in the 200-town list.",
    "Coastal towns in Norfolk County.",
    "Show coastal safe-ish towns.",
    "Coastal towns, schools matter.",
    "Oceanfront towns under 1 million.",
    "Coastal towns with good commute.",
    "Recommend coastal North Shore towns.",
    "Coastal South Shore options.",
    "Coastal towns, prioritize safety.",
    "Show coastal affordable suburbs.",
    "Coastal towns with family appeal.",
    "Find coastal towns close to Boston.",
    "Coastal, not too expensive.",
    "Waterfront suburbs only.",
    "Coastal towns under 700k.",
    "Show coastal practical options.",
    "Coastal towns with short commute.",
    "Recommend seaside suburbs.",
    "Coastal filter — show towns.",
    "Coastal towns, budget under 800k.",
    "Show coastal towns in Middlesex.",
    "Coastal options with schools.",
    "Find coastal safe towns.",
    "Coastal suburbs under 950k.",
    "Coastal towns, commute under 50 min.",
    "Show coastal value towns.",
    "Coastal recommendations only.",
    "Beach-adjacent towns near Boston.",
    "Coastal towns, affordability first.",
    "Show coastal towns with data.",
    "Coastal region filter only.",
    "Recommend coastal commuter towns.",
    "Coastal towns, family-friendly.",
    "Show coastal options under 900k.",
    "Coastal towns with good safety.",
    "Find coastal affordable options.",
    "Coastal suburbs, exclude inland.",
    "Show coastal towns ranked.",
)

SEMANTIC_TEMPLATES: tuple[str, ...] = (
    "I want something like {town} but cheaper.",
    "Towns that feel like {town} without the price tag.",
    "Show suburbs with a {town}-like vibe.",
    "Something similar to {town} but more affordable.",
    "I like {town}'s feel — what else is similar?",
    "Town with {town} energy but lower cost.",
    "Feels somewhat like {town}, less expensive.",
    "Recommend towns similar to {town}.",
    "What feels like {town} but not as pricey?",
    "Suburbs with a similar style to {town}.",
    "I want a {town}-ish town cheaper.",
    "Town like {town} for families.",
    "Similar to {town} with good schools.",
    "Something like {town} on the North Shore.",
    "Vibe similar to {town}, affordable.",
    "Towns like {town} but safer.",
    "Feels like {town} with shorter commute.",
    "Recommend a {town}-style suburb.",
    "What towns feel like {town}?",
    "Similar vibe to {town}, lower price.",
    "I want {town}-like but not inland.",
    "Town energy like {town}, cheaper.",
    "Suburbs reminiscent of {town}.",
    "Something in the spirit of {town}.",
    "Like {town} but closer to Boston.",
    "Feels a bit like {town}, family-friendly.",
    "Recommend towns with {town}'s character.",
    "Similar to {town}, coastal if possible.",
    "I want that {town} suburban feel.",
    "Towns like {town} with good safety.",
    "What feels somewhat like {town}?",
    "Suburbs similar to {town} for kids.",
    "Like {town} but with better commute.",
    "Recommend {town}-like affordable towns.",
    "Something like {town}, not too expensive.",
    "Town vibe like {town}, lower cost.",
    "Feels like {town} without million-dollar prices.",
    "Similar town energy to {town}.",
    "I want a suburb like {town}.",
    "Towns with {town}-like appeal.",
    "Recommend places like {town} but cheaper.",
    "What suburbs feel like {town}?",
    "Similar to {town}, practical budget.",
    "Like {town}'s style, more affordable.",
    "Feels like {town} — show options.",
    "Town similar to {town} for families.",
    "Recommend {town}-like North Shore towns.",
    "Something like {town}, good schools.",
    "Vibe like {town}, not as pricey.",
    "Towns reminiscent of {town} but cheaper.",
    "I want {town}-like with safety.",
    "Similar feel to {town}, affordable.",
    "Recommend suburbs like {town}.",
    "What feels like {town} in your data?",
    "Town like {town}, lower home prices.",
    "Feels somewhat like {town} for commuting.",
    "Similar to {town}, coastal vibe.",
    "Like {town} but more family-friendly.",
    "Recommend towns in the style of {town}.",
    "Something {town}-like under 900k.",
    "Feels like {town}, shorter drive.",
    "Suburbs with {town}-like character.",
    "Similar to {town}, good for kids.",
    "I want that {town} neighborhood feel.",
    "Towns like {town}, practical options.",
    "Recommend a suburb similar to {town}.",
    "What feels like {town} but affordable?",
    "Like {town} energy, lower price point.",
    "Feels like {town} — coastal preferred.",
    "Similar town style to {town}.",
)

INVERTED_TEMPLATES: tuple[str, ...] = (
    "Show me the cheapest towns even if safety is bad.",
    "Rank low-cost towns by worst safety.",
    "Affordable towns with obvious red flags.",
    "I accept weaker safety for lower price.",
    "Prioritize cheap towns — safety not important.",
    "Show tradeoff-heavy affordable options.",
    "Rank towns by highest crime if price is low.",
    "Cheapest towns, even if schools are weak.",
    "Weaker schools are acceptable if affordable.",
    "Ignore school quality and focus on price.",
    "Lowest-priced towns, warn me about downsides.",
    "Show towns you would not normally rank at the top.",
    "Affordable upside even with bad safety.",
    "High-crime affordable towns only.",
    "Rank by affordability, accept high crime.",
    "I do not care about safety — show cheap towns.",
    "Bottom-priced towns in the dataset.",
    "Even if safety is bad, show affordable towns.",
    "Schools are not a strength — cheap towns please.",
    "Low-cost towns but warn about tradeoffs.",
    "Show practical imperfect towns.",
    "Affordability is good but safety is weak — show options.",
    "Rank towns with serious tradeoffs.",
    "Cheapest towns, commute can be long.",
    "Price and commute only — ignore schools and safety.",
    "Ignore schools and safety, rank by price.",
    "Show affordable towns with major downsides.",
    "Even if crime is high, prioritize affordability.",
    "Accept weaker schools for cheaper housing.",
    "Show not top-ranked but affordable towns.",
    "Rank low-cost options with bad safety scores.",
    "I want higher-crime cheaper towns.",
    "Affordable towns even if they have tradeoffs.",
    "Deprioritize safety, show cheap suburbs.",
    "Show towns where affordability beats safety.",
    "Cheapest options even with weak schools.",
    "Rank by price, safety can be poor.",
    "Low price options, okay with lower school scores.",
    "Do not factor schools — cheapest towns.",
    "Second-tier practical affordable towns.",
    "Show lower-cost towns with red flags.",
    "Affordable towns, safety is weak.",
    "Rank worst safety among cheap towns.",
    "Cheap and close is less important — show affordable.",
    "Even if schools are weak, show cheap towns.",
    "Tradeoff-heavy ranking by affordability.",
    "Show towns with affordability upside and bad safety.",
    "I accept serious tradeoffs for price.",
    "Rank affordable towns with high crime.",
    "Ignore safety, prioritize affordability.",
    "Show practical options with obvious downsides.",
    "Lowest cost towns, safety secondary.",
    "Affordable towns, do not filter by safety.",
    "Rank by affordability, accept tradeoffs.",
    "Cheapest towns even if commute is long.",
    "Commute can be bad — show affordable towns.",
    "Sacrifice safety for lower home prices.",
    "Show affordable towns with weak schools.",
    "Rank low-cost towns, safety not a filter.",
    "Affordable with bad safety — show me.",
    "Prioritize cheap towns with tradeoffs.",
    "Show towns where price beats safety.",
    "Even if they have tradeoffs, show affordable towns.",
    "Rank affordable towns by highest crime rate.",
    "Accept bad safety for affordability.",
    "Show imperfect but affordable suburbs.",
    "Cheapest towns, ignore safety ranking.",
    "Affordable towns with weak safety scores.",
    "Rank by price, accept weak schools.",
    "Show towns with affordability upside only.",
    "Low-cost ranking, safety deprioritized.",
    "Affordable red-flag towns please.",
    "Show tradeoff-heavy cheap options.",
)


@dataclass(frozen=True)
class EvalPrompt:
    category: str
    expected_intent: str
    prompt: str


def _town_pool(seed: int) -> list[str]:
    rng = random.Random(seed)
    names = [s["name"] for s in load_suburbs()]
    rng.shuffle(names)
    return names


def _alias_for(town: str) -> str:
    aliases = {
        "Marlborough": "Marlboro",
        "Foxborough": "Foxboro",
        "Northborough": "Northboro",
        "Westborough": "Westboro",
        "Manchester-by-the-Sea": "Manchester by the Sea",
    }
    return aliases.get(town, town.split()[0] if " " in town else town[: max(4, len(town) - 2)])


def _expand_lookup(towns: list[str], count: int, rng: random.Random) -> list[EvalPrompt]:
    combos = [(t, town) for t in LOOKUP_TEMPLATES for town in towns]
    rng.shuffle(combos)
    out: list[EvalPrompt] = []
    for template, town in combos[:count]:
        out.append(EvalPrompt("lookup", "lookup_single_town", template.format(town=town)))
    return out


def _expand_membership(towns: list[str], count: int, rng: random.Random) -> list[EvalPrompt]:
    combos: list[tuple[str, str, str]] = []
    for template, intent in MEMBERSHIP_TEMPLATES:
        if "{town}" in template or "{alias}" in template:
            for town in towns:
                alias = _alias_for(town)
                combos.append((template.format(town=town, alias=alias), intent, town))
        else:
            combos.append((template, intent, ""))
    rng.shuffle(combos)
    out: list[EvalPrompt] = []
    seen: set[str] = set()
    for prompt, intent, _ in combos:
        if prompt in seen:
            continue
        seen.add(prompt)
        out.append(EvalPrompt("membership", intent, prompt))
        if len(out) >= count:
            break
    return out


def _expand_typo(count: int, rng: random.Random) -> list[EvalPrompt]:
    combos: list[tuple[str, str]] = []
    for canonical, typos in TOWN_TYPO_VARIANTS.items():
        for typo in typos:
            town2 = rng.choice([t for t, _ in COMPARE_PAIRS if t != canonical][:5] or ["Natick"])
            for template, intent in TYPO_TEMPLATES:
                if "{town2}" in template:
                    combos.append((template.format(typo=typo, town2=town2), intent))
                else:
                    combos.append((template.format(typo=typo), intent))
    rng.shuffle(combos)
    out: list[EvalPrompt] = []
    seen: set[str] = set()
    for prompt, intent in combos:
        if prompt in seen:
            continue
        seen.add(prompt)
        out.append(EvalPrompt("typo", intent, prompt))
        if len(out) >= count:
            break
    return out


def _expand_compare(count: int, rng: random.Random) -> list[EvalPrompt]:
    combos = [(t.format(a=a, b=b), a, b) for t in COMPARE_TEMPLATES for a, b in COMPARE_PAIRS]
    rng.shuffle(combos)
    out: list[EvalPrompt] = []
    seen: set[str] = set()
    for prompt, _, _ in combos:
        if prompt in seen:
            continue
        seen.add(prompt)
        out.append(EvalPrompt("compare", "compare_towns", prompt))
        if len(out) >= count:
            break
    return out


def _expand_budget(count: int, rng: random.Random) -> list[EvalPrompt]:
    budgets = [550, 600, 650, 700, 750, 800, 850, 900, 950]
    combos = [(t.format(budget=b), b) for t in BUDGET_TEMPLATES for b in budgets]
    rng.shuffle(combos)
    out: list[EvalPrompt] = []
    seen: set[str] = set()
    for prompt, _ in combos:
        if prompt in seen:
            continue
        seen.add(prompt)
        out.append(EvalPrompt("budget", "recommend_structured", prompt))
        if len(out) >= count:
            break
    return out


def _expand_commute(count: int, rng: random.Random) -> list[EvalPrompt]:
    windows = [(25, 35), (30, 45), (35, 50), (40, 55), (45, 60), (20, 30), (30, 40)]
    combos: list[str] = []
    for template in COMMUTE_TEMPLATES:
        if "{max}" in template or "{min}" in template:
            for mn, mx in windows:
                combos.append(
                    template.format(min=mn, max=mx)
                )
        else:
            combos.append(template)
    rng.shuffle(combos)
    out: list[EvalPrompt] = []
    seen: set[str] = set()
    for prompt in combos:
        if prompt in seen:
            continue
        seen.add(prompt)
        out.append(EvalPrompt("commute", "recommend_structured", prompt))
        if len(out) >= count:
            break
    return out


def _expand_coastal(count: int, rng: random.Random) -> list[EvalPrompt]:
    rng.shuffle(list(COASTAL_TEMPLATES))
    out: list[EvalPrompt] = []
    for prompt in COASTAL_TEMPLATES[:count]:
        out.append(EvalPrompt("coastal", "recommend_structured", prompt))
    return out


def _expand_semantic(towns: list[str], count: int, rng: random.Random) -> list[EvalPrompt]:
    vibe_towns = [t for t in towns if t in {
        "Lexington", "Newton", "Brookline", "Concord", "Wellesley", "Cambridge",
        "Hingham", "Marblehead", "Weston", "Needham", "Acton", "Arlington",
    }] or towns[:20]
    combos = [(t.format(town=town), town) for t in SEMANTIC_TEMPLATES for town in vibe_towns]
    rng.shuffle(combos)
    out: list[EvalPrompt] = []
    seen: set[str] = set()
    for prompt, _ in combos:
        if prompt in seen:
            continue
        seen.add(prompt)
        out.append(EvalPrompt("semantic", "recommend_semantic", prompt))
        if len(out) >= count:
            break
    return out


def _expand_inverted(count: int, rng: random.Random) -> list[EvalPrompt]:
    rng.shuffle(list(INVERTED_TEMPLATES))
    out: list[EvalPrompt] = []
    for prompt in INVERTED_TEMPLATES[:count]:
        out.append(EvalPrompt("inverted", "recommend_structured", prompt))
    return out


def generate_eval_pool(
    *,
    seed: int = 160,
    per_category: int = 60,
    min_total: int = 500,
) -> list[EvalPrompt]:
    """Generate at least ``min_total`` unique prompts across intent categories."""
    rng = random.Random(seed)
    towns = _town_pool(seed)

    sections = [
        _expand_lookup(towns, per_category, rng),
        _expand_membership(towns, per_category, rng),
        _expand_typo(per_category, rng),
        _expand_compare(per_category, rng),
        _expand_budget(per_category, rng),
        _expand_commute(per_category, rng),
        _expand_coastal(per_category, rng),
        _expand_semantic(towns, per_category, rng),
        _expand_inverted(per_category, rng),
    ]
    pool: list[EvalPrompt] = []
    seen: set[str] = set()
    for section in sections:
        for item in section:
            if item.prompt in seen:
                continue
            seen.add(item.prompt)
            pool.append(item)

    if len(pool) < min_total:
        boost = per_category + 10
        extra_sections = [
            _expand_lookup(towns, boost, random.Random(seed + 11)),
            _expand_budget(boost, random.Random(seed + 12)),
            _expand_commute(boost, random.Random(seed + 13)),
            _expand_semantic(towns, boost, random.Random(seed + 14)),
        ]
        for section in extra_sections:
            for item in section:
                if item.prompt in seen:
                    continue
                seen.add(item.prompt)
                pool.append(item)
                if len(pool) >= min_total:
                    break
            if len(pool) >= min_total:
                break
    return pool


def sample_prompts(
    pool: Iterable[EvalPrompt],
    *,
    n: int = 150,
    seed: int = 42,
) -> list[EvalPrompt]:
    items = list(pool)
    rng = random.Random(seed)
    if n >= len(items):
        return items
    return rng.sample(items, n)


def prompts_to_cases(prompts: Iterable[EvalPrompt]) -> list[dict[str, str]]:
    counters: dict[str, int] = {}
    cases: list[dict[str, str]] = []
    for item in prompts:
        counters[item.category] = counters.get(item.category, 0) + 1
        cases.append({
            "id": f"{item.category}_{counters[item.category]:03d}",
            "category": item.category,
            "category_label": CATEGORY_LABELS[item.category],
            "expected_intent": item.expected_intent,
            "prompt": item.prompt,
        })
    return cases
