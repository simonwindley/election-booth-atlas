"""Canonical party codes shared across VEC and AEC sources.

Everything maps to a small set of codes so state and federal results can be
compared party-by-party. Anything unknown falls through to 'OTH' (or 'IND'
when the source has no party at all).
"""
import re

CANON = {
    # code: display name
    'ALP': 'Labor',
    'LIB': 'Liberal',
    'NAT': 'National',
    'GRN': 'Greens',
    'IND': 'Independent',
    'ONP': 'One Nation',
    'UAP': 'United Australia',
    'AJP': 'Animal Justice',
    'LDP': 'Liberal Democrats',
    'FFP': 'Family First',
    'SFF': 'Shooters, Fishers & Farmers',
    'DLP': 'DLP',
    'FRP': 'Freedom Party',
    'KAP': "Katter's Australian",
    'RUA': 'Rise Up Australia',
    'DEM': 'Australian Democrats',
    'CDP': 'Christian Democrats',
    'ONP_SPLIT': "Fraser Anning's Conservative National",
    'VSP': 'Victorian Socialists',
    'RUA': 'Reason',
    'SAP': 'Sustainable Australia',
    'LCP': 'Legalise Cannabis',
    'DHJ': 'Derryn Hinch Justice',
    'TMP': 'Transport Matters',
    'NDP': 'New Democrats',
    'HAP': 'Health Australia',
    'AVP': 'Angry Victorians',
    'SDA': 'Sack Dan Andrews',
    'CPP': 'Companions and Pets',
    'AUC': 'Australian Christians',
    'FUS': 'Fusion',
    'ACP': 'Citizens Party',
    'CYA': 'Country Alliance',
    'AIP': 'Indigenous-Aboriginal',
    'TNL': 'TNL',
    'OTH': 'Other',
}

# Regex (case-insensitive) on the source party name -> canonical code. Order matters.
_NAME_RULES = [
    (r'labor', 'ALP'),
    (r'liberal democrat|libertarian', 'LDP'),
    (r'^liberal|liberal party', 'LIB'),
    (r'^the nationals|^national party|^nationals', 'NAT'),
    (r'green', 'GRN'),
    (r'one nation', 'ONP'),
    (r'united australia|trumpet of patriots', 'UAP'),
    (r'animal justice', 'AJP'),
    (r'family first', 'FFP'),
    (r'shooters', 'SFF'),
    (r'labour dlp|democratic labour|\bdlp\b', 'DLP'),
    (r'freedom party', 'FRP'),
    (r'^alp$|labor', 'ALP'),
    (r'sex party|reason', 'FRP'),
    (r'country alliance', 'CYA'),
    (r'australian democrats|^democrats$', 'DEM'),
    (r'christian democratic|^cdp$', 'CDP'),
    (r'victorian socialist', 'VSP'),
    (r'reason', 'RUA'),
    (r'sustainable australia', 'SAP'),
    (r'legalise cannabis', 'LCP'),
    (r'hinch', 'DHJ'),
    (r'transport matters', 'TMP'),
    (r'new democrats', 'NDP'),
    (r'health australia', 'HAP'),
    (r'angry victorians', 'AVP'),
    (r'sack dan andrews', 'SDA'),
    (r'companions and pets', 'CPP'),
    (r'australian christians', 'AUC'),
    (r'fusion', 'FUS'),
    (r'citizens party|citizens electoral|^cec$', 'ACP'),
    (r'^ca$', 'CYA'),   # the VEC's 2010 abbreviation for Country Alliance
    (r'indigenous', 'AIP'),
    (r'^tnl', 'TNL'),
    (r'independent', 'IND'),
]

# AEC party abbreviations -> canonical
_AEC_AB = {
    'ALP': 'ALP', 'LP': 'LIB', 'LNP': 'LIB', 'NP': 'NAT', 'GRN': 'GRN', 'GVIC': 'GRN',
    'IND': 'IND', 'ON': 'ONP', 'HAN': 'ONP', 'UAPP': 'UAP', 'UAP': 'UAP', 'TOP': 'UAP', 'PUP': 'UAP',   # Palmer United -> United Australia lineage
    'ASXP': 'FRP', 'CEC': 'ACP', 'KAP': 'KAP', 'RUA': 'RUA', 'DEM': 'DEM', 'FACN': 'ONP_SPLIT',
    'AJP': 'AJP', 'FFP': 'FFP', 'LDP': 'LDP', 'SFF': 'SFF', 'DLP': 'DLP', 'VNS': 'VSP',
    'REAS': 'RUA', 'SAL': 'SAP', 'LC': 'LCP', 'DHJP': 'DHJ', 'AUC': 'AUC', 'FUSN': 'FUS',
    'CYA': 'CYA', 'AIP': 'AIP', 'TNL': 'TNL', 'XXX': 'IND', 'NAFD': 'IND', 'LTP': 'LDP',
}


def canon_from_name(name: str) -> str:
    if not name or not str(name).strip():
        return 'IND'
    n = str(name).strip().lower()
    for pat, code in _NAME_RULES:
        if re.search(pat, n):
            return code
    return 'OTH'


def canon_from_aec(ab: str, name: str) -> str:
    if ab and str(ab).strip() in _AEC_AB:
        return _AEC_AB[str(ab).strip()]
    return canon_from_name(name)
