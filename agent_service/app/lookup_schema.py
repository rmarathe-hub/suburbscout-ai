"""Supported vs unsupported town lookup attributes (Phase 1.6+)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.entity_extractor import ExtractedEntities, extract_entities

AVAILABLE_FIELDS_BLURB = (
    "home price, commute, safety, schools, coastal status, and data completeness"
)

# Town-level fields suburbs.json can answer (do not route these to unsupported_field).
_SUPPORTED_FIELD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:home price|housing price|median home|latest home price|stored home price)\b(?!\s+forecast\b)",
        re.I,
    ),
    re.compile(r"\b(?:how expensive|pricey|affordability score)\b", re.I),
    re.compile(
        r"\b(?:commute time|drive time|drive distance|how far|minutes to boston|distance to boston|commute to boston|commute from)\b",
        re.I,
    ),
    re.compile(r"\b(?:crime rate|safety score|crime score)\b(?!\s+still\b)", re.I),
    re.compile(r"\b(?:school score|school rating|school number|school data)\b", re.I),
    re.compile(
        r"\b(?:coastal|is_coastal|marked coastal|coast town|waterfront in (?:your )?data)\b(?!\s+flood)",
        re.I,
    ),
    re.compile(r"\b(?:partial[- ]data|full[- ]data|data quality|missing fields|complete data|data completeness)\b", re.I),
    re.compile(r"\b(?:county|region)\b", re.I),
    re.compile(r"\bis .+ safe\b(?!\s+(?:at night|to walk|neighborhood|block|street|mall|downtown))", re.I),
    re.compile(r"\b(?:risky|dangerous)\b(?!\s+(?:blocks?|neighborhoods?|at night|area|for storms))", re.I),
)


@dataclass(frozen=True)
class UnsupportedAttributeMatch:
    """Detected unsupported attribute request."""

    label: str
    category: str


# (regex, human label, category) — first match wins; put specific patterns first.
_UNSUPPORTED_PATTERNS: tuple[tuple[str, str, str], ...] = (
    # --- live market / current data (before generic price) ---
    (r"\b(?:homes? for sale|houses? for sale|listings?)\b.*\b(?:right now|now|today|currently)\b", "live home listings", "live_market"),
    (r"\b(?:right now|currently|today'?s market|live listings?)\b", "live market or listing data", "live_market"),
    (r"\b(?:zillow|redfin|realtor\.com|mls)\b", "live listing portal data", "live_market"),
    (r"\b(?:current rents?|rent listings?|available apartments?)\b", "current rental or apartment listings", "live_market"),
    (r"\b(?:updated prices?|live prices?|today'?s prices?)\b", "live or updated pricing", "live_market"),
    (r"\b(?:mortgage rates?|mortgage-adjusted)\b", "mortgage rate data", "live_market"),
    (r"\b(?:appreciation|appreciating|price forecast|future value|home value growth|investment potential|resale value)\b", "price forecasts or investment projections", "live_market"),
    (r"\b(?:good investment|a good investment)\b", "investment suitability or forecasts", "live_market"),
    (r"\b(?:market trend|days on market|inventory|bidding wars?)\b", "live market trend or inventory data", "live_market"),
    (r"\b(?:prices? (?:dropping|rising|falling|going up|going down))\b", "current price trend forecasts", "live_market"),
    (r"\b(?:will .+ home values? go up|go up in value)\b", "future home value forecasts", "live_market"),
    (r"\b(?:how many houses? are on the market)\b", "current market inventory", "live_market"),
    (r"\b(?:crime rate still current|recent crime|crime spikes?|current crime|latest crime)\b", "current or recent crime incident data", "live_market"),
    (r"\b(?:recent school|school ranking changes?|current school ranking)\b", "current school ranking changes", "live_market"),
    (r"\b(?:safer now than last year|safer than last year)\b", "current safety trend comparisons", "live_market"),
    # --- neighborhood / street-level ---
    (r"\b(?:best neighborhood|worst neighborhood|safest neighborhood|dangerous blocks?|unsafe neighborhoods?)\b", "neighborhood-level detail", "neighborhood"),
    (r"\b(?:best streets?|worst streets?)\b", "street-level detail", "neighborhood"),
    (r"\b(?:which part|which area|which side|north side|south side|east side|west side)\b", "neighborhood or area-level detail", "neighborhood"),
    (r"\b(?:schools different by neighborhood|different by neighborhood|by neighborhood)\b", "neighborhood-level school differences", "neighborhood"),
    (r"\b(?:street-level|block-level|zip[- ]code|specific streets?|specific subdivisions?)\b", "street- or block-level detail", "neighborhood"),
    (r"\b(?:downtown .+ safer than|outskirts|apartment complexes?)\b", "neighborhood-level comparison", "neighborhood"),
    (r"\b(?:safer than the outskirts|safer than outskirts)\b", "neighborhood-level comparison", "neighborhood"),
    (r"\b(?:which part of .+ should i avoid|areas? to avoid)\b", "neighborhood safety guidance", "neighborhood"),
    (r"\b(?:school zones?|catchments?|district boundaries)\b", "school zone or catchment boundaries", "neighborhood"),
    (r"\b(?:north .+ better than south|elementary school zone)\b", "neighborhood or school-zone detail", "neighborhood"),
    # --- granular safety ---
    (r"\b(?:safe at night|walk at night|mall area safe|downtown safe at night)\b", "time- or place-specific safety", "safety_granular"),
    (r"\b(?:car break-ins?|package theft|gang activity|drug activity|domestic crime)\b", "specific crime incident types", "safety_granular"),
    (r"\b(?:police response(?: time)?|violent crime details?|sex offender)\b", "granular crime or enforcement detail", "safety_granular"),
    (r"\b(?:crime by neighborhood|crime trend|recent incidents?)\b", "neighborhood crime trends or incidents", "safety_granular"),
    (r"\b(?:sketchy|shady|sketchiness)\b", "subjective street vibe", "lifestyle"),
    # --- school beyond score ---
    (r"\b(?:which elementary school|middle schools?|high school rankings? by name)\b", "individual school rankings", "school_detail"),
    (r"\b(?:ap classes?|special education|school sports?|college placement)\b", "detailed school program data", "school_detail"),
    (r"\b(?:school bullying|bullying in .+ schools?|bullying)\b", "granular school quality detail", "school_detail"),
    (r"\b(?:private schools?|daycare|preschools?)\b", "private school or childcare options", "school_detail"),
    (r"\b(?:school diversity|school zone in .+ is best)\b", "school-zone or school diversity detail", "school_detail"),
    # --- demographics / politics / culture ---
    (r"\b(?:teacher quality|class size|school buses?)\b", "granular school quality detail", "school_detail"),
    (r"\b(?:indian population|south asian population|asian population|black population|latino population|immigrant population)\b", "demographic composition", "demographics"),
    (r"\b(?:big .+ population|large .+ population)\b", "demographic composition", "demographics"),
    (r"\b(?:religious makeup|hindu temples?|mosques?|churches?|religiously diverse)\b", "religious composition or institutions", "demographics"),
    (r"\b(?:liberal|conservative|republican|democrat|progressive|politics)\b", "political composition", "demographics"),
    (r"\b(?:diverse|diversity|multicultural|demographic composition)\b", "demographic diversity", "demographics"),
    (r"\b(?:low-income|highly educated|college-educated|age demographics|young families|retirees|singles|students)\b", "demographic composition", "demographics"),
    (r"\b(?:mostly immigrant|wealthy people|poor people|class makeup|income groups)\b", "demographic or class composition", "demographics"),
    # --- transit ---
    (r"\b(?:public transit|mbta|subway|commuter rail|train station|bus service|transit access|transit score)\b", "public transit access", "transit"),
    (r"\b(?:bus access|good for bus)\b", "bus transit access", "transit"),
    (r"\b(?:car-dependent|good without a car|walk to train|t access)\b", "transit dependence or train access", "transit"),
    (r"\b(?:orange line|red line|green line|blue line|commuter rail zone)\b", "specific transit line access", "transit"),
    (r"\b(?:take the train from|subway access|bad for transit|good for transit)\b", "transit accessibility", "transit"),
    (r"\b(?:parking in|how is parking|rush hour|traffic)\b", "parking or traffic conditions", "transit"),
    (r"\b(?:airport access)\b", "airport access detail", "transit"),
    # --- risk / environment ---
    (r"\b(?:flood risk|coastal flooding|fema flood|wildfire risk|climate risk|sea-level rise|sea level rise)\b", "flood or climate risk", "risk_environment"),
    (r"\b(?:heat risk|pollution|polluted|air quality|water quality|noise pollution|highway noise|airport noise)\b", "environmental quality", "risk_environment"),
    (r"\b(?:industrial pollution|environmental risk|natural disasters?|storm risk)\b", "environmental or disaster risk", "risk_environment"),
    (r"\b(?:mountainous|mountainousness|mountains?|hilly|hilliness|terrain|elevations?|forested|wetlands?|conservation land)\b", "terrain or environmental landscape", "risk_environment"),
    (r"\b(?:flat|noisy because of highways|basement flooding|drainage)\b", "terrain or local environmental conditions", "risk_environment"),
    (r"\b(?:vulnerable to sea-level|bad air quality|risky for storms)\b", "environmental or storm risk", "risk_environment"),
    # --- utilities / infrastructure ---
    (r"\b(?:fiber internet|internet speed|cell service)\b", "internet or cell service", "utilities"),
    (r"\b(?:water/sewer|septic|sewer problems?|sewer issues?|power outages?|snow plowing|trash pickup)\b", "utility or municipal service reliability", "utilities"),
    (r"\b(?:road quality|potholes|bad roads?|roads bad|are roads|public works|property maintenance|town services?)\b", "road or municipal maintenance", "utilities"),
    (r"\b(?:building permits?)\b", "building permit process", "utilities"),
    # --- taxes / municipal ---
    (r"\b(?:property tax(?:es)?|tax rate|tax bills?|assessments?|overrides?)\b", "property tax or assessment detail", "taxes"),
    (r"\b(?:town budget|municipal debt|school budget|trash fees?|water bills?|hoa fees?|town fees?)\b", "municipal fee or budget detail", "taxes"),
    (r"\b(?:hoa-heavy|hoa heavy)\b", "HOA prevalence detail", "taxes"),
    (r"\b(?:expensive for taxes|cheap after taxes)\b", "tax burden detail", "taxes"),
    # --- healthcare ---
    (r"\b(?:hospitals?|urgent care|doctors?|dentists?|pediatricians?|senior services?)\b", "healthcare facility access", "healthcare"),
    (r"\b(?:mental health services?|pharmacies?|emergency response|ambulance access|healthcare)\b", "healthcare or emergency services", "healthcare"),
    # --- jobs / economy ---
    (r"\b(?:tech jobs?|office jobs?|local jobs?|office parks?|biotech|major employers?)\b", "local employment or industry detail", "jobs"),
    (r"\b(?:unemployment|job growth|remote[- ]worker|remote workers?)\b", "employment trend or remote-work suitability", "jobs"),
    (r"\b(?:commute to (?:cambridge|job centers?)|commuting to (?:cambridge|job centers?)|local employment|local work|good for local work)\b", "non-Boston commute or local jobs detail", "jobs"),
    # --- recreation ---
    (r"\b(?:parks?|trails?|lakes?|beaches?|sports fields?|gyms?|golf courses?)\b", "recreation amenities", "recreation"),
    (r"\b(?:hiking|boating|playgrounds?|dog parks?|conservation areas?|outdoor recreation)\b", "outdoor recreation amenities", "recreation"),
    # --- food / culture ---
    (r"\b(?:indian grocery|asian markets?|halal|vegetarian restaurants?|vegetarian food|indian food|temples?)\b", "cultural food or community institutions", "food_culture"),
    (r"\b(?:good library|a good library)\b", "library amenities", "food_culture"),
    (r"\b(?:good restaurants?|nightlife|bars?|clubs?|coffee shops?|cafes?|cafés?)\b", "restaurant or nightlife amenities", "food_culture"),
    (r"\b(?:community centers?|libraries?|festivals?|farmers markets?|cultural events?)\b", "community or cultural amenities", "food_culture"),
    (r"\b(?:shopping|malls?|grocery stores?|entertainment|social scene)\b", "retail or entertainment amenities", "food_culture"),
    # --- legal / zoning ---
    (r"\b(?:adus?|accessory (?:dwelling|apartment|apartments|units?))\b", "ADU or accessory housing rules", "legal_zoning"),
    (r"\b(?:short-term rentals?|rental rules?|rental restrictions?|landlord rules?|tenant protections?)\b", "rental regulation detail", "legal_zoning"),
    (r"\b(?:zoning restrictions?|strict zoning|multifamily housing|building codes?)\b", "zoning or building regulation", "legal_zoning"),
    (r"\b(?:school enrollment rules?|residency rules?|rent out a basement|build an addition)\b", "housing or enrollment regulation", "legal_zoning"),
    (r"\b(?:good for bike commute|bike commute)\b", "bike commute transit suitability", "transit"),
    # --- lifestyle / town feel (broader, after specific amenity patterns) ---
    (r"\b(?:walkable|walkability|pedestrian-friendly|sidewalks?|bikeable|bike lanes?)\b", "walkability or bikeability", "lifestyle"),
    (r"\b(?:real downtown|town center|village center|downtown feel)\b", "downtown or town-center character", "lifestyle"),
    (r"\b(?:snobby|snobbish|pretentious|elitist|prestigious|old-money feel)\b", "social prestige or vibe", "lifestyle"),
    (r"\b(?:touristy|tourist[- ]heavy|tourist[- ]oriented)\b", "touristiness", "lifestyle"),
    (r"\b(?:urban|suburban|rural|exurban|dense|spacious)\b", "urban/suburban/rural character", "lifestyle"),
    (r"\b(?:boring|dull|lifeless|sleepy|lively|fun|active)\b", "town liveliness or vibe", "lifestyle"),
    (r"\b(?:blue-collar|working-class|family vibe|young-professional|young professionals?|good for young professionals?|college-town feel)\b", "community character", "lifestyle"),
    (r"\b(?:retirement-friendly|kid-friendly|dog-friendly|neighborly|isolated|connected)\b", "community suitability vibe", "lifestyle"),
    (r"\b(?:artsy|historic charm|community feel|amenities)\b", "community character or amenities vibe", "lifestyle"),
    (r"\b(?:good for nightlife)\b", "nightlife suitability", "lifestyle"),
    (r"\b(?:rural or suburban)\b", "urban/suburban/rural character", "lifestyle"),
)

_COMPILED_UNSUPPORTED: tuple[tuple[re.Pattern[str], str, str], ...] = tuple(
    (re.compile(pat, re.I), label, category) for pat, label, category in _UNSUPPORTED_PATTERNS
)

_INTRA_TOWN_AREA_RE = re.compile(
    r"\b(?:outskirts|the outskirts|downtown|north side|south side|east side|west side|"
    r"city center|town center|village center)\b",
    re.I,
)

_SINGLE_TOWN_QUESTION_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?:is|are|does|do|was|were|can|could|would|will|should|has|have)\s+", re.I),
    re.compile(r"^(?:how is|how are|how's|what is|what are|what's|how are)\s+", re.I),
    re.compile(r"^are there\s+", re.I),
    re.compile(r"^which (?:part|area|neighborhood|side|street|school|elementary)\s+", re.I),
    re.compile(r"^where (?:is|are|can)\s+", re.I),
    re.compile(r"^what (?:elementary|middle|high|school|part|area|neighborhood)\s+", re.I),
    re.compile(r"^what .+\s+(?:is|are)\s+best\b", re.I),
    re.compile(r"^are .+\s+(?:high|included)\b", re.I),
    re.compile(r"^can i\s+", re.I),
    re.compile(r"^is .+\s+good for\b", re.I),
    re.compile(r"^how (?:is|are|fast|many|good)\s+", re.I),
)


def _explicit_supported_schema_question(lower: str) -> bool:
    """True when the query primarily asks about a stored schema field."""
    if re.search(
        r"\b(?:sketchy|shady|diverse|liberal|walkable|mountainous|restaurants?|mbta|"
        r"flood risk|forecast|still current|bike commute|commuter rail|transit|"
        r"indian food|vegetarian|town fees|local work|healthcare|build an addition|"
        r"commuting to cambridge|rental restrictions|accessory apartments)\b",
        lower,
    ):
        return False
    for pattern in _SUPPORTED_FIELD_PATTERNS:
        if pattern.search(lower):
            return True
    return False


def _is_single_town_attribute_question(text: str) -> bool:
    stripped = text.strip()
    return any(p.search(stripped) for p in _SINGLE_TOWN_QUESTION_RES)


def _is_intra_town_area_compare(text: str, entities: ExtractedEntities) -> bool:
    """True when a pseudo-compare is really a within-town neighborhood question."""
    if len(entities.valid_towns) != 1 or not entities.compare_pair:
        return False
    lower = text.lower()
    if re.search(r"\b(?:downtown .+ safer than|safer than the outskirts|safer than outskirts)\b", lower):
        return True
    _a, b = entities.compare_pair
    return bool(_INTRA_TOWN_AREA_RE.search(b) or _INTRA_TOWN_AREA_RE.search(_a))


def extract_unsupported_attribute(text: str) -> UnsupportedAttributeMatch | None:
    """Return attribute label + category if query asks about an unsupported field."""
    lower = text.lower()
    for pattern, label, category in _COMPILED_UNSUPPORTED:
        if pattern.search(lower):
            return UnsupportedAttributeMatch(label=label, category=category)
    return None


def _primary_town_for_attribute_question(text: str, entities: ExtractedEntities) -> str | None:
    """Resolve the subject town when a destination town appears in the same question."""
    if len(entities.valid_towns) == 1:
        return entities.valid_towns[0]
    if len(entities.valid_towns) == 2 and re.search(
        r"\b(?:commuting to|commute to|close to|near|jobs in|work in|good for commuting to)\b",
        text,
        re.I,
    ):
        match = re.search(
            r"\b(?:is|does|are|can)\s+([A-Za-z][\w\s\-']+?)\s+(?:good for|close to|near)\b",
            text,
            re.I,
        )
        if match:
            span = match.group(1).strip().lower()
            for town in entities.valid_towns:
                if town.lower() == span:
                    return town
        return entities.valid_towns[0]
    return None


def detect_unknown_field_lookup(
    query: str,
    entities: ExtractedEntities | None = None,
) -> tuple[str, UnsupportedAttributeMatch] | None:
    """
    If query is a single known-town question about an unsupported attribute,
    return (town_name, UnsupportedAttributeMatch).
    """
    text = query.strip()
    if not text:
        return None
    lower = text.lower()
    if re.search(
        r"\b(?:towns|suburbs|places|recommend|show me towns|find towns|give me towns|rank towns)\b",
        lower,
    ):
        return None
    if re.search(r"\b(?:under|below)\s+\$?\d", lower):
        return None

    entities = entities or extract_entities(text)
    if entities.compare_pair and not _is_intra_town_area_compare(text, entities):
        return None
    town = _primary_town_for_attribute_question(text, entities)
    if not town:
        return None

    requested = extract_unsupported_attribute(text)
    if not requested:
        return None
    if _explicit_supported_schema_question(lower):
        return None
    if not _is_single_town_attribute_question(text):
        return None

    return town, requested


def build_unsupported_field_message(
    town_name: str,
    requested_field: str,
    *,
    in_dataset: bool,
    category: str = "lifestyle",
    query: str = "",
) -> str:
    """Deterministic response for unknown-attribute single-town lookups."""
    lower = query.lower()
    opener = (
        f"{town_name} is in the dataset, but "
        if in_dataset
        else f"{town_name} is not in the curated dataset; "
    )

    if category == "demographics":
        core = (
            "this dataset does not include demographic, religious, or political composition fields. "
            "I should not guess demographic details from the available data. "
            f"I can answer about {AVAILABLE_FIELDS_BLURB}."
        )
    elif category == "live_market":
        core = (
            "this dataset does not include live listings, current market conditions, or forecasts. "
            "The dataset is static and may not reflect current conditions. "
            f"I can answer about stored {AVAILABLE_FIELDS_BLURB}."
        )
    elif category == "neighborhood":
        core = (
            "this dataset does not include neighborhood-level or street-level detail. "
            f"I can answer using stored town-level fields: {AVAILABLE_FIELDS_BLURB}."
        )
    elif category == "safety_granular":
        core = (
            "this dataset does not include street-level, time-specific, or current incident-level safety data. "
            f"I can answer using the stored town-level safety/crime score plus {AVAILABLE_FIELDS_BLURB}."
        )
    elif category == "school_detail":
        core = (
            "this dataset does not include school-by-school or program-level school detail. "
            f"I can answer using the stored town-level school score plus {AVAILABLE_FIELDS_BLURB}."
        )
    elif category == "transit":
        core = (
            f"this dataset does not include a {requested_field} field. "
            "Commute data is limited to drive time/distance to Boston. "
            f"I can also answer about {AVAILABLE_FIELDS_BLURB}."
        )
    else:
        core = (
            f"this dataset does not include a {requested_field} field. "
            f"Based on the available fields, I can answer about {AVAILABLE_FIELDS_BLURB}."
        )

    msg = opener + core
    if "in your data" in lower or "in the dataset" in lower:
        msg += " I only answer using stored suburbs.json fields, not live external sources."
    return msg
